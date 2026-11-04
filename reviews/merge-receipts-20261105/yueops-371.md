# YueOps PR #371 review

Reviewed at: 2026-11-04T21:26:04Z

Base: `72bf60474359d831f0cee70a6246ebf50952ea26`

Head / supplied merge commit: `d91a87f73b3aa20a0320b92252b8ee9be1f01743`

DONE_WITH_CONCERNS — Review verdict: **approve** for the static code/declaration changes. Required broader parity: **UNKNOWN**; do not treat this receipt as a release approval.

The supplied diff exactly matches local base..head. I reviewed both grant changes against their consumers: help_sync._upsert UPDATE predicates read source_slug/content/title/active/status, its INSERT column list matches the new declaration, and save_web_transcript reads channel/user_id/session_type/messages in its NOT EXISTS condition. The added support_threads INSERT columns match that consumer. The web reader enumerates current ai_feedback columns because support.py's ranking CTE reads SELECT *. Grants remain role- and column-scoped; they add no DDL, DELETE, broad table privilege or privilege for app_checkin. Existing sequence/default/inheritance behavior is not proved by this static review.

The policy loader adds the new declaration only for app_yue_bot. Manifest changes retain scope/limitations and update source positions, content hashes and explicit historical gaps. I verified app_checkin's grant collection is byte-for-byte equivalent as JSON data between base and head. The English client-import wording changes “update it” to “refresh the subscription”; this keeps the current stable-client guidance while avoiding the broad pre-existing SQL scanner's false UPDATE-on-table-it detection. The base reproduction confirms that exact false positive. No parser bypass or check-in baseline expansion was added.

Head: **172 passed, 29 skipped, 281 xfailed**. Base: **164 passed, 6 failed, 29 skipped, 271 xfailed, 2 errors**. The failures/errors removed at head are the web-reader ref_key coverage, unresolved support requirements, checkin 'it' false positive, companion service gap ratchets and generated-manifest fixture failures. Expected failures represent documented historical grant gaps; the changed expected-failure count is not additional passing coverage. The tested offline behavior has no observed regression, and Ruff passes.

No blocking code defect was identified. However, this PR changes SQL privileges: actual statements under runtime roles, Linux/CI-equivalent verification and production readback were not performed or authorized in this networkless task. Docker is unavailable. The receipt therefore records parity UNKNOWN despite the successful head test command. It cannot prove live permissions or eliminate the declared skipped/expected-failure gaps. The new SQL explicitly says it has not been applied; applying it remains a separate authorized operation.

Protected scope: no check-in ledger/reward grants, money rules, games, Emby, authentication, anti-GFW behavior, backups or rollback code changed. Manifest fingerprints mention protected files but do not change their implementations. No protected repair was attempted. No table removal or destructive migration; archive-table candidates: none.

## Exact evidence

Environment: macOS arm64, Python 3.13.15, pytest 9.1.1, SQLGlot 28.0.0 from an existing local cache; TZ=UTC, four xdist workers. Service credentials are not inherited. No dependencies were installed.

- **lint**: exit 0; `reviews/merge-receipts-20261105/yueops-371-lint.log`; SHA-256 `52f46ee9d40350c75b443ed515dd26fe820e89fff5c4121b83deea117fc9995a`.
  Command: `cd /tmp/rc-371 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m ruff check tests/test_service_role_grants_20261102.py telegram-bot/yue/knowledge/current_rules.py`
- **head**: exit 0; `reviews/merge-receipts-20261105/yueops-371-head.log`; SHA-256 `f4b5a00e911cc3101ccab6e0e9d09a488ce68b8c71eb19e24e3922ff60593d1d`.
  Command: `cd /tmp/rc-371 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_service_role_grants_20261102.py tests/test_service_grant_dependencies_20261102.py tests/test_role_grant_manifest_generated.py tests/test_ai_quality_round2_20261105.py tests/test_ai_quality_p015_20261101.py tests/test_yueboard_chat_transcript.py`
- **binding**: exit 0; `reviews/merge-receipts-20261105/yueops-371-binding.log`; SHA-256 `d565fd549c2e6ea57bfbae5214a17e9b334cf096845b7649c172727f68de5b94`.
  Command: `cd /tmp/rc-371 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python /Users/j/codex-runs/1104c/rcpt-bind.py 371`
- **base**: exit 1; `reviews/merge-receipts-20261105/yueops-371-base.log`; SHA-256 `c3b5f5c989e2225e3f89c047a5d1c6d336115a5764b0906f8465fcc19aafacdc`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_service_role_grants_20261102.py tests/test_service_grant_dependencies_20261102.py tests/test_role_grant_manifest_generated.py tests/test_ai_quality_round2_20261105.py tests/test_ai_quality_p015_20261101.py tests/test_yueboard_chat_transcript.py`

Combined parity log: `reviews/merge-receipts-20261105/yueops-371-parity.log`; SHA-256 `f1af0ee908b3a4184c3e96f0f85bc445c812a40f213e07e937ac1226bd83df76`.

## Receipt boundary

Written offline using exactly the field layout of merge-receipts/yueops/370.json, not scripts/write-merge-receipt.py: that writer requires GitHub API access and accepts only approve/pass. No network attempt was made. Metadata provides headRefOid/baseRefOid/mergeCommit but no mergedAt; mergeCommit equals head and local ancestry/diff binding passed. `backfilled=true` denotes this explicitly retrospective review; the GitHub merge timestamp and the audit's 24-hour eligibility window remain UNKNOWN. No timestamp was backdated. Evidence is intentionally uncommitted at owner request, so normal committed-evidence merge-hygiene acceptance is not asserted. An UNKNOWN receipt is a factual non-approval record for parity and is intentionally not admissible as a green merge receipt.
