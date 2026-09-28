#!/usr/bin/env bash
# poll-sources 的自续链（2026-09-28）：在环境等待计时器之后，再派发一轮 poll。
#
# 为什么：GitHub 自 2026-08-26 起把 schedule 事件大面积延迟/丢弃（社区讨论
# orgs/community#206019、#207346，无官方修复）。本仓实测 poll-sources 的
# `*/20` 从 08-25 的 34 轮/天掉到 08-27 起的 2–6 轮/天、间隔 2.5–6 小时；同仓
# `17,47` 的 deadman 与 `17 2` 的 image-rescan 同样被推迟（后者每天晚 5.5 小时），
# 所以「错开整点」无效，这是平台侧的调度延迟，不是本仓写法问题。
#
# 做法：poll 的 rearm job 绑定 `poll-rearm` 环境；该环境的 wait timer（由仓库管理员
# 设置，建议 20 分钟）让 job 在**不占用 runner** 的情况下等待，然后本脚本用本仓
# GITHUB_TOKEN 派发下一轮 poll-sources（workflow_dispatch 是 GITHUB_TOKEN 允许触发
# 新 run 的明文例外）。整条链默认不启用：仓库变量 YUETO_CI_POLL_REARM=true 才生效。
#
# 两道闸，都 fail closed：
#   1. 距本轮 poll 开始不足 POLL_REARM_MIN_DELAY_S（默认 900s）→ 拒绝派发并报错。
#      环境没配 wait timer（或被删）时 GitHub 会静默自动创建一个空环境、立刻放行，
#      没有这道闸链就退化成每两分钟一轮的死循环。
#   2. 只有「最新的一轮非取消 poll-sources run」可以续链。kick-builds.sh、schedule、
#      上一环各自都会产生 run；旧链在自己的 rearm 处看到有更新的 run 就停下，所以
#      同时存在的链永远收敛到一条，而不是每 kick 一次多一条。读不到 run 列表 = 报错
#      停链（下一次 schedule 会重新拉起），绝不猜「应该续」。
#
# 只派发 poll-sources（它自己永远 promote=false）；不碰 build.yml、不碰任何签名身份。
set -euo pipefail

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${POLL_STARTED_EPOCH:?POLL_STARTED_EPOCH is required}"

min_delay="${POLL_REARM_MIN_DELAY_S:-900}"
now="${POLL_REARM_NOW:-$(date +%s)}"

for value in "$min_delay" "$now" "$POLL_STARTED_EPOCH"; do
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "::error::poll-rearm: non-numeric timing input: ${value}"
    exit 1
  }
done
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]] || {
  echo "::error::poll-rearm: GITHUB_RUN_ID is not a run id"
  exit 1
}

waited=$(( now - POLL_STARTED_EPOCH ))
if [ "$waited" -lt "$min_delay" ]; then
  echo "::error::poll-rearm: only ${waited}s since this poll started (< ${min_delay}s)." \
    "The poll-rearm environment has no (or too short a) wait timer; refusing to" \
    "re-dispatch, otherwise the chain becomes a tight loop."
  exit 1
fi

runs_json="$(gh run list -R "$GITHUB_REPOSITORY" --workflow poll-sources.yml \
  --limit 20 --json databaseId,status,conclusion)" || {
  echo "::error::poll-rearm: cannot list poll-sources runs; stopping the chain (schedule restarts it)"
  exit 1
}
newest="$(jq -r '
  [ .[] | select((.conclusion // "") != "cancelled" and (.conclusion // "") != "skipped") ]
  | (.[0].databaseId // empty) | tostring
' <<<"$runs_json")" || newest=""
[[ "$newest" =~ ^[0-9]+$ ]] || {
  echo "::error::poll-rearm: could not identify the newest poll-sources run; stopping the chain"
  exit 1
}

if [ "$newest" != "$GITHUB_RUN_ID" ]; then
  echo "poll-rearm: newer run ${newest} owns the chain; this chain (${GITHUB_RUN_ID}) stops here"
  exit 0
fi

echo "poll-rearm: waited ${waited}s; dispatching the next poll-sources round"
gh workflow run poll-sources.yml -R "$GITHUB_REPOSITORY" --ref master -f dry_run=false
