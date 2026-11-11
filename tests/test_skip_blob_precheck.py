"""Skip-blob precheck uses the same successor bindings as join."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skip_blob_shards", ROOT / "scripts/pytest-shards.py")
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)

RESTORE = "tests/test_yueops_pg_restore_drill_20260924.py"
RESTORE_BEFORE = "2f57ec05cab6f9af631f66650feaaf76a7770222"
RESTORE_AFTER = "3cca4792fbd3319411901ad3588a879e7b52193f"
RESTORE_NODE = RESTORE + "::test_e2e_real_backup_restores_and_passes"
CDN = "tests/test_cdn_vless_autohide_20261006.py"
CDN_NODE = CDN + "::test_real_vless_ws_tls_requires_authenticated_request"
BOARD = "tests/test_board139_schema_acl_native_20261018.py"
BOARD_RENEWAL = "0509528f81cd39c6e308e130650670a874b1b3df"
REJECTED_CI = "3e50d18a19aad788a7c86bc34ba3ba7885d7397d"
ACCEPTED_CI = "5b0f22c339c0b23a2952df7eb873cc42a1da0ded"
OPS_REV = "4ffbac5644f398473d95b4f19434949ce34a89c5"
OPS_CHECKOUT = Path("/Users/j/Projects/yueto/yueops")

CDN_SOURCE = (
    "import os\n"
    "import pytest\n"
    "\n"
    "def test_real_vless_ws_tls_requires_authenticated_request():\n"
    "    binary = os.environ.get(\"XRAY_PROBE_TEST_BIN\")\n"
    "    if not binary:\n"
    "        pytest.skip(\"set XRAY_PROBE_TEST_BIN\")\n"
)
ROOT_ONLY_SOURCE = (
    "import os\n"
    "import pytest\n"
    "\n"
    "@pytest.mark.skipif(os.geteuid() != 0, reason=\"root only\")\n"
    "def test_real_vless_ws_tls_requires_authenticated_request():\n"
    "    pass\n"
)


def _value(module, blob):
    return {
        "skip_module_blobs": {module: blob},
        "source_revision": "b" * 40,
        "pin_is_ancestor": False,
    }


def _git(repo, *args, input_text=None):
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Skip Blob",
        "GIT_AUTHOR_EMAIL": "skip-blob@example.com",
        "GIT_COMMITTER_NAME": "Skip Blob",
        "GIT_COMMITTER_EMAIL": "skip-blob@example.com",
    })
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], input=input_text, text=True, env=env).strip()


def _object_present(revision):
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", revision],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return completed.returncode == 0


def _commit_policy(repo, source):
    _git(repo, "init", "-q")
    relative = "scripts/pytest-shards.py"
    path = repo / relative
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    _git(repo, "add", "--", relative)
    tree = _git(repo, "write-tree")
    return _git(repo, "commit-tree", tree, input_text="policy fixture\n")


def _drop_function(source, name, follower):
    start = source.index("def " + name + "(")
    end = source.index("def " + follower + "(")
    if start >= end:
        raise AssertionError("policy fixture ranges overlap")
    return source[:start] + source[end:]


def _historical_native_source(source):
    replacements = (
        (
            "def reviewed_board139_native_successor(baseline, value, native, *, require_native=True):",
            "def reviewed_board139_native_successor(baseline, value, native):",
        ),
        (
            "def reviewed_first_native_successor(baseline, value, native, *, require_native=True):",
            "def reviewed_first_native_successor(baseline, value, native):",
        ),
        (
            "    if require_native:\n"
            "        passed = native[\"obligations\"].get(module, {}).get(\"passed\", [])\n"
            "        require(set(passed) == expected and len(passed) == len(expected), message)\n",
            "    passed = native[\"obligations\"].get(module, {}).get(\"passed\", [])\n"
            "    require(set(passed) == expected and len(passed) == len(expected), message)\n",
        ),
        (
            "        if require_native:\n"
            "            require(nodeid in native[\"obligations\"].get(module, {}).get(\"passed\", []),\n"
            "                    \"first native successor lacks exact same-run call: \" + nodeid)\n",
            "        require(nodeid in native[\"obligations\"].get(module, {}).get(\"passed\", []),\n"
            "                \"first native successor lacks exact same-run call: \" + nodeid)\n",
        ),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise AssertionError("historical policy fixture anchor drifted")
        source = source.replace(old, new, 1)
    return source

def _ops_commit(repo, files):
    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
    _git(repo, "read-tree", "--empty")
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(repo, "add", "--", relative)
    tree = _git(repo, "write-tree")
    return _git(repo, "commit-tree", tree, input_text="fixture\n")


RESTORE_SOURCE = (
    "import pytest\n\n"
    "def test_e2e_real_backup_restores_and_passes():\n"
    "    pytest.skip('base image missing')\n"
)
OPS_EVIDENCE = "tests/admission/ordinary-skip-evidence.json"


def _ops_evidence(before, after):
    return json.dumps({
        "schema": 1,
        "updates": {RESTORE_NODE: {"before_blob": before, "after_blob": after}},
        "additions": {},
    }, sort_keys=True) + "\n"


def _restore_module_evidence(after):
    updates = {
        nodeid: {"before_blob": RESTORE_BEFORE, "after_blob": after}
        for nodeid, case in SHARDS.skip_baseline()["cases"].items()
        if nodeid.startswith(RESTORE + "::") and case.get("module_blob") == RESTORE_BEFORE
    }
    if len(updates) < 2:
        raise AssertionError("restore drill module needs every admitted skip")
    return json.dumps(
        {"schema": 1, "updates": updates, "additions": {}}, sort_keys=True) + "\n"


class SkipBlobPrecheck(unittest.TestCase):
    def test_unchanged_reviewed_blob_matches(self):
        self.assertEqual(SHARDS.skip_blob_report(_value(RESTORE, RESTORE_BEFORE), {}), [])

    def test_changed_blob_without_successor_names_module_and_blobs(self):
        mutated = "f" * 40
        lines = SHARDS.skip_blob_report(_value(RESTORE, mutated), {})
        self.assertEqual(len(lines), 1)
        self.assertRegex(
            lines[0],
            r"^" + RESTORE + r"  " + RESTORE_BEFORE + r" -> " + mutated + r"  \(")
        self.assertIn(RESTORE_NODE, lines[0])

    def test_successor_blob_matches(self):
        self.assertEqual(SHARDS.skip_blob_report(_value(RESTORE, RESTORE_AFTER), {}), [])

    def test_ordinary_successor_matches_and_unsealed_blob_is_named(self):
        record = json.loads((ROOT / "reviews/ops-ordinary-skip-evidence-20261111.json").read_text())
        change = record["updates"][CDN_NODE]
        self.assertNotEqual(change["before_blob"], change["after_blob"])
        self.assertEqual(
            SHARDS.skip_blob_report(_value(CDN, change["after_blob"]), {CDN: CDN_SOURCE}), [])
        mutated = "e" * 40
        lines = SHARDS.skip_blob_report(_value(CDN, mutated), {CDN: CDN_SOURCE})
        self.assertEqual(len(lines), 1)
        self.assertIn(CDN, lines[0])
        self.assertIn(change["before_blob"], lines[0])
        self.assertIn(mutated, lines[0])
        self.assertIn(CDN_NODE, lines[0])
        self.assertEqual(
            SHARDS.skip_blob_report(_value(CDN, mutated), {CDN: ROOT_ONLY_SOURCE}), [])

    def test_historical_policy_keeps_the_rejected_restore_blob(self):
        source = _drop_function(
            (ROOT / "scripts/pytest-shards.py").read_text(encoding="utf-8"),
            "reviewed_restore_drill_blob_successor",
            "reviewed_board139_native_successor")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            commit = _commit_policy(repo, source)
            policy = SHARDS.load_policy_module(commit, repo)
        self.assertFalse(hasattr(policy, "reviewed_restore_drill_blob_successor"))
        lines = SHARDS.skip_blob_report(_value(RESTORE, RESTORE_AFTER), {}, policy=policy)
        self.assertEqual(len(lines), 1)
        self.assertIn(RESTORE, lines[0])
        self.assertIn(RESTORE_BEFORE, lines[0])
        self.assertIn(RESTORE_AFTER, lines[0])
        self.assertEqual(SHARDS.skip_blob_report(_value(RESTORE, RESTORE_AFTER), {}), [])

    def test_historical_board_renewal_does_not_need_a_native_receipt(self):
        source = _historical_native_source(
            (ROOT / "scripts/pytest-shards.py").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            commit = _commit_policy(repo, source)
            policy = SHARDS.load_policy_module(commit, repo)
            function = policy.reviewed_board139_native_successor
            self.assertNotIn("require_native", function.__code__.co_varnames)
            bound = policy.prepare_skip_bindings(
                _value(BOARD, BOARD_RENEWAL), {"obligations": {}},
                require_native=False, check_shared_inputs=False)
        blobs = {nodeid.split("::", 1)[0]: case["module_blob"]
                 for nodeid, case in bound["reviewed"]["cases"].items()
                 if nodeid.startswith(BOARD + "::")}
        self.assertEqual(blobs, {BOARD: BOARD_RENEWAL})

    def test_missing_policy_commit_is_an_input_error(self):
        missing = "0" * 40
        with self.assertRaises(ValueError) as caught:
            SHARDS.load_policy_module(missing)
        self.assertIn("not in this clone", str(caught.exception))
        code = SHARDS.skip_blob_precheck_command(type("Args", (), {
            "ops_rev": "b" * 40, "ci_rev": missing, "ops_checkout": ROOT,
        })())
        self.assertEqual(code, 2)

    def test_usage_error_is_not_a_blob_mismatch(self):
        code = SHARDS.skip_blob_precheck_command(type("Args", (), {
            "ops_rev": "not-a-sha", "ci_rev": None, "ops_checkout": ROOT,
        })())
        self.assertEqual(code, 2)

    def test_command_rejects_a_mutated_restore_blob_and_accepts_an_empty_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _git(repo, "init", "-q")
            relative = RESTORE
            path = repo / relative
            path.parent.mkdir(parents=True)
            path.write_text(
                "import pytest\n\n"
                "def test_e2e_real_backup_restores_and_passes():\n"
                "    pytest.skip('base image missing')\n",
                encoding="utf-8")
            _git(repo, "add", "--", relative)
            tree = _git(repo, "write-tree")
            commit = _git(repo, "commit-tree", tree, input_text="fixture\n")
            blob = _git(repo, "rev-parse", f"{commit}:{relative}")
            failed = self._command(repo, commit)
            self.assertEqual(failed.returncode, 1, failed.stderr)
            self.assertIn(RESTORE, failed.stdout)
            self.assertIn(RESTORE_BEFORE, failed.stdout)
            self.assertIn(blob, failed.stdout)
            self.assertIn(RESTORE_NODE, failed.stdout)
            self.assertNotIn(RESTORE_AFTER, failed.stdout)

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _git(repo, "init", "-q")
            tree = _git(repo, "mktree", input_text="")
            commit = _git(repo, "commit-tree", tree, input_text="empty\n")
            passed = self._command(repo, commit)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(passed.stdout.strip(), "skip-blob-precheck ok")

    def test_replay_rejected_pair_and_sealed_pair(self):
        if not OPS_CHECKOUT.is_dir():
            self.skipTest("local yueops checkout is not present")
        if not (_object_present(REJECTED_CI) and _object_present(ACCEPTED_CI)):
            self.skipTest("historical yueto-ci commits are not in this clone")
        rejected = self._command(OPS_CHECKOUT, OPS_REV, REJECTED_CI)
        self.assertEqual(rejected.returncode, 1, rejected.stderr)
        self.assertIn(RESTORE, rejected.stdout)
        self.assertIn(RESTORE_NODE, rejected.stdout)
        self.assertIn(RESTORE_BEFORE, rejected.stdout)
        self.assertIn(RESTORE_AFTER, rejected.stdout)
        accepted = self._command(OPS_CHECKOUT, OPS_REV, ACCEPTED_CI)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout.strip(), "skip-blob-precheck ok")

    def test_ops_commit_evidence_accepts_only_the_sealed_restore_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            bare = _ops_commit(repo, {RESTORE: RESTORE_SOURCE})
            blob = _git(repo, "rev-parse", f"{bare}:{RESTORE}")
            self.assertNotEqual(blob, RESTORE_BEFORE)
            self.assertNotEqual(blob, RESTORE_AFTER)
            missing = self._command(repo, bare)
            self.assertEqual(missing.returncode, 1, missing.stderr)
            self.assertIn(RESTORE_BEFORE, missing.stdout)
            self.assertIn(blob, missing.stdout)
            self.assertIsNone(SHARDS.load_ops_skip_evidence(repo, bare))

            wrong_after = _ops_commit(repo, {
                RESTORE: RESTORE_SOURCE,
                OPS_EVIDENCE: _ops_evidence(RESTORE_BEFORE, "a" * 40),
            })
            unmatched = self._command(repo, wrong_after)
            self.assertEqual(unmatched.returncode, 1, unmatched.stderr)
            self.assertIn(blob, unmatched.stdout)

            wrong_before = _ops_commit(repo, {
                RESTORE: RESTORE_SOURCE,
                OPS_EVIDENCE: _ops_evidence("b" * 40, blob),
            })
            forged = self._command(repo, wrong_before)
            self.assertEqual(forged.returncode, 2, forged.stdout)
            self.assertIn("does not succeed an admitted skip", forged.stderr)
            self.assertIn(RESTORE_NODE, forged.stderr)

            partial = _ops_commit(repo, {
                RESTORE: RESTORE_SOURCE,
                OPS_EVIDENCE: _ops_evidence(RESTORE_BEFORE, blob),
            })
            incomplete = self._command(repo, partial)
            self.assertEqual(incomplete.returncode, 1, incomplete.stderr)
            self.assertIn(blob, incomplete.stdout)

            sealed = _ops_commit(repo, {
                RESTORE: RESTORE_SOURCE,
                OPS_EVIDENCE: _restore_module_evidence(blob),
            })
            passed = self._command(repo, sealed)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(passed.stdout.strip(), "skip-blob-precheck ok")
            record = SHARDS.load_ops_skip_evidence(repo, sealed)
            self.assertGreater(len(record["updates"]), 1)
            self.assertEqual(record["updates"][RESTORE_NODE]["before_blob"], RESTORE_BEFORE)
            self.assertEqual(record["updates"][RESTORE_NODE]["after_blob"], blob)

    def test_malformed_ops_skip_evidence_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            broken = _ops_commit(repo, {OPS_EVIDENCE: "{\n"})
            failed = self._command(repo, broken)
            self.assertEqual(failed.returncode, 2, failed.stdout)
            self.assertIn("invalid ops skip evidence", failed.stderr)
            empty = _ops_commit(repo, {OPS_EVIDENCE: (
                '{"schema": 1, "updates": {}, "additions": {}}\n'
            )})
            rejected = self._command(repo, empty)
            self.assertEqual(rejected.returncode, 2, rejected.stdout)
            self.assertIn("invalid ordinary skip evidence", rejected.stderr)

    def _command(self, checkout, revision, ci_revision=None):
        command = [
            sys.executable, str(ROOT / "scripts/pytest-shards.py"), "skip-blob-precheck",
            "--ops-checkout", str(checkout), "--ops-rev", revision,
        ]
        if ci_revision:
            command.extend(["--ci-rev", ci_revision])
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


if __name__ == "__main__":
    unittest.main()
