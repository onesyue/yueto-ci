# yueboard PR131: exact-head premerge evidence

Head: `6beeaaa23e7a627e45b5d018758c84487c92c2df`. Independent reviewer: `/root/link`. Verdict: APPROVE (source scope; later validation independently recorded below). Reviewed at: 2026-11-04T07:38:51.905874+00:00.

Independent source approval by /root/link. Native Linux Node24.21: actual guard plus4 cases, zero skips, UID1001, network none. Host4/0skip separately recorded. Existing baseline lint findings remain, and new selftest lint passed; this is not blanket lint acceptance.

Runner schema identity `mac-5f08d00f` denotes the local admitted workstation; parity runs in its documented Linux container. This receipt is premerge, backfilled=false, and does not mark pending/red hosted checks green.

| Original evidence | SHA256 |
|---|---|
| `.claude/state/link-takeover/20261104/1039/board-retired-nav-guard-review.json` | `cd75790a706e35c114db937ee027a9b18800216c27218fe82119d8a82613f75c` |
| `.claude/state/board-takeover/20261104/retired-nav-guard/linux-final.log` | `f5042b0adcc54eabdf5cb89d1b4e49cd764629bb9eab5e5e2714e8ba1ff4bdfb` |
| `.claude/state/board-takeover/20261104/retired-nav-guard/candidate.json` | `afea0c91b5566184d404e3cd5391c09704bfdf95a0dac39f8f11e3f61c06bd3d` |

Actual command: `node scripts/ci/verify-page-consistency.mjs && node --test scripts/ci/verify-page-consistency.test.mjs`. ran_at uses the source completion/owner receipt timestamp, not a new execution. Original command-output log bytes remain at the recorded local source path; parity.log_sha256 hashes those bytes. No transcript was reconstructed or redacted. Source tests were not rerun by the evidence lane.
