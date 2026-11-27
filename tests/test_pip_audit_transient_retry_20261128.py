"""The Ops Python audit retries a provider connection reset, never a finding.

Incident 2026-11-28 05:26 SGT: yueops ship build 46070219984 failed in
freshness-yueops because PyPI reset one pip-audit query
(ConnectionResetError 104); every downstream job cascaded and the release
refused with nothing wrong in the candidate.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops-validation-python-audit.sh"

FAKE_UV = r'''#!/bin/bash
set -euo pipefail
state="$FAKE_STATE"
if [ "$1" = export ]; then
  while [ $# -gt 0 ]; do
    if [ "$1" = --output-file ]; then echo "pkg==1.0 --hash=sha256:00" > "$2"; fi
    shift
  done
  exit 0
fi
out=""; service=""
while [ $# -gt 0 ]; do
  case "$1" in
    --output) out="$2"; shift ;;
    --vulnerability-service) service="$2"; shift ;;
  esac
  shift
done
n=$(cat "$state/$service.count" 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" > "$state/$service.count"
mode=$(cat "$state/mode")
if [ "$mode" = reset ] && [ "$service" = pypi ] && [ "$n" -eq 1 ]; then
  cat >&2 <<'TB'
Traceback (most recent call last):
  File "/x/pip_audit/_service/pypi.py", line 404, in query
    response = self.session.get(url=url, timeout=self.timeout)
requests.exceptions.ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
TB
  exit 1
fi
if [ "$mode" = vuln ]; then
  python3 -c 'import json,sys; json.dump({"dependencies":[{"name":"p%d"%i,"version":"1","vulns":[{"id":"X"}] if i==0 else []} for i in range(120)]}, open(sys.argv[1],"w"))' "$out"
  echo "Found 1 known vulnerability in 1 package" >&2
  exit 1
fi
if [ "$mode" = refused ]; then
  echo "requests.exceptions.HTTPError: 403 Client Error: Forbidden" >&2
  exit 1
fi
python3 -c 'import json,sys; json.dump({"dependencies":[{"name":"p%d"%i,"version":"1","vulns":[]} for i in range(120)]}, open(sys.argv[1],"w"))' "$out"
'''


def run(mode: str):
    tmp = tempfile.mkdtemp()
    bindir = Path(tmp, "bin"); bindir.mkdir()
    state = Path(tmp, "state"); state.mkdir()
    (state / "mode").write_text(mode)
    uv = bindir / "uv"; uv.write_text(FAKE_UV); uv.chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_STATE=str(state),
               RUNNER_TEMP=tmp, GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", OPS_ROLE="native",
               PIP_AUDIT_RETRY_FACTOR="0")
    result = subprocess.run(["bash", str(SCRIPT)], cwd=tmp, env=env, text=True,
                            capture_output=True, timeout=120, check=False)
    counts = {p.stem: int(p.read_text()) for p in state.glob("*.count")}
    return result, counts


class PipAuditTransientRetry(unittest.TestCase):
    def test_connection_reset_is_retried_and_passes(self) -> None:
        result, counts = run("reset")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(counts, {"pypi": 2, "osv": 1})
        self.assertIn("pypi: transient provider failure on attempt 1/4", result.stderr)
        self.assertIn("Traceback (most recent call last)", result.stderr)

    def test_finding_fails_on_first_attempt(self) -> None:
        result, counts = run("vuln")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(counts, {"pypi": 1})
        self.assertNotIn("transient provider failure", result.stderr)

    def test_refusal_fails_on_first_attempt(self) -> None:
        result, counts = run("refused")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(counts, {"pypi": 1})

    def test_clean_audit_passes_once_per_provider(self) -> None:
        result, counts = run("clean")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(counts, {"pypi": 1, "osv": 1})


if __name__ == "__main__":
    unittest.main()
