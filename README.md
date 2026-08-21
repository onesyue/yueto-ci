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
`.github/workflows/alert-chain-deadman.yml` 是只读运维探针，不构建、不发布：每
30 分钟读取 bastion 上的 heartbeat，并调用 YueOps 仓库中的规范判定器；异常只在
私有 YueOps 仓开事故 issue，公开仓不记录生产凭据内容。

```sh
# 手动构建默认只生成经过测试、扫描和签名的 candidate，不改 latest
gh workflow run build.yml -R onesyue/yueto-ci -f service=yueboard
gh workflow run build.yml -R onesyue/yueto-ci -f service=all

# 对远端 YueLink 精确源码提交只跑中央契约校验，不进入镜像构建
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yuelink -f ref=<40-hex-yuelink-sha>

# 只有显式 promote=true 且 ref 解析为源码仓当前默认分支 HEAD 才能提升
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-main-head> -f promote=true

# 私有源码仓默认分支由 poll-sources.yml 每 20 分钟拉取检查；缺少精确
# built-<40-hex> 产物时只触发 candidate 构建，不自动提升 latest。
```

`ref` 可以是完整分支或 tag；如果传 commit，必须传完整 40 位 SHA。GitHub
checkout 不把 7‑39 位短 SHA 当作可复现的 commit ref，中央 plan 会提前拒绝。
`service=all` 同时运行 `services.json` 的服务校验与
`validation-targets.json` 的源码校验；后者不会产生 build matrix。仅校验目标不能
使用 `promote=true`。

`poll-sources.yml` 从 `services.json` 派生仓库/镜像组，逐个验证组内所有镜像。
新产物用完整 40 位源码 SHA 作 marker；迁移期仅在旧 7 位 marker 的 OCI
`org.opencontainers.image.revision` 精确等于当前 HEAD 时才承认已构建。registry
权限或网络错误会 fail closed，不会伪装成“镜像不存在”触发冗余重建。

## 必需的 secrets（仓库 Settings → Secrets → Actions）

- `YUETO_CI_PAT` — classic PAT，勾 `repo` + `write:packages`：checkout 私有代码仓 + 推 GHCR。
  （已有包如 ghcr.io/onesyue/yueboard 归属各代码仓，本仓 GITHUB_TOKEN 推不动，必须用 PAT。）
- `DEADMAN_SSH_KEY_B64` — 专用只读 SSH 私钥的 base64。堡垒机公钥必须以
  `command="/bin/cat /var/lib/yue-alert-heartbeat/heartbeat.json",restrict` 强制命令；
  禁止复用任何 root 部署/轮换私钥。

私有源码仓不再需要 `YUETO_CI_DISPATCH_PAT`；拉取式 poll 使用中央仓已有的
`YUETO_CI_PAT`。`repository_dispatch` 入口仅保留给受控兼容调用，仍由可信 actor、
完整 SHA 和默认分支 HEAD 三重门禁约束。

## Actions 白名单闭包

仓库 Settings → Actions 的 selected-actions 必须覆盖工作流直接调用的动作，也必须覆盖
复合动作内部的第三方调用。`aquasecurity/trivy-action` v0.36.0 会继续调用精确固定的
`aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`；只放行顶层
`trivy-action` 会让镜像任务在 `Set up job` 阶段失败，扫描根本不会开始。当前闭包为：

- `anchore/sbom-action@*`
- `aquasecurity/setup-trivy@3fb12ec12f41e471780db15c232d5dd185dcb514`
- `aquasecurity/trivy-action@*`
- `astral-sh/setup-uv@*`
- `docker/build-push-action@*`
- `docker/login-action@*`
- `docker/setup-buildx-action@*`
- `docker/setup-qemu-action@*`
- `sigstore/cosign-installer@*`

同时保持 `github_owned_allowed=true`、`verified_allowed=false`；工作流本身仍必须把每个
第三方动作固定到完整 40 位提交，白名单里的 `@*` 不等于允许可变 tag 进入源码。

## ⚠️ 迁移注意：cosign 签名身份变更

构建搬到本仓后，Sigstore keyless 签名的 identity 从 `https://github.com/onesyue/<代码仓>/...`
变为 `https://github.com/onesyue/yueto-ci/...`。节点侧部署验签（yueops
`scripts/verify-image-signature.sh` 的 `--certificate-identity-regexp`）必须同步更新为：

```
^https://github.com/onesyue/yueto-ci/
```

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
