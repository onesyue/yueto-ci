"""Read owner-authorized evidence from an exact Git object, without executing it.

This is an authenticity/input binding primitive, NOT test admission. Callers must
still verify complete role receipts, outcomes and immutable native obligations.
The trust anchor belongs to the public validator, never the candidate checkout.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "ci/evidence/pytest-skip-baseline.json"
INPUTS = "ci/evidence/shared-inputs.json"
EVIDENCE_PATHS = frozenset((BASELINE, INPUTS))
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class Rejected(ValueError):
    """Missing, unauthenticated or mismatched candidate evidence."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise Rejected("invalid evidence JSON") from exc


def _environment(home):
    # Do not inherit GIT_CONFIG, replace objects, GPG, loader or shell hooks.
    return {"PATH": os.defpath, "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"}


def _git(repo, *args):
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise Rejected("git unavailable")
    with tempfile.TemporaryDirectory(prefix="source-git-") as home:
        result = subprocess.run([executable, "--no-replace-objects", "-C", str(repo),
                                 *args], env=_environment(home), capture_output=True,
                                timeout=60, check=False)
    require(result.returncode == 0, "Git object unavailable")
    return result.stdout


def _signature(commit):
    header, separator, body = commit.partition(b"\n\n")
    require(bool(separator), "invalid commit")
    unsigned, signature = [], []
    active = False
    count = 0
    for line in header.split(b"\n"):
        if line.startswith(b"gpgsig "):
            count += 1
            active = True
            signature.append(line[len(b"gpgsig "):])
        elif active and line.startswith(b" "):
            signature.append(line[1:])
        else:
            active = False
            unsigned.append(line)
    require(count == 1 and signature and signature[0] == b"-----BEGIN PGP SIGNATURE-----",
            "exactly one OpenPGP signature required")
    return b"\n".join(signature) + b"\n", b"\n".join(unsigned) + b"\n\n" + body


def _verify(commit, policy_dir):
    policy = _json((policy_dir / "yueops-owner-signers.json").read_bytes())
    keyring = (policy_dir / "yueops-owner.gpg").read_bytes()
    require(policy.get("schema") == 1 and digest(keyring) == policy.get("keyring_sha256"),
            "invalid trusted keyring")
    signature, payload = _signature(commit)
    # Resolve from the validator's environment, not candidate configuration.
    executable = shutil.which("gpgv")
    if executable is None:
        raise Rejected("gpgv unavailable")
    with tempfile.TemporaryDirectory(prefix="source-signature-") as temporary:
        home = Path(temporary)
        (home / "keyring.gpg").write_bytes(keyring)
        (home / "signature.asc").write_bytes(signature)
        (home / "commit").write_bytes(payload)
        result = subprocess.run([executable, "--homedir", str(home), "--keyring",
                                 str(home / "keyring.gpg"), "--status-fd", "1",
                                 str(home / "signature.asc"), str(home / "commit")],
                                env=_environment(home), capture_output=True,
                                timeout=30, check=False)
    valid = [line.split() for line in result.stdout.decode("utf-8", "replace").splitlines()
             if line.startswith("[GNUPG:] VALIDSIG ")]
    require(result.returncode == 0 and len(valid) == 1 and len(valid[0]) == 12
            and valid[0][2] == policy.get("signer")
            and valid[0][-1] == policy.get("primary"), "unauthorized source signature")


def tree_inputs(repo, revision):
    require(isinstance(revision, str) and HEX40.fullmatch(revision), "exact source SHA required")
    result = {}
    for item in _git(repo, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        name = path.decode("utf-8")
        # Bind submodules and symlinks too; evidence itself must be a regular blob.
        result[name] = {"mode": mode, "kind": kind, "git_blob": blob}
    require(bool(result), "empty source tree")
    return result


def load(repo, revision):
    """Return bound records; never read policy or evidence from the worktree."""
    return _load(repo, revision, ROOT / "policy")


def _load(repo, revision, policy_dir):
    # Explicit private injection exists only for isolated signing-fixture tests.
    require(isinstance(revision, str) and HEX40.fullmatch(revision), "exact source SHA required")
    commit = _git(repo, "cat-file", "commit", revision)
    require(hashlib.sha1(b"commit " + str(len(commit)).encode() + b"\0" + commit).hexdigest()
            == revision, "commit identity mismatch")
    _verify(commit, policy_dir)
    tree = tree_inputs(repo, revision)
    records, bindings = {}, {}
    for path in sorted(EVIDENCE_PATHS):
        entry = tree.get(path, {})
        require(entry.get("kind") == "blob" and entry.get("mode") == "100644",
                "missing or nonregular evidence: " + path)
        data = _git(repo, "cat-file", "blob", entry["git_blob"])
        records[path] = _json(data)
        bindings[path] = entry | {"sha256": digest(data)}
    actual = {path: entry for path, entry in tree.items() if path not in EVIDENCE_PATHS}
    manifest = records[INPUTS]
    require(isinstance(manifest, dict) and set(manifest) == {"schema", "inputs", "inputs_sha256"}
            and manifest["schema"] == 1 and manifest["inputs"] == actual
            and manifest["inputs_sha256"] == digest(canonical(actual)),
            "source input manifest mismatch")
    baseline = records[BASELINE]
    require(isinstance(baseline, dict) and baseline.get("schema") == 1
            and baseline.get("inputs_sha256") == manifest["inputs_sha256"]
            and baseline.get("status") == "HISTORICAL_SKIPS_NOT_PASSES"
            and isinstance(baseline.get("cases"), dict)
            and isinstance(baseline.get("collection_skips"), dict), "invalid source skip baseline")
    return {"schema": 1, "status": "BOUND_SOURCE_EVIDENCE", "source_revision": revision,
            "inputs_sha256": manifest["inputs_sha256"], "evidence": bindings,
            "baseline": baseline, "admission": False}
