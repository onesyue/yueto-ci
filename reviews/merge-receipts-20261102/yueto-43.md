# Retrospective independent Codex review: yueto-43

Reviewed at 2026-11-02T08:41:09.549250+00:00. Read-only `codex exec`; original transcript `/tmp/merge-receipt-evidence/additional-review.log`; prompt `/tmp/merge-receipt-evidence/additional-review-prompt.txt`. All reviews were after merge (backfilled).

Reviewed all four exact heads via `git show`. No actionable defects found.

| PR | Exact head | Verdict | Review basis |
|---|---|---|---|
| yueops-262 | `7152b72f4b98196ba9563b014bdcbf778965ca6b` | **APPROVE** | Assertions match the points-only membership UI. Watcher exemption matches its documented host-specific configuration and installation prerequisites. |
| yueto-43 | `c66811a93a544d762495d97640e7722219e85ea8` | **APPROVE** | English wording preserves the fair-use topic and explicit appeal request. Catalog digest matches the changed source. |
| yuelink-ci-34 | `470121d033d3fc8e309cd2d400585c0fba1ad8e6` | **APPROVE** | Advances the reviewed floor coherently; preserves the previous fixture byte-for-byte and updates replay coverage without weakening verifier logic. |
| yue-node-23 | `620bcaeb5e473db9205072f13f5251f5cea0a591` | **APPROVE** | Shell entry points and Go transport consistently remove repository selectors while retaining credential configuration. Regression controls cover outer-checkout corruption. |

YueLink CI source was read from the existing detached worktree at `/tmp/merge-receipt-evidence/yuelink-ci-34-checkout`.

Source-review verdicts only; no tests, signature verification, live parity checks, agents, edits, comments, commits, pushes, or deployment performed.

## Local parity evidence and exact-head limitation

Backfilled record of `yt-premerge yueto`: `/workspace/yt43-premerge.log` reports fast-check PASS and contracts FAIL (exit 1). The recorded ref is integration merge `85ac012db4efa1ad11fe74d1d760620df87f4b92`, whose parents are PR head `c66811a93a544d762495d97640e7722219e85ea8` and then-origin/master `d7f79431beef2baf04db251072bd609a5300bf1c`. `git diff d7f79431 85ac012d` contains only the two PR catalog changes. It is not a run at the exact PR head.

The retained baseline fast-check log binds the comparison to `d7f79431beef2baf04db251072bd609a5300bf1c`. Extracting sorted unique `FAIL` labels from both contracts logs produces identical sets (53 labels). This corroborates the [original merge comment](https://github.com/onesyue/yueto/pull/43#issuecomment-6572340081): pre-existing sibling-checkout drift, no new failing contract label. Identical labels do not establish passing contracts or identical underlying errors. Fast-check selected zero related tests; it passed the changed-secret scan and skipped shell/Python/test steps.

No schema-1 pass receipt is emitted: passing exact-head contract parity is unavailable. A truthful exception retains the actual integration/baseline evidence rather than asserting all-green parity.

Original-byte logs (copied into this directory):
- `yueto-43-premerge.log` from `/workspace/yt43-premerge.log`: SHA256 `5ca7e7cf3a1d3c13a626144e4a12d06cd230e98ccb4d439a1b6eb35d8add12c0`.
- `yueto-43-contracts.log` from `/tmp/yt-premerge-zobiqveg/contracts.log`: SHA256 `ac6d66f1dbcf32ea2ce59a4b65d5b2662bff323f606730d1492b0137aad83bea`.
- `yueto-43-fast-check.log` from `/tmp/yt-premerge-zobiqveg/fast-check.log`: SHA256 `34279a534b06fdd961737435541ba562814f8a46cfc5c5c20dd55521ee128ba7`.
- `yueto-43-baseline-contracts.log` from `/tmp/yt-premerge-mc3xh7fq/contracts.log`: SHA256 `496fc5de882c9f61ed36491b3f65d4cf392006582d63b0968f36bdb3582e4fce`.
- `yueto-43-baseline-fast-check.log` from `/tmp/yt-premerge-mc3xh7fq/fast-check.log`: SHA256 `3d79d591127a3cce9663c84456bf1b35a6677ca29f4a91940a390b518b9eaab7`.
