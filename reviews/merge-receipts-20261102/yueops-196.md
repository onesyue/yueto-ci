# Historical merge evidence — yueops #196

- PR: https://github.com/onesyue/yueops/pull/196
- Merged PR head: `a6e59a88ec4b69bd8c8091372a223ff618d8502d`
- Merge commit (not the evidence head): `5e83a9ea5277bf87da7fa121e6abde2a87e8e924`
- Merged at: 2026-11-02T09:28:22Z
- GitHub REST head verification: 2026-11-02T10:00:16.456513+00:00
- Disposition: **registered exception; no passing receipt**

The supplied verdict head exactly matches the merged PR head. The original review, verdict and parity log are retained byte-for-byte:

- [yueops-196.review.txt](yueops-196.review.txt)
- [yueops-196.verdict.json](yueops-196.verdict.json)
- [yueops-196.parity.log](yueops-196.parity.log)

Parity SHA256 verified against the supplied verdict: `c154bf8d34761300a6402e17b11328e7c0e7748a117e6b68720190175b72632e`.

Historical independent Codex review found no introduced defects at merged head a6e59a88ec4b69bd8c8091372a223ff618d8502d; source verdict head matches GitHub REST. Exact-head yt-premerge failed: ops-ci=4 and ops-native=4 (central CI pin 17ad41f7 mismatch), admission-precheck=2 (missing required CLI arguments). Source records baseline-identical failures; full CI suites were not reached. READY was conditional on a baseline exception, not passing parity. Missing evidence: passing local CI parity. Original parity log SHA256 c154bf8d34761300a6402e17b11328e7c0e7748a117e6b68720190175b72632e. See reviews/merge-receipts-20261102/yueops-196.md.

The original verdict describes the PR as open at evidence collection time; GitHub now confirms it merged. Baseline-equivalence statements are historical source assertions, not a fresh rerun. No review or execution timestamp has been invented, and targeted tests are not substituted for failed CI gates.

Head/merge metadata: [yueops-196.metadata.json](yueops-196.metadata.json).
