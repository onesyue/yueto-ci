"""Exercise the real historical admission alongside a sealed estate successor."""
import copy
import hashlib
import importlib.util
import json
import os
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("estate_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class EstateInputTransition(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
        self.baseline, _ = SHARDS.reviewed_estate_input_transition(self.baseline)
        self.common = dict(self.baseline["common_inputs"])
        for key in (
            "reviewed_shared_input_transition", "reviewed_python_input_transition",
            "reviewed_frontend_security_transition", "reviewed_miniapp_security_transition",
            "reviewed_w85_input_transition", "reviewed_w85_observability_transition",
            "reviewed_audit_dependency_transition", "reviewed_zod_lock_transition",
            "reviewed_scanner_input_transition",
        ):
            record = self.baseline[key]
            if "path" in record:
                self.common[record["path"]] = record["after_blob"]
            for path, change in record.get("changes", {}).items():
                self.common[path] = change["after_blob"]
        modes = self.baseline["reviewed_shared_input_transition"]["common_input_modes"]
        self.files = {p: (modes[p], b) for p, b in self.common.items()}
        self.record = {
            "schema": 1,
            "prior_baseline_sha256": SHARDS.sha(
                (json.dumps(self.baseline, indent=2, ensure_ascii=False) + "\n").encode()),
            "source_before": self.baseline["reviewed_scanner_input_transition"]["source_after"],
            "source_after": "b" * 40,
            # Test identities only; never copied into the production baseline.
            **{k: hashlib.sha256(("fixture:" + k).encode()).hexdigest() for k in (
                "independent_review_sha256", "source_freeze_sha256", "qualification_receipt_sha256")},
            "changes": {p: {"before_blob": self.common.get(p),
                            "after_blob": hashlib.sha1(("fixture:" + p).encode()).hexdigest(),
                            "mode": "100644"} for p in SHARDS.ESTATE_INPUT_PATHS},
        }
        self.successor = self.common | {p: c["after_blob"] for p, c in self.record["changes"].items()}
        self.successor_files = self.files | {
            p: ("100644", c["after_blob"]) for p, c in self.record["changes"].items()}
        self.sealed = self.baseline | {"reviewed_estate_input_transition": self.record}

    def admit(self, baseline=None, common=None, files=None, source: str | None = "b" * 40):
        SHARDS.admit_shared_inputs(
            self.sealed if baseline is None else baseline,
            self.successor if common is None else common,
            self.successor_files if files is None else files, source_revision=source)

    def test_historical_and_successor_admission(self):
        SHARDS.admit_shared_inputs(self.baseline, self.common, self.files)
        SHARDS.admit_shared_inputs(self.sealed, self.common, self.files)
        self.admit()
        SHARDS.admit_shared_inputs(self.sealed, self.successor, source_revision="b" * 40)
        self.assertNotIn("reviewed_estate_input_transition", self.baseline)

    def test_activated_baseline_reaches_all_three_admission_consumers(self):
        # Keep policy identity and admission real; substitute only source discovery.
        policy = SHARDS.git(ROOT, "rev-parse", "HEAD").decode().strip()
        identity = {"policy_revision": policy, "run_id": "42", "run_attempt": "1"}
        board = "a" * 40
        source = self.record["source_after"]
        planned = SHARDS.seal({
            "schema": 1, "kind": "ops-pytest-module-plan", "source_revision": source,
            "context": identity | {"board_revision": board, "runner_os": "Linux",
                                    "runner_arch": "X64", "runner_image": "controlled-image"},
            "pytest_ini_sha256": "a" * 64, "entry_sha256": "b" * 64,
            "recorder_sha256": "c" * 64, "modules": {"tests/test_control.py": "d" * 64},
            "assignments": [{"id": "ordinary-000", "modules": ["tests/test_control.py"]}],
        }, "plan_sha256")
        target = {"validation": "yueops", "repo": "onesyue/yueops", "ref": source}
        env = {"GITHUB_SHA": policy, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": "onesyue/yueto-ci", "RUNNER_OS": "Linux",
               "RUNNER_ARCH": "X64", "ImageVersion": "controlled-image"}
        session = {"execution_context": self.baseline["context"], "collection_skips": {},
                   "junit_sha256": "b" * 64, "nonpassing_outcomes": []}
        result = {"reference": session | {"assignment_id": "reference"},
                  "shards": [session | {"assignment_id": "ordinary-000"}]}
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = Path(directory) / "activated.json"
            baseline_path.write_text(json.dumps(self.sealed, indent=2) + "\n")
            with (patch.object(SHARDS, "SKIP_BASELINE", str(baseline_path)),
                  patch.dict(os.environ, env),
                  patch.object(SHARDS, "plan", return_value=planned),
                  patch.object(SHARDS, "serial_modules", return_value=[]),
                  patch.object(SHARDS, "shared_inputs", return_value=self.successor),
                  patch.object(SHARDS, "tree_inputs", return_value=self.successor_files | {
                      "tests/test_control.py": ("100644", "e" * 40)})):
                value = SHARDS.expand({"matrix": [target], "validation_matrix": [target]},
                                      ROOT, board, "ubuntu-24.04", 3, 1)
                SHARDS.envelope(value)
                self.assertEqual(SHARDS.admit_skips(value, result, {})["status"], "NO_NEW_SKIPS")
                for mutation in ("source", "blob"):
                    changed = copy.deepcopy(value)
                    if mutation == "source":
                        changed["source_revision"] = "f" * 40
                    else:
                        changed["common_inputs"]["qa/package.json"] = "f" * 40
                    changed.pop("admission_sha256")
                    SHARDS.seal(changed, "admission_sha256")
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        SHARDS.envelope(changed)
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        SHARDS.admit_skips(changed, result, {})
                damaged = copy.deepcopy(self.sealed)
                damaged["reviewed_estate_input_transition"]["prior_baseline_sha256"] = "f" * 64
                baseline_path.write_text(json.dumps(damaged, indent=2) + "\n")
                with self.assertRaises(ValueError):
                    SHARDS.admit_skips(value, result, {})

    def test_unsealed_or_wrong_source_refuses(self):
        with self.assertRaises(ValueError):
            self.admit(baseline=self.baseline)
        for source in (None, "c" * 40, self.record["source_before"]):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.admit(source=source)

    def test_every_successor_blob_and_mode_is_bound(self):
        for path in SHARDS.ESTATE_INPUT_PATHS:
            with self.subTest(path=path, drift="blob"), self.assertRaises(ValueError):
                self.admit(common=self.successor | {path: "d" * 40})
            with self.subTest(path=path, drift="mode"), self.assertRaises(ValueError):
                self.admit(files=self.successor_files | {path: ("100755", self.successor[path])})

    def test_extra_helper_and_unchanged_input_drift_refuse(self):
        for path in ("tests/unreviewed_helper.py", "pytest.ini"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.admit(common=self.successor | {path: "e" * 40},
                           files=self.successor_files | {path: ("100644", "e" * 40)})

    def test_review_history_preimages_and_scope_cannot_be_relaxed(self):
        mutations = [
            lambda b, r: r.update(schema=True),
            lambda b, r: r.update(independent_review_sha256="PENDING"),
            lambda b, r: r.update(qualification_receipt_sha256="0" * 64),
            lambda b, r: r.update(source_freeze_sha256=""),
            lambda b, r: r.update(source_before="a" * 40),
            lambda b, r: r.update(prior_baseline_sha256="0" * 64),
            lambda b, r: b.update(source_revision="a" * 40),
            lambda b, r: r["changes"].pop("qa/package.json"),
            lambda b, r: r["changes"].update({"tests/extra.py": {
                "before_blob": None, "after_blob": "a" * 40, "mode": "100644"}}),
            lambda b, r: r["changes"]["qa/package.json"].update(before_blob="a" * 40),
            lambda b, r: r["changes"][SHARDS.ESTATE_ADDED_INPUT].update(before_blob="a" * 40),
        ]
        for index, mutate in enumerate(mutations):
            baseline = copy.deepcopy(self.sealed)
            mutate(baseline, baseline["reviewed_estate_input_transition"])
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.admit(baseline=baseline)


if __name__ == "__main__":
    unittest.main()
