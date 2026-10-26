"""Exercise the real historical admission alongside a sealed estate successor."""
import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("estate_shards", ROOT / "scripts/pytest-shards.py")
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class EstateInputTransition(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / "ops-pytest-skip-baseline.json").read_text())
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
