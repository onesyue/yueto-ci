"""BuildKit .dockerignore matching (moby/patternmatcher, unix separator)."""

from __future__ import annotations

import re

def _clean(pattern: str) -> str:
    """filepath.Clean + ToSlash + strip one leading '/', like moby/patternmatcher."""
    absolute = pattern.startswith("/")
    parts: list[str] = []
    for part in pattern.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not absolute:
                parts.append(part)
            continue
        parts.append(part)
    return "/".join(parts) or "."


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """Port of moby/patternmatcher Pattern.compile (unix separator)."""
    out = "^"
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 1
                if i + 1 < len(pattern) and pattern[i + 1] == "/":
                    i += 1
                if i + 1 >= len(pattern):
                    out += ".*"
                else:
                    out += "(.*/)?"
            else:
                out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch in ".+()|{}$":
            out += "\\" + ch
        elif ch == "\\":
            if i + 1 < len(pattern):
                i += 1
                out += "\\" + pattern[i]
            else:
                out += "\\\\"
        elif ch in "[]":
            out += ch
        elif ch == "^":
            out += "\\^"
        else:
            out += ch
        i += 1
    return re.compile(out + "$")


class IgnoreRules:
    # Plain class, not a dataclass: importlib-by-path loaders (release-state,
    # tests) need not register the module in sys.modules first.
    def __init__(self) -> None:
        self.patterns: list[tuple[bool, re.Pattern[str]]] = []

    @classmethod
    def parse(cls, text: str) -> "IgnoreRules":
        rules = cls()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:].strip()
            cleaned = _clean(line)
            if cleaned == ".":
                continue
            rules.patterns.append((negate, _pattern_regex(cleaned)))
        return rules

    def ignored(self, path: str) -> bool:
        """moby PatternMatcher.MatchesOrParentMatches."""
        matched = False
        parts = path.split("/")
        parents = ["/".join(parts[: i + 1]) for i in range(len(parts) - 1)]
        for negate, regex in self.patterns:
            if negate != matched:
                continue
            hit = bool(regex.match(path)) or any(regex.match(p) for p in parents)
            if hit:
                matched = not negate
        return matched
