# Historical merge evidence — yueops #257

- PR: https://github.com/onesyue/yueops/pull/257
- Merged PR head: `063b4016d425436d2067e1f572788d09b336191d`
- Merge commit (not the evidence head): `e3fd24382709965a0c52bc535cd46dc04b837137`
- Merged at: 2026-11-02T09:20:55Z
- GitHub REST head verification: 2026-11-02T10:00:16.456513+00:00
- Disposition: **registered exception; no passing receipt**

The supplied verdict head exactly matches the merged PR head. The original review, verdict and parity log are retained byte-for-byte:

- [yueops-257.review.txt](yueops-257.review.txt)
- [yueops-257.verdict.json](yueops-257.verdict.json)
- [yueops-257.parity.log](yueops-257.parity.log)

Parity SHA256 verified against the supplied verdict: `f9b19da87e5b4daf0d73fffbca4922cae9b3042ac60d94e8ceb4b257c8943258`.

Historical independent Codex review found no introduced defects at merged head 063b4016d425436d2067e1f572788d09b336191d; source verdict head matches GitHub REST. Exact-head yt-premerge failed: ops-ci=4 and ops-native=4 (central CI pin 17ad41f7 mismatch), admission-precheck=2 (missing required CLI arguments). Source records baseline-identical failures; full CI suites were not reached. READY was conditional on a baseline exception, not passing parity. Missing evidence: passing local CI parity. Original parity log SHA256 f9b19da87e5b4daf0d73fffbca4922cae9b3042ac60d94e8ceb4b257c8943258. See reviews/merge-receipts-20261102/yueops-257.md.

The original verdict describes the PR as open at evidence collection time; GitHub now confirms it merged. Baseline-equivalence statements are historical source assertions, not a fresh rerun. No review or execution timestamp has been invented, and targeted tests are not substituted for failed CI gates.

Head/merge metadata: [yueops-257.metadata.json](yueops-257.metadata.json).
