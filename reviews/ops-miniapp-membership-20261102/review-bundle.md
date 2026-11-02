# Review bundle: yueops tests/_miniapp_source.py shared-input change
source_before=6e21e7b313cf829b374f4d1f429bb633115ba020 source_after=54f9d8250b61cd75ddde7a4ab301f0e05e6da467 release=300b22ed28a08f46033ebc4e2ffdb2de07027142
before_blob=11f219d4fedc809863f4cd5d747a34cce6abd0ad after_blob=4ab8f017a00cf63f3d0f2f208d8fd37cb6c152f4

## Diff of the shared helper
diff --git a/tests/_miniapp_source.py b/tests/_miniapp_source.py
index 11f219d4..4ab8f017 100644
--- a/tests/_miniapp_source.py
+++ b/tests/_miniapp_source.py
@@ -42,6 +42,7 @@ MINIAPP_BACKEND = (
     _SERVICE / "miniapp_home_state.py",
     _SERVICE / "miniapp_idempotency.py",
     _SERVICE / "miniapp_invite_alias.py",
+    _SERVICE / "miniapp_membership_hint.py",
     _SERVICE / "miniapp_redeem.py",
     _SERVICE / "miniapp_static.py",
     _SERVICE / "miniapp_uno_bff.py",

## Commits touching the helper between 54f9d825 and 300b22ed

## Newly registered module (full source at 300b22ed): telegram-bot/yue/service/miniapp_membership_hint.py
```python
"""Public website guidance authorized by the owner on 2026-10-27.

Serve stale guidance immediately while a single background reader refreshes it.
Defaults are bundled with the release; no runtime setting grants payment access.
"""

from __future__ import annotations

import json
import re
from threading import Lock, Thread
from time import monotonic
from urllib.parse import urlsplit

from yueboard_internal_readonly import settings_read

from yueops.brand_g import URL_PANEL

SETTING_KEY = "miniapp_membership_purchase_hint"
COPY_LIMIT = 300
DEFAULT_HINT = {
    "zh": "会员与套餐请在官网用户中心购买或续费。",
    "en": "Buy or renew memberships and plans in the user panel on the official website.",
    "url": f"{URL_PANEL}/#/plans",
}


REFRESH_TTL = 300.0
FAILURE_BACKOFF = 30.0
_lock = Lock()
_cached_hint = dict(DEFAULT_HINT)
_refreshing = False
_next_refresh = 0.0


def safe_hint_url(value: object) -> str:
    if isinstance(value, str) and len(value) <= 2048:
        # Match the raw path: browser URL parsing would normalize /other/../.
        route = re.fullmatch(r"https://([^/?#]+)(/?)(?:\?[^#]*)?#(/plans/?(?:\?[^#]*)?)", value)
        host = urlsplit(URL_PANEL).hostname
        if (
            route
            and route[1].lower() in (host, f"{host}:443")
            and not any(c.isspace() or ord(c) < 32 or c == "\ufeff" for c in value)
            and "\\" not in value
        ):
            return value
    return DEFAULT_HINT["url"]


def plain_copy(value: object, fallback: str) -> str:
    # Reject markup rather than interpreting it; React also renders text nodes.
    if not isinstance(value, str) or "<" in value or ">" in value:
        return fallback
    text = " ".join(value.split())[:COPY_LIMIT]
    return text or fallback


def _refresh_hint() -> None:
    global _cached_hint, _refreshing, _next_refresh
    delay = FAILURE_BACKOFF
    try:
        raw = settings_read((SETTING_KEY,), timeout_seconds=2.0).get(SETTING_KEY)
        value = json.loads(raw) if isinstance(raw, str) and len(raw) <= 8192 else None
        refreshed = dict(DEFAULT_HINT)
        if isinstance(value, dict):
            refreshed = {
                "zh": plain_copy(value.get("zh"), DEFAULT_HINT["zh"]),
                "en": plain_copy(value.get("en"), DEFAULT_HINT["en"]),
                "url": safe_hint_url(value.get("url")),
            }
        with _lock:
            _cached_hint = refreshed
        delay = REFRESH_TTL
    except Exception:
        # Keep the last good value; never expose transport errors or credentials.
        pass
    finally:
        with _lock:
            _next_refresh = monotonic() + delay
            _refreshing = False


def membership_purchase_hint() -> dict[str, str]:
    """Return immediately; Board I/O never runs under the cache lock."""
    global _refreshing, _next_refresh
    with _lock:
        result = dict(_cached_hint)
        if _refreshing or monotonic() < _next_refresh:
            return result
        _refreshing = True
    try:
        Thread(target=_refresh_hint, daemon=True, name="membership-hint-refresh").start()
    except Exception:
        with _lock:
            _next_refresh = monotonic() + FAILURE_BACKOFF
            _refreshing = False
    return result
```
<!-- list -->
telegram-bot/yue/service/miniapp_membership_hint.py
tests/fixtures/miniapp_membership_hint_urls.json
tests/test_miniapp_membership_hint.py

## Full helper at 300b22ed
"""Mini App 后端的源码扫描面（tg_miniapp 外提后的单一入口）。

2026-09-20 把 UNO BFF 辅助层（1024 行、30 个符号）从 `service/tg_miniapp.py`
外提到 `service/miniapp_uno_bff.py`。此前有若干测试直接读 tg_miniapp.py 的源码
做契约断言——那是把判据绑在文件名上，而文件名不是契约的一部分。

危险的不是变红那一半（看得见），是「某字符串必须不出现」那一半：少读一个文件
就是少判几条，而少判等于全过。所以扫描面跟着**模块族**走，并带地板。

2026-09-20（同日第二轮）tg_miniapp.py 3708 → 670 行，再外提十个同族模块
（util / static / broadcast / invite_alias / redeem / exchange_ops / battle_pass /
dashboard / home_state / core_routes）。这一轮把「地板」真正做出来，三道：

1. **族清单 vs 磁盘**：`service/miniapp_*.py` 的实际文件集合必须与下面的显式
   清单逐名相等。以后再外提一个模块却忘了登记，这里当场红——而不是让负向断言
   悄悄少扫一个文件。
2. **行数地板**：族源码总行数不得低于 `MIN_TOTAL_LINES`。整族被搬空/被 glob
   漏掉时，负向断言会全绿；行数地板是那种「扫描面塌了」的唯一可见信号。
3. **必到场文件**：每个登记文件都必须存在，缺一个就 AssertionError。
"""

from __future__ import annotations

import ast
from pathlib import Path

BOT = Path(__file__).resolve().parents[1] / "telegram-bot" / "yue"
_SERVICE = BOT / "service"

#: tg_miniapp 及其外提出去的同族模块。新增外提文件时加进来——
#: 漏加会让这里的负向断言静默失去扫描面（`test_family_matches_disk` 会先红）。
MINIAPP_BACKEND = (
    _SERVICE / "tg_miniapp.py",
    _SERVICE / "miniapp_battle_pass.py",
    _SERVICE / "miniapp_broadcast.py",
    _SERVICE / "miniapp_client_guard.py",
    _SERVICE / "miniapp_core_routes.py",
    _SERVICE / "miniapp_dashboard.py",
    _SERVICE / "miniapp_exchange_history.py",
    _SERVICE / "miniapp_entry.py",
    _SERVICE / "miniapp_gamble.py",
    _SERVICE / "miniapp_home_state.py",
    _SERVICE / "miniapp_idempotency.py",
    _SERVICE / "miniapp_invite_alias.py",
    _SERVICE / "miniapp_membership_hint.py",
    _SERVICE / "miniapp_redeem.py",
    _SERVICE / "miniapp_static.py",
    _SERVICE / "miniapp_uno_bff.py",
    _SERVICE / "miniapp_util.py",
)

#: 扫描地板：族源码总行数。2026-09-20 实测 6254 行，留 15% 余量防正常删减误红。
#: 低于此值几乎只有一个原因——扫描面塌了（文件被搬走 / 清单失配 / 路径写错）。
MIN_TOTAL_LINES = 5300


def miniapp_family_on_disk() -> list[Path]:
    """磁盘上真实存在的同族文件（tg_miniapp.py + service/miniapp_*.py）。"""
    found = sorted(_SERVICE.glob("miniapp_*.py"))
    return [_SERVICE / "tg_miniapp.py", *found]


def assert_scan_floor() -> None:
    """扫描面地板。任何读这份源码做断言的测试都隐式经过它。"""
    listed = {p.name for p in MINIAPP_BACKEND}
    on_disk = {p.name for p in miniapp_family_on_disk()}
    if listed != on_disk:
        raise AssertionError(
            "Mini App 后端模块族清单与磁盘不符——新外提的模块必须登记进 "
            f"tests/_miniapp_source.MINIAPP_BACKEND；只在磁盘={sorted(on_disk - listed)} "
            f"只在清单={sorted(listed - on_disk)}"
        )
    missing = [p.name for p in MINIAPP_BACKEND if not p.is_file()]
    if missing:
        raise AssertionError(f"Mini App 后端源缺失 {missing}——扫不到不能算通过")
    total = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in MINIAPP_BACKEND)
    if total < MIN_TOTAL_LINES:
        raise AssertionError(
            f"Mini App 后端扫描面只剩 {total} 行 < 地板 {MIN_TOTAL_LINES}——"
            "负向断言（『某字符串必须不出现』）此刻是靠少扫文件通过的，不算通过"
        )


def miniapp_backend_paths() -> list[Path]:
    assert_scan_floor()
    return list(MINIAPP_BACKEND)


def miniapp_backend_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in miniapp_backend_paths())


def miniapp_function_source(name: str) -> str:
    """模块族里某个顶层函数的源码。

    比「从 `def X` 切到 `def Y`」稳得多：既不绑文件名，也不绑相邻定义的顺序。
    2026-09-20 拆包后 `_enqueue_broadcast` 与 `register_miniapp_routes` 已经不在
    同一个文件里，靠相邻标记切片会切出空串——而空串里什么都 `not in`。
    """
    for path in miniapp_backend_paths():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                segment = ast.get_source_segment(src, node)
                assert segment, f"取不到 {name} 的源码片段"
                return segment
    raise AssertionError(f"Mini App 模块族里没有顶层函数 {name}——扫描面已失效，不是通过")
