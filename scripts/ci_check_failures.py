"""Print unique failing pytest node ids from a shard log, one per line."""

from __future__ import annotations

import re
import sys

# Node ids keep spaces inside parameter brackets. Pytest puts " - " before the message.
_NODE = re.compile(r"(?:FAILED|ERROR) (tests/.+?)(?: - |$)")


def node_ids(text: str) -> list[str]:
    """Return failing node ids in first-seen order."""
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        payload = line.split("Z ", 1)[-1]
        match = _NODE.search(payload)
        if match is None:
            continue
        node = match.group(1).strip()
        if node and node not in seen:
            seen.add(node)
            found.append(node)
    return found


def main() -> int:
    items = node_ids(sys.stdin.read())
    for item in items:
        print(item)
    return 1 if items else 0


if __name__ == "__main__":
    raise SystemExit(main())
