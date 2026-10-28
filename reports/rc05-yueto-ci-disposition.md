# PLAN 9.4 RC05：yueto-ci 普通注释处置

基准 SHA：`56e97e22f20137fad8396aa7cbf844bb8baceaa0`。
分支：`chore/rc05-comment-cleanup-20261029`。

## 验收合同与车道

本批只删除两个第一方测试文件的独立普通注释行，不改变可执行代码、字符串、文档字符串或工具指令。约束说明全部保留。不涉及 migrations、生成代码、第三方代码或 docs。交付为签名提交及 PR；master 冻结期间不合并，不进入本次 release。自动化验证统一交给 box，本地不运行测试、构建、lint 或语义诊断。候选发布不等于完成全项目 RC05/RC07。

| 车道 | 责任与文件所有权 |
| --- | --- |
| rc05tci | 唯一写者；两个下列测试文件及本报告；负责签名、推送和 PR。 |
| rc05tci-review | 独立只读审阅候选 diff 与本报告，不运行测试，不写文件。 |

## 逐文件处置

行号均对应基准 SHA；没有删除配额。

| 文件 | 处置 | 理由与证据 |
| --- | --- | --- |
| `tests/test_go_cache_policy.py` | 删除 L244 一行；其他注释保留 | “Cold/no-service…”重复紧邻的 `run("build", "-x", "./...")` 和 `assertIn("compile ", cold)`；不承载缓存信任边界。L192、L263 的不绕过验证约束保留。 |
| `tests/test_ui_static_units.py` | 删除 L451 一行；其他注释保留 | “An outside-only tree…”重复紧邻的 unchanged/changed 判定断言；未改选择逻辑。L376 的门禁来源说明和字符串内 shebang 保留。 |
| `scripts/pytest-timing.py` | 保留 | L214 说明诊断完整性不能替代原始门禁结果。 |
| `scripts/pytest-shards.py` | 保留 | 本批不修改证据汇总及准入相关源码。 |
| `scripts/ui_static_units.py` | 保留 | 镜像摘要出处、workspace 安装布局及 type-ignore 有实际用途。 |
| `scripts/list-integration-tests.go` | 保留 | 文件头说明执行位置和私有源码边界。 |
| `scripts/changed-migrations.py` | 保留 | 不启用 rename detection 的解释属于迁移安全约束。 |
| `scripts/go-cache-plan.py` | 保留 | 缓存信任、工具链隔离及失败回退约束。 |
| `scripts/input-fingerprint.py` | 保留 | 保留树完整性、动态加载、脱敏及 UNKNOWN 约束；不为凑数只删分隔线。 |
| `scripts/poll-skip-decision.py` | 保留 | token 权限及可信镜像覆盖约束。 |
| `scripts/plan-rescan-targets.py` | 保留 | 回滚目标、分页完整性及已审阅 registry 边界。 |
| `tests/test_pytest_timing.py` | 保留 | L96–97 防止修改测试运行器真实 site-packages。 |
| `tests/test_pytest_shards.py` | 保留 | collection hook、证据完整性及失败源码身份的说明。 |
| `tests/test_rescan_pagination.py` | 保留 | 历史日期和 build 编号是 fixture 来源证据，并非过时修复叙述。 |
| `tests/test_changed_migrations.py` | 保留 | 未选择任何删除；迁移安全测试保持原样。 |

## 验证及交接

本地仅阅读源码和 diff；测试、构建、lint、词法 token/AST 自动比较均为 deferred。PR 提供在仓库根目录执行的 box 精确命令；测试中的 Go 编译仅由 box 调度执行。Python 语义诊断也因本轮禁止本地检查而延后，不以静态阅读替代通过结果。

独立审阅结论及签名、远端 PR 回执写入任务 findings。无新增代码，因此不新增测试。回滚采用撤销本批签名提交。待议（Parked）：无。
