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


def _git(repo, *args, input_data=None):
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise Rejected("git unavailable")
    with tempfile.TemporaryDirectory(prefix="source-git-") as home:
        result = subprocess.run([executable, "--no-replace-objects", "-C", str(repo),
                                 *args], env=_environment(home), input=input_data, capture_output=True,
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
    commit = _object(repo, "commit", revision)
    tree_lines = [line for line in commit.split(b"\n\n", 1)[0].splitlines()
                  if line.startswith(b"tree ")]
    require(len(tree_lines) == 1, "invalid commit tree")
    root_tree = tree_lines[0][5:].decode("ascii")
    # ls-tree supplies batching hints only. Every returned raw tree is hashed,
    # and traversal below follows only links from the authenticated root tree.
    tree_ids = {root_tree}
    for row in _git(repo, "ls-tree", "-rzt", "--full-tree", revision).split(b"\0"):
        if row:
            metadata = row.split(b"\t", 1)[0].split()
            if len(metadata) == 3 and metadata[1] == b"tree":
                tree_ids.add(metadata[2].decode("ascii"))
    trees = _objects(repo, "tree", sorted(tree_ids))
    result = {}

    def visit(oid, prefix, depth):
        require(depth < 100, "source tree nesting limit")
        require(oid in trees, "missing linked tree object")
        raw = trees[oid]
        offset = 0
        names = set()
        while offset < len(raw):
            end = raw.find(b"\0", offset)
            require(end >= offset and len(raw) >= end + 21, "invalid tree entry")
            metadata = raw[offset:end]
            mode, separator, name_bytes = metadata.partition(b" ")
            name = name_bytes.decode("utf-8")
            require(separator and name and name not in (".", "..") and "/" not in name
                    and name not in names, "invalid tree path")
            names.add(name)
            child = raw[end + 1:end + 21].hex()
            offset = end + 21
            path = prefix + name
            if mode == b"40000":
                visit(child, path + "/", depth + 1)
            else:
                require(mode in (b"100644", b"100755", b"120000", b"160000"),
                        "invalid tree mode")
                result[path] = {"mode": mode.decode(),
                                "kind": "commit" if mode == b"160000" else "blob",
                                "git_blob": child}

    visit(root_tree, "", 0)
    return result


def _object(repo, kind, oid):
    require(HEX40.fullmatch(oid), "invalid object identity")
    raw = _git(repo, "cat-file", kind, oid)
    header = kind.encode() + b" " + str(len(raw)).encode() + b"\0"
    require(hashlib.sha1(header + raw).hexdigest() == oid, "Git object identity mismatch")
    return raw


def _objects(repo, kind, ids):
    require(all(HEX40.fullmatch(oid) for oid in ids), "invalid batch object identity")
    stream = _git(repo, "cat-file", "--batch", input_data=("\n".join(ids) + "\n").encode())
    offset, result = 0, {}
    for expected in ids:
        end = stream.find(b"\n", offset)
        require(end >= offset, "missing batch object")
        header = stream[offset:end].split()
        require(len(header) == 3 and header[0].decode() == expected
                and header[1].decode() == kind and header[2].isdigit(), "wrong batch object")
        size = int(header[2])
        raw = stream[end + 1:end + 1 + size]
        offset = end + 2 + size
        require(len(raw) == size and stream[offset - 1:offset] == b"\n", "truncated batch object")
        identity = hashlib.sha1(kind.encode() + b" " + str(size).encode() + b"\0" + raw).hexdigest()
        require(identity == expected, "Git object identity mismatch")
        result[expected] = raw
    require(offset == len(stream), "unexpected batch objects")
    return result


def load(repo, revision):
    """Return bound records; never read policy or evidence from the worktree."""
    return _load(repo, revision, ROOT / "policy")


def verify_commit(commit, policy_dir=None):
    """Require one OpenPGP signature by policy/yueops-owner-signers.json.

    ``commit`` is the raw commit object. The keyring is the validator's,
    never a file from the candidate tree.
    """
    _verify(commit, Path(policy_dir) if policy_dir is not None else ROOT / "policy")

def optional(repo, revision):
    """Legacy trees remain on historical policy; partial enrollment is an error."""
    tree = tree_inputs(repo, revision)
    if not EVIDENCE_PATHS.intersection(tree):
        return None
    return load(repo, revision)


def verify_signed_commit(repo, revision):
    """Require one owner signature. Branch membership is not an input."""
    require(isinstance(revision, str) and HEX40.fullmatch(revision), "exact source SHA required")
    _verify(_object(repo, "commit", revision), ROOT / "policy")


def validate_baseline(bound, module_blobs):
    baseline = bound["baseline"]
    require(set(baseline) == {"schema", "status", "inputs_sha256", "context", "cases",
                              "collection_skips"}, "unexpected source baseline fields")
    context = baseline["context"]
    require(isinstance(context, dict) and set(context) == {"platform", "uid"}
            and context["platform"] == "linux" and type(context["uid"]) is int
            and context["uid"] >= 0, "invalid skip platform")
    for nodeid, records in baseline["cases"].items():
        variants = records if isinstance(records, list) else [records]
        require(variants and len({canonical(item) for item in variants}) == len(variants),
                "empty or duplicate skip variants")
        for case in variants:
            require(isinstance(nodeid, str) and "::" in nodeid and isinstance(case, dict),
                    "invalid skip case")
            fields = {"outcome", "reason", "when", "module_blob", "disposition"}
            native = case.get("disposition") == "SAME_RUN_NATIVE_REQUIRED"
            require(set(case) == fields | ({"native_target"} if native else set())
                    and case["outcome"] in ("skipped", "xfail")
                    and isinstance(case["reason"], str) and bool(case["reason"])
                    and case["when"] in ("setup", "call", "teardown")
                    and case["disposition"] in ("HISTORICAL_UNEXECUTED", "OWNER_CANCELED",
                                                 "SAME_RUN_NATIVE_REQUIRED")
                    and case["module_blob"] == module_blobs.get(nodeid.split("::", 1)[0])
                    and isinstance(case["module_blob"], str)
                    and HEX40.fullmatch(case["module_blob"]), "invalid or stale skip case: " + nodeid)
            if native:
                require(case["native_target"] == nodeid.split("::", 1)[0], "native target differs")
    for module, case in baseline["collection_skips"].items():
        require(isinstance(case, dict) and set(case) == {"reason", "module_blob"}
                and isinstance(case["reason"], str) and bool(case["reason"])
                and case["module_blob"] == module_blobs.get(module)
                and isinstance(case["module_blob"], str)
                and HEX40.fullmatch(case["module_blob"]), "invalid collection skip")
    return baseline


def admit_skips(bound, module_blobs, result, native, mandatory_modules, mandatory_nodes=()):
    """Check observed facts; this does not replace the caller's native/role join."""
    baseline = validate_baseline(bound, module_blobs)
    counts = {"HISTORICAL_UNEXECUTED": 0, "OWNER_CANCELED": 0, "SAME_RUN_NATIVE_REQUIRED": 0}
    collection = {}
    for session in [result["reference"], *result["shards"]]:
        require(session["execution_context"] == baseline["context"], "skip platform differs")
        require(session.get("junit_sha256"), "missing JUnit evidence")
        for row in session["nonpassing_outcomes"]:
            nodeid = row["nodeid"]
            records = baseline["cases"].get(nodeid, [])
            variants = records if isinstance(records, list) else [records]
            matching = [case for case in variants if all(row.get(key) == case[key]
                        for key in ("outcome", "reason", "when"))]
            require(len(matching) == 1, "unregistered or ambiguous skip/xfail: " + nodeid)
            case = matching[0]
            module = nodeid.split("::", 1)[0]
            if module in mandatory_modules or nodeid in mandatory_nodes:
                require(case["disposition"] == "SAME_RUN_NATIVE_REQUIRED",
                        "cannot waive native obligation: " + nodeid)
            if case["disposition"] == "SAME_RUN_NATIVE_REQUIRED":
                require(nodeid in native["obligations"].get(case["native_target"], {}).get("passed", []),
                        "missing same-run native evidence: " + nodeid)
            counts[case["disposition"]] += 1
        for module, reason in session["collection_skips"].items():
            require(module not in mandatory_modules
                    and not any(nodeid.startswith(module + "::") for nodeid in mandatory_nodes),
                    "cannot collection-skip native module")
            require(baseline["collection_skips"].get(module) == {
                "reason": reason, "module_blob": module_blobs.get(module)}, "unregistered collection skip")
            if session["assignment_id"] != "reference":
                require(module not in collection, "duplicate collection skip")
                collection[module] = reason
    require(collection == result["reference"]["collection_skips"], "collection evidence differs")
    return {"status": "NO_NEW_SKIPS", "baseline_sha256": bound["evidence"][BASELINE]["sha256"],
            "baseline_source_revision": bound["source_revision"], "skips_are_passes": False,
            "disposition_counts": counts, "host_native_acceptance": "INDEPENDENT"}


def _load(repo, revision, policy_dir):
    # Explicit private injection exists only for isolated signing-fixture tests.
    require(isinstance(revision, str) and HEX40.fullmatch(revision), "exact source SHA required")
    commit = _object(repo, "commit", revision)
    _verify(commit, policy_dir)
    tree = tree_inputs(repo, revision)
    records, bindings = {}, {}
    for path in sorted(EVIDENCE_PATHS):
        entry = tree.get(path, {})
        require(entry.get("kind") == "blob" and entry.get("mode") == "100644",
                "missing or nonregular evidence: " + path)
        data = _object(repo, "blob", entry["git_blob"])
        records[path] = _json(data)
        bindings[path] = entry | {"sha256": digest(data)}
    actual = {path: entry for path, entry in tree.items() if path not in EVIDENCE_PATHS}
    require(actual, "empty source inputs")
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
