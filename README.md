# yueto-ci

Unified build and external-control repository for Yue.to server components.
This public repository contains no business source. Private source repositories
are checked out with scoped credentials, and outputs go only to
`ghcr.io/onesyue/*`. Diagnostic artifacts are limited to the explicitly declared
test evidence below; private source and images are not uploaded as artifacts. Public Actions avoids the private
repository billing dependency. This repository also hosts an alert-chain deadman
observer outside production hosts.

Client builds run in [yuelink-ci](https://github.com/onesyue/yuelink-ci). These are
the two build repositories.

### Passive Ops timing evidence

The formal serial Ops pytest entry records collection, selected corpus identity,
and every setup/call/teardown phase. The existing root-owned Linux lens recorder
is projected into `scripts/lens_report.py`; do not edit that generated file.
Regenerate/check it from the workspace with
`python3 scripts/sync-lens-report.py --apply|--check --ci-root <central-checkout>`.
The central installer checks the projection's canonical-path/hash manifest;
the workspace contract additionally checks it against the actual canonical bytes.

The run/attempt-specific `yueops-pytest-timing-*` artifact retains event records,
source/policy/recorder/entry identities, tool versions, the original pytest exit
code and a summary for 14 days, including failed validation. It contains test
identifiers and phase/outcome metadata, not source files or environment dumps.
Missing starts, interrupted sessions, incomplete case phases, lost records and
absent process-exit receipts remain MISSING/PARTIAL. A COMPLETE timing artifact
can describe failed tests and never constitutes release acceptance.

Nested pytest subprocesses do not claim the parent stream. Subtest durations
are retained but excluded from parent-phase totals. The summary is scoped to
the existing serial entry; native nginx/PostgreSQL/systemd obligations retain
their separate execution and gates. Aggregate CPU and process-tree peak memory
are UNKNOWN; no single-process high-water mark substitutes for them. Collect
the next required run, rather than dispatching a profiling-only full suite.
The central policy self-tests use the five hash-locked wheels in
`requirements-policy.txt` to exercise real pytest subprocesses. Install that
file before the existing unittest discovery command when running policy tests
outside the Ops dependency environment.

Shared test/dependency inputs remain exact complete maps. A reviewed frontend
security lock update appends its own transition after the original frontend and
Python transitions, binding their history, the previous lock blob and its regular
file mode. Both source admission and sealed-envelope validation consume that
transition; mixed dependency generations and unrelated changes still fail.
The release coordinator verifies the actual signed source, independent review and
freeze artifacts before recording their identities. Hash syntax alone does not
authenticate those artifacts. Historical skip/collection evidence stays dated;
an admitted input map does not reuse successful jobs from an earlier release.

## Covered services

`services.json` lists image targets: yue-node, yueops-web, checkin-api, yue-bot and
yueboard. `validation-targets.json` separately lists source-contract-only targets,
currently YueLink. Keep these lists separate so the client cannot enter the Docker
build matrix accidentally.

## Triggers

`.github/workflows/build.yml` is the only release workflow. Promotion is its final
controlled step after validation, build, signing and attestation.

`.github/workflows/alert-chain-deadman.yml` is a read-only operations probe. It
reads the bastion heartbeat and uses the canonical YueOps evaluator. Failures open
incident issues only in the private YueOps repository; production credentials are
not recorded here. This supplies **additional evidence from another failure
domain, not the alert SLA**. See the measured deadman SLO below.

`.github/workflows/image-rescan.yml` scans potentially running images daily:
`:latest` for each service plus the three most recent
`promoted-<rev>-<digest>` digests, covering current and rollback predecessors while
deployment trails `:latest` (`scripts/plan-rescan-targets.py`). It scans every
declared production platform with SHA-256-verified Trivy 0.74.0. Root
`release.yaml` desired state is authoritative, but this public repository
intentionally has no credential for that private repository; registry promotion
markers provide the bounded substitute. Enumeration fails closed. Failed or
cancelled plans/scans open or update one deduplicated private YueOps image-rescan
incident, using the same App-token/PAT-fallback path as deadman. No private source
checkout, registry writes or public artifacts are involved.

Enumeration follows [GitHub REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api),
100 versions per page, before selecting recent promotion markers. Requests stay
on the reviewed owner/package rather than following credential-bearing Link URLs.
The limit is 100 pages. Even without a Link header, a full page requires another
request to establish the end. Duplicate versions, malformed pagination, HTTP
errors or an unproven complete listing at the limit fail explicitly. The first
100 entries must never be treated as all versions, which would omit rollback
images. For an exact multiple of the page size, GitHub may return an extra empty
page whose `last` points to the immediately preceding page. Accept that only when
the current page is empty and has no `next`; nonempty or multi-page backward jumps
remain invalid.

```sh
# Unpinned YueBoard HEAD: validation only, no registry writes. Exact reviewed pin: candidate build.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin>
gh workflow run build.yml -R onesyue/yueto-ci -f service=all \
  -f migration_base=<40-hex-trusted-yueops-previous-revision>

# Validate the exact remote YueLink source revision without building an image.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yuelink -f ref=<40-hex-yuelink-sha>

# Promotion additionally requires explicit promote=true, default-branch ancestry,
# image inputs identical to HEAD, no regression behind :latest, and YueBoard's
# exact reviewed yueboard_contract_pin in native-node-contract.json.
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin> -f promote=true

# poll-sources.yml checks private default branches. Its nominal cron is 20 minutes;
# measured scheduling is documented below. Missing exact built-<40-hex> artifacts
# trigger candidate builds only, never automatic latest promotion.
```

`ref` may be a full branch or tag for validation; commit refs must contain all
40 SHA characters. Checkout does not treat 7–39-character SHAs as reproducible
commit references, and planning rejects them. **With `promote=true`, ref must be
a full 40-character SHA for every event type** (2026-09-27 C3). Validate and build
check out independently, minutes apart. Branches, tags and an empty ref
(defaulting to registered `master`) can move between jobs, producing unvalidated
bytes. `ship.sh` already supplies `git rev-parse HEAD`. Promotion must also run
from this repository's `refs/heads/master`, the sole production signing identity.

An unpinned YueBoard default-branch HEAD can still receive full validation with
`promote=false`. It is explicitly `non-promotable` and removed from the build
matrix: no registry login, image build, candidate, `built-*`, `sha-*` or `latest`
writes. Candidate build and promotion require signed cross-repository convergence
of `yueboard_contract_pin` to that exact SHA first. `service=all` validates both
image services and source-only targets; the latter never enter the build matrix
and cannot use `promote=true`. `scripts/promote-source-gate.py` repeats the source
and input checks immediately before tags change (P2 #11, 2026-09-24).

YueOps builds, including single images and `all`, require explicit
`migration_base=<full40-characterSHA>`. SQL lint covers the entire baseline-to-
candidate change; the baseline must exist and be an ancestor. SQL deletion and
rename are rejected. There is no `HEAD^` or full-history fallback. Workspace
`scripts/ship.sh yueops` reads the predecessor from verified signed `release.yaml`
desired state. Manual validation must use that same trusted basis, never the
candidate itself to suppress an error. Poll derives the published ancestor from
verified master provenance and OCI revision, using the earliest group member
when versions differ; absence fails explicitly for retry on the next poll.
Squawk 2.60.0, its fixed SHA-256, PG15 and existing rule exclusions remain pinned.

### Measured poll cadence and optional rearming (2026-09-28)

Recorded schedule delays/loss began broadly on 2026-08-26 (community discussions
orgs/community#206019 and #207346; no official fix recorded then). Natural
poll-sources runs numbered28 on08-24 and34 on08-25, falling to2–6 daily from08-27.
Intervals during09-18→09-28 were2.5–6hours. Off-hour deadman (`17,47`) and
image-rescan (`17 2`, roughly5.5hours late daily) were delayed too; changing the
minute did not resolve it.

Two independent remedies:

- Run root `scripts/kick-builds.sh` after pushing private source to dispatch an
  immediate round using the workstation's `gh` identity.
- **Rearming is disabled by default.** poll-sources.yml's `rearm` job waits in the
  `poll-rearm` environment, without occupying a runner, then
  `scripts/poll-rearm.sh` uses this repository's `GITHUB_TOKEN` to dispatch only
  poll-sources, always with `promote=false`. An administrator must create
  `poll-rearm` with a20-minute wait and deployment branches restricted to`master`,
  then set repository variable `YUETO_CI_POLL_REARM=true`. Remove the variable to
  disable it. Two fail-closed gates apply: reject dispatch less than900seconds
  after poll start (GitHub otherwise auto-creates a missing empty environment and
  releases immediately), and allow only the newest noncancelled poll to rearm.
  Older chains stop, so manual kicks and schedules cannot multiply chains.
  `tests/test_poll_rearm_policy.py` executes the real script with fake `gh`.

Poll derives repository/image groups from `services.json` and verifies every
image in each group. New markers use full40-character source SHAs. Transitional
seven-character markers count only if OCI `org.opencontainers.image.revision`
exactly equals current HEAD. Registry authorization/network failures fail closed,
never masquerading as a missing image and causing redundant builds.

P3 (2026-09-24): a missing marker can avoid a build only if promoted `:latest` has
**identical build inputs**, verified GitHub build provenance, unchanged recipe
(services.json entry and build-job text), a promoted revision ancestral to HEAD,
and no floating Dockerfile `# syntax=` frontend. `scripts/poll-skip-decision.py`
implements this. Unknown facts cause a normal build, subject to YueOps's SQL
baseline prerequisite. A skipped build creates no `built-*` marker: the existing
artifact retains its original source identity, and the next poll checks again.

## Go validation cache ownership

`setup-go` installs the pinned compiler with its combined cache disabled. Explicit
module and compiler caches use the existing pinned `actions/cache`; only hosted
`master` workflow runs with source commits reachable from the registered source
`origin/master` can read/write them. Missing trust/runner/toolchain metadata runs
without remote cache. The local release runner keeps its local caches and never
uploads these remote caches.

The module key covers dependencies and workload/toolchain identity. The compiler
key additionally names the actual checked-out source SHA; its single restore
prefix retains the exact repository, profile, workflow, dependencies, compiler,
C compiler and runner image. Changed source can reuse compatible objects then
save its newly compiled objects after successful validation; an exact hit never
creates a redundant entry. There is no run-ID key, broad fallback or cache-based
gate skip. `go clean -testcache` expires test results while retaining compiled
objects. Cache download failures remain optional and cold validation remains
valid. Measure changed-source reuse in the next required central run; this change
alone does not establish a whole-pipeline speedup.

## Required secrets (Settings → Secrets → Actions)

- `YUETO_CI_PAT`: classic PAT with `repo` and `write:packages` for private checkout
  and GHCR push. Existing packages belong to source repositories, so this
  repository's GITHUB_TOKEN needs explicit package access before replacing it.
- `DEADMAN_SSH_KEY_B64`: base64 of a dedicated read-only SSH private key. The
  bastion public key must enforce
  `command="/bin/cat /var/lib/yue-alert-heartbeat/heartbeat.json",restrict`.
  Never reuse a root deployment/rotation key.

### Credential migration: classic PAT → GitHub App + GITHUB_TOKEN

Since2026-09-23, workflows support a configuration switch with PAT fallback when
the switch is absent. A classic `YUETO_CI_PAT` with full `repo` scope can write all
private repositories if a workflow is compromised. The owner can configure the
following without changing workflow code:

| Purpose | Consumer | Replacement | Minimum privilege |
|---|---|---|---|
| Read YueBoard SHA | build.yml plan | App token | yueboard contents:read |
| Checkout source and Board contract | validate/build | App token | yueboard/yue-node/yueops/yuelink contents:read |
| Verify Node private fork tags | Verify yue-node signed fork tags only | App token | quic-go contents:read; Validate yue-node has no credentials and uses vendored dependencies, GOFLAGS=-mod=vendor |
| Recheck default HEAD before promotion | promote | Fresh App token | Three service source repositories, contents:read; a build may last two hours, beyond a token's one-hour lifetime |
| GHCR push/sign/provenance | Login to GHCR | GITHUB_TOKEN, packages:write | Grant yueto-ci Write on each package |
| GHCR reads | poll-sources/image-rescan | GITHUB_TOKEN, packages:read | Grant yueto-ci at least Read |
| Read three source HEADs | poll scan | App token | contents:read |
| Dispatch local build.yml | poll Trigger builds | GITHUB_TOKEN, actions:write | workflow_dispatch is an allowed new-run exception |
| Read YueOps evaluator | deadman | App token | yueops contents:read |
| Open incident issue | deadman | Separate App token | yueops issues:write |

GitHub App tokens cannot authenticate GHCR. The registry path uses this
repository's GITHUB_TOKEN after adding `onesyue/yueto-ci` under each package's
**Package settings → Manage Actions access**.

Switches under Settings → Secrets and variables → Actions → **Variables**:

- Nonempty `YUETO_CI_APP_CLIENT_ID`, with secret `YUETO_CI_APP_PRIVATE_KEY`, moves
  all source reads to App tokens. Token issuance failure fails the job, **without
  silently falling back to PAT**.
- `YUETO_CI_GHCR_VIA_GITHUB_TOKEN=true` changes GHCR login to GITHUB_TOKEN.

After both switches and a successful poll/candidate build/promotion/rescan/deadman
drill, delete `YUETO_CI_PAT` and revoke the classic PAT in GitHub.
`tests/test_credential_policy.py` rejects unguarded PAT use. App setup is documented
in root `docs/2026-09-23-ci-credential-migration.md`.

Private source repositories no longer need `YUETO_CI_DISPATCH_PAT`; pull-based
polling uses the central credentials above. `repository_dispatch` remains only
for controlled compatibility calls, gated by trusted actor, full SHA and default
branch HEAD.

## Promotion records: this repository does not write root release.yaml

Since2026-09-14, workspace `onesyue/yueto`'s `release.yaml` is the canonical record
of promoted revisions/digests. Workstation `scripts/ship.sh` obtains the promotion
digest, passes signature/SBOM/provenance verification, writes it, signs the commit
and pushes. `scripts/release-yaml.py verify` compares the record to GHCR
`sha-<revision>` and `latest`.

Promotion intentionally writes no repository: the private free-tier root has no
ruleset enforcing signatures; a CI bot cannot produce the owner's signed commit;
introducing PAT-based private writes expands the impact to all private
repositories; and three parallel YueOps matrix jobs would race over root commits.
`tests/test_build_policy.py::test_promotion_records_nothing_in_the_workspace_root_repo`
rejects workflow git commit/push, root contents-write APIs and `release.yaml`.
Promotion `DIGEST`, `SOURCE_SHA` and `IMAGE` environment anchors must remain because
ship.sh consumes them.

## Input shadow analysis: reports only, never skips (since2026-09-24)

build.yml's `input-shadow` runs alongside validation. No job depends on it;
`continue-on-error: true`, read-only permissions. It writes annotations and step
summaries for two analyses:

1. `scripts/input-fingerprint.py shadow-ci` derives image inputs from actual
   Dockerfile COPY/ADD/bind sources and the **effective** ignore file:
   `<Dockerfile>.dockerignore`, otherwise context-root `.dockerignore`.
   BuildKit does not read arbitrary adjacent `services/*/.dockerignore` files.
   Compare with GHCR latest's revision and the build-job recipe at the central
   commit in that digest's provenance. Output is `would-skip`, `would-build` or
   `would-build (unknown)`. **All builds still run.** Local equivalent:
   `python3 scripts/input-fingerprint.py compare|history --repo ../yueops ...`.
2. `scripts/verification-evidence.py probe`, promotion runs only, looks for
   successful validation with the same central commit, service, full source SHA
   and hosted-runner image version within24hours. **Reuse is disabled and remains
   disabled**: pip-audit/npm audit/pnpm audit findings vary over time, so matching
   identities do not prove safety at promotion time.

Rollback removes the input-shadow job; it has no consumers.

## Buildx tool version

Build, source poll and image rescan share `scripts/install-verified-buildx.sh`.
Linux x86_64 is pinned to v0.37.1 with HTTPS-only download, hardcoded SHA-256
verification before execution and actual `docker buildx version` path verification.
The digest was independently compared with the [official release asset](https://github.com/docker/buildx/releases/tag/v0.37.1)
and same-version checksums.txt. Reuse correct bytes; an old version, failed download
or mismatched digest cannot proceed. Review version/digest changes together;
environment variables cannot override them.

setup-buildx-action normally reuses a preinstalled version; that does not mean it
selects the newest release. After verified installation, the pinned action creates
the pinned OCI BuildKit builder. Poll/rescan need only CLI imagetools and do not
create builders. This build/push reliability change does not require republishing
accepted application images or changing production node APT packages.

## Actions allowlist closure

Settings → Actions → selected-actions must permit direct workflow actions **and
third-party actions invoked inside composite actions**. trivy-action v0.36.0 calls
`aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`. Allowing only the
parent fails at Set up job before scanning. The closure is:

- `anchore/sbom-action@*`
- `aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`
- `aquasecurity/trivy-action@*`
- `astral-sh/setup-uv@*`
- `bufbuild/buf-action@*`
- `docker/build-push-action@*`
- `docker/login-action@*`
- `docker/setup-buildx-action@*`
- `docker/setup-qemu-action@*`
- `sigstore/cosign-installer@*`

On2026-09-27, archived node20 `bufbuild/buf-setup-action` was replaced by
`bufbuild/buf-action` v1.6.0 with `setup_only` and pinned `checksum`. **Before
merging**, add `bufbuild/buf-action@*` to selected-actions or validate-yueboard stops
at Set up job. Remove the old entry only after merging and a passing run:

```sh
gh api -X PUT repos/onesyue/yueto-ci/actions/permissions/selected-actions --input - <<'JSON'
{"github_owned_allowed":true,"verified_allowed":false,"patterns_allowed":[
 "anchore/sbom-action@*","aquasecurity/trivy-action@*","astral-sh/setup-uv@*",
 "docker/build-push-action@*","docker/login-action@*","docker/setup-buildx-action@*",
 "docker/setup-qemu-action@*","sigstore/cosign-installer@*",
 "aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514",
 "bufbuild/buf-setup-action@*","bufbuild/buf-action@*"]}
JSON
```

Retain `github_owned_allowed=true` and `verified_allowed=false`. Workflow source
must still pin every third-party action to a full40-character commit; allowlist
`@*` entries do not authorize mutable tags in source.

## Runner image: ubuntu-24.04 (2026-09-27)

The recorded GitHub migration of ubuntu-latest to Ubuntu26 starts2026-10-19
(actions/runner-images#14748). All GitHub-hosted jobs here, including build/sign,
pin `ubuntu-24.04`; `tests/test_hardening_20260927.py` rejects ubuntu-latest.
A runner-major upgrade requires review of build environment, Python/toolchains
and verification-evidence.py's runner identity together, not implicit label drift.

## Trivy tool version (2026-09-27 C6)

Build jobs hold `id-token: write` for Sigstore and `packages: write`. Runtime
setup-trivy downloads checked only against checksums from the same release lack
an independent anchor. `scripts/install-verified-trivy.sh` pins v0.74.0 and the
Linux-64bit.tar.gz SHA-256, independently compared with the GitHub asset digest and
trivy_0.74.0_checksums.txt. Download is HTTPS-only, verified before execution, added
through `$GITHUB_PATH`, and checked for actual command resolution. All trivy-action
calls (both build platforms and image-rescan) use `skip-setup-trivy: true`. SBOM
still uses anchore/sbom-action's syft; its separate installation path was not
changed in that round.

## Signing identity: master only (2026-09-27 C2)

Production `yueops/scripts/verify-image-signature.sh` accepts only this cosign
identity and SLSA provenance source ref:

```text
^https://github.com/onesyue/yueto-ci/\.github/workflows/build\.yml@refs/heads/master$
```

The former main/master alternative, retained for the2026-08-31 branch rename,
was unsafe when this repository had no main branch or branch protection: anyone
able to create main could sign unreviewed workflow bytes with an accepted identity.
Before tightening, every digest in root release.yaml history, including rollback
predecessors, passed actual signature, two-platform SBOM and provenance checks
under master-only verification. Source refs in services.json and
validation-targets.json likewise allow only master.

## Historical migration note: cosign identity change

Moving builds here changed keyless identity from the source repository's workflow
to `https://github.com/onesyue/yueto-ci/...`. The initial node verifier migration
used this prefix:

```text
^https://github.com/onesyue/yueto-ci/
```

This is historical. Use the exact master-only identity above today. Per-service
migration order was successful central build → update/deploy verifier regexp →
move deployment pin to the central artifact → remove source docker-publish workflow.

## Public repository rules

- Keep logs concise; never echo sensitive configuration/path details. Values
  belong in secrets with Actions masking.
- Upload no public artifacts. Outputs go only to GHCR.
- A writer may manually select `yue-local-release` through workflow_dispatch.
  repository_dispatch and default manual runs use GitHub-hosted runners. The
  workflow bootstraps GNU make and fails closed on actual toolchains before
  validation/build/promotion. Node race tests bootstrap build-essential and enable
  CGO. Signing also needs Debian gettext-base for envsubst. Hosted runners use
  setup-python; Debian13 yue-local-release uses system Python3.13 and verifies its
  exact major/minor before any Python policy. Manual runner state is not evidence
  of a passing bootstrap. Registration must retain the default labels
  `self-hosted`, `Linux`, `X64` and add `yue-local-release`.
  All four must match; the custom label alone must not admit non-Linux/non-x86_64
  hosts into release jobs.
- While this repository is public, do not register a persistent self-hosted runner.
  Never attach a bastion, panel, database or user-traffic node. First make the
  control repository private and establish protected branches and the Actions
  allowlist. Only then use a dedicated Debian13 x86_64 disposable VM, without
  production credentials or production network access, with an
  `--ephemeral --disableupdate` runner. Each runner takes one job; export diagnostic
  logs, then destroy the entire VM and Docker state.

## Measured alert-chain deadman SLO (2026-09-27 C4)

Its cron is `17,47 * * * *`, nominally30minutes, but actual GitHub scheduling does
not guarantee that. Across100 natural schedule runs from2026-09-11 to09-26,
intervals were minimum1.72h, median3.53h, P90 5.36h, maximum6.93h.

- Detection delay is the measured2–7hour schedule gap (median~3.5h), plus the
  45-minute heartbeat threshold. This is supplementary evidence outside the
  panel/bastion failure domain, **not the alert SLA**.
- The SLA authority is the panel's YueOps `panel-alert-chain-deadman.timer`, every
  ten minutes, direct Telegram, VERSION3 issue-code-set deduplication: detection
  ≤45min +10min. See `docs/runbook/panel-alert-chain-deadman.md` in YueOps.
- `--max-age-seconds 2700` is heartbeat freshness, not scheduling frequency.
  The bastion emitter writes every five minutes. Both deadmen use the canonical
  evaluator and contract. Do not relax freshness because GitHub throttles: that
  makes samples less sensitive without making them more frequent.
- Retain the30-minute cron; making it sparser can only increase intervals.

## YueBoard PostgreSQL integration coverage

Central validation runs domain fixtures first against fresh PostgreSQL, then
`clean-pg-gate.sh` in a **separate fresh database in that cluster**, then module
suites serially, then full db/nativeproto migration and production-scale suites.
Migrations first would precreate cluster roles and mask fixture initialization
bugs. Early deviceidentity/nodesync runs would clear public schema needed by
other suites.

`validate-yueboard-postgres.py` discovers integration files/tests using Go build
selection and AST, then reconciles source packages with actual run/pass and
package completion events. Every go test uses
`-count=1 -p 1 -tags integration -json -v` with full job logs. Top-level or subtest
SKIP, missing execution, nonzero exit and newly discovered unscheduled packages
all fail. A run/attempt-specific receipt binds domain and later stages to the
same source manifest. All four DSNs must match and target only loopback
`yueboard_test`; migration-reset confirmation and the production-scale switch
remain mandatory.

Schema floor130 requires all ten current packages. Candidates below130 may
explicitly lack only the historically later user/referencelock/nativeproto
packages. Every discovered suite still runs, with no SKIP exemption. Review
whether new packages rebuild public schema before adding their execution order;
never automatically parallelize or silently omit them. Policy regressions run
real Go test processes covering missing DSNs, real subtest SKIP, early TestMain
exit, empty selectors, unit-only passes, missing packages, changed-source reuse
of stale receipts and failure-log retention, without fabricated Go output.
