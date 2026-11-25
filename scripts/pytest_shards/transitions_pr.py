"""Reviewed pull-request input seals and estate successor proof."""
from __future__ import annotations

import json
import re
import subprocess

from .config import (
    AUDIT_LOCK_INPUT,
    BOT_PACKAGING_INPUT,
    COLLECTION_SHUFFLE_INPUT,
    HANG_GUARD_INPUT,
    MINIAPP_MEMBERSHIP_INPUT,
    MINIAPP_MEMBERSHIP_TRANSITION_SHA256,
    NATIVE_PROTOCOL_HELPER_POLICY_SHA256,
    P015_HELPER_POLICY_SHA256,
    PR_SHARED_INPUT_AFTER_BLOBS,
    PR_SHARED_INPUT_SEALS,
    PR_SHARED_INPUT_SOURCE_REVISIONS,
    REVIEWED_PR_INPUTS,
    REVIEWED_PR_INPUT_ACTIVATION,
    REVIEWED_PR_INPUT_FILES,
    SHA,
    SITE_LOCK_INPUT,
)
from .support import ROOT, baseline_bytes, encoded, git, read_json, require, sha, tree_inputs
from .transitions_estate import reviewed_estate_input_transition, reviewed_site_lock_transition
from .transitions_native import (
    historical_skip_baseline_bytes,
    reviewed_audit_lock_transition,
    reviewed_bot_packaging_transition,
    reviewed_collection_shuffle_transition,
    reviewed_hang_guard_input_transition,
    reviewed_npm_security_transition,
    reviewed_ops_packaging_transition,
    reviewed_runtime_dependency_transition,
    reviewed_tornado66_dependency_transition,
)


def estate_successor_proof(baseline, source, revision):
    """Prove a later Ops revision descends from the sealed estate successor.

    Only the planner has the full source history. It records the proven
    predecessor inside the sealed admission; validators and the join re-admit
    against that sealed value and still compare every estate input blob.
    """
    native_protocol_helper_proof(source, revision)
    pr_shared_input_successor_proof(source, revision)
    reviewed_pr_input_proof(source, revision)
    _, security = reviewed_npm_security_transition(baseline)
    if security is not None:
        successor = revision == security["source_after"]
        if revision not in (security["source_before"], security["source_after"]):
            try:
                git(source, "merge-base", "--is-ancestor", security["source_after"], revision)
                successor = True
            except subprocess.CalledProcessError as exc:
                require(exc.returncode == 1, "npm security ancestry unavailable")
        files = tree_inputs(source, revision)
        changed = any(files.get(path, (None, None))[1] == item["after_blob"]
                      for path, item in security["changes"].items())
        if successor or changed:
            try:
                git(source, "merge-base", "--is-ancestor", security["source_before"], security["source_after"])
                git(source, "merge-base", "--is-ancestor", security["source_after"], revision)
                parent_revision = git(source, "rev-parse", security["source_after"] + "^1").decode().strip()
                parent = tree_inputs(source, parent_revision)
                introduced = tree_inputs(source, security["source_after"])
                before = tree_inputs(source, security["source_before"])
            except subprocess.CalledProcessError:
                raise ValueError("npm security source ancestry differs") from None
            for path, item in security["changes"].items():
                require(files.get(path) == introduced.get(path) == (item["mode"], item["after_blob"])
                        and parent.get(path) == before.get(path) == (item["mode"], item["before_blob"]),
                        "npm security successor blob or mode differs")
    _, shuffle = reviewed_collection_shuffle_transition(baseline)
    if shuffle is not None:
        change = shuffle["changes"][COLLECTION_SHUFFLE_INPUT]
        try:
            blob = git(source, "rev-parse", f"{revision}:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        qualified_successor = revision == shuffle["source_after"]
        if revision not in (shuffle["source_before"], shuffle["source_after"]):
            try:
                git(source, "merge-base", "--is-ancestor", shuffle["source_after"], revision)
                qualified_successor = True
            except subprocess.CalledProcessError as exc:
                require(exc.returncode == 1,
                        "collection shuffle successor ancestry unavailable")
        # Absence is historical only before the qualified source. A descendant
        # cannot delete the hook and silently regain the old baseline admission.
        if qualified_successor or blob is not None:
            try:
                git(source, "merge-base", "--is-ancestor", shuffle["source_before"], change["source"])
                git(source, "merge-base", "--is-ancestor", change["source"], shuffle["source_after"])
                git(source, "merge-base", "--is-ancestor", shuffle["source_after"], revision)
                introduced = git(source, "rev-parse",
                                 f"{change['source']}:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
            except subprocess.CalledProcessError:
                raise ValueError("collection shuffle successor source revision differs") from None
            try:
                parent = git(source, "rev-parse",
                             f"{change['source']}^1:{COLLECTION_SHUFFLE_INPUT}").decode().strip()
            except subprocess.CalledProcessError:
                parent = None
            require(blob == introduced == change["after_blob"] and parent is None,
                    "collection shuffle successor source revision differs")
    _, packaging = reviewed_ops_packaging_transition(baseline)
    _, tornado = reviewed_tornado66_dependency_transition(baseline)
    _, hang = reviewed_hang_guard_input_transition(baseline)
    _, runtime = reviewed_runtime_dependency_transition(baseline)
    _, lock = reviewed_audit_lock_transition(baseline)
    _, bot = reviewed_bot_packaging_transition(baseline)
    _, site = reviewed_site_lock_transition(baseline)
    _, record = reviewed_estate_input_transition(baseline)
    if record is None or revision == record["source_after"]:
        return None
    if hang is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{HANG_GUARD_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob is not None:
            try:
                git(source, "merge-base", "--is-ancestor", hang["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("hang guard successor source revision differs") from None
    after = record["source_after"]
    try:
        git(source, "merge-base", "--is-ancestor", after, revision)
    except subprocess.CalledProcessError:
        raise ValueError("estate successor source revision differs") from None
    if site is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{SITE_LOCK_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == site["changes"][SITE_LOCK_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", site["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("site lock successor source revision differs") from None
    if bot is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{BOT_PACKAGING_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == bot["changes"][BOT_PACKAGING_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", bot["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("bot packaging successor source revision differs") from None
    if lock is not None:
        try:
            blob = git(source, "rev-parse", f"{revision}:{AUDIT_LOCK_INPUT}").decode().strip()
        except subprocess.CalledProcessError:
            blob = None
        if blob == lock["changes"][AUDIT_LOCK_INPUT]["after_blob"]:
            try:
                git(source, "merge-base", "--is-ancestor", lock["source_after"], revision)
            except subprocess.CalledProcessError:
                raise ValueError("audit lock successor source revision differs") from None
    if packaging is not None:
        for path, change in sorted(packaging["changes"].items()):
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob != change["after_blob"]:
                continue
            # The named signed source must descend from the Tornado successor, must
            # itself introduce exactly this blob transition, and must be an
            # ancestor of the revision being planned.
            try:
                git(source, "merge-base", "--is-ancestor",
                    packaging["source_before"], change["source"])
                git(source, "merge-base", "--is-ancestor", change["source"], revision)
                introduced = git(source, "rev-parse",
                                 f"{change['source']}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                raise ValueError("ops packaging successor source revision differs") from None
            try:
                parent = git(source, "rev-parse",
                             f"{change['source']}^1:{path}").decode().strip()
            except subprocess.CalledProcessError:
                parent = None
            require(introduced == change["after_blob"] and parent == change["before_blob"],
                    "ops packaging successor source revision differs")
    if tornado is not None:
        for path, change in tornado["changes"].items():
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob == change["after_blob"]:
                try:
                    git(source, "merge-base", "--is-ancestor",
                        tornado["source_before"], tornado["source_after"])
                    git(source, "merge-base", "--is-ancestor", tornado["source_after"], revision)
                except subprocess.CalledProcessError:
                    raise ValueError("Tornado dependency successor source revision differs") from None
                break
    if runtime is not None:
        for path, change in runtime["changes"].items():
            try:
                blob = git(source, "rev-parse", f"{revision}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                blob = None
            if blob == change["after_blob"]:
                try:
                    git(source, "merge-base", "--is-ancestor", runtime["source_after"], revision)
                except subprocess.CalledProcessError:
                    raise ValueError(
                        "runtime dependency successor source revision differs") from None
    return after


def first_native_policy():
    """Trusted central policy; it grants no historical execution credit."""
    policy = read_json(ROOT / "ops-first-native-successors.json")
    require(policy.get("schema") == 1 and len(policy.get("cases", {})) == 4
            and len(policy.get("module_blobs", {})) == 3,
            "invalid first native successor policy")
    return policy


def release_pin():
    return first_native_policy()["source_revision"]


def release_pin_is_ancestor(source, revision):
    """True when revision is the release pin or a descendant of it.

    A repository that does not contain the pin commit is not a descendant.
    That keeps fixture repositories on the exact-pin rule. A present pin with
    unreadable history still raises EvidenceUnavailable. Sealed blobs stay exact.
    """
    pin = release_pin()
    if revision == pin:
        return True
    try:
        git(source, "cat-file", "-e", pin + "^{commit}")
    except subprocess.CalledProcessError:
        return False
    try:
        git(source, "merge-base", "--is-ancestor", pin, revision)
    except subprocess.CalledProcessError as exc:
        require(exc.returncode == 1, "release pin ancestry unavailable")
        return False
    return True


def holds_release_pin(source_revision, *, pin_is_ancestor):
    """Exact pin, or a caller-proved descendant. The blob checks stay exact."""
    return source_revision == release_pin() or pin_is_ancestor is True


def admit_first_native_helper(common, files, source_revision, *, pin_is_ancestor=False):
    policy = first_native_policy()
    item = policy["shared_input"]
    path = item["path"]
    if path not in common and not holds_release_pin(
            source_revision, pin_is_ancestor=pin_is_ancestor):
        return common, files
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "first native helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "first native helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


def native_protocol_helper_policy():
    payload = (ROOT / "reviews/ops-native-protocol-helper-20261106/helper-policy.json").read_bytes()
    require(sha(payload) == NATIVE_PROTOCOL_HELPER_POLICY_SHA256, "unreviewed native protocol helper policy")
    return json.loads(payload)


def native_protocol_helper_proof(source, revision):
    policy = native_protocol_helper_policy()
    item = policy["shared_input"]
    files = tree_inputs(source, revision)
    if item["path"] not in files:
        return
    try:
        git(source, "merge-base", "--is-ancestor", policy["source_revision"], revision)
        introduced = tree_inputs(source, policy["source_revision"])
    except subprocess.CalledProcessError:
        raise ValueError("native protocol helper source ancestry differs") from None
    require(files[item["path"]] == introduced.get(item["path"])
            == (item["mode"], item["blob"]), "native protocol helper blob or mode differs")


def admit_native_protocol_helper(common, files, source_revision, *, pin_is_ancestor=False):
    path = "tests/native_protocol_fixture.py"
    if path not in common:
        return common, files
    item = native_protocol_helper_policy()["shared_input"]
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "native protocol helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "native protocol helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


def admit_p015_offline_helper(common, files, source_revision, *, pin_is_ancestor=False):
    if "tests/p015_offline_plugin.py" not in common:
        return common, files
    payload = (ROOT / "reviews/ops-p015-20261105/helper-policy.json").read_bytes()
    require(sha(payload) == P015_HELPER_POLICY_SHA256,
            "unreviewed p015 helper policy")
    policy = json.loads(payload)
    item = policy["shared_input"]
    path = item["path"]
    if path not in common:
        return common, files
    # Blob and mode stay exact. A descendant of the pin is enough when they match.
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor)
            and common.get(path) == item["blob"],
            "p015 offline helper requires the signed release pin or its descendant, and the exact blob")
    if files is not None:
        require(files.get(path) == (item["mode"], item["blob"]),
                "p015 offline helper mode or tree changed")
        files = {p: v for p, v in files.items() if p != path}
    return {p: v for p, v in common.items() if p != path}, files


def reviewed_pr_shared_input_transitions():
    """Peel exact outermost successors without modifying any historical seal."""
    original = dict(read_json(ROOT / "ops-shared-input-successors.json"))
    records = []
    for number, identity, paths in PR_SHARED_INPUT_SEALS:
        record = original.pop(f"reviewed_pr{number}_shared_input_transition", None)
        require(isinstance(record, dict) and set(record) == {
            "schema", "reviewer", "prior_baseline_sha256", "prior_successors_sha256",
            "source_before", "source_after", "independent_review_sha256",
            "source_freeze_sha256", "qualification_receipt_sha256", "changes"}
            and type(record["schema"]) is int and record["schema"] == 1,
            "invalid PR shared-input transition")
        require(sha(encoded(record)) == identity, "unreviewed PR shared-input transition")
        require(record["prior_successors_sha256"] == sha(baseline_bytes(original))
                and record["prior_baseline_sha256"] == sha(
                    historical_skip_baseline_bytes()),
                "PR shared-input transition changed historical predecessor")
        require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                    for k in ("source_before", "source_after"))
                and record["source_before"] != record["source_after"],
                "invalid PR shared-input source")
        require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                    and record[k] != "0" * 64 for k in (
                        "independent_review_sha256", "source_freeze_sha256",
                        "qualification_receipt_sha256")), "missing PR shared-input evidence")
        require(isinstance(record["changes"], dict) and set(record["changes"]) == paths,
                "invalid PR shared-input paths")
        for item in record["changes"].values():
            require(isinstance(item, dict) and set(item) == {
                "before_blob", "after_blob", "mode", "source"}
                and item["mode"] == "100644"
                and all(isinstance(item[k], str) and SHA.fullmatch(item[k])
                        for k in ("before_blob", "after_blob", "source"))
                and item["before_blob"] != item["after_blob"]
                and item["source"] == record["source_after"],
                "invalid PR shared-input blob identity")
        records.append(record)
    for outer, inner in zip(records, records[1:]):
        require(outer["source_before"] == inner["source_after"] and all(
            item["before_blob"] == inner["changes"][path]["after_blob"]
            for path, item in outer["changes"].items()), "PR shared-input merge order differs")
    return records


def admit_pr_shared_inputs(common, files, source_revision, *, pin_is_ancestor=False):
    """Undo reviewed PR bundles before any inner seal sees the shared map."""
    if source_revision not in PR_SHARED_INPUT_SOURCE_REVISIONS and not any(
            common.get(path) == blob for path, blob in PR_SHARED_INPUT_AFTER_BLOBS):
        return common, files
    for record in reviewed_pr_shared_input_transitions():
        changes = record["changes"]
        if source_revision != record["source_after"] and not any(
                common.get(path) == item["after_blob"] for path, item in changes.items()):
            continue
        require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
                "PR shared-input successor requires the signed release pin or its descendant")
        common = dict(common)
        if files is not None:
            files = dict(files)
        for path, item in changes.items():
            require(common.get(path) == item["after_blob"],
                    "PR shared-input successor bundle missing or changed")
            common[path] = item["before_blob"]
            if files is not None:
                require(files.get(path) == (item["mode"], item["after_blob"]),
                        "PR shared-input successor mode or tree differs")
                files[path] = (item["mode"], item["before_blob"])
    return common, files


def pr_shared_input_successor_proof(source, revision):
    """Bind bundles to reviewed source ancestry and exact before/after trees."""
    files = tree_inputs(source, revision)
    # Exact outer Ruff successor must be proved and peeled before PR256/122.
    reviewed_pr_input_proof(source, revision, names=("ruff_retired_video",))
    _, files = admit_reviewed_pr_inputs(
        {p: value[1] for p, value in files.items()}, files, revision,
        names=("ruff_retired_video",),
        pin_is_ancestor=release_pin_is_ancestor(source, revision))
    successors = set()
    for after in PR_SHARED_INPUT_SOURCE_REVISIONS:
        try:
            git(source, "cat-file", "-e", after + "^{commit}")
        except subprocess.CalledProcessError:
            continue  # Historical source repositories may predate these merges.
        try:
            git(source, "merge-base", "--is-ancestor", after, revision)
            successors.add(after)
        except subprocess.CalledProcessError as exc:
            require(exc.returncode == 1, "PR shared-input ancestry unavailable")
    if not successors and not any(files.get(path, (None, None))[1] == blob
                                  for path, blob in PR_SHARED_INPUT_AFTER_BLOBS):
        return
    for record in reviewed_pr_shared_input_transitions():
        changes = record["changes"]
        if record["source_after"] not in successors and not any(
                files.get(path, (None, None))[1] == item["after_blob"]
                for path, item in changes.items()):
            continue
        try:
            git(source, "merge-base", "--is-ancestor", record["source_after"], revision)
            git(source, "merge-base", "--is-ancestor", record["source_before"], revision)
            before = tree_inputs(source, record["source_before"])
            after = tree_inputs(source, record["source_after"])
        except subprocess.CalledProcessError:
            raise ValueError("PR shared-input successor ancestry differs") from None
        files = dict(files)
        for path, item in changes.items():
            require(files.get(path) == after.get(path) == (item["mode"], item["after_blob"])
                    and before.get(path) == (item["mode"], item["before_blob"]),
                    "PR shared-input successor blob or mode differs")
            files[path] = (item["mode"], item["before_blob"])


def reviewed_miniapp_membership_transition():
    """Reviewed successor of one shared input, kept outside the sealed skip baseline.

    The record follows the historical transition format (plus a reviewer label);
    storing it separately leaves every sealed prior_baseline_sha256 untouched.
    """
    value = read_json(ROOT / "ops-shared-input-successors.json")
    record = value.get("reviewed_miniapp_membership_transition")
    require(value.get("schema") == 1 and isinstance(record, dict) and set(record) == {
        "schema", "reviewer", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and record["schema"] == 1, "invalid miniapp membership transition")
    require(sha(encoded(record)) == MINIAPP_MEMBERSHIP_TRANSITION_SHA256,
            "unreviewed miniapp membership transition identity")
    require(record["prior_baseline_sha256"] == sha(historical_skip_baseline_bytes()),
            "miniapp membership transition changed historical baseline")
    require(all(re.fullmatch(r"[0-9a-f]{64}", record[k]) and record[k] != "0" * 64
                for k in ("independent_review_sha256", "source_freeze_sha256",
                          "qualification_receipt_sha256")),
            "miniapp membership review or qualification missing")
    changes = record["changes"]
    require(set(changes) == {MINIAPP_MEMBERSHIP_INPUT}, "unreviewed miniapp membership paths")
    change = changes[MINIAPP_MEMBERSHIP_INPUT]
    require(set(change) == {"before_blob", "after_blob", "mode", "source"}
            and SHA.fullmatch(change["before_blob"]) and SHA.fullmatch(change["after_blob"])
            and change["before_blob"] != change["after_blob"] and change["mode"] == "100644"
            and change["source"] == record["source_after"] != record["source_before"],
            "invalid miniapp membership blob, mode or source")
    return record


def admit_miniapp_membership(common, files, source_revision, *, pin_is_ancestor=False):
    """Swap the reviewed after-blob back to its predecessor at the pin or a descendant."""
    if not isinstance(common, dict) or MINIAPP_MEMBERSHIP_INPUT not in common:
        return common, files
    change = reviewed_miniapp_membership_transition()["changes"][MINIAPP_MEMBERSHIP_INPUT]
    if common[MINIAPP_MEMBERSHIP_INPUT] != change["after_blob"]:
        return common, files
    require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
            "miniapp membership successor requires the signed release pin or its descendant")
    common = dict(common) | {MINIAPP_MEMBERSHIP_INPUT: change["before_blob"]}
    if files is not None:
        require(files.get(MINIAPP_MEMBERSHIP_INPUT) == (change["mode"], change["after_blob"]),
                "miniapp membership input mode or tree changed")
        files = dict(files) | {MINIAPP_MEMBERSHIP_INPUT: (change["mode"], change["before_blob"])}
    return common, files


def reviewed_pr_input_active(name, blob_of):
    blobs = REVIEWED_PR_INPUT_ACTIVATION.get(name)
    return blobs is None or any(blob_of(path) == blob for path, blob in blobs)


def reviewed_pr_input_transition(name):
    """Validate an exact reviewed sidecar seal without rewriting inner seals."""
    identity, paths = REVIEWED_PR_INPUTS[name]
    value = read_json(ROOT / REVIEWED_PR_INPUT_FILES.get(name, "ops-shared-input-successors.json"))
    record = value.get("reviewed_" + name + "_transition")
    require(value.get("schema") == 1 and isinstance(record, dict) and set(record) == {
        "schema", "reviewer", "prior_baseline_sha256", "source_before", "source_after",
        "independent_review_sha256", "source_freeze_sha256",
        "qualification_receipt_sha256", "changes",
    } and type(record["schema"]) is int and record["schema"] == 1,
            "invalid reviewed PR input transition: " + name)
    require(sha(encoded(record)) == identity,
            "unreviewed PR input transition identity: " + name)
    require(record["prior_baseline_sha256"] == sha(historical_skip_baseline_bytes()),
            "reviewed PR input transition changed historical baseline: " + name)
    require(all(isinstance(record[k], str) and SHA.fullmatch(record[k])
                for k in ("source_before", "source_after"))
            and record["source_before"] != record["source_after"],
            "invalid reviewed PR input source: " + name)
    require(all(isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
                and record[k] != "0" * 64 for k in (
                    "independent_review_sha256", "source_freeze_sha256",
                    "qualification_receipt_sha256")),
            "reviewed PR input evidence missing: " + name)
    changes = record["changes"]
    require(isinstance(changes, dict) and set(changes) == paths,
            "unreviewed PR input paths: " + name)
    for change in changes.values():
        require(isinstance(change, dict) and set(change) == {
            "before_blob", "after_blob", "mode", "source"}
            and all(isinstance(change[k], str) and SHA.fullmatch(change[k])
                    for k in ("before_blob", "after_blob", "source"))
            and change["before_blob"] != change["after_blob"]
            and change["mode"] == "100644"
            and change["source"] == record["source_after"],
            "invalid reviewed PR input blob, mode or source: " + name)
    return record


def reviewed_pr_input_proof(source, revision, *, names=None):
    """The planner proves source ancestry for each selected exact input bundle."""
    files = tree_inputs(source, revision)
    for name, (_, paths) in REVIEWED_PR_INPUTS.items():
        if names is not None and name not in names:
            continue
        if not paths.intersection(files) or not reviewed_pr_input_active(
                name, lambda p: files.get(p, (None, None))[1]):
            continue
        record = reviewed_pr_input_transition(name)
        if not any(files.get(p, (None, None))[1] == c["after_blob"]
                   for p, c in record["changes"].items()):
            continue
        try:
            for ancestor in (record["source_before"], record["source_after"]):
                git(source, "merge-base", "--is-ancestor", ancestor, revision)
            before = tree_inputs(source, record["source_before"])
            after = tree_inputs(source, record["source_after"])
        except subprocess.CalledProcessError:
            raise ValueError("reviewed PR input source ancestry differs: " + name) from None
        for path, change in record["changes"].items():
            require(before.get(path) == (change["mode"], change["before_blob"])
                    and after.get(path) == files.get(path)
                    == (change["mode"], change["after_blob"]),
                    "reviewed PR input successor blob or mode differs: " + path)


def admit_reviewed_pr_inputs(common, files, source_revision, *, names=None, pin_is_ancestor=False):
    """Peel exact bundles at the release pin, or a descendant, before historical validators.

    Stacked successors must peel to a fixpoint. A later map entry can expose a
    predecessor's after-blob (site_refresh_plans leaves the site_devdeps lockfile
    and package.json after-blobs); a single pass over insertion order would skip
    the earlier name and leave those blobs for _admit_existing_shared_inputs.
    """
    if not isinstance(common, dict):
        return common, files
    peeled = set()
    progressed = True
    while progressed:
        progressed = False
        for name, (_, paths) in REVIEWED_PR_INPUTS.items():
            if name in peeled or (names is not None and name not in names):
                continue
            if not paths.intersection(common) or not reviewed_pr_input_active(name, common.get):
                continue
            record = reviewed_pr_input_transition(name)
            changes = record["changes"]
            if not any(common.get(p) == c["after_blob"] for p, c in changes.items()):
                continue
            require(holds_release_pin(source_revision, pin_is_ancestor=pin_is_ancestor),
                    "reviewed PR input successor requires the signed release pin or its descendant: " + name)
            common = dict(common)
            if files is not None:
                files = dict(files)
            for path, change in changes.items():
                require(common.get(path) == change["after_blob"],
                        "reviewed PR input bundle missing or changed: " + path)
                common[path] = change["before_blob"]
                if files is not None:
                    require(files.get(path) == (change["mode"], change["after_blob"]),
                            "reviewed PR input mode or tree changed: " + path)
                    files[path] = (change["mode"], change["before_blob"])
            peeled.add(name)
            progressed = True
    return common, files
