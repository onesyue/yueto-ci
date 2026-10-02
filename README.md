# yueto-ci

Yue.to 服务端组件的**统一构建与外部控制仓**。本仓库公开（公开仓 GitHub Actions 免费、无分钟上限），不含业务代码；私有代码仓由 PAT checkout，产物只推 `ghcr.io/onesyue/*`，不留 artifacts。它也承载必须脱离生产主机、且不能被私有 Actions 计费冻结拖死的告警链 dead-man 观察者。

客户端（yuelink）构建在 [yuelink-ci](https://github.com/onesyue/yuelink-ci)，与本仓并列，即"两个构建仓"架构。

## 覆盖的服务

可构建镜像见 `services.json`：yue-node、yueops-web、checkin-api、yue-bot、
yueboard。只做跨仓源码契约校验、不应构建镜像的产品见
`validation-targets.json`；目前包含 YueLink。两份清单刻意分离，避免客户端被误送入
Docker 构建矩阵。

## 触发

本仓只有一个发布工作流：`.github/workflows/build.yml`。Promotion 不是独立
workflow，而是该工作流在完成校验、构建、签名和证明后的最后一个受控步骤。
`.github/workflows/alert-chain-deadman.yml` 是只读运维探针，不构建、不发布：读取
bastion 上的 heartbeat，并调用 YueOps 仓库中的规范判定器；异常只在私有 YueOps 仓开
事故 issue，公开仓不记录生产凭据内容。它是**补充的异域证据，不承担告警 SLA**——
真实调度节奏与 SLO 见下文「告警链 deadman 的真实 SLO」。
`.github/workflows/image-rescan.yml` 每天重扫生产可能在跑的镜像：每个服务的 `:latest`
加上最近 3 个 `promoted-<rev>-<digest>` 标记的 digest（当前、回滚前任、再前一个，
覆盖部署落后于 `:latest` 的窗口；`scripts/plan-rescan-targets.py`），按声明的每个生产
平台用校验过 sha256 的 Trivy 0.74.0 扫。生产的权威期望是根仓 `release.yaml` 的
`desired`，但根仓私有、本仓刻意不持有它的凭据，所以用 registry 侧的 promote 标记代替；
枚举失败一律 fail closed。任一 plan/scan 失败或取消都在私有 YueOps 仓开（或追评）同一个
去重 issue「🛡️ 已发布镜像复扫失败（image-rescan）」，走与 deadman 相同的 App token /
PAT 兜底路径。它不 checkout 私有源码、不写 registry、不上传公开 artifact。
枚举按 [GitHub REST 分页](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
每页 100 条逐页读取完整版本集合，再选择最近的 promote 标记；请求始终固定在已评审的
owner/package，不直接跟随携带凭据的 Link URL。最多 100 页；满页即使没有 Link 也继续
探测终页。重复版本、异常分页、HTTP 失败或达到上界仍无法证明枚举完整时明确失败，
不会把前 100 条当作全部版本而漏扫回滚镜像。

```sh
# YueBoard 未 pin HEAD 只做验证，零 registry 写；精确 pin 才构建 candidate
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin>
gh workflow run build.yml -R onesyue/yueto-ci -f service=all \
  -f migration_base=<40-hex-trusted-yueops-previous-revision>

# 对远端 YueLink 精确源码提交只跑中央契约校验，不进入镜像构建
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yuelink -f ref=<40-hex-yuelink-sha>

# 只有显式 promote=true、ref 在默认分支上且本镜像构建输入与 HEAD 相同、不比 :latest 旧
# （P2 #11，scripts/promote-source-gate.py，改标签前再判一次），且 YueBoard ref 精确等于
# native-node-contract.json 的已评审 yueboard_contract_pin，才能提升
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-reviewed-contract-pin> -f promote=true

# 私有源码仓默认分支由 poll-sources.yml 拉取检查（cron 写 20 分钟，实际见下文
# 「poll 的真实节奏」）；缺少精确 built-<40-hex> 产物时只触发 candidate 构建，
# 不自动提升 latest。
```

`ref` 可以是完整分支或 tag；如果传 commit，必须传完整 40 位 SHA。GitHub
checkout 不把 7‑39 位短 SHA 当作可复现的 commit ref，中央 plan 会提前拒绝。
**`promote=true` 时 `ref` 必须是完整 40 位 SHA**（2026-09-27 C3，任何事件类型）：
validate 与 build 是两个相隔数分钟的 job，各自 checkout；分支/tag/空 ref（即注册表里的
`master`）可能在两者之间移动，镜像就会建自 validate 从没判过的提交。`ship.sh` 一直传
`git rev-parse HEAD`，不受影响。promote 还必须从本仓 `refs/heads/master` 运行——那是
生产验签唯一接受的签名身份（见下文）。
YueBoard 的未 pin 默认分支 HEAD 仍可用 `promote=false` 做完整验证，日志会明确
标为 `non-promotable`，并从 build matrix 剔除，因此不会登录 registry、构建镜像或
写 candidate / `built-*` / `sha-*` / `latest`。只有先通过签名的跨仓 pin 收敛把
`yueboard_contract_pin` 精确推进到该 40 位 SHA，candidate 构建和 promotion 才可运行。
`service=all` 同时运行 `services.json` 的服务校验与
`validation-targets.json` 的源码校验；后者不会产生 build matrix。仅校验目标不能
使用 `promote=true`。

YueOps（含单镜像和 `all`）必须显式传 `migration_base=<完整40位SHA>`：SQL lint
检查该基线到候选的整批变更，基线必须存在且为候选祖先；删除/重命名 SQL 也会拒绝。
没有 `HEAD^` 或全历史扫描兜底。工作区 `scripts/ship.sh yueops` 自动从当前验签成功的
`release.yaml` desired 读取上一版本并传入。手动验证须使用同一可信基线，不要为了
消除报错把候选自身当作上一版本。poll 从已有镜像的已验证 master provenance 和
OCI revision 取得已发布祖先，组内版本不同时取最早者；取不到则明确失败，下一轮重试。
Squawk 2.60.0 固定 SHA-256、PG15 与原规则豁免保持不变。

### poll 的真实节奏与自续链（2026-09-28）

GitHub 自 2026-08-26 起大面积推迟/丢弃 schedule 事件（社区讨论 orgs/community#206019、
#207346，无官方修复）。本仓实测 `poll-sources` 自然 schedule run：08-24 28 轮、08-25 34 轮，
08-27 起每天 2–6 轮，09-18→09-28 间隔 2.5–6 h；同仓错开整点的 deadman（`17,47`）与
image-rescan（`17 2`，每天晚约 5.5 h）同样被推迟，所以不是「整点拥堵」，改分钟无效。

两条补救，互不排斥：

- 人手推完私仓后跑根仓 `scripts/kick-builds.sh`（立即派发一轮，走本机 `gh` 身份）。
- **自续链（默认关闭）**：`poll-sources.yml` 的 `rearm` job 在 `poll-rearm` 环境的
  wait timer 里等待（不占 runner），然后由 `scripts/poll-rearm.sh` 用本仓 `GITHUB_TOKEN`
  再派发一轮 poll（只派发 poll-sources，`promote` 恒为 false，与签名身份无关）。启用需要
  仓库管理员：① 建环境 `poll-rearm`，Wait timer = 20 分钟，Deployment branches 仅
  `master`；② 设仓库变量 `YUETO_CI_POLL_REARM=true`。停用：删变量即可。
  fail closed 的两道闸：距 poll 开始不足 900 s（计时器缺失时 GitHub 会自动建一个空环境
  立即放行）拒绝派发；只有最新的非取消 poll run 可以续链，旧链自行终止，kick 与 schedule
  不会让链越来越多。行为测试：`tests/test_poll_rearm_policy.py`（假 `gh` 真跑脚本）。

`poll-sources.yml` 从 `services.json` 派生仓库/镜像组，逐个验证组内所有镜像。
新产物用完整 40 位源码 SHA 作 marker；迁移期仅在旧 7 位 marker 的 OCI
`org.opencontainers.image.revision` 精确等于当前 HEAD 时才承认已构建。registry
权限或网络错误会 fail closed，不会伪装成“镜像不存在”触发冗余重建。

P3（2026-09-24）：缺 marker 的镜像若与已 promote 的 `:latest` **构建输入完全相同**——
先用 `gh attestation verify` 验过它的 build provenance、recipe（services.json 条目 + build job
文本）未变、promoted revision 是 HEAD 的祖先、Dockerfile 没有浮动 `# syntax=` frontend——
就不派发它的构建（`scripts/poll-skip-decision.py`）。任何一项测不到都照常构建
（YueOps 仍须先证明上述 SQL 基线）；跳过不打
`built-*` 标签（旧产物保留原来的源码身份），下一轮 poll 会再问一次。

## 必需的 secrets（仓库 Settings → Secrets → Actions）

- `YUETO_CI_PAT` — classic PAT，勾 `repo` + `write:packages`：checkout 私有代码仓 + 推 GHCR。
  （已有包如 ghcr.io/onesyue/yueboard 归属各代码仓，本仓 GITHUB_TOKEN 推不动，必须用 PAT。）
- `DEADMAN_SSH_KEY_B64` — 专用只读 SSH 私钥的 base64。堡垒机公钥必须以
  `command="/bin/cat /var/lib/yue-alert-heartbeat/heartbeat.json",restrict` 强制命令；
  禁止复用任何 root 部署/轮换私钥。

### CI 凭据迁移：classic PAT → GitHub App + GITHUB_TOKEN（2026-09-23 起，零停机开关）

`YUETO_CI_PAT` 是 classic、`repo` 全权限：本公开仓任一 workflow 被改坏，它对**全部私仓可写**。
工作流已改成「开关优先、PAT 兜底」，业主在控制台做完下面的事、设好变量即切换，不需要改代码：

| 用途 | 位置 | 迁移后凭据 | 最小权限 |
|---|---|---|---|
| 读 yueboard 提交 SHA（plan） | build.yml `plan` | App token | yueboard `contents:read` |
| checkout 源码 + YueBoard 契约 | build.yml `validate` / `build` | App token | yueboard / yue-node / yueops / yuelink `contents:read` |
| yue-node 私有 fork tag 校验 | build.yml `Verify yue-node signed fork tags`（**只有这一步**持有；跑 `go test` 的 `Validate yue-node` 不带任何凭据，依赖 vendored，`GOFLAGS=-mod=vendor`） | App token | quic-go `contents:read` |
| promote 前复核默认分支 HEAD | build.yml promote（**现签**一枚，因为 build job 可跑两小时而 App token 一小时过期） | App token | 三个服务源码仓 `contents:read` |
| GHCR 推送 / 签名 / provenance | build.yml `Login to GHCR` | 本仓 `GITHUB_TOKEN`（`packages: write`） | 每个 package 授予 yueto-ci **Write** |
| GHCR 读 | poll-sources / image-rescan | 本仓 `GITHUB_TOKEN`（`packages: read`） | 每个 package 授予 yueto-ci **Read** 以上 |
| 读三个源码仓 HEAD | poll-sources `scan` | App token | `contents:read` |
| 派发本仓 build.yml | poll-sources `Trigger builds` | 本仓 `GITHUB_TOKEN`（`actions: write`；workflow_dispatch 是 GITHUB_TOKEN 允许触发新 run 的例外） | — |
| deadman 读 YueOps 判定器 | alert-chain-deadman | App token | yueops `contents:read` |
| deadman 开事故 issue | alert-chain-deadman | 单独签发的 App token | yueops `issues:write` |

GitHub App 不能认证 GHCR，所以 registry 那一半走本仓 `GITHUB_TOKEN`，前提是每个 package 在
**Package settings → Manage Actions access** 里把 `onesyue/yueto-ci` 加进来。

两个开关（Settings → Secrets and variables → Actions → **Variables**）：

- `YUETO_CI_APP_CLIENT_ID`（+ secret `YUETO_CI_APP_PRIVATE_KEY`）：非空即所有源码读取改用 App token；
  签发失败让 job 失败，**不会**静默回退 PAT。
- `YUETO_CI_GHCR_VIA_GITHUB_TOKEN=true`：GHCR 登录改用本仓 `GITHUB_TOKEN`。

两个都开并跑绿一轮（poll / build 候选 / 一次 promote / rescan / deadman 演练）后，删除 secret
`YUETO_CI_PAT` 并在 GitHub 撤销该 classic PAT。任何一处裸用 PAT 都会被
`tests/test_credential_policy.py` 拦下。App 的创建步骤见根仓
`docs/2026-09-23-ci-credential-migration.md`。

私有源码仓不再需要 `YUETO_CI_DISPATCH_PAT`；拉取式 poll 使用中央仓已有的
`YUETO_CI_PAT`。`repository_dispatch` 入口仅保留给受控兼容调用，仍由可信 actor、
完整 SHA 和默认分支 HEAD 三重门禁约束。

## promote 的记录：根仓 `release.yaml` 不由本仓写

2026-09-14 起，「哪个 revision / digest 已 promote」的唯一真源是工作区根仓
`onesyue/yueto` 的 `release.yaml`。它由工作站 `scripts/ship.sh` 在拿到 promote 步骤的
digest、并通过签名/SBOM/provenance 三门验签之后写入、**签名**提交、推送
（`scripts/release-yaml.py verify` 再把记录与 GHCR `sha-<revision>` / `latest` 比对）。
本仓的 promote 步骤刻意**不**写任何仓，理由：根仓是私有免费档、无 ruleset 可强制签名，
CI 机器人写不出业主签名的提交；`YUETO_CI_PAT` 的 `repo` scope 对全部私仓可写，本仓
迄今一次都没用它写过——第一条「用它推私仓」的步骤会把爆炸半径扩到全部私仓；
yueops group 派发的三个矩阵 job 并行 promote，三处同时提交根仓必然互撞。
`tests/test_build_policy.py::test_promotion_records_nothing_in_the_workspace_root_repo`
钉住这一条：workflow 里不得出现 git commit/push、根仓 contents 写 API 或 `release.yaml`，
而 promote 步骤的 `DIGEST` / `SOURCE_SHA` / `IMAGE` env 锚点必须保留（那是 ship.sh 的输入）。

## 影子分析 `input-shadow`：只报告，不跳过（2026-09-24 起）

`build.yml` 的 `input-shadow` job 与验证并行，**没有任何 job `needs` 它**，
`continue-on-error: true`，权限全是 read。它做两件事，都只写 annotation 和 step summary：

1. `scripts/input-fingerprint.py shadow-ci`：对每张镜像，按 Dockerfile 实际的
   `COPY`/`ADD`/bind 源 + **生效的** ignore 文件（`<Dockerfile>.dockerignore`，否则
   上下文根 `.dockerignore`；`services/*/.dockerignore` 这种同目录文件 BuildKit 不读）
   算输入指纹，与 GHCR `:latest` 的 revision 比较；再从该 digest 的 GitHub build
   provenance 取出构建它的本仓 commit，比较 build job 文本（recipe）。输出
   `would-skip` / `would-build` / `would-build (unknown)`。**任何构建都照常执行。**
   本地同一实现：`python3 scripts/input-fingerprint.py compare|history --repo ../yueops ...`。
2. `scripts/verification-evidence.py probe`（仅 promote run）：检查是否存在同一本仓
   commit、同一 service、同一 40 位源码 SHA、同一 hosted runner 镜像版本、24 小时内
   的成功验证。**复用是关闭的，且本轮结论是不开**：validate 里的 pip-audit / npm audit /
   pnpm audit 结论随时间变化，身份再一致也不能代表 promote 时刻的结果。

回滚：删掉 `input-shadow` job（没有消费者，删除零影响）。

## Buildx 工具版本

构建、source poll、镜像重扫三个真实 Buildx 消费者共用
`scripts/install-verified-buildx.sh`：Linux x86_64 固定 v0.37.1，下载前限制
HTTPS、执行前核对硬编码 SHA-256，再通过实际 `docker buildx version` 验证解析路径。
摘要来自 [官方发布资产](https://github.com/docker/buildx/releases/tag/v0.37.1)
与同版 `checksums.txt` 的独立对照。已有正确字节直接复用；旧版、下载失败或摘要不符
不能继续构建。版本/摘要变更必须一起评审，环境变量不能覆盖它们。

setup-buildx-action 默认复用 runner 已装版本是正常行为，不代表自动选择最新版。
安装器先完成验证，原固定 action 才创建固定 OCI BuildKit builder；只做 imagetools
的 poll/重扫仅安装 CLI，不创建多余 builder。这是构建/推送可靠性更新，不要求重发
已验收应用镜像，也不改变生产节点 APT 包清单。

## Actions 白名单闭包

仓库 Settings → Actions 的 selected-actions 必须覆盖工作流直接调用的动作，也必须覆盖
复合动作内部的第三方调用。`aquasecurity/trivy-action` v0.36.0 会继续调用精确固定的
`aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`；只放行顶层
`trivy-action` 会让镜像任务在 `Set up job` 阶段失败，扫描根本不会开始。当前闭包为：

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

2026-09-27：`bufbuild/buf-setup-action`（已归档、声明 node20）换成继任者
`bufbuild/buf-action` v1.6.0（`setup_only` + 固定 `checksum`）。**合入前**必须先把
`bufbuild/buf-action@*` 加进仓库 selected-actions（不加则 validate-yueboard 停在
`Set up job`），合入并跑绿后再删掉旧的 `bufbuild/buf-setup-action@*`：

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

同时保持 `github_owned_allowed=true`、`verified_allowed=false`；工作流本身仍必须把每个
第三方动作固定到完整 40 位提交，白名单里的 `@*` 不等于允许可变 tag 进入源码。

## Runner 镜像：钉 ubuntu-24.04（2026-09-27）

GitHub 自 2026-10-19 起把 `ubuntu-latest` 迁到 Ubuntu 26（actions/runner-images#14748）。
本仓所有 GitHub-hosted job（含镜像构建与签名 job）都钉 `ubuntu-24.04`，
`tests/test_hardening_20260927.py` 拒绝任何 `ubuntu-latest`。升级 runner 大版本是一次
评审过的改动（构建环境、系统 Python/工具链、`verification-evidence.py` 的 runner 类判据
要一起动），不许由 GitHub 的标签漂移替我们做。

## Trivy 工具版本（2026-09-27 C6）

build job 持有 `id-token: write`（Sigstore keyless 签名）与 `packages: write`。trivy-action
自带的 setup-trivy 在运行时下载 Trivy，只拿同一个 release 里的 checksums 文件核对——同源
校验，等于没有独立锚点。现在与 Buildx / actionlint 同一做法：
`scripts/install-verified-trivy.sh` 固定 v0.74.0、硬编码 `Linux-64bit.tar.gz` 的 SHA-256
（GitHub release 资产 digest 与同版 `trivy_0.74.0_checksums.txt` 独立对照一致），HTTPS-only
下载、执行前核对、经 `$GITHUB_PATH` 前置并验证实际解析到的就是它；所有 trivy-action 调用
（build 两个平台 + image-rescan）都 `skip-setup-trivy: true`。SBOM 仍由 anchore/sbom-action
自带的 syft 生成（未改：它的安装路径另议）。

## 签名身份：只认 master（2026-09-27 C2）

生产验签（yueops `scripts/verify-image-signature.sh`）的 cosign 身份与 SLSA provenance
`--source-ref` 已收紧为单一
`^https://github.com/onesyue/yueto-ci/\.github/workflows/build\.yml@refs/heads/master$`。
此前为 2026-08-31 默认分支改名保留的 main/master 二选一，在本仓**没有 main 分支、也没有
分支保护**的现状下是一个真实入口：谁能在本仓建一个叫 main 的分支，谁就能用未评审的
workflow 字节签出生产接受的身份。收紧前对根仓 `release.yaml` 全部历史里出现过的每一个
digest（含所有可回滚前任）用 master-only 版本逐个真跑了签名 + 2×SBOM + provenance。
`services.json` / `validation-targets.json` 的源码 ref 同样只允许 `master`。

## ⚠️ 迁移注意：cosign 签名身份变更

构建搬到本仓后，Sigstore keyless 签名的 identity 从 `https://github.com/onesyue/<代码仓>/...`
变为 `https://github.com/onesyue/yueto-ci/...`。节点侧部署验签（yueops
`scripts/verify-image-signature.sh` 的 `--certificate-identity-regexp`）必须同步更新为：

```
^https://github.com/onesyue/yueto-ci/
```

（历史记录。今天的精确锚点见上文「签名身份：只认 master」。）

迁移顺序（每个服务）：本仓构建成功 → 验签脚本 regexp 更新并部署 → 切换部署 pin 到本仓产出的 tag → 删除代码仓里的旧 docker-publish workflow。

## 公开仓纪律

- 日志保持简洁，绝不回显配置/路径细节；敏感值一律走 secrets（Actions 自动打码）。
- 不产出 artifacts（公开仓 artifacts 任何人可下载），产物只进 GHCR。
- Self-hosted runner 仅能通过有写入权限的人员手动 `workflow_dispatch`
  并显式选择 `yue-local-release`；代码仓 `repository_dispatch` 与默认手动运行
  仍使用 GitHub-hosted runner。工作流会自举 GNU make，并在校验、构建和
  promotion 前对实际工具链 fail closed。YueNode 的 race 门禁会自举
  `build-essential`并显式启用 CGO；镜像签名阶段还要求 Debian 的
  `gettext-base`（提供 `envsubst`）。GitHub-hosted runner 使用 `setup-python`；
  Debian 13 的 `yue-local-release` 使用系统 Python 3.13，且在执行任何 Python
  policy 前验证精确主/次版本。不接受依赖 runner 手工状态的隐式通过。
  注册时必须同时保留默认 `self-hosted`、`Linux`、`X64` 标签并添加唯一自定义
  标签 `yue-local-release`；四个标签必须全部匹配，不能只靠可误贴的自定义标签
  把非 Linux 或非 x86_64 主机送入发布任务。
- 安全前置：本仓保持 public 时不得注册常驻 self-hosted runner，更不得把堡垒机、
  面板、数据库或承载用户流量的业务节点接成 runner。只有先把控制仓改为 private、
  完成受保护分支与 Actions 白名单门禁后，才能在无生产凭据和生产网络访问权的
  专用 Debian 13 x86_64 一次性虚机上启用 `--ephemeral --disableupdate` runner；
  每个 runner 只领取一个 job，并在外送诊断日志后销毁整台虚机和 Docker 状态。

## 告警链 deadman 的真实 SLO（2026-09-27 C4 实测）

`alert-chain-deadman.yml` 的 cron 写的是 `17,47 * * * *`（每 30 分钟），**GitHub 实际不按它
跑**。2026-09-11 → 09-26 连续 100 次自然 schedule run 的间隔：最短 1.72 h、中位 3.53 h、
P90 5.36 h、最长 6.93 h。所以：

- 本观察者的检测延迟 = 调度间隔（实测 ~2–7 h，中位 ~3.5 h）+ 心跳阈值 45 min。它是
  **补充的异域证据**（面板机与 bastion 同时失联时仍能从 GitHub 侧看见），不承担告警 SLA。
- **告警 SLA 的权威是面板机上的 `panel-alert-chain-deadman.timer`**（yueops，每 10 分钟，
  直连 Telegram，VERSION 3 按问题码集合去重）：检测延迟 ≤ 45 min + 10 min。见 yueops
  `docs/runbook/panel-alert-chain-deadman.md`。
- `--max-age-seconds 2700` **不是**调度间隔，而是 bastion 心跳 receipt 的新鲜度阈值
  （emitter 每 5 分钟写一次），与面板机 deadman 共用同一个 canonical 判定器与契约；它不应
  随 GitHub 节流放宽——放宽只会让每次抽样更迟钝，而不会让抽样更频繁。
- cron 仍保留 30 分钟：GitHub 只会少跑、不会多跑，写得稀疏只会让间隔更长。
