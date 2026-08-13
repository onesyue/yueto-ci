#!/usr/bin/env python3
"""Dead man's switch — the DECIDING half. Runs off-box, in GitHub Actions.

Reads the heartbeat receipt that `scripts/alert-chain-heartbeat.sh` publishes on
the bastion and decides whether the alert chain is still alive. Exit non-zero
means "raise the alarm"; the calling workflow's failure is itself the alarm,
delivered by GitHub's own notification email to the account owner.

## Why the decision cannot be made on the bastion

Every alert this fleet has is "shout when something breaks", and twice the thing
that broke was the shouting:

  * 2026-08-02  `/dev/null` became a regular file; 17 units died `226/NAMESPACE`
    including `yue-tg-notify-drain`, the Telegram spool worker.
  * 2026-05-12  `IPAddressDeny` hardening severed the drain unit's egress.

Both faults kill any watcher that shares the box or the transport. So the two
halves are deliberately split across failure domains:

    emitter   bastion systemd timer  → writes a receipt to local disk
    decider   GitHub Actions cron    → SSHes in, reads it, fails the workflow

The decider touches neither systemd, nor the spool, nor the bastion's egress.
When the bastion is gone entirely — the case no bastion-resident watchdog can
ever report — the SSH read fails and that is also a workflow failure.

## Three states, deliberately distinguished

    missing / unreadable  → the emitter never ran, or the host is unreachable
    stale                 → the emitter stopped running at a known time
    status=degraded       → the host is alive but *cannot deliver alerts*

Collapsing these would repeat the mistake this whole exercise is about: a check
whose output is the same whether or not its subject exists is not a check.
Absence is always a failure here, never a pass — there is no "no receipt, so
nothing to complain about" branch.

Usage:
    alert-chain-deadman-check.py --receipt <path> [--max-age-seconds N]
    alert-chain-deadman-check.py --receipt - < receipt.json      # stdin
"""
from __future__ import annotations

import argparse
import json
import sys
import time

# The emitter fires every 5 minutes and the observer polls every 30. The window
# must absorb both periods plus scheduling jitter (GitHub cron is best-effort
# and routinely late by minutes) without absorbing a real outage. 45 minutes =
# ~9 missed heartbeats: unambiguous, and still well inside the 22 minutes it
# took a human to notice the 2026-08-02 outage by eye.
DEFAULT_MAX_AGE_SECONDS = 2700

EXIT_OK = 0
EXIT_ALARM = 1
EXIT_USAGE = 2


class Verdict:
    def __init__(self, state: str, detail: str) -> None:
        self.state = state
        self.detail = detail

    @property
    def alarming(self) -> bool:
        return self.state != "ok"


def evaluate(raw: str | None, *, now: float, max_age_seconds: int) -> Verdict:
    """Pure decision function. `raw is None` means the receipt could not be read."""
    if raw is None:
        return Verdict(
            "missing",
            "心跳凭据读不到：发射端没跑过，或者 bastion 整个够不着。"
            "两种都是告警链已经不可信——「读不到」永远不算通过。",
        )
    stripped = raw.strip()
    if not stripped:
        return Verdict("missing", "心跳凭据是空的（写了一半？发射端被 kill？）")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return Verdict("corrupt", f"心跳凭据不是合法 JSON：{exc}")
    if not isinstance(payload, dict):
        return Verdict("corrupt", "心跳凭据不是一个 JSON 对象")

    epoch = payload.get("epoch")
    if not isinstance(epoch, (int, float)):
        return Verdict("corrupt", "心跳凭据缺少数值型 `epoch` 字段")

    age = now - float(epoch)
    if age > max_age_seconds:
        return Verdict(
            "stale",
            f"心跳已经停了 {int(age)} 秒（阈值 {max_age_seconds} 秒，"
            f"最后一次 seq={payload.get('seq')} ts={payload.get('ts')}）。"
            "alert-chain-heartbeat.timer 停了、bastion 挂了、"
            "或者 /dev/null 那类故障把带 namespace 加固的单元成片打死了。",
        )
    # 未来时间同样可疑：时钟跳变曾让面板铸出「铸出即不可消费」的票（2026-07-27）。
    # 允许一点点时钟偏差，但大幅超前说明凭据不可信，不能当成新鲜。
    if age < -max_age_seconds:
        return Verdict(
            "corrupt",
            f"心跳凭据的时间戳比现在超前 {int(-age)} 秒——时钟漂移或凭据被伪造，"
            "两种都不能当成「新鲜」。",
        )

    status = payload.get("status")
    if status != "ok":
        problems = payload.get("problems")
        detail = "; ".join(problems) if isinstance(problems, list) and problems else "(未列出)"
        return Verdict(
            "degraded",
            f"心跳还在（{int(age)} 秒前），但发射端自报 status={status!r}："
            f"这台机器还活着，**但告警发不出去**。问题：{detail}",
        )

    return Verdict("ok", f"心跳新鲜（{int(age)} 秒前，seq={payload.get('seq')}）")


def _read(path: str) -> str | None:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--receipt", required=True, help="心跳凭据路径，`-` 表示 stdin")
    parser.add_argument(
        "--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS
    )
    args = parser.parse_args(argv)

    if args.max_age_seconds <= 0:
        print("--max-age-seconds 必须为正：非正阈值会让任何心跳都算新鲜", file=sys.stderr)
        return EXIT_USAGE

    verdict = evaluate(
        _read(args.receipt), now=time.time(), max_age_seconds=args.max_age_seconds
    )
    if verdict.alarming:
        print(f"::error::告警链失联[{verdict.state}] {verdict.detail}")
        print(
            "\n这条告警**不经过 bastion 的 Telegram spool**——它就是为了在那条链子"
            "自己死掉的时候还能响。排查顺序：\n"
            "  1. ssh bastion; systemctl status alert-chain-heartbeat.timer\n"
            '  2. stat -c "%F %a %t:%T" /dev/null   # 必须是 character special file 666 1:3\n'
            "  3. systemctl --failed | grep -c 226  # 成片 226/NAMESPACE = /dev/null 被换掉了\n"
            "  4. systemctl status yue-tg-notify-drain.service\n"
            "  5. cat /var/lib/yue-alert-heartbeat/heartbeat.json",
            file=sys.stderr,
        )
        return EXIT_ALARM
    print(f"alert-chain deadman: ok — {verdict.detail}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
