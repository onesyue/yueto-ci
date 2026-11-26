"""The weekly scan deadman fails only when success is missing or too old."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import weekly_scan_deadman as deadman  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "weekly-scan-deadman.yml"
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def _run(created: datetime, conclusion: str = "success") -> dict[str, str]:
    return {"conclusion": conclusion, "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ")}


class WeeklyScanDeadmanTest(unittest.TestCase):
    def test_window_is_eight_days(self) -> None:
        self.assertEqual(deadman.WEEKLY_SCAN_SUCCESS_MAX_AGE, timedelta(days=8))

    def test_success_inside_the_window_passes(self) -> None:
        ok, detail = deadman.evaluate(
            [_run(NOW - timedelta(days=7, hours=23))],
            NOW,
        )
        self.assertTrue(ok, detail)

    def test_success_older_than_the_window_fails(self) -> None:
        ok, detail = deadman.evaluate([_run(NOW - timedelta(days=8, seconds=1))], NOW)
        self.assertFalse(ok)
        self.assertIn("outside 8 days", detail)

    def test_failures_do_not_count_as_success(self) -> None:
        ok, detail = deadman.evaluate(
            [_run(NOW - timedelta(hours=1), conclusion="failure")],
            NOW,
        )
        self.assertFalse(ok)
        self.assertIn("no successful run", detail)

    def test_cli_reads_the_run_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.json"
            path.write_text(
                json.dumps([_run(NOW - timedelta(days=1))]),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "weekly_scan_deadman.py"),
                    "--runs",
                    str(path),
                    "--now",
                    NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("last succeeded", result.stdout)

    def test_workflow_is_a_read_only_scheduled_alert(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn("cron: '17 4 * * *'", text)
        self.assertIn("permissions:\n  contents: read\n  actions: read", code)
        self.assertIn("runs-on: ubuntu-24.04", code)
        self.assertIn("scripts/weekly_scan_deadman.py", code)
        self.assertIn("weekly-vuln-sbom.yml/runs?status=success", code)
        self.assertIn("::error::Weekly scan deadman did not complete successfully.", code)
        self.assertNotIn("packages: write", code)
        self.assertNotIn("id-token: write", code)
        self.assertNotIn("secrets.", code)
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            code,
        )


if __name__ == "__main__":
    unittest.main()
