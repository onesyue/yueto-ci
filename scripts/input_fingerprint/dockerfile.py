"""Dockerfile COPY/ADD/bind facts used as the fingerprint source set."""

from __future__ import annotations

import json
import re

from .constants import PINNED_IMAGE, Unknown
from .ignore import _clean

class DockerfileFacts:
    def __init__(self) -> None:
        self.sources: list[str] = []          # context-relative COPY/ADD/bind sources
        self.external_images: list[str] = []
        self.syntax = ""
        self.caveats: list[str] = []
        self.problems: list[str] = []         # any entry => unknown


HEREDOC = re.compile(r"<<(-?)([\"']?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _logical_lines(text: str) -> tuple[list[str], str]:
    """Join continuations, drop comments, skip heredoc bodies."""
    lines = text.splitlines()
    escape = "\\"
    syntax = ""
    for raw in lines:  # parser directives only at the very top
        m = re.match(r"^#\s*([a-zA-Z]+)\s*=\s*(\S+)\s*$", raw)
        if not m:
            break
        key = m.group(1).lower()
        if key == "escape":
            escape = m.group(2)
        elif key == "syntax":
            syntax = m.group(2)
    logical: list[str] = []
    buf = ""
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        stripped = raw.strip()
        if stripped.startswith("#") or (not stripped and buf):
            continue
        if not stripped:
            continue
        if stripped.endswith(escape):
            buf += stripped[: -len(escape)] + " "
            continue
        line = (buf + stripped).strip()
        buf = ""
        heredocs = HEREDOC.finditer(line) if line.split(" ", 1)[0].upper() in ("RUN", "COPY", "ADD") else ()
        for m in heredocs:
            strip_tabs, _, word = m.groups()
            while i < len(lines):
                body = lines[i]
                i += 1
                if (body.lstrip("\t") if strip_tabs else body) == word:
                    break
            else:
                raise Unknown(f"unterminated heredoc {word}")
        logical.append(line)
    if buf:
        logical.append(buf.strip())
    return logical, syntax


def _split_args(rest: str) -> list[str]:
    rest = rest.strip()
    if rest.startswith("["):
        try:
            values = json.loads(rest)
        except ValueError as exc:
            raise Unknown(f"unparseable JSON-form instruction: {rest[:60]}") from exc
        if not all(isinstance(v, str) for v in values):
            raise Unknown("non-string JSON-form argument")
        return values
    return rest.split()


def parse_dockerfile(text: str) -> DockerfileFacts:
    facts = DockerfileFacts()
    logical, facts.syntax = _logical_lines(text)
    if facts.syntax and not PINNED_IMAGE.search(facts.syntax):
        facts.caveats.append(
            f"floating Dockerfile frontend `# syntax={facts.syntax}` (not digest-pinned)"
        )
    stages: list[str] = []
    for line in logical:
        word, _, rest = line.partition(" ")
        instr = word.upper()
        if instr == "FROM":
            tokens = [t for t in rest.split() if not t.startswith("--")]
            if not tokens:
                facts.problems.append("FROM without image")
                continue
            image = tokens[0]
            internal = image == "scratch" or image.lower() in stages
            if len(tokens) >= 3 and tokens[1].upper() == "AS":
                stages.append(tokens[2].lower())
            if internal:
                continue
            if "$" in image:
                facts.problems.append(f"FROM image uses a build arg: {image}")
            elif not PINNED_IMAGE.search(image):
                facts.problems.append(f"FROM image not digest-pinned: {image}")
            else:
                facts.external_images.append(image)
        elif instr in ("COPY", "ADD"):
            args = _split_args(rest)
            flags = [a for a in args if a.startswith("--")]
            operands = [a for a in args if not a.startswith("--")]
            if len(operands) < 2:
                facts.problems.append(f"{instr} with fewer than two operands")
                continue
            from_ref = ""
            has_checksum = False
            for flag in flags:
                name, _, value = flag.partition("=")
                if name == "--from":
                    from_ref = value
                elif name == "--exclude":
                    facts.problems.append(f"{instr} --exclude is not modelled")
                elif name == "--checksum":
                    has_checksum = True
            if from_ref:
                if from_ref.lower() in stages or from_ref.isdigit():
                    continue
                if not PINNED_IMAGE.search(from_ref):
                    facts.problems.append(f"{instr} --from image not digest-pinned: {from_ref}")
                else:
                    facts.external_images.append(from_ref)
                continue
            for src in operands[:-1]:
                if src.startswith("<<"):
                    continue  # heredoc: content is Dockerfile text
                if "://" in src or src.startswith("git@"):
                    if instr == "ADD" and has_checksum:
                        facts.caveats.append(f"remote ADD with --checksum: {src}")
                    else:
                        facts.problems.append(f"remote {instr} source without checksum: {src}")
                    continue
                if "$" in src:
                    facts.problems.append(f"{instr} source uses a variable: {src}")
                    continue
                facts.sources.append(_clean(src))
        elif instr == "RUN":
            for m in re.finditer(r"--mount=(\S+)", rest):
                opts = dict(
                    (kv.partition("=")[0], kv.partition("=")[2]) for kv in m.group(1).split(",")
                )
                kind = opts.get("type", "bind")
                if kind == "bind":
                    if opts.get("from"):
                        continue
                    src = opts.get("source", opts.get("src", "."))
                    if "$" in src:
                        facts.problems.append(f"bind mount source uses a variable: {src}")
                    else:
                        facts.sources.append(_clean(src))
                elif kind == "secret":
                    facts.problems.append("RUN secret mount is an unfingerprinted input")
        elif instr == "ONBUILD" and re.search(r"\b(COPY|ADD)\b", rest, re.I):
            facts.caveats.append("ONBUILD COPY/ADD (applies to child builds only)")
    return facts


def _source_regex(source: str) -> re.Pattern[str] | None:
    if not any(c in source for c in "*?["):
        return None
    out = ""
    for ch in source:
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        elif ch in "[]":
            out += ch
        else:
            out += re.escape(ch)
    return re.compile(out + "$")


def selected(path: str, sources: list[str]) -> bool:
    for src in sources:
        if src == ".":
            return True
        regex = _source_regex(src)
        if regex is None:
            if path == src or path.startswith(src + "/"):
                return True
            continue
        depth = src.count("/") + 1
        prefix = "/".join(path.split("/")[:depth])
        if regex.match(prefix):
            return True
    return False
