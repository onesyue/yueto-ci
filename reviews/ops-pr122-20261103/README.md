# Sequential shared-input admission: #122 then #256

Required merge order: c56159246c31ede8e24b40b8626b6a3c6b0b0137 -> #122 -> #256.
The second seal names the first merge as its predecessor, including the exact
intermediate pyproject and uv.lock blobs. Peel #256 first, then #122, before
running #131's deploy-AI-exit/site-devdeps admission and then historical
admission. The #131 records, historical skip baseline and miniapp seal
(including its prior_baseline_sha256) remain byte-identical.

The records live in ops-shared-input-successors.json, following the miniapp
separate-file pattern. Each new record binds the original skip baseline and the
complete preceding successor file. Its canonical identity is pinned in policy.
After integrating #131 from origin/master, #122 binds the complete master
sidecar and #256 binds that sidecar plus #122. Only these two outer predecessor
hashes and their pinned canonical identities change; source evidence is unchanged.
Admission requires complete bundles, regular-file modes and the first-native
source_revision pin. The planner additionally proves exact merge parent trees
and ancestry. The checked-in first-native pin remains at master; qualification
uses disposable policy copies pinned to each local merge. Real merge commits
with different identities require new source evidence and reviewed records.

Reproduce from this checkout:

```sh
python3 reviews/ops-pr122-20261103/qualification-driver.py /path/to/local/yueops
```

The driver creates only disposable local Git merge objects, checks frozen blobs
and modes, and invokes admission-precheck.py with the full master SHA as base.
It restores no branches because it changes no source branches or working trees.
The source checkout must contain the three PR head objects and pinned master.

| Tree | Before | After |
| --- | --- | --- |
| pinned master | ADMISSION_ACCEPTED | ADMISSION_ACCEPTED |
| master + #122 | ADMISSION_REJECTED | ADMISSION_ACCEPTED |
| master + #122 + #256 | ADMISSION_REJECTED | ADMISSION_ACCEPTED |
| master + #260 | ADMISSION_REJECTED | ADMISSION_REJECTED |

Before sealing, #122 and #256 were rejected for the four changed shared inputs
and the existing ops packaging successor check. #260 remains rejected for
checkin-api/requirements.txt, pyproject.toml and uv.lock. Structured after-results
are in admission-results.json. The source freezes and static qualification
receipts bind exact source trees and dependency changes. This is admission
qualification only: no runtime execution, full collection comparison or
production deployment approval is claimed. Reviews were performed by Codex in
this session, not by a separate independent reviewer.

## #260 disposition: split; no seal

Compared with its merge base, the lock touches these auth/crypto dependencies:

- cryptography 50.0.1 -> 50.0.2 (cryptographic primitives).
- PyJWT 2.15.0 -> 2.15.1 (JWT authentication).
- paramiko 5.0.0 -> 5.1.0 (SSH authentication and encrypted transport).
- certifi 2026.10.19 -> 2026.10.23 (TLS trust roots; security-adjacent).

No dedicated money/payment library changes were found in the changed package
records. SQLAlchemy 2.0.54 -> 2.1.6 and Alembic 1.20.0 -> 1.20.1 also change the
database stack; FastAPI and Starlette change the web/auth integration surface.
Split the auth/crypto changes into focused reviews and qualifications, separate
from observability, tooling and other runtime updates. Database changes warrant
their own schema/transaction qualification. Do not admit the broad #260 bundle
under either successor authored here.

## Policy test result

`python3 -m pytest -q tests`: **622 passed, 5141 subtests passed**.
The run used the existing yueops virtualenv on PATH (system Python has no pytest),
`GOCACHE=/tmp/seal-b-go-cache` (the default cache is read-only in this sandbox),
and process-local Git configuration `commit.gpgsign=false` for test fixture
commits. No repository Git configuration was changed. Negative policy tests
cover partial bundles, mutated blobs/modes/pins, seal-chain tampering, unrelated
history and whole-bundle reversions after a reviewed successor.

## origin/master integration validation

Integrated origin/master `32b399beade5b7f46f6298d0eeef603b10002301` into the
worktree based on `077a1ee221a15f50ac495753bda4fb99ac7d04a6`.
`git merge origin/master` refused to create ORIG_HEAD.lock because Git metadata
is read-only; the resolution is unstaged, with no merge commit or push.
All tests from both branches are retained byte-identically. Removing #256 and
#122 from the sidecar reproduces master's sidecar bytes exactly; #131's validator
functions and identity constants are also byte-identical.

`python -m pytest -q tests`: **628 passed, 5177 subtests passed** (303.52s),
using the same virtualenv, writable Go cache and process-local Git settings above.
The qualification driver was rerun against the combined policy: pinned master,
master + #122 and master + #122 + #256 all returned ADMISSION_ACCEPTED;
master + #260 still returned ADMISSION_REJECTED. Results match
`admission-results.json`. `git diff --check` passed.
