# Source-owned evidence and common admission

`scripts/source_evidence.py:load(source_checkout, exact_commit)` authenticates
the exact Ops commit using the public validator's fixed owner signing subkey,
primary key and public certificate. The authority is projected from the existing
root release authority; candidate files, Git configuration and environment
cannot substitute it. This does not execute candidate Python, hooks or tests.

The loader returns `BOUND_SOURCE_EVIDENCE` and `admission: false`. The planner
binds this record into the existing admission digest. Shared-input and skip-blob
prechecks use the same loader; neither is a runtime success receipt. Every shard
and the final join independently reverify the signed source binding. The join
requires `--source` for enrolled sources and still requires every role artifact,
successful validation, exact observed outcomes/platform and same-run native
obligations. Its output remains schema 1 `VALIDATION_MATRIX_COMPLETE` with the
original `admission_sha256`. PR and ship callers must use this same join for
complete validation, not treat a successful precheck as complete validation.
Trees without either evidence path continue on historical policy.

Two regular, nonexecutable files are read from the signed commit, never the
mutable checkout:

- `ci/evidence/shared-inputs.json`: exactly `schema: 1`, `inputs`, and
  `inputs_sha256`. The inputs map covers every tracked tree entry except these
  two evidence files. Each path maps to its Git `mode`, `kind`, and `git_blob`.
  Hash the map as UTF-8 JSON with sorted keys, compact separators and ASCII
  escaping, using SHA-256. This deliberately also binds symlinks, submodules,
  configuration and collection helpers. No blanket `ci/` exclusion is allowed.
- `ci/evidence/pytest-skip-baseline.json`: `schema: 1`,
  `status: HISTORICAL_SKIPS_NOT_PASSES`, the identical `inputs_sha256`,
  `context: {platform: linux, uid: <integer>}`, `cases` and `collection_skips`.
  Each case maps a nodeid to one record or a list of exact variants, with
  `outcome` (`skipped` or `xfail`), `reason`, `when` (`setup`, `call` or
  `teardown`), `module_blob` and `disposition`. Dispositions are
  `HISTORICAL_UNEXECUTED`, `OWNER_CANCELED` or `SAME_RUN_NATIVE_REQUIRED`; the
  latter also requires `native_target` equal to the case's module. Public native
  obligations cannot be waived. Collection records contain `reason` and
  `module_blob`. Arbitrary dictionary content cannot produce passing admission.

Generate input identities after staging code and before staging the two evidence
files. Evidence files do not embed their own eventual commit SHA. The signed
commit binds both code and evidence; the returned receipt supplies the exact
source revision and each evidence blob's Git identity and SHA-256. Changing any
other tracked path requires regenerating the input map. Missing files, unsigned
or foreign-signed commits, nonregular evidence, duplicate JSON keys and stale
input maps fail closed.

`pytest-shards.py export-source-baseline --source <checkout> --revision <sha>`
exports approved public records whose existing module blobs match the target.
It uses the same historical successor binder as the original join and preserves
all hosted variants. Historical records without a phase constraint explicitly
enumerate all three previously allowed phases. It never learns approvals from
new runtime skips, guesses new module blobs or converts native evidence into
historical waivers. `unmatched` lists old records that cannot be migrated;
these are not necessarily current skips. A subsequent runtime occurrence is
unregistered and fails. The export is always `admission: false`; neither its
status nor an empty unmatched list replaces full role evidence.

The export projects existing public mandatory native cases to
`SAME_RUN_NATIVE_REQUIRED` plus their exact module as `native_target`. It changes
no approved outcome, reason, phase or module blob. Only the observed matching
phase is checked; alternative approved phases are not extra execution duties.
Every observed mandatory skip still needs its exact nodeid in the verified
same-run native `passed` list. This projection does not create execution credit.

The public certificate and fixed signer projection are deliberately outside the
Ops candidate. Raw commit, recursively linked tree and consumed evidence blob
identities are recomputed, including when a local object database is corrupted.
Git's object pathname is not accepted as proof of its contents.

Tests use a temporary fixture-only certificate through a private test injection
point. No fixture identity is added to production policy. Both Darwin and the
offline Linux CI image run the real Git/OpenPGP paths; no signature subprocess
is mocked.
