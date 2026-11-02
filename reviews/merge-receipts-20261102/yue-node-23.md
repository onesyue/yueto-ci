# Retrospective independent Codex review: yue-node-23

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

Local parity ran on a detached checkout at the exact PR head. Command: `GOMAXPROCS=2 bash scripts/premerge.sh HEAD^ && GOMAXPROCS=2 GOFLAGS="-mod=vendor -p=1" go test ./internal/gateretry -count=1`. Started 2026-11-02T08:43:37.838712+00:00; exit 0. Original output, including any suite skips and scope limits, is committed as `yue-node-23.log`. This is local repository gate evidence, not hosted release or deployment verification.

The first invocation failed in `TestVerifyForkTagsRetryAndVerification/digest_failure`: its expected fixture call-count file was missing, although the unexpected-commit rejection occurred. The unchanged exact-head retry passed the full command. Initial output is retained in `yue-node-23-initial-failed.log`; no root cause or fix is claimed. The passing run verified all five signed fork tags, profile dependency boundaries, 12 runner controls, mandatory guards, both affected HY2/VLESS package sets and the direct gateretry suite. Proto sync was digest-only because the canonical sibling checkout was absent; this is not a cross-repository release gate.
