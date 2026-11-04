# yueto PR103: exact-head premerge evidence

Head: `78f831ece1b96ed75c38dd2119b865dae3e63e2c`. Independent reviewer: `/root/board`. Verdict: APPROVE (source scope; later validation independently recorded below). Reviewed at: 2026-11-04T07:39:39.999072+00:00.

Independent source approval by /root/board. Exact-source Linux driver6 plus50 tests passed with zero skips; host50/0skip separately recorded. Initial Linux tmpfs disk admission failure and initial host static skip remain historical; successful final logs do not erase them. No production gate or deployment claim.

Runner schema identity `mac-5f08d00f` denotes the local admitted workstation; parity runs in its documented Linux container. This receipt is premerge, backfilled=false, and does not mark pending/red hosted checks green.

| Original evidence | SHA256 |
|---|---|
| `.claude/state/board-takeover/20261104/resume-1039/root-first-contract-owner-review.json` | `c0af8f64ff65d906203320ba01eb1a65cd0fffb4c4b6a4500787048a6b12ec17` |
| `.claude/state/link-takeover/20261104/1039/first-contract-owner/linux-r2.log` | `c0be9e10bccfe2f06a39b6769c0246412d0efb5aed2d72878ee5e7c4d936250c` |
| `.claude/state/link-takeover/20261104/1039/first-contract-owner/verification.json` | `2e60daebd6fe8b307bd8e00ab7903c56a5094cf8dea87c19056ff65ce666948a` |

Actual command: `bash .claude/state/link-takeover/20261104/1039/first-contract-owner/linux-r2.sh`. ran_at uses the source completion/owner receipt timestamp, not a new execution. Original command-output log bytes remain at the recorded local source path; parity.log_sha256 hashes those bytes. No transcript was reconstructed or redacted. Source tests were not rerun by the evidence lane.

Parity script runs scripts/test-release-chain-drivers.py and pytest for first-contract-transaction, ship-root-no-implicit-detach and ship-builder-identity with the unchanged disk guard. Mutation9 failures against original source are negative-control evidence, not new passing tests.
