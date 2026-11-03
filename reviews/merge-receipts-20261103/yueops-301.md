# Pre-merge evidence — yueops #301 @ 1f0c2adb56876e18dee7d3aea0bd97c04cda8390

Status: PRE-MERGE evidence only. This file is not a schema-1 merge-hygiene receipt and does not establish merge readiness.

PARITY: NOT pass.

## Withdrawn pass claim

The previous head `8bf68a13d563eb85f35521f54081fcc8c9754563` committed `merge-receipts/yueops/301.json` with `parity.result` `pass` and `log_sha256` `05db2780d6deef23ced0de229ee497fc01db6aa3a7735f109340183e6b98efc0`. That pass claim is withdrawn. Schema 1 allows only `parity.result` `pass` and has no no-regression result, so this tree has no `merge-receipts/yueops/301.json`.

The receipt also recorded `ran_at` `2026-11-03T04:13:46Z`. That timestamp is not in the log, so it is not restated as a run time.

## Review artifact

`reviews/merge-receipts-20261103/yueops-301-review.txt` is the same bytes as on `8bf68a13d563eb85f35521f54081fcc8c9754563`. SHA256 `a22f3e46851bc8aa582f2800c86274ea13f4e4cc4c3ebdf457e77f26aba80cc3` (1023 bytes).

The artifact's first line names `yueops #301 @1f0c2adb56876e18dee7d3aea0bd97c04cda8390`. Its last line is `VERDICT: approve @1f0c2adb5`. That line is the text of the committed artifact. This note is not a new APPROVE.

`gh api repos/onesyue/yueops/pulls/301` returned HTTP 404 on 2026-11-03. The live pull request head, merge state, and an independent re-review were not read from `onesyue/yueops`. The artifact's prose about 28 targeted cases is not the pytest transcript below and is not a parity result.

## Parity log

`reviews/merge-receipts-20261103/yueops-301.log` is the same 161919 bytes as `parity-logs/20261103/yueops-301.log` on `8bf68a13d563eb85f35521f54081fcc8c9754563`. SHA256 `05db2780d6deef23ced0de229ee497fc01db6aa3a7735f109340183e6b98efc0`. The path is under `reviews/merge-receipts-20261103/` so the tree stays on the evidence paths. The bytes were not edited. This move is not a new run.

The log header is `## yueops #301 parity (box): targeted pytest at head 1f0c2adb5 vs base 8b8d38401, same command`. The HEAD section names `head=1f0c2adb56876e18dee7d3aea0bd97c04cda8390`.

Read from that log in this checkout:

- HEAD short summary: `25 failed, 546 passed, 4 skipped, 2 warnings, 28 errors in 19.22s`
- BASE short summary: `25 failed, 546 passed, 4 skipped, 2 warnings, 28 errors in 19.25s`
- The short-summary `FAILED` and `ERROR` lines in the HEAD and BASE sections are the same 53 lines, in the same order. That match is a comparison of those lines. It is not a pass.
- Admission line: `base==head 8b8d38401: ADMISSION_ACCEPTED; head 1f0c2adb5: REJECTED 'PR shared-input successor requires the signed release pin' (no shared-input paths changed; needs pin successor at ship time)`

`8b8d38401` is the prefix written in the log. This checkout did not resolve it in `onesyue/yueops`.

## Companion

[yueto-ci #185](https://github.com/onesyue/yueto-ci/pull/185) was open at head `bee330db4ad5de6d68b4c0e2311fd506f30bbfd3` when read on 2026-11-03. Its description calls itself the companion to yueops #301. This file does not merge yueops #301, does not merge #185, and does not record an Ops ship.
