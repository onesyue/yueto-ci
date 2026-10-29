# A 层独立审查回执：tests/_subprocess.py

结论：APPROVE（技术内容）。

日期：2026-10-29。审查角色：独立审查者。任务：xrev-hang2，接续 xrev-hang。

## 审查对象与证据

- 候选基点：56e97e22f20137fad8396aa7cbf844bb8baceaa0。
- 待审 diff SHA-256：c59dd85f748cc6b6d551e41b7b1a3b6498fe44aaa7b2ddd321f735d4ff9cdd82；证据文件：review-out/under-review.diff。本轮确认当前 staged diff 与该文件逐字节相同，且无 unstaged tracked diff。
- source_before：bc583a440c466c039e8ba0c4b448012700d339a3。
- source_after：03db123be8bc722cacaa47776c94776f6e8623be。
- source freeze：review-out/source-freeze-03db123be.lstree；文件 SHA-256：141df51e561e21b4eaa968715e21031026977cfb4b60729397363cf5a1765c1c。
- helper：tests/_subprocess.py；before_blob=null；after_blob=21c2cca9901c5cea683324a269d859bdd7b784d0；mode=100644。
- 上轮技术核对：review-out/independent-review-tests-_subprocess.md。本轮重读并复用同对象证据；源树核对结果见 review-out/independent-verification.json，文件 SHA-256：830a12fd2d0104b03166feb76f8918eb57d7ea53cc297e2f0e8e324134844174。

## 技术判断

批准上述 A 层技术内容。helper 仅读取环境变量并计算至少 300 秒的预算，无文件、网络、子进程 I/O，无 pytest hook、测试定义或收集注册。before_blob=null 是相对 bc583a44 的净新增，并非相对其直接父提交的新增。

精确 helper blob、mode、estate addition 和 estate successor 祖先证明共同限制准入；原有 shared_inputs 发现、完整映射等式、模块与集合检查保留。schema 与整体记录 pin 约束完整。旁支及孤儿历史拒绝测试的静态审查通过；本轮未执行测试，不将静态审查或数据解析表述为测试通过。

上轮 A-1 指向独立审查凭证尚未闭合。本回执提供真实独立审查结论，不再以原记录的占位摘要本身作为技术拒绝理由。

## 回执绑定与变更边界

本回执最终文件字节的 SHA-256 将被填入 A 记录的 independent_review_sha256。本回执不包含自身摘要。

除该字段及因此连带变化的 prior/pin/测试常量外，任何其他改动都需重审。B 对其自身回执的绑定范围由回执 B 单独授权。负责人完成绑定后，须由独立复核确认 pin 等于回执文件摘要，并确认其余内容与本次审查对象一致。

本结论是技术审查批准，不代表后续 pin 复核、测试门禁或发布验收已经完成；不解除既有发布门禁。本轮未运行测试、构建或 workflow，未提交、推送或访问生产。
