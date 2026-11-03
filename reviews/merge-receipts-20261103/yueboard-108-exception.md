# yueboard #108 — exception evidence (exact-head review CHANGES; fixed by #112; master re-review APPROVE)

head: ae53f2f31f6dcce2d338c365edee1a92ffe0d8bd
merge: ed6166eabf13ae7a66137385db745a24a18d72f7 (merged 2026-11-03T10:07:36Z by cursor[bot], before any receipt)
parity: box, go test -count=1 -p 1 ./..., rc=0, ran 2026-11-03T11:38:17Z, log sha256 c37d81069649f13229c28cf12c12dfc6cc71925fec3aa412fae071e8dd89025c

REVIEW AT EXACT HEAD: NOT approve (VERDICT: changes).

## Exact-head review (ae53f2f3)
- [P2] `web/src/routes/_app/devices.tsx:176`：`over_limit` 表示实际在线数超限，但新文案要求删除设备登记。删除登记不会断开代理连接；未上报 HWID 的客户端甚至没有可删除的条目，用户无法按提示恢复。应保留断开不用设备或全部设备的指引，将登记删除说明限定于订阅登记超限。

仅静态审查指定提交差异，未运行测试。

VERDICT: changes
- [P2] `web/src/routes/_app/devices.tsx:176`：`over_limit` 表示实际在线数超限，但新文案要求删除设备登记。删除登记不会断开代理连接；未上报 HWID 的客户端甚至没有可删除的条目，用户无法按提示恢复。应保留断开不用设备或全部设备的指引，将登记删除说明限定于订阅登记超限。

仅静态审查指定提交差异，未运行测试。

VERDICT: changes

## Resolution
yueboard #112 (merged c7d21273) restores the disconnect guidance for over_limit.

## Re-review of the #108 findings against master 305452a3f75f4854a49c175b5d54c16e8aaa6d3c
**RESOLVED — [P2] 在线超限提示误导删除登记。** 已核对 `origin/master` 为指定提交 `305452a3f75f4854a49c175b5d54c16e8aaa6d3c`。

- [devices.tsx:176](<path>)：`over_limit` 提示已恢复为“请退出不再使用的设备，或断开所有设备”。
- [device-limit-help.tsx:11](<path>)：移除登记说明位于“新设备提示已达上限？”帮助中；第 16 行明确“已连接的代理不会立即断开”。
- [devices.tsx:101](<path>)：页头“断开所有设备”按钮仅依赖身份加载及操作状态，不要求存在 HWID 登记条目。

VERDICT: approve (all resolved)
