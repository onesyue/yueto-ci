# YueOps PR #372 review

Reviewed at: 2026-11-04T21:26:04Z

Base: `d91a87f73b3aa20a0320b92252b8ee9be1f01743`

Head / supplied merge commit: `7bc341567c9d04f81104657a5a88420d3dab9628`

DONE — Review verdict: **approve**. Scoped head/base parity: **pass**.

The supplied diff exactly matches local base..head and deletes only docs/audits/2026-09-05-provisioning-tuning-boundary.md (35 lines). I read the deleted document: it records the historical private staging and package-verification closure, not an executable configuration or rollback procedure. The deletion does not remove the provisioning implementation, package manifest, runtime gate, tests or rollback switch. A tracked-tree search for the document stem has no inbound references at either base or head, so no tracked link was found to break. The historic text remains recoverable from the base commit.

The repository's relevant provisioning private-stage suite runs unchanged at both revisions: **39 passed** at head and **39 passed** at base, with no skips. It uses local fixture bytes and fake SSH, with no server access. Exact-diff binding and whitespace checks pass. No separate Markdown content remains to lint in this deletion; git diff --check and the inbound-reference check cover its document validation. No runtime/schema/protected feature change is present. Archive-table candidates: none. Restoring the one document from the base is sufficient to reverse the reviewed PR; this lane only writes receipt artifacts.

## Exact evidence

Environment: macOS arm64, Python 3.13.15, pytest 9.1.1, SQLGlot 28.0.0 from an existing local cache; TZ=UTC, four xdist workers. Service credentials are not inherited. No dependencies were installed.

- **head**: exit 0; `reviews/merge-receipts-20261105/yueops-372-head.log`; SHA-256 `8b86e355c3e84ea9c406fe6637c8d3ae827302737092d4844701f219ed19b10c`.
  Command: `cd /tmp/rc-372 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_provision_tuning_private_stage_20260905.py`
- **base**: exit 0; `reviews/merge-receipts-20261105/yueops-372-base.log`; SHA-256 `bb882f72081061ae5b624c6b12399df83ef4de46fb1fb5dccfc10e34a1d55867`.
  Command: `cd /tmp/rc-371 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_provision_tuning_private_stage_20260905.py`
- **binding**: exit 0; `reviews/merge-receipts-20261105/yueops-372-binding.log`; SHA-256 `43bedbb20f900a6677389a046cfa4f0ba45c26e9ff77c44993bde6efe61b4d5f`.
  Command: `cd /tmp/rc-372 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python /Users/j/codex-runs/1104c/rcpt-bind.py 372`
- **head-doc-check**: exit 0; `reviews/merge-receipts-20261105/yueops-372-head-doc-check.log`; SHA-256 `a19876b895a4f70710be4f9e862836ff651ca2ad1fb04c7ef35ff19e865eb388`.
  Command: `cd /tmp/rc-372 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python /Users/j/codex-runs/1104c/rcpt-doc-check.py`
- **base-doc-check**: exit 0; `reviews/merge-receipts-20261105/yueops-372-base-doc-check.log`; SHA-256 `9b9803b3e7b1345b03231f344205c25caae848b5105ac1e5c300d4114de13dd6`.
  Command: `cd /tmp/rc-371 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python /Users/j/codex-runs/1104c/rcpt-doc-check.py`

Combined parity log: `reviews/merge-receipts-20261105/yueops-372-parity.log`; SHA-256 `cafe3cf74965997d1279c9833492703c817075a242a8966f065612903f48a66a`.

## Receipt boundary

Written offline using exactly the field layout of merge-receipts/yueops/370.json, not scripts/write-merge-receipt.py: that writer requires GitHub API access and accepts only approve/pass. No network attempt was made. Metadata provides headRefOid/baseRefOid/mergeCommit but no mergedAt; mergeCommit equals head and local ancestry/diff binding passed. `backfilled=true` denotes this explicitly retrospective review; the GitHub merge timestamp and the audit's 24-hour eligibility window remain UNKNOWN. No timestamp was backdated. Evidence is intentionally uncommitted at owner request, so normal committed-evidence merge-hygiene acceptance is not asserted. An UNKNOWN receipt is a factual non-approval record for parity and is intentionally not admissible as a green merge receipt.
