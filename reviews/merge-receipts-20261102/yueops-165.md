# Historical merge evidence — yueops #165

- PR: https://github.com/onesyue/yueops/pull/165
- Merged PR head: `9fadc37bf965af3efae322a33559b73656b5c9ef`
- Merge commit (not the evidence head): `76db75f90ec3a04a7070a9ed5a4d6b65cfbc59bf`
- Merged at: 2026-11-02T09:22:48Z
- GitHub REST head verification: 2026-11-02T10:00:16.456513+00:00
- Disposition: **registered exception; no passing receipt**

The supplied verdict head exactly matches the merged PR head. The original review, verdict and parity log are retained byte-for-byte:

- [yueops-165.review.txt](yueops-165.review.txt)
- [yueops-165.verdict.json](yueops-165.verdict.json)
- [yueops-165.parity.log](yueops-165.parity.log)

Parity SHA256 verified against the supplied verdict: `af0e96a42b7ff5b9d074a794077a5ab3bf0b3336b756830e86f96b44094cc87f`.

Historical independent Codex review found no introduced defects at merged head 9fadc37bf965af3efae322a33559b73656b5c9ef; source verdict head matches GitHub REST. Exact-head yt-premerge failed: ops-ci=4 and ops-native=4 (central CI pin 17ad41f7 mismatch), admission-precheck=2 (missing required CLI arguments). Source records baseline-identical failures; full CI suites were not reached. READY was conditional on a baseline exception, not passing parity. Missing evidence: passing local CI parity. Original parity log SHA256 af0e96a42b7ff5b9d074a794077a5ab3bf0b3336b756830e86f96b44094cc87f. See reviews/merge-receipts-20261102/yueops-165.md.

The original verdict describes the PR as open at evidence collection time; GitHub now confirms it merged. Baseline-equivalence statements are historical source assertions, not a fresh rerun. No review or execution timestamp has been invented, and targeted tests are not substituted for failed CI gates.

Head/merge metadata: [yueops-165.metadata.json](yueops-165.metadata.json).
