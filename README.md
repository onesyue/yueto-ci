# yueto-ci

Yue.to 服务端组件的**统一构建仓**。本仓库公开（公开仓 GitHub Actions 免费、无分钟上限），只含构建脚本，不含业务代码；私有代码仓由 PAT checkout，产物只推 `ghcr.io/onesyue/*`，不留 artifacts。

客户端（yuelink）构建在 [yuelink-ci](https://github.com/onesyue/yuelink-ci)，与本仓并列，即"两个构建仓"架构。

## 覆盖的服务

可构建镜像见 `services.json`：yue-node、yueops-web、checkin-api、yue-bot、
yueboard。只做跨仓源码契约校验、不应构建镜像的产品见
`validation-targets.json`；目前包含 YueLink。两份清单刻意分离，避免客户端被误送入
Docker 构建矩阵。

## 触发

本仓只有一个发布工作流：`.github/workflows/build.yml`。Promotion 不是独立
workflow，而是该工作流在完成校验、构建、签名和证明后的最后一个受控步骤。

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

# 代码仓默认分支 push 后自动触发并提升：在代码仓放 thin workflow
# （计费落在公开仓；发送者、精确 SHA、默认分支 HEAD 均由中央门复核）
```

`ref` 可以是完整分支或 tag；如果传 commit，必须传完整 40 位 SHA。GitHub
checkout 不把 7‑39 位短 SHA 当作可复现的 commit ref，中央 plan 会提前拒绝。
`service=all` 同时运行 `services.json` 的服务校验与
`validation-targets.json` 的源码校验；后者不会产生 build matrix。仅校验目标不能
使用 `promote=true`。

代码仓 thin workflow 模板（`.github/workflows/trigger-build.yml`）：

```yaml
name: Trigger yueto-ci build
on:
  push:
    branches: [main] # 按仓库主分支改
jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: peter-evans/repository-dispatch@ff45666b9427631e3450c54a1bcbee4d9ff4d7c0 # v3.0.0
        with:
          token: ${{ secrets.YUETO_CI_DISPATCH_PAT }}
          repository: onesyue/yueto-ci
          event-type: build
          client-payload: '{"service": "<本服务名>", "ref": "${{ github.sha }}", "before": "${{ github.event.before }}", "promote": true}'
```

## 必需的 secrets（仓库 Settings → Secrets → Actions）

- `YUETO_CI_PAT` — classic PAT，勾 `repo` + `write:packages`：checkout 私有代码仓 + 推 GHCR。
  （已有包如 ghcr.io/onesyue/yueboard 归属各代码仓，本仓 GITHUB_TOKEN 推不动，必须用 PAT。）
- 各代码仓需要 `YUETO_CI_DISPATCH_PAT` — 归属可信 `onesyue` actor 的
  fine-grained PAT，只授 yueto-ci 发 repository dispatch 所需的最小权限。
  中央 workflow 会拒绝其他 actor 发起的自动提升。

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
  `build-essential`并显式启用 CGO。GitHub-hosted runner 使用 `setup-python`；
  Debian 13 的 `yue-local-release` 使用系统 Python 3.13，且在执行任何 Python
  policy 前验证精确主/次版本。不接受依赖 runner 手工状态的隐式通过。
