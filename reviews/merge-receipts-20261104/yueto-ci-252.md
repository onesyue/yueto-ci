# yueto-ci PR 252 exact-source evidence

Source: `f05a7b9e6a8039e86ca638cd333b63fe8932bd5c`. Independent review is reproduced below. Original parity log: `.claude/state/board-takeover/20261104/resume-1039/ci-linux-final/tests.log`.

```json
{
  "reviewer": "/root/board",
  "reviewed_at": "2026-11-04T03:19:27.784341+00:00",
  "verdict": "APPROVE",
  "scope": "Independent source review of all five changed files; not final execution/merge/release acceptance",
  "base": "74e02c811223de58233cd1cdb281789513930a90",
  "head": "f05a7b9e6a8039e86ca638cd333b63fe8932bd5c",
  "diff_sha256": "b2a339a148dd27e07cdbd5cf58fface596448e89a54160c00fc169f884cdeddd",
  "findings": [],
  "checks": [
    "Final Board pin is 6e3454932469f81ded1bc96ec764ef8c21839be9 in native contract and policy assertion; floor153 unchanged",
    "Template DSN registered in both workflow phases with unchanged hosted/manual-local boundary",
    "All five DSNs required and constrained to identical loopback disposable yueboard_test database",
    "CAS expected_sha256 source capability requires admin integration package; old source compatibility does not waive discovered suites",
    "Existing discovery and execution verifier rejects missing suites, skips, non-execution and failed package completion",
    "New tests exercise missing admin package rejection, recovered execution and legitimate pre-CAS source",
    "Local runner URL occurrence assertion updated exactly13 to15 for two new template DSNs; no weakening of opt-in policy"
  ],
  "evidence": [
    "ci248-hosted-failure.log: both new CAS policy tests pass at727; stale count failure repaired in final source",
    "Coordinator reports85 build-policy tests pass atf05a7b9; full696 host/Linux with actual Ops checkout pending",
    "final-pin-converge.log uses measured production Boardf710; mixed Node versions correctly omitted from single-value argument"
  ],
  "remaining_acceptance": [
    "Complete full mandatory policy/native validation with real Ops checkout and required Linux perspective; do not count prior skip as pass",
    "Bind final native receipt to this exact SHA and fresh validation evidence; independent source approval does not itself authorize production deployment"
  ]
}
```

Linux execution receipt:
```json
{
  "owner": "/root/board",
  "finished_at": "2026-11-04T03:34:20.434151+00:00",
  "source_sha": "f05a7b9e6a8039e86ca638cd333b63fe8932bd5c",
  "ops_source_sha": "b94b4f50be7e71231a57b0800cc4941830e24ab1",
  "image": "sha256:ee698ffafd0f02befc8b1350046f7c661001d0552dba5207e980022fdc6b0257",
  "platform": "linux/arm64",
  "user": 1001,
  "timezone": "UTC",
  "memory_limit": "4GiB",
  "cpu_limit": 2,
  "suite_timeout_seconds": 1500,
  "tests": 696,
  "failed": 0,
  "skipped": 0,
  "duration_seconds": 449.223,
  "tests_exit_code": 0,
  "lint_exit_code": 0,
  "checks": [
    "full unittest discovery",
    "compileall scripts/tests",
    "bash -n scripts/*.sh",
    "shellcheck --severity=warning scripts/*.sh",
    "actionlint1.7.12 .github/workflows/*.yml"
  ],
  "source_object_check": "PASS with actual Git history from readonly Ops common directory",
  "environment_note": "Initial fresh pip setup failed before tests because requirements-policy PyYAML wheel hash excludes ARM64. Complete successful run reused existing native lens venv, originally installed with frozen uv export and require-hashes; all six policy dependency versions verified equal. No hashes or source requirements changed. This proves Linux policy execution, not fresh hosted amd64 dependency installation.",
  "process_note": "Initial shell paused to prevent duplicate suite after slow container download. Tests and lint executed once via docker exec; after both exit0 this lane stopped its owned container. No active jobs remain.",
  "artifacts": {
    "tests.log": "2bb5586ece3c3549584a03e6e148a1ad9140972f5ce8b369e2b25d735c72dcaa",
    "lint.log": "455a141e60dad7062f00a5a694237f1b6da00a55283d20da0bea8869138f0bed",
    "setup-hash-failure.log": "c153b1817e0538823240f68890950299dd7e5b7189d83275a896cf009d7ffa81",
    "run-r2.sh": "8e53dade4da9b476a59d26fadc9c5afe015b79edcd0f9d8c3f09206730d3f58c",
    "checksums-host.txt": "433028cf0ba3c42163ea1a668dedce30fcdbe84fe912b1a5e288c006eab8a4f5",
    "actionlint-host.tar.gz": "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6"
  },
  "retention": "Keep logs and receipt as acceptance evidence; isolated clones are reproducible scratch and not source candidates."
}

```
Host full execution had one GNU-versus-Darwin checksum-output failure; all nine affected module tests passed with the GNU tools used by CI. The complete Linux run passed all 696 tests with no skips.
