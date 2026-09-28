"""Execute the workflow's actual dispatch block with real jq and a recording gh."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PollDispatchBehaviorTest(unittest.TestCase):
    def run_dispatch(self, statuses, *, list_fail=False):
        workflow = (ROOT / ".github/workflows/poll-sources.yml").read_text()
        trigger = workflow.split("- name: Trigger builds", 1)[1]
        lines = trigger.split("        run: |\n", 1)[1].splitlines()
        block = []
        for line in lines:
            if line and not line.startswith("          "):
                break
            block.append(line[10:])
        script = "\n".join(block)
        self.assertIn("gh workflow run build.yml", script)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "runs.json").write_text(json.dumps([{"status": value} for value in statuses]))
            gh = base / "gh"
            gh.write_text('''#!/usr/bin/env bash
set -euo pipefail
if [ "$1 $2" = "run list" ]; then
  [ "$LIST_FAIL" = 1 ] && exit 1
  while [ "$1" != --jq ]; do shift; done
  jq -r "$2" "$RUNS"
elif [ "$1 $2" = "workflow run" ]; then
  printf '%s\\n' "$*" >> "$DISPATCHES"
else
  exit 97
fi
''')
            gh.chmod(0o755)
            log = base / "dispatches"
            result = subprocess.run(["bash", "-c", script], text=True, capture_output=True,
                                    timeout=10, env={**os.environ,
                                        "PATH": f"{base}:{os.environ['PATH']}",
                                        "RUNS": str(base / "runs.json"),
                                        "DISPATCHES": str(log), "LIST_FAIL": str(int(list_fail)),
                                        "GITHUB_REPOSITORY": "onesyue/yueto-ci",
                                        "PENDING": json.dumps([{"group": "yue-node", "sha": "a" * 40}])})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return log.read_text().splitlines() if log.exists() else []

    def test_every_active_status_defers_without_dispatch(self):
        for status in ("in_progress", "queued", "pending", "waiting", "requested"):
            with self.subTest(status=status):
                self.assertEqual(self.run_dispatch(["completed", status]), [])

    def test_completed_or_empty_history_dispatches_once_without_promotion(self):
        for statuses in (["completed"], []):
            with self.subTest(statuses=statuses):
                self.assertEqual(self.run_dispatch(statuses), [
                    f"workflow run build.yml -R onesyue/yueto-ci -f service=yue-node -f ref={'a' * 40} -f promote=false"
                ])

    def test_unreadable_history_defers_without_dispatch(self):
        self.assertEqual(self.run_dispatch([], list_fail=True), [])
