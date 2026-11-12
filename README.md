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
must use the same trusted basis, never the candidate itself. Poll derives a
published ancestor from verified master provenance and OCI revision, choosing
the earliest group member when versions differ; missing evidence fails. Squawk
version/digest, PG15 and rule exclusions remain pinned in the workflow.

## Polling and cache reuse

[poll-sources.yml](.github/workflows/poll-sources.yml) checks private default
branches on a nominal 20-minute schedule. Product groups dispatch candidate
builds only (`promote=false`).
GitHub scheduling is not a delivery guarantee. Root `scripts/kick-builds.sh`
provides an immediate authorized poll after a source push.

The `rearm` job is disabled by default. Enabling it requires `poll-rearm` with
a 20-minute wait and master-only deployment branches, plus repository variable
`YUETO_CI_POLL_REARM=true`; remove that variable to disable it. The script rejects
dispatch before 900 seconds and permits only the newest noncancelled poll to
rearm. It dispatches only poll-sources, preventing duplicate chains; the next poll
retains the product-candidate and static-UI promotion rules above. The environment
wait does not occupy a runner.

The poller groups images from `services.json` and verifies every group member.
Markers use full source SHAs; transitional seven-character markers require an
exact OCI revision match. Registry/network failures cannot masquerade as missing
images. A missing marker avoids a build only when promoted `:latest` has identical
inputs, verified GitHub provenance, the same service/build-job recipe, an ancestral
revision and no floating Dockerfile frontend. Unknown facts cause a normal build,
subject to the SQL baseline. A skip creates no marker or new artifact identity.
See [poll-skip-decision.py](scripts/poll-skip-decision.py).

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

[ops-pytest-skip-baseline.json](ops-pytest-skip-baseline.json) and
[pytest-shards.py](scripts/pytest-shards.py) own exact collection, skip and shared-
input contracts. Reviewed successor records are append-only: they bind specific
source parents, before/after blobs and modes, and prior accepted review/freeze
identities. Unknown paths/blobs, mixed dependency generations, missing history
or resealed inconsistent envelopes fail. Hash syntax does not authenticate a
review; the coordinator verifies its signed source and actual artifacts first.
Historical skips retain their source/run identity. Admission never reuses prior
successful jobs or replaces same-run native, reference, serial and ordinary
execution. Host/root skips are not Linux acceptance.
Before a yueops release, run `python3 scripts/pytest-shards.py skip-blob-precheck --ops-checkout <yueops-checkout> --ops-rev <40-character sha>` and stop if it exits 1: a skip module whose blob changed without a successor seal is what validation-evidence rejects. A yueops commit may carry `tests/admission/ordinary-skip-evidence.json` (schema 1, with non-empty `updates` or `additions`). That commit is the seal: each admitted skip nodeid in the changed module has `before_blob` equal to its admitted blob and `after_blob` equal to the new module blob. One nodeid does not cover its siblings. A missing path adds no successor. Malformed JSON fails the precheck. The SHA-pinned files under `reviews/` remain the historical chain.
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
for builds. Poll/rescan need CLI imagetools only. Trivy actions use the verified
installation with `skip-setup-trivy: true`; SBOM keeps its own Syft path.

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
while hosted jobs use setup-python. Manual runner state is not validation evidence.

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

Run shared-input admission from a trusted, reviewed **yueto-ci** checkout before
requesting a build (the source checkout needs the sealed successor history):

```sh
python3 scripts/admission-precheck.py --repo yueops --source ../yueops --base "$BASE_SHA" --head "$HEAD_SHA"
```

The precheck reads committed Git trees without checking out or executing Ops
code. It calls the build planner's exact shared-input selector, ancestry proof
and admission validator, including `ops-shared-input-successors.json`,
`ops-first-native-successors.json` and historical reviewed seals. A changed
packaging file or shared helper is accepted only if the existing sealed policy
admits that complete tree. Even an unchanged base/head is validated. Exit codes:
**0** admitted, **1** rejected, **2** invalid input or unavailable local evidence.
A rejection names the changed inputs and the seal requirement in `reviews/`.
This checks shared-input admission only; it does not certify all build gates.

The build workflow's `pytest-shards.py expand` emits a single-line
`ADMISSION_REJECTED: <reason>` Actions error annotation and step summary on
rejection. Ship callers can surface that reason instead of reporting “no build
found”. Existing JSON rejection diagnostics remain available.

```sh
python3 scripts/merge-hygiene-audit.py --hours 24
python3 scripts/merge-hygiene-audit.py --hours 24 --format json
```

The audit uses the authenticated `gh api` client and defaults to all seven repos:
`yueops`, `yueboard`, `yueto`, `yueto-ci`, `yuelink`, `yuelink-ci`, `yue-node`.
The credential must be able to read PRs, reviews, checks and statuses in each
repo. It paginates closed PRs and head-commit evidence, looking for absent human
approval, nonpassing or pending checks/statuses **at merge time**. Later reruns
and status successes cannot erase an observed violation. Successful, neutral and
skipped completed check runs follow GitHub's passing conclusions. Missing check
evidence is a finding. Check attempts supersede earlier runs only within the
same app, check suite and job name; runs without suite identity stay independent.
Creation timestamps establish queue timing when available. A postmerge execution
start without creation timing is ambiguous even if an older run passed.
API/input failures exit **2** (incomplete), never clean.
JSON goes to stdout with `complete`, `findings`, and an `unregistered` count;
text is the default. Unregistered findings exit **1**, clean or explicitly
registered findings exit **0**.

Remote evidence is cached under `~/.cache/yueto/merge-hygiene/`
(override with `MERGE_HYGIENE_CACHE_DIR`), keyed by owner/repo, PR number and
`merge_commit_sha` for immutable file comparisons. Reviews, checks and statuses
remain mutable after merge, so every audit revalidates each evidence page and
recomputes findings. Only the file comparison between the same base/head commit
SHAs can skip its API request. Receipts, exception registrations, accepted-history
baseline and activation policy are evaluated each run. Version 2 ignores the old
version 1 verdict snapshots; unavailable evidence exits incomplete even with a
warm cache. The cache contains private repository metadata and should remain
local to the auditing user.

GET responses (including each list page and the activation anchor) store ETags
and bodies. Reruns send `If-None-Match`; authenticated 304 responses reuse the
body without consuming the primary REST quota. Discovery and mutable evidence
still make conditional requests, so a warm audit is not offline. Closed PRs are sorted by
`updated` descending and pagination stops once a page is older than the effective
cutoff, including the receipt-enforcement activation date.

When `X-RateLimit-Remaining` falls below `MERGE_HYGIENE_RATE_FLOOR` (default
`300`), the audit exits **2** with `incomplete: rate-floor`. HTTP 403/429 responses
above that floor get at most two retries, honoring `Retry-After` and exhausted
quota reset times, with 60/120-second fallback backoff. A wait exceeding five
minutes exits incomplete instead of retrying early. HTTP and authentication
diagnostics are never printed.

Historical `merge-hygiene-exceptions.json` entries require
`repo`, integer `pr`, nonempty `reason`, and `approver`; no wildcards. Exceptions
remain visible in both output formats and must be reviewed as policy changes.
GitHub does not retain every overwritten check-run state or review dismissal
state in these REST responses. Ambiguous/missing evidence is reported
conservatively; this retrospective audit cannot prove branch protection or
replace required reviews/checks. These scripts do not add DB schema/grant,
version/tag or live-ship verification gates; those remain separate checks.

### Attach merge receipts from each lane

Receipt enforcement activates at the actual `merged_at` of
[yueto-ci PR #71](https://github.com/onesyue/yueto-ci/pull/71), queried through
GitHub's API on every audit. An unavailable or invalid activation record exits
**2**, never disables enforcement. While #71 is open the historical policy
remains active. PRs merged strictly after that cutoff require a valid committed
`merge-receipts/<repo>/<pr>.json`, even with approving GitHub reviews and green
checks. Exceptions cannot waive any finding for those PRs. Historical exceptions
and #71 itself retain the prior rules. The audit scans back to activation even
when `--hours` is shorter, so an unreceipted merge cannot age out of the gate.
No workflow, scheduled job or paid Actions dispatch is added.

An **evidence-only** PR in `yueto-ci` adds or modifies files exclusively under
`merge-receipts/` or `reviews/merge-receipts-*/`. These PRs stop the
receipt-of-receipt chain: both the audit and `--premerge` waive the receipt
requirement and only the missing approval/check-evidence findings. They still
need normal branch rules; red, pending and unknown checks remain findings.
Clean rows include `"evidence_only": true` and print as `EVIDENCE-ONLY`.
Mixed source/evidence PRs, removed or renamed files, and other repositories use
normal rules. File lists are paginated; API errors, lists of 3,000 or more files,
or a previous filename outside the allowed paths make the audit incomplete.

Before merging a lane's source candidate:

**Required for source PRs: no merge without a committed receipt.** Steps 1–3 must all be done
before pressing merge. A PR comment, a local file or a staged file does not count as a receipt.
For a yueto-ci source PR, open its companion evidence PR (step 4) with the
committed receipt for the frozen head **before** merging the source PR. A merge
without one is a hygiene failure that needs a backfilled receipt PR (e.g.
yueto-ci #72, merged 2026-11-02 with only a comment).

1. Freeze its final PR **head SHA**. Obtain an independent read-only Codex review
   of that exact diff, with an `approve` verdict, and run local parity, for example
   `YUETO_ROOT=/home/box/Projects/yueto /home/box/Projects/yueto/scripts/yt-premerge <repo> <head>`.
   Preserve the actual command-output log and its `sha256sum`; describe any scope
   limitations in the review artifact. A failed review or parity run blocks merge.
2. In a dedicated yueto-ci evidence checkout, commit the review artifact, parity
   log and receipt using the [schema](merge-receipts/README.md). Use
   `backfilled: false` and the actual review/run timestamps. The receipt's review
   and parity heads both equal the frozen candidate head. Evidence must already
   match Git HEAD; staging alone is insufficient.
3. From that evidence checkout, run
   `python3 scripts/merge-hygiene-audit.py --premerge <repo> <pr>`.
   This runs the historical audit plus the candidate gate. It reads the live open
   PR head and checks, requires a committed receipt, rejects backfills/future
   evidence, and never waives red, pending or unknown checks. Any nonzero exit
   blocks merge. Rerun after any head/check change and use GitHub's expected-head
   merge option and normal branch protections to prevent a head race.
4. Publish the evidence through the normal reviewed yueto-ci PR process together
   with the lane's merge handoff. Run the audit again from the evidence checkout
   after the source merge and retain the receipt on yueto-ci master. For a
   yueto-ci source PR, keep its receipt in a **separate companion evidence
   commit/PR**: putting a receipt for a commit into that same commit changes its
   hash. Never regenerate a receipt for an unreviewed new head to solve this.

The gate is a local authenticated command; lanes must invoke it in addition to
repository parity. It does not install GitHub branch protection or modify the
external `yt-premerge` program. Existing hosted policy CI tests the gate behavior
without private-repository credentials. After activation, missing evidence must
be produced before a lane proceeds; new post-cutoff PR exceptions are not a
remediation. An emergency or failed check remains visible and fails the audit.

### Offline Board UA parser gate

The Board `quality` validation row runs the source-owned UA matrix after the
existing full Go quality checks. `scripts/validate-board-ua-cores.sh` prepares
only checksum-verified official archives with `--download-only`, then executes
the entire source gate in Docker with `--network none`. The Board helper also
requires loopback to be the only interface UP, rejects non-loopback routes,
and requires an unprivileged process before forcing offline core
verification. There is no host parser execution or connected fallback.

The runtime is the official Go 1.27.3 multiarch index
`golang@sha256:c292963ad0e5f51e843c726edc204a4e4c26a859ba1e4d736d91028aa3633048`
(AMD64 manifest `sha256:5bbe76a31abbe0f1449d7820e550131c020b097c24d3bcfc5ad1231779982c1c`).
The source toolchain, host cache toolchain and container must agree; a toolchain
change requires reviewing the image pin. Go auto-download and module-network
access are disabled inside the gate. The source is read-only; verified core,
module and compiler caches remain writable for locks and offline compilation.
The temporary tmpfs explicitly permits test-binary execution while retaining
nosuid/nodev. Only fixed non-secret environment settings enter the container. Execution is
bounded to two CPUs, 4 GiB, and an 18-minute attach timeout; cleanup removes only
the container ID created by this invocation. No image is built or published.

The source-owned receipt remains authoritative for coverage: Stash transport
projections do not certify native Stash, and structural-only client rows remain
native-check unavailable. Missing source helpers, incomplete receipt coverage,
invalid archives, unavailable Docker and failed isolation are failures, not
optional skips. This gate requires the companion Board offline-helper change.
