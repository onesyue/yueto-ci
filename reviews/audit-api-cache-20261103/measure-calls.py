"""Compare baseline and candidate against identical offline HTTP fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cache_tests", ROOT / "tests/test_merge_hygiene_cache.py")
assert spec is not None and spec.loader is not None
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
baseline_ref = sys.argv[1] if len(sys.argv) > 1 else "5a551afd3cd86dc0d783726253d6e2c81927e869"
source = subprocess.run(["git", "show", baseline_ref + ":scripts/merge-hygiene-audit.py"],
                        cwd=ROOT, capture_output=True, text=True, check=True).stdout
baseline = types.ModuleType("baseline")
baseline.__file__ = str(ROOT / "scripts/merge-hygiene-audit.py")
exec(compile(source, baseline.__file__, "exec"), baseline.__dict__)

results = []
for repo in ("yueops", "yueto-ci"):
    for count in (1, 100):
        case = fixtures.MergeCache()
        case.setUp()
        try:
            case.fixture["reviews"] = []
            case.pulls = {1: [case.pr | {"number": 1000 + i} for i in range(count)]}
            if count == 100:
                case.pulls[2] = [case.pr | {"merged_at": "2026-10-01T00:00:00Z",
                                          "updated_at": "2026-10-01T00:00:00Z"}] * 100

            def legacy_http(command, **kwargs):
                result = case.http(command + ["--include"], **kwargs)
                result.stdout = result.stdout.split("\r\n\r\n", 1)[1]
                return result

            def legacy_rows():
                with patch.object(baseline.subprocess, "run", side_effect=legacy_http), patch.object(
                        baseline, "receipt", return_value=None):
                    return baseline.audit("onesyue", [repo], case.cutoff, {}, case.now)

            expected = legacy_rows()
            before = len(case.requests)
            case.requests.clear()
            assert legacy_rows() == expected
            before_warm = len(case.requests)
            case.requests.clear()
            assert case.audit_rows(repo) == expected
            cold = len(case.requests)
            case.requests.clear()
            case.conditional = True
            assert case.audit_rows(repo) == expected
            results.append({"repo": repo, "merged_prs": count, "before": before,
                            "before_rerun": before_warm, "after_cold": cold,
                            "after_rerun": len(case.requests), "rerun_304": case.not_modified,
                            "rerun_charged": len(case.requests) - case.not_modified,
                            "verdicts_equal": True})
        finally:
            case.doCleanups()
print(json.dumps({"baseline": baseline_ref, "network_calls": 0, "fixtures": results}, indent=2))
