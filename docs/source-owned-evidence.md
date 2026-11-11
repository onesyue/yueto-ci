# Source-owned evidence binding (prerequisite)

`scripts/source_evidence.py:load(source_checkout, exact_commit)` authenticates
the exact Ops commit using the public validator's fixed owner signing subkey,
primary key and public certificate. The authority is projected from the existing
root release authority; candidate files, Git configuration and environment
cannot substitute it. This does not execute candidate Python, hooks or tests.

The loader returns `BOUND_SOURCE_EVIDENCE` and `admission: false`. This is not a
new validation gate or a substitute for the existing join. Planner/precheck/join
integration, exact outcome/platform checks and immutable native obligations are
required before this can admit source-owned evidence. Historical admission is
unchanged by this prerequisite commit.

Two regular, nonexecutable files are read from the signed commit, never the
mutable checkout:

- `ci/evidence/shared-inputs.json`: exactly `schema: 1`, `inputs`, and
  `inputs_sha256`. The inputs map covers every tracked tree entry except these
  two evidence files. Each path maps to its Git `mode`, `kind`, and `git_blob`.
  Hash the map as UTF-8 JSON with sorted keys, compact separators and ASCII
  escaping, using SHA-256. This deliberately also binds symlinks, submodules,
  configuration and collection helpers. No blanket `ci/` exclusion is allowed.
- `ci/evidence/pytest-skip-baseline.json`: `schema: 1`,
  `status: HISTORICAL_SKIPS_NOT_PASSES`, the identical `inputs_sha256`, `cases`
  and `collection_skips` dictionaries. Outcome and platform record validation
  belongs to the subsequent admission integration; arbitrary dictionary content
  cannot produce a passing admission through this loader.

Generate input identities after staging code and before staging the two evidence
files. Evidence files do not embed their own eventual commit SHA. The signed
commit binds both code and evidence; the returned receipt supplies the exact
source revision and each evidence blob's Git identity and SHA-256. Changing any
other tracked path requires regenerating the input map. Missing files, unsigned
or foreign-signed commits, nonregular evidence, duplicate JSON keys and stale
input maps fail closed.

Tests use a temporary fixture-only certificate through a private test injection
point. No fixture identity is added to production policy. Both Darwin and the
offline Linux CI image run the real Git/OpenPGP paths; no signature subprocess
is mocked.
