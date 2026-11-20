"""Official Yue.to URL and bot-handle literals for CI helpers.

Copied from yueto ``design/sources/brand.json`` at 9976072b
(``telegram.bot`` is ``yuetoo_bot``). This module does not import or read
the yueto repository.
"""

from __future__ import annotations

# urls.panel
PANEL_URL = "https://app.yue.to"
PANEL_HOST = "app.yue.to"

# security.origins.widget
WIDGET_URL = "https://bot.yue.to"
WIDGET_HOST = "bot.yue.to"

# telegram.bot. The retired username is not a value here.
TELEGRAM_BOT = "yuetoo_bot"
TELEGRAM_BOT_HANDLE = "@" + TELEGRAM_BOT
TELEGRAM_BOT_URL = "https://t.me/" + TELEGRAM_BOT

# mirrors.panel[0]
PANEL_MIRROR_PRIMARY_URL = "https://app.xn--jdu596h.com"
PANEL_MIRROR_PRIMARY_HOST = "app.xn--jdu596h.com"

# security.origins.panelMirrorAlternate
PANEL_MIRROR_ALTERNATE_URL = "https://app.xn--9kq451mn9g.com"
PANEL_MIRROR_ALTERNATE_HOST = "app.xn--9kq451mn9g.com"

# Sealed CI needles. Same registrable domain as the panel mirrors, Mini label.
RETIRED_MINI_PRIMARY_HOST = "mini.xn--jdu596h.com"
RETIRED_MINI_ALTERNATE_HOST = "mini.xn--9kq451mn9g.com"


def _host(url: str) -> str:
    prefix = "https://"
    if not url.startswith(prefix):
        raise ValueError("brand URL must be https://host")
    rest = url[len(prefix):]
    if not rest or "/" in rest:
        raise ValueError("brand URL must be https://host")
    return rest


def _domain(host: str) -> str:
    label, dot, domain = host.partition(".")
    if not label or not dot or not domain or "/" in domain:
        raise ValueError("brand host must be a DNS name")
    return domain


def _require_pair(url: str, host: str) -> None:
    if _host(url) != host:
        raise ValueError("brand URL and host disagree")


_require_pair(PANEL_URL, PANEL_HOST)
_require_pair(WIDGET_URL, WIDGET_HOST)
_require_pair(PANEL_MIRROR_PRIMARY_URL, PANEL_MIRROR_PRIMARY_HOST)
_require_pair(PANEL_MIRROR_ALTERNATE_URL, PANEL_MIRROR_ALTERNATE_HOST)

if TELEGRAM_BOT_URL != "https://t.me/" + TELEGRAM_BOT:
    raise ValueError("bot URL disagrees with the official username")
if TELEGRAM_BOT_HANDLE != "@" + TELEGRAM_BOT:
    raise ValueError("bot handle disagrees with the official username")
if TELEGRAM_BOT == "yue_" + "to_bot":
    raise ValueError("retired bot username")
if _domain(RETIRED_MINI_PRIMARY_HOST) != _domain(PANEL_MIRROR_PRIMARY_HOST):
    raise ValueError("primary Mini needle drifted from the panel mirror")
if _domain(RETIRED_MINI_ALTERNATE_HOST) != _domain(PANEL_MIRROR_ALTERNATE_HOST):
    raise ValueError("alternate Mini needle drifted from the panel mirror")
if _domain(PANEL_HOST) != _domain(WIDGET_HOST):
    raise ValueError("panel and widget hosts drifted apart")
