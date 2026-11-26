"""Input hashes, recipe hashes and advisory feedback manifests."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.util
import json
import os
import re
import sys
import types
from pathlib import Path, PurePosixPath

from .constants import (
    BUILD_JOB,
    FEEDBACK_SCHEMA,
    FULL_GATES,
    RECIPE_SCHEMA,
    ROOT,
    SCHEMA,
    SHA40,
    Unknown,
)
from .dockerfile import parse_dockerfile, selected
from .ignore import IgnoreRules, _clean
from .tree import GitHubTree, LocalGit

def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def load_services(path: Path | None = None) -> dict[str, dict]:
    data = json.loads((path or ROOT / "services.json").read_text(encoding="utf-8"))
    return {entry["service"]: entry for entry in data}


_UI_UNITS = None


def _ui_units():
    """The static-unit catalog. Loaded lazily so non-UI fingerprints stay import-free."""
    global _UI_UNITS
    if _UI_UNITS is None:
        spec = importlib.util.spec_from_file_location(
            "ui_static_units_for_fingerprint", ROOT / "scripts" / "ui_static_units.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _UI_UNITS = module
    return _UI_UNITS


def _ui_scope(entry: dict) -> str | None:
    """Unit path for a ui-* service; None for every other service.

    Non-UI services never load the catalog, so a vendored copy without
    scripts/ui_static_units.py (yueops scripts/lib) keeps working. A ui-*
    service whose catalog cannot be loaded is unknown, never widened.
    """
    service = entry.get("service")
    if not isinstance(service, str) or not service.startswith("ui-"):
        return None
    try:
        units = _ui_units()
    except (OSError, ImportError) as exc:
        raise Unknown(f"{service} static-unit catalog unavailable: {exc}") from exc
    try:
        return units.unit_scope(entry)
    except units.ScopeError as exc:
        raise Unknown(str(exc)) from exc


def compute(source, rev: str, entry: dict) -> dict:
    """Return {"fingerprint", "files", ...} or {"unknown": reason, ...}."""
    result: dict = {"schema": SCHEMA, "service": entry["service"], "revision": rev}
    try:
        if entry.get("context", ".") != ".":
            raise Unknown(f"non-root build context {entry.get('context')!r} is not modelled")
        dockerfile = _clean(entry["dockerfile"])
        tree = source.entries(rev)
        if dockerfile not in tree:
            raise Unknown(f"{dockerfile} not present at {rev[:12]}")
        facts = parse_dockerfile(source.blob(tree[dockerfile][2]).decode("utf-8"))
        result["caveats"] = facts.caveats
        if facts.problems:
            raise Unknown("; ".join(facts.problems))
        specific = dockerfile + ".dockerignore"
        ignore_path = specific if specific in tree else (".dockerignore" if ".dockerignore" in tree else "")
        rules = IgnoreRules.parse(source.blob(tree[ignore_path][2]).decode("utf-8")) if ignore_path else IgnoreRules()
        docker_dir = dockerfile.rpartition("/")[0]
        dead = sorted(
            p for p in tree
            if p.rpartition("/")[0] == docker_dir and p.rsplit("/", 1)[-1] == ".dockerignore"
            and p != ignore_path
        )
        attributes = sorted(p for p in tree if p.rsplit("/", 1)[-1] == ".gitattributes")
        for attr in attributes:
            if re.search(rb"(^|\s)filter=", source.blob(tree[attr][2])):
                raise Unknown(f"{attr} declares a checkout filter")
        files = sorted(
            [path, tree[path][0], tree[path][2]]
            for path in tree
            if selected(path, facts.sources) and not rules.ignored(path)
        )
        scope = _ui_scope(entry)
        if scope is not None:
            def in_unit(path: str) -> bool:
                return _ui_units().path_in_unit(path, scope, dockerfile)
            escaped = sorted(
                src for src in set(facts.sources)
                if not (src == scope or src.startswith(scope + "/"))
            )
            if escaped:
                raise Unknown(
                    f"{entry['service']} build inputs escape {scope}: {', '.join(escaped[:6])}"
                )
            files = [row for row in files if in_unit(row[0])]
            attributes = [path for path in attributes if in_unit(path)]
            dead = [path for path in dead if in_unit(path)]
            if ignore_path and not in_unit(ignore_path):
                ignore_path = ""
        if not files:
            raise Unknown("no build-context file selected (scan floor)")
        payload = {
            "schema": SCHEMA,
            "context": ".",
            "dockerfile": [dockerfile, tree[dockerfile][2]],
            "ignore": [ignore_path, tree[ignore_path][2]] if ignore_path else None,
            "gitattributes": [[p, tree[p][2]] for p in attributes],
            "files": files,
        }
        result.update(
            fingerprint=_digest(payload),
            dockerfile=dockerfile,
            ignore_file=ignore_path or None,
            dead_ignore_files=dead,
            sources=sorted(set(facts.sources)),
            external_images=sorted(set(facts.external_images)),
            file_count=len(files),
            files=files,
        )
    except Unknown as exc:
        result["unknown"] = str(exc)
    return result


def recipe(entry: dict, workflow_text: str) -> dict:
    match = BUILD_JOB.search(workflow_text)
    if not match:
        return {"schema": RECIPE_SCHEMA, "unknown": "build job not found in build.yml"}
    stable = {k: v for k, v in entry.items() if k != "ref"}
    return {
        "schema": RECIPE_SCHEMA,
        "fingerprint": _digest({"schema": RECIPE_SCHEMA, "service": stable, "build_job": match.group(0).rstrip()}),
    }


def compare(base: dict, head: dict) -> str:
    """unchanged | changed | unknown -- unknown never collapses into unchanged."""
    if "unknown" in base or "unknown" in head or "fingerprint" not in base or "fingerprint" not in head:
        return "unknown"
    return "unchanged" if base["fingerprint"] == head["fingerprint"] else "changed"


def changed_paths(base: dict, head: dict) -> list[str]:
    a = {p: (m, o) for p, m, o in base.get("files", [])}
    b = {p: (m, o) for p, m, o in head.get("files", [])}
    return sorted(p for p in a.keys() | b.keys() if a.get(p) != b.get(p))


def verdict(inputs: str, recipe_state: str) -> str:
    if inputs == "unchanged" and recipe_state == "unchanged":
        return "would-skip"
    if inputs == "unknown" or recipe_state == "unknown":
        return "would-build (unknown)"
    return "would-build"


def _feedback_policy(filename: str):
    if filename == "pytest-shards.py":
        # Two attributes only. Callers patch this object; the package is not re-exported.
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from pytest_shards.config import NATIVE_TARGETS
        from pytest_shards.support import safe_module
        return types.SimpleNamespace(safe_module=safe_module, NATIVE_TARGETS=NATIVE_TARGETS)
    spec = importlib.util.spec_from_file_location(filename, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feedback_tree(source, revision: str) -> dict:
    # The existing readers address committed Git objects, never working bytes.
    try:
        if source.resolve(revision) != revision:
            raise Unknown("tree revision differs from the exact requested commit")
        tree = (source.entries(revision, strict=True) if isinstance(source, GitHubTree)
                else source.entries(revision))
    except (Unknown, ValueError, KeyError, TypeError, AttributeError, OSError,
            UnicodeError, http.client.HTTPException) as exc:
        # Reader exceptions can contain an API URL, response body or local path.
        raise Unknown("committed tree unavailable: " + type(exc).__name__) from exc
    if not isinstance(tree, dict):
        raise Unknown("malformed complete tree")
    for path, entry in tree.items():
        if (not isinstance(path, str) or not path or
                PurePosixPath(path).as_posix() != path or path.startswith("/") or
                ".." in PurePosixPath(path).parts or any(ord(c) < 32 for c in path)):
            raise Unknown("unsafe tree path")
        if (not isinstance(entry, (tuple, list)) or len(entry) != 3 or
                (entry[0], entry[1]) not in {
                    ("100644", "blob"), ("100755", "blob"),
                    ("120000", "blob"), ("160000", "commit"),
                } or not isinstance(entry[2], str) or not SHA40.fullmatch(entry[2])):
            raise Unknown("malformed tree object")
    return tree


def _feedback_changes(base: dict, head: dict) -> list[dict]:
    def object_id(value):
        return dict(zip(("mode", "kind", "oid"), value)) if value is not None else None

    return [
        {"path": path, "operation": "add" if path not in base else
         "delete" if path not in head else "modify",
         "before": object_id(base.get(path)), "after": object_id(head.get(path))}
        for path in sorted(base.keys() | head.keys()) if base.get(path) != head.get(path)
    ]


def feedback_manifest(source, base: str, matrix: list, validators: list, context: dict) -> dict:
    """Report full source differences and useful modules, never a release verdict."""
    result = {
        "schema": FEEDBACK_SCHEMA, "preliminary": True, "release_admission": False,
        "status": "UNKNOWN", "comparison_complete": False,
        "inputs": {"source_repository": "onesyue/yueops",
                   "base": base if isinstance(base, str) and SHA40.fullmatch(base) else None,
                   "head": None, "baseline_origin": "explicit-previous-source",
                   **{k: context.get(k) if isinstance(context.get(k), str) and
                      re.fullmatch(r"[0-9a-f]+", context[k]) else None
                      for k in ("policy_commit", "run_id", "run_attempt")}},
        "full_validation_obligations": [], "obligation_inventory_complete": False,
        "changed_paths": None, "changed_count": None, "changed_paths_sha256": None,
        "selected_obligations": [],
        "fallback": {"scope": "full-gate", "gate_ids": list(FULL_GATES),
                     "reasons": []},
    }
    try:
        if (set(context) != {"policy_commit", "run_id", "run_attempt"} or
                not isinstance(context["policy_commit"], str) or
                not SHA40.fullmatch(context["policy_commit"]) or
                any(not isinstance(context[k], str) or
                    not re.fullmatch(r"[1-9][0-9]*", context[k])
                    for k in ("run_id", "run_attempt"))):
            raise Unknown("missing or malformed policy/run identity")
        if (not isinstance(matrix, list) or not isinstance(validators, list) or
                not validators or
                not all(isinstance(row, dict) for row in matrix + validators)):
            raise Unknown("missing or malformed target matrices")
        if not all(isinstance(row.get("validation"), str) and
                   re.fullmatch(r"[a-z0-9-]+", row["validation"]) for row in matrix + validators):
            raise Unknown("invalid validator identity")
        jobs = _feedback_policy("verification-evidence.py").validation_job_names(validators)
        if len(jobs) != len(set(jobs)) or not all(re.fullmatch(r"[a-z0-9-]+", j) for j in jobs):
            raise Unknown("duplicate or malformed validation obligations")
        result["full_validation_obligations"] = jobs
        result["obligation_inventory_complete"] = True
        result["inputs"].update(build_matrix_sha256=_digest(matrix),
                                validation_matrix_sha256=_digest(validators))
        images = [row for row in matrix if row.get("validation") == "yueops"]
        ops = [row for row in validators if row["validation"] == "yueops"]
        if not images and not ops:
            result["status"] = "NOT_APPLICABLE"
            result["fallback"]["reasons"] = ["No Ops target; no Ops acceptance is claimed."]
        else:
            if not images or not ops:
                raise Unknown("Ops image and validator selections differ")
            if any(row.get("node_profile") or (row.get("ops_role") not in (None, "legacy") and
                   (not isinstance(row["ops_role"], str) or not re.fullmatch(
                       r"reference(?:-(?:serial|ordinary-[0-9]{3}))?|native|serial|ordinary-[0-9]{3}", row["ops_role"])))
                   for row in ops):
                raise Unknown("invalid Ops validator role")
            services = [row.get("service") for row in images]
            if (not all(isinstance(name, str) and name in {
                    "yueops-web", "checkin-api", "yue-bot"} for name in services) or
                    len(services) != len(set(services))):
                raise Unknown("duplicate or unsupported Ops image selection")
            if (any(row.get("repo") != "onesyue/yueops" or
                    not isinstance(row.get("ref"), str) or
                    not SHA40.fullmatch(row["ref"]) for row in images + ops) or
                    len({row["ref"] for row in images + ops}) != 1):
                raise Unknown("Ops repository/head identities differ or are not exact")
            head = images[0]["ref"]
            result["inputs"]["head"] = head
            if result["inputs"]["base"] is None:
                raise Unknown("baseline must be an explicit exact source commit")
            before, after = _feedback_tree(source, base), _feedback_tree(source, head)
            changes = _feedback_changes(before, after)
            policy = _feedback_policy("pytest-shards.py")
            selected, reasons = [], []
            for change in changes:
                path, old, new = change["path"], change["before"], change["after"]
                regular = all(obj is not None and obj["mode"] in ("100644", "100755")
                              and obj["kind"] == "blob" for obj in (old, new))
                if (policy.safe_module(path) and path not in policy.NATIVE_TARGETS
                        and change["operation"] == "modify" and regular):
                    selected.append({
                        "id": "pytest-module:" + path, "path": path,
                        "reason": "Modified owned whole test module; dependent coverage is unproved.",
                        "trigger_paths": [path],
                    })
                    reasons.append({"path": path, "reason": "transitive-test-mapping-unknown"})
                else:
                    reasons.append({"path": path, "reason":
                                    "test-inventory-or-native-change" if policy.safe_module(path)
                                    else "shared-generated-dependency-or-unclassified-input"})
            result.update(
                status="COMPLETE", comparison_complete=True, changed_paths=changes,
                changed_count=len(changes), changed_paths_sha256=_digest(changes),
                selected_obligations=selected,
            )
            result["fallback"]["reasons"] = reasons or [
                "No source difference; full and time-dependent obligations remain required."
            ]
    except (Unknown, ValueError, KeyError, TypeError, OSError, UnicodeError,
            http.client.HTTPException) as exc:
        # No credentials, remote response body or exception-supplied URL enters
        # the manifest. A failed comparison is never an empty change set.
        reason = str(exc) if isinstance(exc, Unknown) else type(exc).__name__
        result["fallback"]["reasons"] = ["Comparison unavailable: " + reason[:240]]
    result["manifest_sha256"] = _digest(result)
    return result


def validate_feedback_manifest(value: dict) -> None:
    """Check the actual persisted advisory contract without admitting a gate."""
    payload = dict(value)
    digest = payload.pop("manifest_sha256", None)
    if (digest != _digest(payload) or value.get("schema") != FEEDBACK_SCHEMA or
            value.get("preliminary") is not True or value.get("release_admission") is not False or
            value.get("fallback", {}).get("scope") != "full-gate" or
            value["fallback"].get("gate_ids") != FULL_GATES or not value["fallback"].get("reasons")):
        raise Unknown("invalid advisory manifest or missing full-gate fallback")
    if value.get("status") == "COMPLETE":
        changes = value.get("changed_paths")
        if (value.get("comparison_complete") is not True or
                value.get("obligation_inventory_complete") is not True or
                not value.get("full_validation_obligations") or
                not isinstance(changes, list) or value.get("changed_count") != len(changes) or
                value.get("changed_paths_sha256") != _digest(changes)):
            raise Unknown("incomplete advisory comparison")
    elif (value.get("status") not in ("UNKNOWN", "NOT_APPLICABLE") or
          value.get("comparison_complete") is not False or
          value.get("changed_paths") is not None or value.get("changed_count") is not None or
          value.get("changed_paths_sha256") is not None or value.get("selected_obligations")):
        raise Unknown("unavailable comparison mislabeled as a selection")


def feedback_command(args: argparse.Namespace) -> int:
    source = LocalGit(args.repo) if args.repo else GitHubTree(
        "onesyue/yueops", os.environ.get("GH_API_TOKEN", ""))
    context = {"policy_commit": args.policy_commit,
               "run_id": args.run_id, "run_attempt": args.run_attempt}
    # Malformed JSON must still produce an explicit UNKNOWN artifact.
    try:
        matrix, validators = json.loads(args.matrix), json.loads(args.validation_matrix)
    except ValueError:
        matrix, validators = None, None
    value = feedback_manifest(source, args.base, matrix, validators, context)
    validate_feedback_manifest(value)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"affected-feedback: {value['status']}; preliminary only; full gate required")
    return 3 if value["status"] == "UNKNOWN" else 0
