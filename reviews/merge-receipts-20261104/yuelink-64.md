# yuelink PR64 exact-head acceptance evidence

Head `041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8`. Original raw log: `.claude/state/c3-consumer/20261104/run1/module-linux.log`. Copied bytes and SHA-256 are unchanged; run time is the original log modification time.

Host and Linux each147 passed with2 unchanged platform-specific skips, explicitly not passed; required C3 cases zero skips. Native hook5204 passed with8 existing skips. Actual Dart consumer and loopback TLS/HTTP boundary only; no running mihomo or same-IP DNS acceptance. DNS companion remains pending.

Independent review:

```json
{
  "verdict": "APPROVE",
  "reviewer": "root/link independent reviewer",
  "reviewed_at": "2026-11-04T05:11:07.628438+00:00",
  "scope": "Exact signed two-file C3 source delta; prior scoped approval retained. Release/integration gates remain coordinator-owned.",
  "base": "bb034c504e01eecd9777f992edd892958787927f",
  "files": {
    "lib/core/tun/desktop_tun_supervisor.dart": "3881fa6e4243dd8971822ebe06fe8c05723bd85d70b8ce12876dfd75c07f2b2a",
    "test/services/desktop_tun_egress_consumer_test.dart": "114a46637fcbac3b8465cb457a17559941aaa8c067a45b473e7121b06e0bef1c"
  },
  "findings": [],
  "checks": [
    "The optional egressNow constructor injection defaults to the DateTime.now tear-off; only existing egress cadence sampling calls it. Other timing, restart and repair logic is unchanged.",
    "Test calls real DesktopTunDiagnostics.proxyEgressReachable through real DesktopTunSupervisor.checkEgressHealth; proxy fixture performs actual CONNECT and TLS with matching hostname and synthetic CA, without bad-certificate bypass.",
    "First target fails while second returns real TLS204; ten-second clock advance proves cadence suppression. Both targets then fail over threshold, yielding running/degraded; recovery clears the owned degraded mark.",
    "Useful HTTP responses are exchanged before and after each supervisor check on one retained peer TCP port. Actual CoreActions.restart provider boundary is spied and remains zero; controller requests must be GET /yuelink/proxies only. Selection context and selected line remain unchanged.",
    "The local fixture proves the Dart consumer boundary, not a running mihomo process or real native socket/DNS cache retention. It does not claim A-to-B-to-A switch testing or same-IP DNS lookup refresh.",
    "All fixture resources have teardown and the scenario has a15-second timeout. No external destination is dialed; trusted test certificate uses only local TLS origin."
  ],
  "gate_observation": {
    "host": "Existing log ends147 passed /2 skipped",
    "linux": "Existing log ends147 passed /2 skipped",
    "status": "Required C3 consumer and cross-platform cases passed on host/Linux with zero required skips. Two unchanged platform-specific privilege tests are unsupported on these runners and remain UNKNOWN, not passed.",
    "skip_disposition": {
      "path": ".claude/state/c3-consumer/20261104/run1/skip-disposition.json",
      "sha256": "e08752a4f598917d50e4fc0cc142b28fc13ea73bd1aa488762596c40c807355a",
      "reviewed_at": "2026-11-04T05:12:43.259259+00:00",
      "parent_file_identity_verified": true,
      "windows_and_mobile_execution": "UNKNOWN"
    }
  },
  "dns_companion": "UNKNOWN: no integrated post-refresh lookup evidence; retained separately as required by contract.",
  "tests_rerun": false,
  "head": "041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8",
  "tree": "046c8a5c496ca3882b34cb0a14ee4b44095570d8",
  "bound_at": "2026-11-04T05:17:48.200547+00:00",
  "binding": "Signed candidate matches both previously approved file hashes and only those two paths differ from base. No source re-review or test rerun. Writer reports native hook5204 passed and8 existing skips; host/Linux147 passed and2 existing unsupported-platform skips each. This candidate is not part of the first164 source bb034c5."
}
```

Supplemental original receipt:

```json
{
  "base": "bb034c504e01eecd9777f992edd892958787927f",
  "source": "source-hashes.json",
  "targeted": {
    "exit": 0,
    "passed": 1,
    "log": "consumer-host-r2.log"
  },
  "initial_fixture_failure": {
    "log": "consumer-host.log",
    "reason": "Test expected retired /proxies instead of actual /yuelink/proxies; corrected exact path, not broadened matcher"
  },
  "module_host": {
    "exit": 0,
    "passed": 147,
    "skips_not_passed": 2,
    "log": "module-host.log"
  },
  "module_linux": {
    "exit": 0,
    "passed": 147,
    "skips_not_passed": 2,
    "log": "module-linux.log",
    "platform": "linux/amd64",
    "timezone": "UTC",
    "sdk": "Flutter3.47.8/Dart3.13.7",
    "image": "sha256:cf320c534782414c6e047c7d79b7c3a1f31433c5e4774c5889d43df525030e48"
  },
  "skipped_cases": [
    "Windows-only privilege diagnostic",
    "mobile-only privilege contract"
  ],
  "required_c3_cases_skipped": 0,
  "analysis": "pinned CLI and scoped MCP clear",
  "format": "two explicit paths unchanged",
  "companion_dns": "UNKNOWN: no integrated actual subsequent core lookup evidence; no flush-spy substitution",
  "native_hook": {
    "exit": 0,
    "passed": 5204,
    "existing_skips_not_passed": 8,
    "log": "commit.log",
    "analysis_format_security_architecture": "pass"
  },
  "independent_review": {
    "path": "/Users/j/Projects/yueto/.claude/state/link-takeover/20261104/1039/c3-consumer-source-review.json",
    "verdict": "APPROVE",
    "files_match": true,
    "gate_skip_disposition": "reviewed and accepted; Windows/mobile remain UNKNOWN"
  },
  "candidate": {
    "head": "041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8",
    "signature": "G",
    "worktree": "clean",
    "review_binding": "review-binding.json"
  },
  "delivery": {
    "pr": "https://github.com/onesyue/yuelink/pull/64",
    "draft": true,
    "base": "codex/cn01-joint-20261104",
    "branch": "codex/c3-consumer-20261104",
    "remote_head": "041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8",
    "push_exit": 0,
    "jobs": "none",
    "locks": "none",
    "published": false,
    "source": "frozen"
  }
}
```
