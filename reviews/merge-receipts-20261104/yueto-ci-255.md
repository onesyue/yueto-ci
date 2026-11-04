# yueto-ci PR255 final exact-head evidence

Current head `6407488db38bbc94f0fa58ef5dc1330d5fc40252`. Current copied log is byte-identical to `.claude/state/takeover/20261104/resume-1039/ops557-pin-linux/full.log`. Prior candidate logs and reviews remain in predecessor commits; the current receipt binds only this head.

The final557 pointer passed its own full Linux696 suite with zero skips, plus32 complete directly affected cases with actual Git history, native admission and all compile/bash/ShellCheck/actionlint stages. These final results were obtained after the source review with identical reviewed JSON bytes. Prior361/0fcf evidence remains historical and is not relabeled. Ops full host/Linux execution and production acceptance remain separate.

Independent review:

```json
{
  "reviewer": "/root/board",
  "reviewed_at": "2026-11-04T05:48:12.172511+00:00",
  "decision": "APPROVE_SOURCE",
  "head": "6407488db38bbc94f0fa58ef5dc1330d5fc40252",
  "signature": "G",
  "ops_head": "557588e6c09cbeb41289ba772ce7e617473ebadf",
  "ops_signature": "G",
  "diff_sha256": "de17a6d5322ffc2e4c3f10c028c300783889882110d50a528a4dc0edf6d35b51",
  "finding": "Only source_revision0fcf to signed descendant557 changes. Remaining parsed JSON, including all module/shared blobs, cases and sealing data, is identical. Tested affected-complete JSON hash matches exact committed file.",
  "validation": "Existing native actual557 precheck ACCEPTED; four complete affected Linux modules32pass0skip (10+9+7+6), with real Git history. No reviewer rerun.",
  "broad_suite": "PENDING on6407488. Previous361696pass is historical evidence, not640 full pass.",
  "ops_review": "ops-pruner-pin-review.json"
}
```

Current verification receipt:

```json
{
  "owner": "01a1a469-81cc-75f3-baa3-7394a3901519",
  "finished_at": "2026-11-04T05:52:09.061824+00:00",
  "source_base": "361c7b1669ae136af9178b814344197c5daa52ad",
  "source_file_sha256": "d9e69ceecaba95150f2cf5f965d210ca54f7d15a47285e1c2f3e567e37959768",
  "ops_source": "557588e6c09cbeb41289ba772ce7e617473ebadf",
  "native_precheck": "ACCEPTED actual source on host and Linux",
  "linux": {
    "passed": 696,
    "skipped": 0,
    "failed": 0,
    "exit_code": 0,
    "seconds": 330.974,
    "image": "sha256:ee698ffafd0f02befc8b1350046f7c661001d0552dba5207e980022fdc6b0257",
    "user": 1001,
    "cpus": 2,
    "memory": "4GiB",
    "timezone": "UTC",
    "command": "python3 -m unittest discover -s tests -p test_*.py -v",
    "log": "ops557-pin-linux/full.log",
    "log_sha256": "74d4002b107bb59b474e519279eefdef684b74b3beff16bc3791118afc3efd02",
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
    "first_linux": "read-only/source-PATH/history lens was unsuitable; timeout124; original log preserved",
    "previous_pin": "361c7b1 admitted0fcf and passed696; current640/557 separately passed own696, not relabeled"
  },
  "scope": "Static policy/source admission only; pending Ops full execution and production release are not claimed",
  "head": "6407488db38bbc94f0fa58ef5dc1330d5fc40252",
  "extra_affected_modules": {
    "passed": 32,
    "skipped": 0,
    "actual_git_history": true
  }
}
```
