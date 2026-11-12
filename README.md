# Yue.to server CI

Public build and release control for Yue.to server components. Private source
is checked out with scoped credentials; images publish only to `ghcr.io/onesyue/*`.
Client packages use [yuelink-ci](https://github.com/onesyue/yuelink-ci).

[services.json](services.json) defines image targets. Frontends ship inside
their backend images (负责人 decision AX03-A, 2026-10-30); the former scratch
UI units `ui-*` are retired and must not be re-registered.
[validation-targets.json](validation-targets.json) defines source-only targets
(YueLink and `yue-node-validation`, which never enter the image matrix).
The only release workflow is [build.yml](.github/workflows/build.yml): validate,
build, sign, attest, then explicitly promote. Candidate builds may overlap
validation, but publication requires both the complete validation matrix and its
current-run evidence to succeed. Failed, skipped or cancelled prerequisites
cannot write built/source/latest tags. Publication is never interrupted to react
to an already-failed validation; that failure prevents it from starting.
Board release E2E compares committed Linux snapshots and refuses missing baselines;
use the separate `board-visual-capture.yml` workflow to author reviewed baselines.

## Recover interrupted server delivery

Image promotion is not deployment. Use the workspace's
[release and recovery procedure](../docs/release-chain-runbook.md) and
[native ship driver](../scripts/ship.sh), preserving the original receipt and
release owner. Once all exact selected Ops images are promoted, resume from the
workspace root without starting another build:

```sh
scripts/ship.sh yueops --from-promoted --detach
```

Use `yueboard` for the panel. `yue-node` verifies and records image publication;
fleet rollout remains a separate operation. These paths retain signed desired-state
and applicable deployment verification. An incomplete promotion or changed source
is not permission to substitute another revision into the interrupted release.

## Run validation or promotion

```sh
# Exact reviewed Board pin: validate and build a candidate.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin>

# Validate all targets and build registry-eligible candidate images (no promotion).
# Supply the trusted predecessor required by Ops SQL lint.
gh workflow run build.yml -R onesyue/yueto-ci -f service=all \
  -f migration_base=<40-hex-trusted-yueops-previous-revision>

# Source-only validation: no image or registry writes.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yuelink -f ref=<40-hex-yuelink-sha>
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yue-node-validation -f ref=<40-hex-yue-node-sha> -f promote=false

# Promotion additionally requires the conditions below.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin> -f promote=true
```

Validation accepts full branch/tag names or full 40-character commit SHAs;
7–39-character commit abbreviations are rejected. `promote=true` requires a
full 40-character source SHA and this workflow's `refs/heads/master`. Validation
and build check out independently, so movable refs cannot authorize promotion.

Promotion also requires source default-branch ancestry, build inputs identical
to HEAD, no regression behind `:latest`, and Board's exact signed
`yueboard_contract_pin` in [native-node-contract.json](native-node-contract.json).
[promote-source-gate.py](scripts/promote-source-gate.py) repeats these checks
immediately before changing tags. Unpinned Board HEAD receives full validation
but is `non-promotable`: no registry login, image, candidate or tag writes.
Source-only targets reject promotion; ordinary `service=yue-node` still builds
an image, while `yue-node-validation` runs both complete native profiles only.

Ops builds require `migration_base=<full40-characterSHA>`, an existing ancestor.
SQL lint covers baseline through candidate and rejects deleted/renamed SQL;
there is no `HEAD^` or full-history fallback. Workspace `scripts/ship.sh yueops`
derives the predecessor from verified signed `release.yaml`. Manual validation
must use the same trusted basis, never the candidate itself. Squawk
version/digest, PG15 and rule exclusions remain pinned in the workflow.

## Explicit validation and cache reuse

The disabled source-poll workflow and its self-rearm chain are retired.
Use `scripts/ci-check.sh` for validation-only runs, or the root workspace's
signed `scripts/ship.sh` flow for an authorized release. A source push alone
is not a promise that validation or publication will run automatically.
The obsolete root `kick-builds.sh` poll caller is retired in the paired root PR.
No replacement unattended publication trigger is introduced.

Go installs use pinned compilers with `setup-go`'s combined cache disabled.
Explicit module/compiler caches are available only to hosted master runs whose
source is reachable from registered `origin/master`. Missing trust, runner or
toolchain facts use cold validation. Compiler restore retains exact repository,
profile, workflow, dependencies, Go/C compilers and runner image; keys also name
the actual source SHA. There is no broad fallback, run-ID key or cache-based gate
skip. `go clean -testcache` expires results, not compiled objects. Local runners
keep local caches and never upload hosted caches; cache download failure is
nonfatal. Configuration alone does not establish a pipeline speedup.

## Credentials and publication boundaries

| Credential or switch | Purpose and boundary |
|---|---|
| `YUETO_CI_PAT` | Legacy `repo`/`write:packages` fallback while App/registry switches are absent. |
| `YUETO_CI_APP_CLIENT_ID` + secret `YUETO_CI_APP_PRIVATE_KEY` | App tokens for private source reads. Issuance failure aborts; no silent PAT fallback. |
| `YUETO_CI_GHCR_VIA_GITHUB_TOKEN=true` | GHCR login with this repository's GITHUB_TOKEN. App tokens cannot authenticate GHCR. |
| `DEADMAN_SSH_KEY_B64` | Dedicated read-only key forced to `command="/bin/cat /var/lib/yue-alert-heartbeat/heartbeat.json",restrict`; never a deployment key. |

Grant `onesyue/yueto-ci` access under each package's **Manage Actions access**:
Write for push/sign/provenance and at least Read for poll/rescan. App tokens need
contents:read only on the source repositories each job consumes. The fork-tag
verification step also reads quic-go; Node validation itself has no credentials
and uses vendored dependencies with `GOFLAGS=-mod=vendor`. Promotion obtains a
fresh token because a build may outlast token expiry. Failure reports use workflow summaries and error annotations without
Issue or PR creation. Poll dispatch uses GITHUB_TOKEN with
actions:write. Configure switches under repository Actions Variables.

After both switches and successful poll/build/promotion/rescan/deadman drills,
remove and revoke the legacy PAT. Source repositories no longer need
`YUETO_CI_DISPATCH_PAT`. The `repository_dispatch` trigger has been removed;
builds enter through `workflow_dispatch`, including requests from the poller.
Retained compatibility guards in the plan do not expose a dispatch entry point.
[Credential tests](tests/test_credential_policy.py)
protect these boundaries.

Production accepts only this signing workflow and provenance source ref:

```text
^https://github.com/onesyue/yueto-ci/\.github/workflows/build\.yml@refs/heads/master$
```

`release.yaml` in the private workspace is the signed desired-state authority.
`scripts/ship.sh` verifies the promoted digest, signature, SBOM and provenance,
then writes, signs and pushes that record. This public CI never writes root Git
state. Promotion's `DIGEST`, `SOURCE_SHA` and `IMAGE` anchors remain inputs to
that workstation chain. Builds, promotion and installed production are separate
facts; changing a source pin does not establish deployment.

Keep public logs concise and free of sensitive values or environment dumps.
Private source and images are never uploaded as artifacts. Only explicitly
allowlisted diagnostic evidence and candidate identity metadata may be published.
Product outputs go to GHCR.

The plan freezes every selected source ref before validation and candidate image
preparation start in parallel. Candidate preparation retains all vulnerability,
SBOM, signature and provenance gates. Its write-once artifact contains only the
verified digest and service, source, workflow, run and attempt identities. The
publication job requires successful candidate builds, validators and the complete
validation-evidence join; it checks that receipt against the frozen plan and
uses the exact digest without resolving a mutable candidate tag. Only then may
it write `built-<sha>` or perform the existing authorized promotion. Failed,
canceled or skipped required jobs block publication. Source-only plans keep an
empty image matrix and skip both candidate build and publication.
Receipts belong to one run attempt; retry the complete workflow when a failed
publication needs a fresh attempt, rather than reusing a prior candidate receipt.

## Validation and diagnostic evidence

### Ops corpus and timing

[pytest-shards.py](scripts/pytest-shards.py) admits a skip or xfail when pytest
recorded a non-empty reason, and it reports that skip. validation-evidence fails
when a selected shard did not run, or when a skip has no reason. A reason is not
a pass: host and root skips are not Linux acceptance, and admission never reuses
a prior successful job or replaces same-run native, reference, serial and ordinary
execution.

Plan admission for a commit without source evidence is an owner signature on the
default branch: `policy/yueops-owner-signers.json` plus ancestry of `origin/master`.
Shared-input successor seals are not that gate. A new test helper or conftest does
not need a yueto-ci seal. Shards still come from the timing file. Hash syntax does
not authenticate a review; the commit signature does.

[ops-pytest-skip-baseline.json](ops-pytest-skip-baseline.json) remains hashed by
envelope and expand. Deleting the file here would make a missing baseline look
like an open gate. Skip comparison no longer treats that file, or the dated
`reviews/ops-ordinary-skip-evidence-*.json` chain, as an allow-list. Those dated
files are deleted.

Before a yueops release, run
`python3 scripts/pytest-shards.py skip-blob-precheck --ops-checkout <yueops-checkout> --ops-rev <40-character sha>`.
A moved test-module blob is not a rejection. Exit 2 means the commit is
unreadable, a requested historical policy commit is missing, or
`tests/admission/ordinary-skip-evidence.json` is malformed or does not succeed
an admitted skip. A missing evidence path adds no successor. Malformed JSON
fails the precheck.
The owner's 2026-11-03 Nezha retirement removes two active skip IDs. Historical
seal verification reconstructs their exact predecessor bytes; admission rejects
skips from the retired module, and historical review artifacts stay unchanged.

The serial pytest entry records collection and every setup/call/teardown phase.
[lens_report.py](scripts/lens_report.py) is a generated projection; use root
`python3 scripts/sync-lens-report.py --apply|--check --ci-root <central-checkout>`.
The installer validates its canonical-path/hash manifest; the workspace also
compares actual canonical bytes.

The run/attempt-specific `yueops-pytest-timing-*` artifact retains test identities,
phase/outcome metadata, source/policy/recorder/entry identities, tool versions and
the original pytest exit for 14 days, including failures. Missing starts, phases,
records or exit receipts remain MISSING/PARTIAL. COMPLETE timing can describe
failed tests and is not release acceptance. Nested pytest does not claim the
parent stream; subtest durations are excluded from parent-phase totals. CPU and
process-tree peak memory remain UNKNOWN. Nginx/PostgreSQL/systemd keep their
separate gates. Gather timing on the next required run, not a profiling-only
full-suite dispatch.

Native Ops PG18 admission uses Ubuntu 24.04 amd64, isolated temporary APT
sources/indexes, HTTPS Ubuntu/security/PGDG repositories and fingerprint-verified
Signed-By keys. Fetch, update, tool, major-version and non-root checks remain
mandatory even for an existing installation. Shell-fixture tests do not replace
native public validation.

### Board PostgreSQL integration

Run domain fixtures against fresh PostgreSQL first, then `clean-pg-gate.sh` in
a separate fresh database in that cluster, serial module suites, and full
DB/nativeproto migration and production-scale suites. Earlier migrations can
mask fixture-role bugs; early deviceidentity/nodesync can clear needed schema.

[validate-yueboard-postgres.py](scripts/validate-yueboard-postgres.py) discovers
Go-selected suites through AST and reconciles actual run/pass/package events.
Commands use `-count=1 -p 1 -tags integration -json -v` with full logs. Any top-level
or subtest SKIP, missing execution, nonzero exit or unscheduled discovered package
fails. Run/attempt receipts bind all stages to the same source manifest. All four
DSNs must match loopback `yueboard_test`; reset confirmation and production-scale
switch remain required. Required packages follow the validator's floor and source
capability rules: floor 130 adds user/referencelock/nativeproto, floor 138 adds
subscribe, and floor 139 adds statcron. Reminder and usage-policy suites depend
on their source capability markers; the operator command suite is required when
its owned Linux gate exists. Every discovered suite must execute, including on
older sources; these compatibility rules grant no SKIP exemption. Review
schema-reset behavior before changing execution order.

### Input fingerprint and verification helpers

[input-fingerprint.py](scripts/input-fingerprint.py) derives actual COPY/ADD/bind
inputs for polling and publication admission. Its optional feedback CLI retains
complete/unknown reports, with full validation always required. Shared evidence
identity helpers remain in verification-evidence.py; verification reuse is disabled.
The former non-gating `input-shadow` reporting job is retired. No release job
consumes its diagnostic artifacts, so no scheduled probe or artifact upload remains.

## Observers outside production

[alert-chain-deadman.yml](.github/workflows/alert-chain-deadman.yml) reads the
bastion heartbeat with the canonical evaluator and records failures in the workflow
summary and error annotations, keeping a failed run. Its nominal 30-minute GitHub cron is supplementary evidence,
not the alert SLA. The dated 100-run September11–26 sample had 1.72–6.93-hour
gaps (median3.53h, P90 5.36h); it is not a current measurement. The panel's native
`panel-alert-chain-deadman.timer`, every ten minutes with direct Telegram and
VERSION3 issue-code-set deduplication, owns the ≤45min +10min detection target.
`--max-age-seconds 2700` is freshness, not cadence; the bastion emits every five
minutes. Keep the 30-minute cron and freshness threshold; scheduling delay is
not a reason to weaken stale-heartbeat detection. The maintained runbook is
`docs/runbook/panel-alert-chain-deadman.md` in YueOps.

[image-rescan.yml](.github/workflows/image-rescan.yml) scans every declared platform
of each latest image plus the three most recent promoted revision/digest markers.
Those markers bound current/rollback coverage because this public repository has
no credential for private `release.yaml`. Enumeration fails closed; scan/plan
failure or cancellation records a workflow summary and error annotation and
fails the reporting job. There is no private checkout, registry write or public artifact.

[plan-rescan-targets.py](scripts/plan-rescan-targets.py) paginates 100 versions per
page, at most100 pages, using only the reviewed owner/package. A full page requires
another request even without a Link header. Malformed/duplicate/error/truncated
listings fail. An extra empty final page may point `last` to the immediately
preceding page only when it has no `next`; other backward jumps fail.

## Toolchains and runner boundaries

Hosted jobs pin `ubuntu-24.04`; implicit `ubuntu-latest` drift is rejected.
Review runner major, Python/toolchains and evidence identity together.
[Verified Buildx](scripts/install-verified-buildx.sh) and
[verified Trivy](scripts/install-verified-trivy.sh) installers own exact versions
and independently anchored SHA-256 pins. HTTPS download, hash verification before
execution and actual command resolution are mandatory; environment overrides
cannot replace these pins. Buildx creates the pinned OCI BuildKit builder only
for builds. Rescan needs CLI imagetools only. Trivy actions use the verified
installation with `skip-setup-trivy: true`; SBOM keeps its own Syft path.
Buildx, Cosign and Gitleaks installers download the already pinned upstream
artifacts, with the existing release-asset API fallback and checksum verification.
Their binary copies are no longer stored in `third_party/`; a download failure
remains a failure rather than admitting an unverified replacement.

While this repository is public, do not register a persistent self-hosted runner.
Never attach production hosts. Before using a local release runner, make the
control repository private, protect branches and establish the Actions allowlist.
Only then use a dedicated disposable Debian13 x86_64 VM without production
credentials or network access and an `--ephemeral --disableupdate` runner.
Registration must retain `self-hosted`, `Linux`, `X64` and add `yue-local-release`.
All four labels must match. It takes one job; export permitted diagnostics and
destroy the VM/Docker state. Only an authorized manual dispatch can select it;
default manual runs and poll-triggered builds use hosted runners. Bootstrap GNU make,
required Go/C toolchains and gettext-base; Debian13 verifies system Python3.13,
while hosted jobs use the toolchain image Python at /usr/local/bin/python3. Manual runner state is not validation evidence.

## Actions allowlist closure

Selected-actions covers direct actions and nested composite dependencies.
The exact external closure is:

- `anchore/sbom-action@*`
- `aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`
- `aquasecurity/trivy-action@*`
- `astral-sh/setup-uv@*`
- `bufbuild/buf-action@*`
- `docker/build-push-action@*`
- `docker/login-action@*`
- `docker/setup-buildx-action@*`
- `docker/setup-qemu-action@*`

Retain `github_owned_allowed=true` and `verified_allowed=false`. Source references
must still use full 40-character SHAs; `@*` permissions never authorize mutable
tags in workflow source. Review permission changes before adding a new action.

## Local policy checks

Install [requirements-policy.txt](requirements-policy.txt) in the test environment
for real-pytest recorder controls, then run:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Discovery rejects unreachable test cases and import failures. Policy CI also
compiles Python, checks shell syntax, runs pinned actionlint and ShellCheck.
See [policy-ci.yml](.github/workflows/policy-ci.yml) for exact commands and pins.

### I33 A13 toolchain and PostgreSQL pin coverage

The workspace guard `scripts/check-toolchain-pin-agreement.py` in `onesyue/yueto`
compares YueLink's `core/go.mod` toolchain with its build workflows and benchmark
image, in addition to the native services. It also checks the PostgreSQL Alpine
18.6 pins in the clean-PG gate, e2e harness, workspace PG gate and i18n clients.
Run that guard from an assembled workspace containing the companion PR revisions;
a single central-CI checkout cannot establish cross-repository agreement.

Central validation retains its reviewed `postgres:18@sha256:…` service image.
It is digest-pinned and uses a different image variant from the Alpine helpers;
changing its tag to Alpine while retaining that digest would mislabel the bytes.
`python3 -m unittest discover -s tests -p 'test_postgres_image_pin.py'` rejects
service-pin removal, mutable replacements and unreviewed digest changes.

### Admission precheck and merge hygiene

Run admission from a trusted **yueto-ci** checkout before requesting a build.
The source checkout must contain the commit and `refs/heads/master` or
`refs/remotes/origin/master`:

```sh
python3 scripts/admission-precheck.py --repo yueops --source ../yueops --base "$BASE_SHA" --head "$HEAD_SHA"
```

The precheck reads the committed object without executing Ops code. Head is
admitted when it is an ancestor of the default branch (or the tip) and its
OpenPGP signature matches `policy/yueops-owner-signers.json`. A new helper or
conftest is not a seal. Exit codes: **0** admitted, **1** rejected, **2**
invalid input. This does not certify the rest of the build gates.

The build workflow's `pytest-shards.py expand` emits a single-line
`ADMISSION_REJECTED: <reason>` Actions error annotation and step summary on
rejection. Ship callers can surface that reason instead of reporting “no build
found”. Existing JSON rejection diagnostics remain available.

```sh
python3 scripts/merge-hygiene-audit.py --hours 24
python3 scripts/merge-hygiene-audit.py --hours 24 --format json
```

The audit reads native GitHub reviews, checks and statuses using authenticated
`gh api`. It defaults to all seven repositories: `yueops`, `yueboard`, `yueto`,
`yueto-ci`, `yuelink`, `yuelink-ci`, and `yue-node`. The credential needs read
access to this evidence. A non-author, non-bot approval must name the exact PR
head in its `commit_id`; an approval of an older commit cannot admit a new head.
Latest review state and checks/statuses are evaluated at merge time. Later green
reruns cannot erase observed failures. Completed `success`, `neutral`, and
`skipped` checks retain GitHub's passing-conclusion semantics; this does not
claim that skipped work executed. Missing, pending, red or ambiguous evidence
remains a finding. API/input failures exit **2**, never clean.

`--hours` explicitly controls the retrospective window (default 24 hours).
There is no implicit PR-71 activation date that extends it indefinitely. This
bounded report does not certify older history or replace GitHub branch rules.
Optional `--baseline PATH` still accepts only exact historical repo/PR/head
findings at or before its frozen timestamp; it cannot waive an open candidate
or the direct source of an indirect merge.

For an open candidate, run:

```sh
python3 scripts/merge-hygiene-audit.py --premerge yueboard 123
```

This also evaluates the current candidate using native evidence and rechecks
head/base after fetching it. Rerun after changes and use GitHub's expected-head
merge option plus branch protection. Indirect ancestor closures require a
unique direct PR, matching target and times, verified ancestry, and independent
native admission of the direct head. Old-head findings stay visible as history;
the audit does not relabel them as passing tests.

JSON output is **schema 2**, with `complete`, `findings`, `accepted_history`, and
`unregistered`. Findings exit **1**; clean or explicitly accepted historical
findings exit **0**. Schema 2 removes `receipt`, `satisfied_by_receipt`,
`exception`, and `evidence_only` fields and text states. The retired `--exceptions`
argument is rejected. Local receipt files, companion evidence PRs, and exception
registrations no longer substitute for GitHub evidence. Repository parity and
independent review remain required by the delivery process.

HTTP ETags and response bodies are cached under `~/.cache/yueto/merge-hygiene/`
(override with `MERGE_HYGIENE_CACHE_DIR`). Every page is revalidated on every
run; cached verdicts and immutable file-comparison waivers are gone. Cache
version 3 ignores older snapshots. A warm audit still needs authenticated HTTP
and fails closed if an endpoint becomes unavailable. The cache contains private
repository metadata and should remain local to its user. Pagination stops when
an updated-at-sorted page is older than the requested cutoff.

Below `MERGE_HYGIENE_RATE_FLOOR` (default 300), the audit exits **2** with
`incomplete: rate-floor`. HTTP 403/429 above that floor receive at most two
retries honoring server retry/reset times; waits longer than five minutes remain
incomplete. Transport diagnostics and authenticated headers are never printed.
GitHub cannot expose every overwritten check or review state, so missing history
remains unknown. No workflow or private-repository Actions job is added.

Historical receipt/parity artifacts are archived at
`archive/merge-receipts-20261112` (pre-removal commit
`539ab94ea15230045ff48ff5e29190cc471357a3`). Before merging this retirement PR,
the coordinator must publish the signed archive tag; this PR-only lane creates
and verifies it locally but does not push tags. The archive is evidence history,
not a continuing audit input.

### Validate an exact candidate without publication

The existing `build.yml` manual dispatch accepts `validation_only: true` with
`service` selecting one source repository and `ref` set to its full lowercase
40-hex commit SHA. For example, select `yueboard`, `yue-node`, `yueops`, or
`yuelink`; `all` is rejected because one SHA cannot identify several repositories.
YueOps still requires an exact trusted `migration_base`; the existing optional
`yueboard_contract_ref` retains its ACL validation meaning. Set `promote: false`.

This mode uses the same planner, complete selected validation matrix, Ops
admission/skip-blob checks, and validation-evidence join as a build. It has its
own `validate-only` concurrency group. Image builds, signing, registry publication
and cancellation jobs are skipped, including when planning or validation fails;
its executable jobs have only `contents: read` workflow permissions. Source
checkout retains the existing read-only credential mechanism. The evidence join
runs after failed validation so a failed gate is visible without publication.
The default remains `validation_only: false`, preserving ordinary candidate builds.
Validation success is not release approval and does not move any image tag.

### Evidence-only promotion resume

An explicit resume dispatch uses `ref` for the replacement signed Ops evidence
source and `resume_build_run_id`, `resume_build_attempt`, `resume_build_source`
for the original image build. It requires `promote=true`, `validation_only=false`,
hosted Linux and an explicit Ops service/group. The existing planner and all
validation roles run against the new source. The build job is skipped only on
this path; promotion still requires successful complete validation and join.

`scripts/resume-binding.py inspect` verifies exact GitHub run/attempt/jobs,
immutable artifact archive digests, original image provenance, Board/migration
context and actual Docker input/recipe equality. A candidate artifact includes
its unchanged schema-1 receipt plus `candidate-context.json`; older artifacts
without this context are refused rather than reconstructed from local claims.
Evidence files are not unconditionally excluded: if Docker consumes them, their
change invalidates reuse. The original image source revision remains unchanged.

The trusted policy can be exported without `.git` and invoked using `python -I`
with explicit `--policy-sha`. `prepare` binds a new validation run; `resolve`
checks its canonical join before publication; `publication` reads back the
registry digest/revision and retains an immutable per-service receipt.
`verify-publication` independently reads those exact API artifacts and returns
both original build and new publication identities. The protocol marker is
`resume-protocol.json`. No helper dispatches or publishes on its own.

This protocol does not relax existing default-branch, fingerprint, signature,
SBOM or rollback rules. The root caller currently restricts resume to the Ops
group with `--no-deploy`; deployment consumers must separately validate the old
image/new evidence identity binding before deployment resume can be enabled.

### Validate Board or Node remotely (B10-2)

`scripts/ci-check.sh yueboard <sha>` and `scripts/ci-check.sh yue-node <sha>`
reuse the existing hosted validation roles on the current pushed policy branch.
Every request fixes `validation_only=true` and `promote=false`, resolves an exact
source commit, and binds its run to that source, policy commit and unique nonce.
`remote.log` retains all job logs; `result.json` retains the terminal GitHub result.
`failures.txt` summarizes pytest, Go test and Go compiler/lint diagnostics, including
S1009. An empty summary never overrides a failed workflow conclusion.

Board/Node local execution is not implemented: `--local` is rejected before any
network request. Board context, migration base and prepared execution options
remain YueOps-only. This interface does not establish local/remote equivalence.

### Reproduce a signed YueOps validation (B9-9)

`scripts/ci-check.sh yueops <sha>` dispatches validation only from the current
pushed policy branch. The source can be any owner-signed branch commit. The
command verifies the policy head and binds the new run by a unique nonce, then
prints failing pytest node IDs from all job logs. It never selects an image build
or publication. `CI_CHECK_MIGRATION_BASE` can supply the exact historical baseline;
otherwise the source commit's first parent is used.

Add `--local` to use the same planner, immutable toolchain image, locked dependency
installation, owned pytest selection, native obligations and final evidence join.
Each admitted role gets an isolated container and complete Git clones. Source,
Board and policy clones retain exact revisions; they are removed at exit. Set
`YUEOPS_CHECKOUT` / `YUEBOARD_CHECKOUT` to existing clones to avoid downloading their
history again. The local Docker engine must support privileged Linux amd64 containers. Each
role starts its own disposable Docker daemon; the shared host daemon socket is
never passed to test code. The command does
not build a replacement toolchain image.

Receipts, role logs, planner output and `failures.txt` remain under
`.lane/ci-check-<time>-<pid>/` (or `CI_CHECK_OUTPUT`). A failing role does not cancel
its siblings. Missing logs, incomplete execution, unsigned sources and failed
native/evidence gates cannot produce success. Historical comparison must use the
same Board contract revision and migration baseline; differences are reported,
not silently treated as matching failures.

### B9-8 Board validation context (requires paired ship change)

Ops dispatches must provide `yueboard_contract_ref`: the exact production Board
revision read from the signed root `release.yaml`. Missing input fails closed.
The planner seals this revision into admission; shards and native obligations
verify its owner signature and clean checkout, and evidence joins bind the same
revision. Board's own publication pin remains unchanged.

`ci-check.sh` resolves the default via `YUETO_ROOT/scripts/release-yaml.py`'s
`verified_desired()` snapshot API. Set `YUETO_ROOT` when CI is in a worktree rather
than a sibling of root. To reproduce a historical environment, pass
`--board-ref <40-hex-SHA>`; ci-check always dispatches `validation_only=true` and
`promote=false`. There is no fallback to a central pin or unsigned desired.

This CI batch must remain draft until root ship passes signed desired Board
identity and its resume verifier uses the original admission identity. The Ops
`board_contract` marker/consumer contracts (LANE-A A9-4) and their execution by
Board candidate CI are separate required B9-8 work. This batch does not establish
historical replay success or completion of B9-8.

### Hosted execution of the local replay engine

Central policy CI has a manual-only `local-replay` job. Supply exact
`source_ref`, `board_ref`, and `migration_base` SHAs, and dispatch the frozen
policy branch. It calls the same `ci-check.sh --local` engine for every role in
admission and the final join; it does not replace the run with a smoke test.
Only one manual local replay runs at a time, independently of PR policy checks.

Preparation uses `--local --prepare-only` to fetch standalone clones and save
`prepared.json`. The App token can read only yueops/yueboard, is scoped to that
step, and is explicitly revoked before execution. Revocation failure stops the
job. The next step consumes `--prepared <receipt>` without credentials or the
preparation Git/gh configuration. Input identities, clean clone state, origin,
default-branch refs and single ownership are checked before source planning.

The hosted controller reserves 330 minutes of the 360-minute job limit for
execution. It requires 8 GiB free initially and checks a 2 GiB operational disk
reserve while running; these are failure thresholds, not a measured bound on
native test disk use. Time or resource exhaustion yields an incomplete
infrastructure failure. Source execution waits for a durable owned-session receipt;
all exit paths stop that process group, including descendants whose leader exits
early. The always-step can recover a surviving authenticated session if the
controller itself was killed. It also reads exact controller/Docker
container ID receipts, verifies the per-replay owner label, retains logs and
removes only those owned containers. Evidence upload excludes source clones and
authentication directories and retains logs, admission, resource samples,
per-role exits and the complete-role/join receipt for seven days.

Resource reference: the fixed toolchain reports 642,314,601 bytes via Docker
image inspect. Historical remote run 43313724086 selected 35 validation roles,
whose summed job durations were 140.83 minutes (maximum 16.75 minutes), plus a
separate join. Its native job failed early, so this is not proof that the full
local replay fits the limit. Role counts always come from admission. Compare
local and remote failures only at identical policy/source/Board/baseline SHAs;
actual full local execution remains required for B9-9 acceptance.
