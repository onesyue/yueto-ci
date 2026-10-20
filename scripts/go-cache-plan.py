#!/usr/bin/env python3
"""Plan optional Go caches; no cache observation authorizes skipping a gate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess


POLICY = Path(__file__).resolve().parents[1]
GO_FIELDS = (
    "GOVERSION GOOS GOARCH GOHOSTOS GOHOSTARCH GOAMD64 GOARM64 GOEXPERIMENT "
    "CGO_ENABLED CC CXX CGO_CFLAGS CGO_CPPFLAGS CGO_CXXFLAGS CGO_LDFLAGS "
    "GOFLAGS GOTOOLCHAIN GOMODCACHE GOCACHE"
).split()


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=20).strip()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def plan() -> dict[str, str]:
    disabled = {"enabled": "false"}
    if (
        os.environ.get("GITHUB_REPOSITORY") != "onesyue/yueto-ci"
        or os.environ.get("GITHUB_REF") != "refs/heads/master"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("CACHE_RUNNER") != "ubuntu-24.04"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        return disabled
    kind = os.environ.get("VALIDATION_KIND")
    profile = os.environ.get("NODE_PROFILE", "")
    if kind not in ("yueboard", "yue-node") or (
        (kind == "yueboard" and profile) or (kind == "yue-node" and profile not in ("hy2", "vless"))
    ):
        return disabled
    repo = f"onesyue/{kind}"
    if os.environ.get("SOURCE_REPOSITORY") != repo:
        return disabled
    remote = command("git", "remote", "get-url", "origin").removesuffix(".git")
    if remote != f"https://github.com/{repo}":
        return disabled
    source = command("git", "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        return disabled
    # Checkout fetches all heads. Missing ancestry fails cold, never fetches or
    # admits arbitrary branch code as a writer of the shared trusted cache.
    command("git", "merge-base", "--is-ancestor", source, "refs/remotes/origin/master")
    command("git", "diff-index", "--quiet", "HEAD", "--")
    runner = {key: os.environ.get(key, "") for key in ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion")}
    if any(not value for value in runner.values()):
        return disabled
    go = json.loads(command("go", "env", "-json", *GO_FIELDS))
    module_path = go.pop("GOMODCACHE")
    compiler_path = go.pop("GOCACHE")
    if any(not Path(path).is_absolute() or "\n" in path or "\r" in path for path in (module_path, compiler_path)):
        return disabled
    compiler = command(*shlex.split(go["CC"]), "--version")
    dependencies = {
        path: command("git", "show", f"HEAD:{path}") for path in ("go.mod", "go.sum")
    }
    if kind == "yue-node":
        dependencies["vendor/modules.txt"] = command("git", "show", "HEAD:vendor/modules.txt")
    workload = digest({
        "workflow": (POLICY / ".github/workflows/build.yml").read_text(),
        "planner": Path(__file__).read_text(),
        "profile": profile,
    })
    compatible = digest({
        "repo": repo, "runner": runner, "go": go, "cc": compiler,
        "dependencies": dependencies, "workload": workload,
    })
    prefix = f"yue-go-build-v1-{kind}-{profile or 'backend'}-{compatible}-"
    return {
        "enabled": "true",
        "module_path": module_path,
        "module_key": "yue-go-mod-v1-" + digest({
            "repo": repo, "runner": runner, "go": go,
            "dependencies": dependencies, "workload": workload,
        }),
        "compiler_path": compiler_path,
        "compiler_key": prefix + source,
        # One compatible prefix only: never fall back across trust, toolchain,
        # dependency, workload or runner-image boundaries.
        "compiler_restore": prefix,
    }


def main() -> None:
    try:
        outputs = plan()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        # Cache metadata is optional. The ordinary validation steps still
        # diagnose unavailable tools/source inputs and remain authoritative.
        outputs = {"enabled": "false"}
        print("::notice::Go cache metadata unavailable; validation will run without remote cache")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        for key, value in outputs.items():
            stream.write(f"{key}={value}\n")
    print(f"Go remote cache enabled={outputs['enabled']}; validation gates are unchanged")


if __name__ == "__main__":
    main()
