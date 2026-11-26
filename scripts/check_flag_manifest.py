#!/usr/bin/env python3
"""Check reviewed CI defaults against workflow env, repository vars and shell defaults."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCH_NAME = re.compile(r"ENABLE|DISABLE|REQUIRE|SKIP|FORCE|_MODE", re.I)
SWITCH_VALUES = {"0", "1", "true", "false", "yes", "no", "on", "off"}
FIELD = re.compile(r"""^( *)(- )?(?:([\w.-]+)|'([\w.-]+)'|"([\w.-]+)"):(?:\s+(.*)|$)""")
SHELL_DEFAULT = re.compile(r"\$\{([A-Za-z_]\w*):-(.*?)\}")
EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
# Skip expression string literals, including Actions' doubled single quotes.
VAR_TOKEN = re.compile(
    r"'(?:[^']|'')*'|(?<![\w.])vars\s*(?:\.\s*(\w+)|\[\s*'([\w]+)'\s*\]|(?=\[))", re.I
)
FALLBACK = re.compile(r"\s*\)*\s*\|\|\s*")
LITERAL = re.compile(r"'((?:[^']|'')*)'|(-?\d+|true|false)\b", re.I)


def scalar(text):
    """Unquote a workflow scalar and discard a trailing YAML comment."""
    match = re.fullmatch(r"""('[^']*(?:''[^']*)*'|"(?:[^"\\]|\\.)*")(?:\s+#.*)?""", text)
    if match:
        quoted = match[1]
        return quoted[1:-1].replace("''", "'") if quoted[0] == "'" else quoted[1:-1]
    return re.split(r"\s+#", text, maxsplit=1)[0].strip()


def workflow_fields(text):
    """Read the block mappings used in Actions, keeping shell blocks out of YAML keys."""
    lines = text.splitlines()
    parents = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = FIELD.match(line)
        index += 1
        if not match:
            if line.lstrip().startswith("- "):
                yield (), scalar(line.lstrip()[2:])
            continue
        spaces, item, plain, single, double, value = match.groups()
        indent = len(spaces) + len(item or "")
        while parents and parents[-1][0] >= indent:
            parents.pop()
        key = plain or single or double
        path = tuple(name for _, name in parents) + (key,)
        value = (value or "").strip()
        if not value or value.startswith("#"):
            parents.append((indent, key))
            yield path, ""
            continue
        start = index
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            index += 1
        if re.fullmatch(r"[|>][-+]?\d*(?:\s+#.*)?", value):
            value = "\n".join(lines[start:index]).strip()
        else:
            continuation = [line.strip() for line in lines[start:index]
                            if line.strip() and not line.lstrip().startswith("#")]
            value = scalar(" ".join([value, *continuation]))
        yield path, value


def variable_defaults(expression):
    for token in VAR_TOKEN.finditer(expression):
        if token[0].startswith("'"):
            continue
        name = token[1] or token[2]
        if name is None:
            raise ValueError("dynamic vars lookup has no reviewable variable name")
        fallback = FALLBACK.match(expression, token.end())
        value = ""
        if fallback:
            literal = LITERAL.match(expression, fallback.end())
            if not literal:
                raise ValueError(f"vars.{name} has a nonliteral fallback")
            value = literal[2] if literal[1] is None else literal[1].replace("''", "'")
        yield "vars." + name.upper(), value


def shell_defaults(text):
    for line in text.splitlines():
        if not line.lstrip().startswith("#"):
            yield from SHELL_DEFAULT.findall(re.split(r"\s+#", line, maxsplit=1)[0])


def check(root):
    rows = json.loads((root / "policy/flags.json").read_text())["flags"]
    expected = {}
    inputs = {}
    names = set()
    for row in rows:
        name, default = row["name"], row["default"]
        if row["kind"] not in {"switch", "value"} or not isinstance(default, str):
            raise ValueError(f"invalid row for {name}")
        if not (row.get("workflows") or row.get("scripts")):
            raise ValueError(f"{name} has no source")
        names.add(name)
        for folder, sources in [(".github/workflows", row.get("workflows", [])),
                                ("scripts", row.get("scripts", []))]:
            for source in sources:
                path = Path(folder, source)
                if (path, name) in expected:
                    raise ValueError(f"duplicate row for {path} {name}")
                expected[path, name] = default
                if "input" in row:
                    inputs[path, name] = row["input"]
                    expected[path, "inputs." + row["input"]] = default
    if not expected:
        raise ValueError("empty flag manifest")

    seen = set()
    errors = set()

    def observe(path, name, value):
        key = path, name
        if key not in expected:
            errors.add(f"{path}: {name} has no manifest row")
        elif expected[key] != value:
            errors.add(f"{path}: {name} differs from its reviewed default")
        seen.add(key)

    def check_shell(path, body, *, script):
        for name, value in shell_defaults(body):
            if name not in names:
                name = "vars." + name
            if name in names:
                if script:
                    observe(path, name, value)
                elif (path, name) not in expected or expected[path, name] != value:
                    errors.add(f"{path}: {name} shell default differs from manifest")

    workflows = root / ".github/workflows"
    for file in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        path = file.relative_to(root)
        for keys, value in workflow_fields(file.read_text()):
            key = keys[-1] if keys else None
            if key == "env" and value:
                raise ValueError(f"{path}: expected an env block mapping")
            if keys[-2:-1] == ("env",):
                if (path, key) in inputs:
                    input_name = inputs[path, key]
                    binding = re.fullmatch(
                        rf"\$\{{\{{\s*inputs\.{re.escape(input_name)}\s*&&\s*'true'\s*\|\|\s*'([^']*)'\s*\}}\}}",
                        value,
                    )
                    observe(path, key, binding[1] if binding else None)
                elif key in names or ("${{" not in value and
                                      (value.lower() in SWITCH_VALUES or SWITCH_NAME.search(key))):
                    observe(path, key, value)
            if keys[-5:-2] == ("on", "workflow_dispatch", "inputs") and key == "default":
                input_key = "inputs." + keys[-2]
                if (path, input_key) in expected:
                    observe(path, input_key, value)
            expressions = EXPRESSION.findall(value)
            if key == "if" and not expressions:
                expressions = [value]
            for expression in expressions:
                for name, default in variable_defaults(expression):
                    observe(path, name, default)
            if key == "run":
                check_shell(path, value, script=False)

    for file in sorted((root / "scripts").glob("*.sh")):
        check_shell(file.relative_to(root), file.read_text(), script=True)

    for path, name in expected.keys() - seen:
        errors.add(f"{path}: missing reviewed source for {name}")
    return sorted(errors)


def main():
    try:
        errors = check(ROOT)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("CI flag manifest matches workflow and script defaults")
    return 0


if __name__ == "__main__":
    sys.exit(main())
