# P015 单 helper 准入

仅准入 tests/p015_offline_plugin.py，100644，blob 396456b1fd3fd2066de2a69be144525a62d2c63a，固定目标 d91a87f73b3aa20a0320b92252b8ee9be1f01743。helper-policy.json 沿用既有 first-native helper 数据形状，文件 SHA256 在准入函数内封印。

source-freeze.json 保存目标树、引入提交、共享输入及 modes；主车道已核对引入提交 fcd5a5ee4ba44550911b9f8ed6463d388821116d 的父提交不含此路径，引入后即为指定 blob/mode，且为目标祖先。依赖 blobs 等于 #256 after-blobs。

qualification-driver.py 沿用 #256 driver，改为本目标和本证据目录，复用原 #256 三份封印证据；临时克隆创建于本目录并自动清理。运行：

    python3 reviews/ops-p015-20261105/qualification-driver.py /path/to/read-only/yueops

admission-results.json 是真实 expand 的结果；current-policy-admission.log 是其完整输出。runner 参数 ubuntu-24.04 不是 Linux 执行证明。本机为 macOS，Linux 容器不可用的既有证据见 FINDINGS.seal256.md；本轮不重复尝试。

既有 tests 文件未修改；新测试在 tests/test_ops_p015_offline_helper.py。SHA256SUMS 覆盖本目录交付文件（排除清单自身和缓存）。完整脚本 diff 见 pytest-shards-vs-origin-master.diff。
