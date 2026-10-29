# B 层独立审查回执：release skip blob successors

结论：APPROVE（技术内容，304 条逐条 approve）。

日期：2026-10-29。审查角色：独立审查者。任务：xrev-hang2，接续 xrev-hang。

## 审查对象与证据

- 候选基点：56e97e22f20137fad8396aa7cbf844bb8baceaa0。
- 待审 diff SHA-256：c59dd85f748cc6b6d551e41b7b1a3b6498fe44aaa7b2ddd321f735d4ff9cdd82；证据文件：review-out/under-review.diff。本轮确认当前 staged diff 与该文件逐字节相同，且无 unstaged tracked diff。
- run_id：40578720805；run_attempt：1。
- source_before：8ffdedad24dcb23ca0c33a05ea0ea889cbdab0fe。
- source_after：d9c302e126c039e90b5f34c82b796582b1e367e8。
- 独立逐条核对：review-out/independent-verification.json；文件 SHA-256：830a12fd2d0104b03166feb76f8918eb57d7ea53cc297e2f0e8e324134844174。
- 原始 validation evidence：review-out/ops-validation-evidence-40578720805-1.json；文件 SHA-256：ddee18466eeb1d58b28fe1c5775ff48dcef8cbc4dee513136264859d7bb21f81。
- 原始 admission：review-out/ops-admission.json；文件 SHA-256：eed29c1c376c0bcad834404801b39cf3120edacc719eeb3c3da28d9926b48c48。
- 上轮技术核对及 17 模块 before/after blob 表：review-out/independent-review-release-skip-blob-successors.md。本轮重读并复用同对象证据，核实上述原始文件摘要与独立核对记录相符。

## 逐条批准依据

批准 B updates 的全部 304 条，覆盖 17 个模块。逐条身份以本次 diff 中的 updates nodeid 为准，并与上述独立核对文件 extracted 的 nodeid 一一对应：304 个唯一 nodeid，每条出现一次，缺失 0、重复 0、差异 0。

每条 verdict=approve、basis=environmental，依据均为原始 run 的 environmental skip：outcome=skipped，reason 非空且与原准入链完全一致，原链已准入该条且非 reviewed_hosted，原准入 module_blob 与 source_before 的 before_blob 相同，after_blob 与 source_after 对应模块相同，before/after 不同。迁移仅替换 module_blob，保持 reason/outcome 不变。原始 run 的执行源是 source_before；本回执不把该 run 视为 source_after 的执行结果，也不把 skipped 视为 passed。

独立提取基于原始 validation evidence、绑定的 admission 和 HEAD 原 baseline 重建原链，并通过只读 Git 源树核对 17 个模块，不以作者的 obs304.json、updates304.json 或候选测试生成函数作为独立判断依据。现存核对文件中的 synthetic_review_matches 仅记录旧占位文档与旧摘要的吻合，不作为独立批准依据。

B 的 schema、prior 和整体记录 pin 检查，以及历史 skipped、精确 before_blob、非 reviewed_hosted、accepted equality、native 和 collection_skips 约束均保留。新增与既有测试的静态审查未发现拒绝条件弱化。本轮未执行测试，不将静态审查或数据解析表述为测试通过。

上轮 B-1 指向含占位收据的合成文档。本回执提供真实独立审查结论，不再以原占位摘要本身作为技术拒绝理由。

## 回执绑定与变更边界

本回执最终文件字节的 SHA-256 将作为 B review document 的 review_receipt_sha256；负责人须按既有 review document 格式重算 B independent_review_sha256，并重算因此连带变化的两层 prior/记录 pin 和测试常量。A 的回执绑定范围由回执 A 单独授权。本回执不包含自身摘要。

除上述回执绑定字段、派生摘要、prior/pin/测试常量外，任何其他改动都需重审；304 条的 nodeid、reason、outcome、before_blob、after_blob、source 和 run 身份必须与本次对象一致。完成绑定后，须由独立复核确认回执摘要和派生 pin 正确，且其余内容与本次审查对象一致。

本结论是技术审查批准，不代表后续 pin 复核、测试门禁或发布验收已经完成；不解除既有发布门禁。本轮未运行测试、构建或 workflow，未提交、推送或访问生产。
