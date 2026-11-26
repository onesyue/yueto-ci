"""Commit trees from local git objects or the GitHub git-trees API."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .constants import SHA40, Unknown

class LocalGit:
    """Read a commit's tree and blobs straight from git objects.

    Never reads the working tree: untracked or modified files are not what
    the central builder sees (it checks out the exact commit).
    """

    def __init__(self, repo: str | os.PathLike):
        self.repo = str(repo)

    def _git(self, *args: str) -> bytes:
        proc = subprocess.run(
            ["git", "-C", self.repo, *args], capture_output=True, check=False
        )
        if proc.returncode != 0:
            raise Unknown(f"git {' '.join(args[:2])} failed: {proc.stderr.decode(errors='replace').strip()[:200]}")
        return proc.stdout

    def resolve(self, rev: str) -> str:
        sha = self._git("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
        if not SHA40.match(sha):
            raise Unknown(f"cannot resolve {rev}")
        return sha

    def entries(self, rev: str) -> dict[str, tuple[str, str, str]]:
        out = self._git("ls-tree", "-r", "-z", "--full-tree", rev)
        result: dict[str, tuple[str, str, str]] = {}
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            mode, kind, oid = meta.decode().split(" ")
            result[path.decode("utf-8", "surrogateescape")] = (mode, kind, oid)
        return result

    def blob(self, oid: str) -> bytes:
        return self._git("cat-file", "blob", oid)


class GitHubTree:
    """The same data through the GitHub REST API (CI planning job)."""

    def __init__(self, repo: str, token: str, api: str = "https://api.github.com"):
        if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
            raise Unknown(f"invalid repository name {repo!r}")
        self.repo, self.token, self.api = repo, token, api.rstrip("/")

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.api}/repos/{self.repo}/{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise Unknown(f"GitHub API {path.split('?')[0]} unavailable: {exc}") from exc

    def resolve(self, rev: str) -> str:
        sha = self._get(f"commits/{urllib.parse.quote(rev, safe='')}").get("sha", "")
        if not SHA40.match(sha):
            raise Unknown(f"cannot resolve {rev}")
        return sha

    def entries(self, rev: str, *, strict: bool = False) -> dict[str, tuple[str, str, str]]:
        tree = self._get(f"git/trees/{urllib.parse.quote(rev, safe='')}?recursive=1")
        if tree.get("truncated") is not False:
            # The recursive endpoint silently drops entries past its limit.
            raise Unknown("GitHub tree listing truncated or malformed")
        if strict and not isinstance(tree.get("tree"), list):
            raise Unknown("malformed complete tree")
        result, seen = {}, set()
        for item in tree.get("tree", []):
            if strict:
                if (not isinstance(item, dict) or not isinstance(item.get("path"), str) or
                        item["path"] in seen or item.get("type") not in ("blob", "commit", "tree")):
                    raise Unknown("malformed or duplicate tree object")
                seen.add(item["path"])
                if item["type"] == "tree" and (item.get("mode") != "040000" or
                        not isinstance(item.get("sha"), str) or not SHA40.fullmatch(item["sha"])):
                    raise Unknown("malformed directory object")
            if item.get("type") in ("blob", "commit"):
                result[item["path"]] = (item["mode"], item["type"], item["sha"])
        return result

    def blob(self, oid: str) -> bytes:
        body = self._get(f"git/blobs/{oid}")
        if body.get("encoding") != "base64":
            raise Unknown(f"blob {oid} has unexpected encoding")
        return base64.b64decode(body.get("content", ""))
