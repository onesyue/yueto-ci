# yueto-ci PR255 exact-head acceptance evidence

Head `361c7b1669ae136af9178b814344197c5daa52ad`. Original raw log: `.claude/state/takeover/20261104/resume-1039/ops-pin-linux-r2/full.log`. Copied bytes and SHA-256 are unchanged; run time is the original log modification time.

Complete Linux policy696 passed, zero skipped; real source admission and compile/bash/ShellCheck/actionlint exit0. Prior host failure/skip and unsuitable Linux timeout remain retained, never counted as pass. Pending Ops full execution and production acceptance are separate.

Independent review:

```json
{
  "reviewer": "/root/board",
  "reviewed_at": "2026-11-04T05:13:49.314309+00:00",
  "decision": "APPROVE",
  "base": "05c6b56b7fba084129a7f2f933011c6041807c1a",
  "diff_sha256": "c702c93a8fcb3524b98b6948f91ac4fd6e3359c6ad0b71bfa36c855721cdece4",
  "changed_path": "ops-first-native-successors.json",
  "changed_field": "source_revision",
  "before": "80f7c8e6589c68eefa88aff25cad2e1f55e17350",
  "after": "0fcf40c70dc819208e138d1263975008e9bcb78c",
  "checks": [
    "Parsed JSON excluding source_revision is exactly equal: cases, module pins, shared blobs and sealing data unchanged.",
    "Old pinned source is an ancestor of signed0fcf; final0fcf and immediate production predecessor5d5 have valid G signatures.",
    "Existing public-admission-deltas.json reports empty required/module deltas; existing native precheck logs ADMISSION_ACCEPTED.",
    "The independently reviewed two-file test delta at0fcf retains75 native obligations and existing signed-root negative controls."
  ],
  "test_status": {
    "linux_correct_harness_r2": "696 passed, 0 skipped, 0 failed; exit0; actual precheck ACCEPTED; compileall/bash/shellcheck/actionlint passed. Reused coordinator verification receipt.",
    "linux_initial_readonly_harness": "Failed timeout124, retained",
    "host": "696 run: one failure and one skip, not green"
  },
  "tests_run_by_reviewer": false,
  "scope_limit": "Exact signed source and existing Linux validation bound; no production/full Ops execution claim.",
  "signed_head": "361c7b1669ae136af9178b814344197c5daa52ad",
  "signature": "G",
  "bound_at": "2026-11-04T05:22:43.378265+00:00",
  "verification_receipt": ".claude/state/takeover/20261104/resume-1039/ops-final-pin-verification.json",
  "verification_sha256": "3ed936b91b75ec75a3675a293b1d6116cc7b92e6e7b3e05bd2cc8382d964a68e"
}
```

Supplemental original receipt:

```json
{
  "owner": "01a1a469-81cc-75f3-baa3-7394a3901519",
  "finished_at": "2026-11-04T05:20:36.651653+00:00",
  "source_base": "05c6b56b7fba084129a7f2f933011c6041807c1a",
  "source_file_sha256": "c99b0733b664a4b7d8d3f6b328956e664484faf7f9645be9cdfb5690201f3fa1",
  "ops_source": "0fcf40c70dc819208e138d1263975008e9bcb78c",
  "native_precheck": "ACCEPTED actual source on host and Linux",
  "linux": {
    "passed": 696,
    "skipped": 0,
    "failed": 0,
    "exit_code": 0,
    "seconds": 438.23,
    "image": "sha256:ee698ffafd0f02befc8b1350046f7c661001d0552dba5207e980022fdc6b0257",
    "user": 1001,
    "cpus": 2,
    "memory": "4GiB",
    "timezone": "UTC",
    "command": "python3 -m unittest discover -s tests -p test_*.py -v",
    "log": "ops-pin-linux-r2/full.log",
    "log_sha256": "0294935dde2f74031a385403a1808579c923812aa17a47e0611f9e051a785434",
    "checks": [
      "actual admission-precheck",
      "complete unittest discovery",
      "compileall scripts/tests",
      "bash syntax all scripts",
      "shellcheck warning severity",
      "actionlint1.7.12 all workflows"
    ]
  },
  "retained_predecessors": {
    "host": "696 run,1 actionlint stdout assertion failure,1 missing actual Git-history skip; not accepted as pass",
    "first_linux": "read-only/source-PATH/history lens was unsuitable; timeout124; original log preserved"
  },
  "scope": "Static policy/source admission only; pending Ops full execution and production release are not claimed"
}
```
