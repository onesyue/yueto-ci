# YueOps PR #360 review

Reviewed at: 2026-11-04T21:26:04Z

Base: `fd8f334ab332eb2cf3143d676e6a98e889ac0f87`

Head / supplied merge commit: `72bf60474359d831f0cee70a6246ebf50952ea26`

DONE_WITH_CONCERNS — Review verdict: **approve**, limited to the reviewed offline guard change. Scoped regression parity: **pass**, not a clean suite or release gate.

The supplied diff exactly matches local base..head. I reviewed the added SQL interpreter and its controls, the frozen baseline, applied-head marker, exception file, CI path triggers, dependency pin/lock and grant-matrix correction. The guard scans scripts only; it does not execute SQL or alter production schema. The marker remains 20261027_0026 and explicitly distinguishes an owner assertion from measured production state. The SQLGlot dependency is pinned to 28.0.0 in the test group and lock, rather than a runtime dependency.

The implementation preserves CTE scope and RETURNING output when rewriting DML, checks INSERT conflict/VALUES subqueries, retains correlated bindings, and rejects unresolved/ambiguous columns. Runtime-expression fingerprints, nonempty exception reasons, duplicate/stale exception rejection and both discovery/checked-file floors avoid a vacuous green. The new suite includes missing-schema, pending-migration and synthetic missing-column controls. Shared-catalog and runtime-builder exclusions are explicit limitations, not evidence that those queries are safe. The production-schema interpreter remains intentionally limited to the documented migration forms; this review does not certify arbitrary future DDL or procedural SQL.

No blocking defect was identified in the changed behavior. The two role-suite failures concern ai_feedback.ref_key, and both reproduce at the supplied base with identical failed test identities and causes. The head adds 134 passing schema cases. Head: **188 passed, 2 failed, 25 skipped**; base (the two pre-existing role modules): **54 passed, 2 failed, 25 skipped**. The new schema module does not exist at base, so it was not copied or fabricated there. The 25 skips are not passes. The first head attempt lacked SQLGlot and ended with a collection error; that evidence is retained, and the corrected invocation uses an already cached SQLGlot package without installation. Ruff and dependency-manifest validation pass.

Risk: this is test/documentation/CI-discovery-only coverage. Linux execution was unavailable (Docker socket permission denied); no full-suite or production claim is made. The base role failures are carried forward, not repaired by this lane. Exception references to anti-GFW/rollback scripts do not modify or run those protected scripts. No database migration or archive-table candidate is introduced.

## Exact evidence

Environment: macOS arm64, Python 3.13.15, pytest 9.1.1, SQLGlot 28.0.0 from an existing local cache; TZ=UTC, four xdist workers. Service credentials are not inherited. No dependencies were installed.

- **head**: exit 1; `reviews/merge-receipts-20261105/yueops-360-head.log`; SHA-256 `53b5c44cbecc39335d52402e107ec5848c1ef180d1f9ec8725f2a3b45f04c6e2`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_sql_columns_exist_in_schema_20261102.py tests/test_monitor_role_covers_guard_sql_20260924.py tests/test_service_role_grants_20261102.py`
- **head-cached**: exit 1; `reviews/merge-receipts-20261105/yueops-360-head-cached.log`; SHA-256 `1019aea6ad0c513009f90a2d58ac999927dad4484cbe2eb0b58734053b977b61`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_sql_columns_exist_in_schema_20261102.py tests/test_monitor_role_covers_guard_sql_20260924.py tests/test_service_role_grants_20261102.py`
- **base**: exit 1; `reviews/merge-receipts-20261105/yueops-360-base.log`; SHA-256 `c90392bb9d09ddb555083b9ac664aca1fb5557d1ecd5b4cd38c4a7ae6e3806a1`.
  Command: `cd /tmp/rc-360-base && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m pytest -q -n 4 -p no:cacheprovider tests/test_monitor_role_covers_guard_sql_20260924.py tests/test_service_role_grants_20261102.py`
- **lint**: exit 0; `reviews/merge-receipts-20261105/yueops-360-lint.log`; SHA-256 `b821479926f1797dd81c84dc451fac07c48f7e0b02b486acc9c32b9b036ebc64`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -m ruff check tests/test_sql_columns_exist_in_schema_20261102.py`
- **dependency-manifest**: exit 0; `reviews/merge-receipts-20261105/yueops-360-dependency-manifest.log`; SHA-256 `326e41dda09f52782347f55e6e413348f8fedebcbc994d19dfbd2804d4af07a0`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python scripts/check-python-dependency-groups.py`
- **environment**: exit 0; `reviews/merge-receipts-20261105/yueops-360-environment.log`; SHA-256 `6cb6730dff32a5ca843aead29e312996c6bbe5c55388d53ac3b3978e08673ca1`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python -c 'import platform,pytest,sqlglot;print(platform.platform());print("Python",platform.python_version(),"pytest",pytest.__version__,"SQLGlot",sqlglot.__version__)'`
- **linux-unavailable**: exit 1; `reviews/merge-receipts-20261105/yueops-360-linux-unavailable.log`; SHA-256 `09d7bc70003227685bed948d11ace5bd05b62b0351996cc70bf8da56c31ef8e8`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 docker info --format '{{.OSType}}'`
- **binding**: exit 0; `reviews/merge-receipts-20261105/yueops-360-binding.log`; SHA-256 `d11e3e69834314103c8616c9b4cd953bb3235ce355882bb7fb71385792286b9d`.
  Command: `cd /tmp/rc-360 && env TZ=UTC PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/j/.cache/uv/archive-v0/Q0dWVy592ziKaZh8 /Users/j/Projects/yueto/yueops/.venv/bin/python /Users/j/codex-runs/1104c/rcpt-bind.py 360`

Combined parity log: `reviews/merge-receipts-20261105/yueops-360-parity.log`; SHA-256 `6b827796ab068b9bf04ff0c7082801a46a28e9b10d31cbc73afca5a71eb391c1`.

## Receipt boundary

Written offline using exactly the field layout of merge-receipts/yueops/370.json, not scripts/write-merge-receipt.py: that writer requires GitHub API access and accepts only approve/pass. No network attempt was made. Metadata provides headRefOid/baseRefOid/mergeCommit but no mergedAt; mergeCommit equals head and local ancestry/diff binding passed. `backfilled=true` denotes this explicitly retrospective review; the GitHub merge timestamp and the audit's 24-hour eligibility window remain UNKNOWN. No timestamp was backdated. Evidence is intentionally uncommitted at owner request, so normal committed-evidence merge-hygiene acceptance is not asserted. An UNKNOWN receipt is a factual non-approval record for parity and is intentionally not admissible as a green merge receipt.
