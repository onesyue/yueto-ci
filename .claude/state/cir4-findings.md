# I32-E（C13）cir4 验收合同

本车道独占当前工作树中 R4/R7/R5 涉及的 workflow、脚本和对应测试。依据 I32 E 节 R4/R7/R5；I33 的漂移原则要求确认源仓同步契约。本仓未包含 sync-build.sh，检索到的同步脚本属于 yuelink-ci，不是此 build.yml 的源。

完成条件：R4 仅白名单传输错误重试，身份/签名/证明拒绝与未知错误立即失败，最多六次且最后失败不等待；R7 所有 4xx 立即失败，下载次数不超过原上限，摘要门禁保留；R5 拒绝 0（含全零字符串），不新增无依据的 900 秒硬下限。加入 mock 负控及接线约束。保留最终签名和两种 SBOM 验证。测试由 box 执行，Mac 不运行测试、构建或诊断；草稿 PR 不代表门禁通过。

交付：默认 GPG 签名并核对子钥，推当前 PR 分支，开中文草稿 PR；不合并、不部署。待议（Parked）：无。

DONE_WITH_CONCERNS 测试待 box：R4 helper 已接入 sign/attest/verify/两种 verify-attestation；R7 三个脚本及 policy-ci 使用原上限 4/5 次；R5 加入零值负控。现有 Buildx/Trivy 临时夹具同步携带 helper，保留真实摘要错误负控，新增 actionlint 摘要拒绝测试。Mac 未运行测试、lint、构建或语义诊断，未声明通过。待 box 验证命令见草稿 PR。
