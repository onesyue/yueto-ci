"""I32-E R4/R7: execute real retry helpers with failing external commands."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/ci-retry.sh"


class CiRetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.env = {
            **os.environ,
            "PATH": f"{self.base}:{os.environ['PATH']}",
            "CALLS": str(self.base / "calls"),
            "SLEEPS": str(self.base / "sleeps"),
            "TOKENS": str(self.base / "tokens"),
            "ERROR": "TLS handshake timeout",
            "SUCCEED_AT": "99",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-request",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.invalid/?fixture=1",
        }
        self.shim("sleep", 'echo "$*" >> "$SLEEPS"\n')
        self.shim("cosign", '''
echo "$*" >> "$CALLS"
n=$(wc -l < "$CALLS")
if [ "$n" -ge "$SUCCEED_AT" ]; then echo verified; exit 0; fi
echo partial-output
echo "$ERROR" >&2
exit 23
''')
        self.shim("curl", '''
case "$*" in
  *oidc.invalid*)
    echo token >> "$TOKENS"
    if [ -n "${TOKEN_ERROR:-}" ]; then echo "$TOKEN_ERROR" >&2; exit 22; fi
    n=$(wc -l < "$TOKENS" | tr -d ' ')
    printf '{"value":"fixture-token-%s"}\\n' "$n"
    exit 0;;
esac
echo "$*" >> "$CALLS"
n=$(wc -l < "$CALLS")
if [ "$n" -ge "$SUCCEED_AT" ]; then echo downloaded; exit 0; fi
echo "$ERROR" >&2
exit 22
''')

    def shim(self, name, body):
        path = self.base / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def run_helper(self, command, **env):
        for name in ("calls", "sleeps", "tokens"):
            (self.base / name).unlink(missing_ok=True)
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; ' + command,
             "fixture", str(HELPER)],
            env={**self.env, **env}, capture_output=True, text=True, timeout=15,
        )

    def lines(self, name):
        path = self.base / name
        return path.read_text().splitlines() if path.exists() else []

    def test_refusals_and_unknown_errors_fail_on_first_attempt(self):
        for error in (
            "certificate identity does not match expected identity",
            "invalid signature", "attestation rejected",
            "no matching signatures: verification failed",
            "unknown failure", "HTTP 403 Forbidden: TLS handshake timeout",
            "invalid signature\nHTTP 503 Service Unavailable",
            "attestation denied\nTLS handshake timeout",
            "none of the expected identities matched\nHTTP 503",
            "x509: certificate signed by unknown authority",
        ):
            for command in ("keyless_cosign sign image", "keyless_cosign attest image",
                            "verify_cosign verify image", "verify_cosign verify-attestation image"):
                with self.subTest(error=error, command=command):
                    result = self.run_helper(command, ERROR=error)
                    self.assertEqual(result.returncode, 23, result.stderr)
                    self.assertEqual(len(self.lines("calls")), 1)
                    self.assertEqual(self.lines("sleeps"), [])
                    self.assertEqual(result.stdout, "")

    def test_transport_exhaustion_preserves_six_attempts_and_five_sleeps(self):
        for error in ("TLS handshake timeout", "HTTP 503 Service Unavailable",
                      "rekor unavailable", "connection reset by peer", "MANIFEST_UNKNOWN"):
            for command in ("keyless_cosign sign image", "keyless_cosign attest image",
                            "verify_cosign verify image",
                            "verify_cosign verify-attestation --type cyclonedx image",
                            "verify_cosign verify-attestation --type spdxjson image"):
                with self.subTest(error=error, command=command):
                    result = self.run_helper(command, ERROR=error)
                    self.assertEqual(result.returncode, 23, result.stderr)
                    self.assertEqual(len(self.lines("calls")), 6)
                    self.assertEqual(len(self.lines("sleeps")), 5)
                    self.assertEqual(result.stdout, "")

    def test_success_on_first_or_last_attempt_has_no_trailing_sleep(self):
        for attempt in (1, 6):
            with self.subTest(attempt=attempt):
                result = self.run_helper("verify_cosign verify image", SUCCEED_AT=str(attempt))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "verified\n")
                self.assertEqual(len(self.lines("calls")), attempt)
                self.assertEqual(len(self.lines("sleeps")), attempt - 1)

    def test_eventual_success_uses_fresh_tokens_and_only_successful_stdout(self):
        result = self.run_helper("keyless_cosign sign image", SUCCEED_AT="3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "verified\n")
        self.assertEqual(len(self.lines("tokens")), 3)
        self.assertEqual(len(self.lines("sleeps")), 2)
        for index, call in enumerate(self.lines("calls"), 1):
            self.assertIn(f"--identity-token fixture-token-{index}", call)

    def test_oidc_refusal_stops_before_cosign_and_transport_is_bounded(self):
        for error, count in (("curl: (22) HTTP 403", 1), ("TLS handshake timeout", 6)):
            with self.subTest(error=error):
                result = self.run_helper("keyless_cosign sign image", TOKEN_ERROR=error)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.lines("tokens")), count)
                self.assertEqual(len(self.lines("sleeps")), count - 1)
                self.assertEqual(self.lines("calls"), [])

    def test_download_4xx_including_curl_transient_defaults_never_retry(self):
        for status in (400, 401, 403, 404, 408, 429):
            with self.subTest(status=status):
                result = self.run_helper("ci_download 4 --fail https://fixture.invalid",
                                         ERROR=f"curl: (22) The requested URL returned error: {status}")
                self.assertEqual(result.returncode, 22)
                self.assertEqual(len(self.lines("calls")), 1)
                self.assertIn("--retry 0", self.lines("calls")[0])
                self.assertEqual(self.lines("sleeps"), [])

    def test_download_limits_and_eventual_success(self):
        for attempts in (4, 5):
            for succeeds in (False, True):
                with self.subTest(attempts=attempts, succeeds=succeeds):
                    result = self.run_helper(
                        f"ci_download {attempts} --fail https://fixture.invalid",
                        ERROR="curl: (22) The requested URL returned error: 503",
                        SUCCEED_AT=str(attempts if succeeds else 99),
                    )
                    self.assertEqual(result.returncode, 0 if succeeds else 22)
                    self.assertEqual(len(self.lines("calls")), attempts)
                    self.assertEqual(len(self.lines("sleeps")), attempts - 1)

    def test_download_callers_use_helper_and_retain_checksum_gates(self):
        for name in ("install-verified-buildx.sh", "install-verified-trivy.sh", "freeze-build-plan.sh"):
            source = (ROOT / "scripts" / name).read_text()
            self.assertIn('/ci-retry.sh"', source)
            self.assertIn("ci_download 4 --fail", source)
            self.assertNotIn("--retry", source)
            if name.startswith("install-"):
                self.assertIn("sha256sum --check --strict", source)
        policy = (ROOT / ".github/workflows/policy-ci.yml").read_text()
        self.assertIn("source scripts/ci-retry.sh", policy)
        self.assertIn("ci_download 5 --fail", policy)
        self.assertIn("sha256sum --check --strict", policy)
        self.assertNotIn("--retry-all-errors", policy)

    def test_actionlint_bad_digest_stops_before_extraction(self):
        policy = (ROOT / ".github/workflows/policy-ci.yml").read_text()
        body = policy.split("      - name: Install pinned actionlint\n", 1)[1]
        body = body.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
        body = "\n".join(line[10:] for line in body.splitlines())
        self.shim("curl", '''
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then echo corrupt > "$2"; exit 0; fi
  shift
done
exit 97
''')
        self.shim("tar", 'echo unexpected-extraction >> "$CALLS"; exit 97\n')
        result = subprocess.run(["bash", "-c", body], cwd=ROOT,
                                env={**self.env, "RUNNER_TEMP": str(self.base),
                                     "ACTIONLINT_VERSION": "fixture",
                                     "ACTIONLINT_ARCHIVE_SHA256": "0" * 64},
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertEqual(self.lines("calls"), [])
