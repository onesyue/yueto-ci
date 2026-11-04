# yueto-ci PR261: exact-head premerge evidence

Head: `a17d2b4aa9f9e5fab300b2d621df349833b81626`. Independent reviewer: `/root/board`. Verdict: APPROVE (source scope; later validation independently recorded below). Reviewed at: 2026-11-04T06:49:53.332467+00:00.

Independent source approval by /root/board. Linux actual admission precheck plus four complete modules:10+9+7+6=32 cases, zero skips; private source history present. Hosted policy is711 passed/1 skipped, NOT zero skips. The Linux modules supply the missing source-availability coverage; this is not a repeated full suite or Ops full-release acceptance.

Runner schema identity `mac-5f08d00f` denotes the local admitted workstation; parity runs in its documented Linux container. This receipt is premerge, backfilled=false, and does not mark pending/red hosted checks green.

| Original evidence | SHA256 |
|---|---|
| `.claude/state/board-takeover/20261104/resume-1039/ops-ef8-pin-review.json` | `669200934be24fb18a0ea523168f98bef8ca466d8ba381547847295cd7b47e0b` |
| `.claude/state/takeover/20261104/resume-1039/ops-ef8-pin-linux/module.log` | `fb21158e1009e76a3fb6c184789b8adb1e1a3ca34a160e1a92f0c1dc85be567f` |
| `.claude/state/takeover/20261104/resume-1039/ops-ef8-pin-linux/receipt.json` | `27d977cf9194be4492159c7327e554da5436061727c141b5795b87f529b4830b` |

Actual command: `bash .claude/state/takeover/20261104/resume-1039/ops-ef8-pin-linux/run.sh`. ran_at uses the source completion/owner receipt timestamp, not a new execution. Original command-output log bytes remain at the recorded local source path; parity.log_sha256 hashes those bytes. No transcript was reconstructed or redacted. Source tests were not rerun by the evidence lane.

Hosted original policy log: `.claude/state/takeover/20261104/resume-1039/ops-ef8-pin-hosted-policy.log`, SHA256 `1bc919bde03a8c6e14b3ab90c6cfcf224524159a88c556a9a5a10d793677440f`;711 passed/1 skipped is retained separately. The local32-case command is original Linux container execution, not hosted evidence. Reviewed pin target remains ef8d04dc42f4a15f7f4170318b8f944f34a94bcb.
