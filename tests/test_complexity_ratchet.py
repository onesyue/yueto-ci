import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "complexity-ratchet.py"
SPEC = importlib.util.spec_from_file_location("complexity_ratchet", SCRIPT)
ratchet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ratchet
SPEC.loader.exec_module(ratchet)


def function(ccn, nloc=10, fingerprint="original"):
    return ratchet.Function({"ccn": ccn, "nloc": nloc}, fingerprint)


class ComplexityRatchetTests(unittest.TestCase):
    def setUp(self):
        self.dead = {"go": 3, "python": 2}
        self.baseline = {
            "functions": {"legacy": function(40, 220).metrics},
            "dead_code": self.dead.copy(),
        }

    def test_new_function_over_either_limit_fails(self):
        for measured in (function(31), function(1, 201)):
            with self.subTest(measured=measured):
                self.assertEqual(
                    len(
                        ratchet.compare({"new": measured}, {}, self.dead, self.baseline)
                    ),
                    1,
                )
        self.assertEqual(
            ratchet.compare({"new": function(30, 200)}, {}, self.dead, self.baseline),
            [],
        )

    def test_changed_function_with_same_metrics_fails_and_untouched_passes(self):
        previous = {"existing": function(31)}
        self.assertEqual(
            ratchet.compare(previous, previous, self.dead, self.baseline), []
        )
        changed = {"existing": function(31, fingerprint="edited")}
        self.assertEqual(
            len(ratchet.compare(changed, previous, self.dead, self.baseline)), 1
        )

    def test_baselined_function_shrink_passes_and_reduces_budget(self):
        current = {"legacy": function(39, 210)}
        self.assertEqual(ratchet.compare(current, {}, self.dead, self.baseline), [])
        updated = ratchet.shrink(current, {"go": 2, "python": 1}, self.baseline)
        self.assertEqual(
            updated,
            {
                "functions": {"legacy": current["legacy"].metrics},
                "dead_code": {"go": 2, "python": 1},
            },
        )

    def test_baselined_function_growth_fails_even_when_other_metric_shrinks(self):
        for measured in (function(41, 200), function(39, 221)):
            with self.subTest(measured=measured):
                current = {"legacy": measured}
                self.assertEqual(
                    len(ratchet.compare(current, {}, self.dead, self.baseline)), 1
                )

    def test_dead_code_growth_fails_independently_for_each_language(self):
        for language in self.dead:
            with self.subTest(language=language):
                counts = self.dead | {language: self.dead[language] + 1}
                self.assertEqual(len(ratchet.compare({}, {}, counts, self.baseline)), 1)
                self.assertEqual(
                    ratchet.shrink({}, counts, self.baseline)["dead_code"], self.dead
                )

    def test_update_drops_resolved_entries_and_never_adds_or_expands_budgets(self):
        self.baseline["functions"]["deleted"] = function(50).metrics
        current = {"legacy": function(42, 215), "new": function(31)}
        self.assertEqual(
            ratchet.shrink(current, self.dead, self.baseline)["functions"],
            {"legacy": function(40, 215).metrics},
        )
        self.assertEqual(
            ratchet.shrink({"legacy": function(30, 200)}, self.dead, self.baseline)[
                "functions"
            ],
            {},
        )

    def test_invalid_baseline_is_a_scan_error(self):
        with self.assertRaises(ValueError):
            ratchet.validate_baseline('{"functions": {}, "dead_code": {"go": 0}}')


if __name__ == "__main__":
    unittest.main()
