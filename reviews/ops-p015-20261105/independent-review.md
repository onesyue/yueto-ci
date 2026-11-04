# P015 独立静态审阅

Reviewer: /root/p015_review（独立只读子代理，2026-11-05）
VERDICT: APPROVE

审阅范围：新 admit_p015_offline_helper、新测试、helper-policy.json、source-freeze.json、qualification-driver.py 和 source pin。未写源码、未重复执行测试。

新规则沿用 admit_first_native_helper 的 shared_input {path, blob, mode} 与 source_revision 数据形状，绑定唯一指定路径、blob、100644 和 d91a87f73b3aa20a0320b92252b8ee9be1f01743。policy SHA256 与代码中的 cb32a56317731b0e57429ac7ca333c24bb527a7e3bc778af518e3ebc95c918a5 一致。精确剥离后继续原链，无 glob、前缀匹配或 modes 检查放宽，#256 严格封印不变。

新测试覆盖完整准入链、错误 blob/mode/tree/revision、相似及嵌套其他 helper 的原始 modes 拒绝，且检查输入不变。

有意差异：helper 缺席时直接透传以保持既有 fixtures；实际 expand 从固定 revision 的 Git tree 收集该 helper。此行为不放行其他 helper。driver 使用隔离 clone、真实 CLI 和正式 policy，无策略覆盖，并明确本地准入不等于 Linux 运行测试。

最终测试与真实 expand 的执行结果由主车道另行记录，不属于本静态审阅的执行声明。

## 最终修复复核

VERDICT: APPROVE（/root/p015_review）
读取 policy 之前增加字面量 tests/p015_offline_plugin.py 缺席即透传的门槛。它修复历史 fixture 不带 reviews 文件的读取问题；存在目标路径时 SHA256、完整 revision、blob 和 mode 校验全部仍执行。其他 helper 仍交给原拒绝链。driver 的 import、check=False、等价 if 整理不改变执行和退出码判定。无源码写入、无重复测试。
