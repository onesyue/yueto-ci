"""poll-sources self-rearm (2026-09-28): real-shell behaviour of scripts/poll-rearm.sh
plus the workflow wiring that keeps it inert, bounded and away from signing.

GitHub has delayed or dropped scheduled runs since 2026-08-26 (this repo went from
34 poll rounds/day to 2-6). The rearm job waits in the `poll-rearm` environment's
wait timer (no runner held) and re-dispatches poll-sources. The failure modes that
matter are all "the chain runs away": a missing wait timer turning it into a tight
loop, and kicks/schedules multiplying chains. Each is exercised here against a fake
`gh` that records what the script would have dispatched.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "poll-rearm.sh"
POLL = ROOT / ".github" / "workflows" / "poll-sources.yml"

FAKE_GH = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail
    printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
    if [ "$1 $2" = "run list" ]; then
      [ "${FAKE_GH_LIST_FAIL:-0}" = 1 ] && exit 1
      cat "$FAKE_GH_RUNS"
      exit 0
    fi
    if [ "$1 $2" = "workflow run" ]; then
      exit 0
    fi
    echo "unexpected gh call: $*" >&2
    exit 97
    """
)


class PollRearmScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = self.base / "gh.log"
        self.runs = self.base / "runs.json"
        self.path = f"{bin_dir}:{os.environ['PATH']}"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_script(self, *, runs, run_id="200", started=1000, now=2300,
                   list_fail=False, min_delay=None) -> subprocess.CompletedProcess:
        self.runs.write_text(json.dumps(runs))
        env = {
            "PATH": self.path,
            "HOME": str(self.base),
            "FAKE_GH_LOG": str(self.log),
            "FAKE_GH_RUNS": str(self.runs),
            "FAKE_GH_LIST_FAIL": "1" if list_fail else "0",
            "GITHUB_REPOSITORY": "onesyue/yueto-ci",
            "GITHUB_RUN_ID": run_id,
            "POLL_STARTED_EPOCH": str(started),
            "POLL_REARM_NOW": str(now),
        }
        if min_delay is not None:
            env["POLL_REARM_MIN_DELAY_S"] = str(min_delay)
        return subprocess.run(["bash", str(SCRIPT)], env=env,
                              capture_output=True, text=True, timeout=60)

    def dispatched(self) -> list[str]:
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text().splitlines() if l.startswith("workflow run")]

    def test_newest_run_after_the_wait_dispatches_exactly_one_poll(self) -> None:
        result = self.run_script(runs=[
            {"databaseId": 200, "status": "in_progress", "conclusion": ""},
            {"databaseId": 150, "status": "completed", "conclusion": "success"},
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.dispatched(), [
            "workflow run poll-sources.yml -R onesyue/yueto-ci --ref master -f dry_run=false"
        ])

    def test_missing_wait_timer_is_refused_before_any_gh_call(self) -> None:
        # 120 s after poll start = the environment released the job immediately.
        result = self.run_script(runs=[{"databaseId": 200, "conclusion": ""}], now=1120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wait timer", result.stdout)
        self.assertEqual(self.dispatched(), [])
        self.assertFalse(self.log.exists(), "must not even list runs before the delay gate")

    def test_delay_boundary_is_inclusive(self) -> None:
        ok = self.run_script(runs=[{"databaseId": 200, "conclusion": ""}], now=1900)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.log.unlink()
        short = self.run_script(runs=[{"databaseId": 200, "conclusion": ""}], now=1899)
        self.assertNotEqual(short.returncode, 0)
        self.assertEqual(self.dispatched(), [])

    def test_an_older_chain_stops_when_a_newer_run_exists(self) -> None:
        result = self.run_script(runs=[
            {"databaseId": 310, "status": "queued", "conclusion": ""},
            {"databaseId": 200, "status": "in_progress", "conclusion": ""},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("newer run 310 owns the chain", result.stdout)
        self.assertEqual(self.dispatched(), [])

    def test_cancelled_and_skipped_newer_runs_do_not_steal_the_chain(self) -> None:
        result = self.run_script(runs=[
            {"databaseId": 330, "status": "completed", "conclusion": "cancelled"},
            {"databaseId": 320, "status": "completed", "conclusion": "skipped"},
            {"databaseId": 200, "status": "in_progress", "conclusion": ""},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.dispatched()), 1)

    def test_unreadable_run_list_stops_the_chain_loudly(self) -> None:
        for kwargs in ({"list_fail": True}, {}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()} or {"case": "empty"}):
                if self.log.exists():
                    self.log.unlink()
                result = self.run_script(runs=[], **kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.dispatched(), [])

    def test_non_numeric_inputs_fail_closed(self) -> None:
        for kwargs in ({"run_id": "abc"}, {"started": "x"}, {"min_delay": "-5"}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                if self.log.exists():
                    self.log.unlink()
                result = self.run_script(runs=[{"databaseId": 200, "conclusion": ""}], **kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.dispatched(), [])


def _job(text: str, name: str) -> str:
    start = text.index(f"\n  {name}:\n")
    nxt = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start + 1:])
    return text[start: start + 1 + nxt.start()] if nxt else text[start:]


class PollRearmWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.poll = POLL.read_text(encoding="utf-8")
        cls.rearm = _job(cls.poll, "rearm")
        cls.poll_job = _job(cls.poll, "poll")

    def test_rearm_is_opt_in_master_only_and_behind_the_environment(self) -> None:
        for fragment in (
            "needs: poll",
            "vars.YUETO_CI_POLL_REARM == 'true'",
            "github.ref == 'refs/heads/master'",
            "needs.poll.result != 'cancelled'",
            "inputs.dry_run != true",
            "environment: poll-rearm",
            "run: bash scripts/poll-rearm.sh",
            "POLL_STARTED_EPOCH: ${{ needs.poll.outputs.started_epoch }}",
            "GH_TOKEN: ${{ github.token }}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.rearm)

    def test_rearm_holds_no_registry_signing_or_source_credential(self) -> None:
        code = "\n".join(l for l in self.rearm.splitlines() if not l.lstrip().startswith("#"))
        for forbidden in ("secrets.", "packages:", "id-token", "attestations",
                          "build.yml", "promote", "cosign", "YUETO_CI_PAT"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)
        perms = self.rearm.split("permissions:\n", 1)[1].split("    steps:", 1)[0]
        self.assertEqual(
            sorted(l.strip() for l in perms.splitlines() if l.strip()),
            ["actions: write", "contents: read"],
        )

    def test_poll_concurrency_is_job_scoped_so_kicks_are_not_delayed(self) -> None:
        self.assertIn("    concurrency:\n      group: poll-sources\n      cancel-in-progress: false",
                      self.poll_job)
        header = self.poll.split("\njobs:\n", 1)[0]
        self.assertNotIn("\nconcurrency:", header)
        self.assertNotIn("concurrency:", self.rearm)
        # The start stamp is the first step so it exists even if a later step fails.
        steps = self.poll_job.split("    steps:\n", 1)[1]
        self.assertTrue(steps.lstrip().startswith("- name: Record poll start"))

    def test_script_only_ever_dispatches_poll_sources(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
        self.assertEqual(re.findall(r"gh workflow run (\S+)", code), ["poll-sources.yml"])
        self.assertNotIn("promote", code)


if __name__ == "__main__":
    unittest.main()
