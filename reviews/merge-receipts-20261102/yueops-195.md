# Historical merge evidence — yueops #195

- PR: https://github.com/onesyue/yueops/pull/195
- Merged PR head: `de93e49d0a502e75fdd2649eb44da1b42dd4d226`
- Merge commit (not the evidence head): `15d9c6fb10202d97b704adb299796e5e3acd92b4`
- Merged at: 2026-11-02T09:28:17Z
- GitHub REST head verification: 2026-11-02T10:00:16.456513+00:00
- Disposition: **registered exception; no passing receipt**

The supplied verdict head exactly matches the merged PR head. The original review, verdict and parity log are retained byte-for-byte:

- [yueops-195.review.txt](yueops-195.review.txt)
- [yueops-195.verdict.json](yueops-195.verdict.json)
- [yueops-195.parity.log](yueops-195.parity.log)

Parity SHA256 verified against the supplied verdict: `ac5fda31094683c62ac49db1ba305a1f8cfe7a680727fe23595cbd746d109258`.

Historical independent Codex review found no introduced defects at merged head de93e49d0a502e75fdd2649eb44da1b42dd4d226; source verdict head matches GitHub REST. Exact-head yt-premerge failed: ops-ci=4 and ops-native=4 (central CI pin 17ad41f7 mismatch), admission-precheck=2 (missing required CLI arguments). Source records baseline-identical failures; full CI suites were not reached. READY was conditional on a baseline exception, not passing parity. Missing evidence: passing local CI parity. Original parity log SHA256 ac5fda31094683c62ac49db1ba305a1f8cfe7a680727fe23595cbd746d109258. See reviews/merge-receipts-20261102/yueops-195.md.

The original verdict describes the PR as open at evidence collection time; GitHub now confirms it merged. Baseline-equivalence statements are historical source assertions, not a fresh rerun. No review or execution timestamp has been invented, and targeted tests are not substituted for failed CI gates.

Head/merge metadata: [yueops-195.metadata.json](yueops-195.metadata.json).
