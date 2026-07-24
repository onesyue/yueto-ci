# yueto-ci

Yue.to 服务端组件的**统一构建仓**。本仓库公开（公开仓 GitHub Actions 免费、无分钟上限），只含构建脚本，不含业务代码；私有代码仓由 PAT checkout，产物只推 `ghcr.io/onesyue/*`，不留 artifacts。

客户端（yuelink）构建在 [yuelink-ci](https://github.com/onesyue/yuelink-ci)，与本仓并列，即"两个构建仓"架构。

## 覆盖的服务

见 `services.json`：yue-node、yueops-web、checkin-api、yue-bot、yueboard。增删服务改这一个文件即可。

## 触发

```sh
# 手动构建默认只生成经过测试、扫描和签名的 candidate，不改 latest
gh workflow run build.yml -R onesyue/yueto-ci -f service=yueboard
gh workflow run build.yml -R onesyue/yueto-ci -f service=all

# 只有显式 promote=true 且 ref 解析为源码仓当前默认分支 HEAD 才能提升
gh workflow run build.yml -R onesyue/yueto-ci \
  -f service=yueboard -f ref=<40-hex-main-head> -f promote=true

# 代码仓默认分支 push 后自动触发并提升：在代码仓放 thin workflow
# （计费落在公开仓；发送者、精确 SHA、默认分支 HEAD 均由中央门复核）
```

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
- **绝不给本仓挂 self-hosted runner**（公开仓 fork PR 可在 runner 上执行任意代码）。
