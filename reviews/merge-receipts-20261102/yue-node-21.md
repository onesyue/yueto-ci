Independent Codex re-review — verdict: APPROVE

Independently reviewed the complete diff against `origin/master` at HEAD `500bff05c5df11f992131b2b7873ed9f5b9e2237` (base `080a877d9d9afb0ffb1b9d27f1d9c5747be56be1`), after reading the prior review and “Review fixes” comment. The PR head matches this checkout.

1. **Resolved — transitive test-only dependencies.** Discovery now uses `go list -deps -test -json`, merges test variants through `ForTest`, normalizes synthetic dependency names, and retains ordinary packages as vet/test targets. Missing discovery targets fail closed. The real temporary-module regressions passed for internal and external indirect test imports in both HY2 and VLESS; they check consumer selection and prove that mutating the indirect dependency reaches the failing consumer test.

2. **Resolved — annotated/signed tag pushes.** The hook resolves each non-deletion object with `^{commit}` before comparing it with HEAD. Real annotated and SSH-signed tag positive controls passed. Mixed-ref pushes containing an older commit are rejected in either order before gates execute, and a tag targeting a blob is rejected clearly. Dirty-tree and deletion controls also passed.

3. **No new blocking findings.** Reviewed all four changed files, including selection, failure propagation, hook behavior and documented scope. No existing ratchet is relaxed and no private Actions are introduced. The optional hook and local short tests are correctly described as limited evidence rather than server-side merge protection or release approval.

Validation independently rerun successfully:
- `bash scripts/premerge.sh origin/master`: all 10 runner tests; mandatory vet, fork-ledger and script guard tests; vulnerability-wrapper regressions; proto digest check; profile dependency boundaries; all five signed fork tags; selected vet and short tests for both profiles (`./scripts`).
- `GOWORK=off GOFLAGS=-mod=vendor GOMAXPROCS=2 go test -race -p=1 -count=1 ./scripts ./internal/forkledger`.
- `bash -n scripts/premerge.sh scripts/git-hooks/pre-push` and `git diff --check origin/master`.

Limits: canonical sibling checkout is absent, so proto verification used the documented digest-only mode. Full release gauntlet, full repository test suites, and macOS/Bash 3 execution were not run. Repository files remain unchanged; no commit or push was performed.

VERDICT: APPROVE


Receipt provenance: https://github.com/onesyue/yue-node/pull/21#issuecomment-6570991449

Original command-output transcript: `/workspace/gates/rv/rr-yue-node.log`; SHA256 `4f8cd7ab23161bda1b480f391aa750395e3ce892e96d8b0e0c23049a22573da6`. The transcript includes the review, head verification and actual test output. The parity time is the completion bound supplied by the posted review. Full transcript retained locally; not republished. This receipt preserves the validation limits above and does not assert full component CI.
