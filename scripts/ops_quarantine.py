"""Pytest policy for exact source-owned quarantine cases and shared Ops validation."""
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


POLICY_FILE = Path(__file__).resolve().parents[1] / "ci" / "quarantine.yaml"
_ENTRY_KEYS = ("id", "owner", "issue", "expires")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISSUE = re.compile(r"^https://github\.com/onesyue/\S+$")


def parse_quarantine_yaml(text):
    """Parse the policy quarantine document. Expired rows are not applied here."""
    if text.startswith("\ufeff") or "\t" in text or "\x00" in text:
        raise ValueError("invalid ci/quarantine.yaml")
    schema = None
    entries = None
    current = None
    closed = False
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        if raw.startswith("#") or raw.strip().startswith("#") and raw.lstrip().startswith("#"):
            continue
        if raw.startswith("schema:"):
            if schema is not None or entries is not None or not raw.startswith("schema: "):
                raise ValueError("invalid ci/quarantine.yaml")
            value = raw.split(": ", 1)[1]
            if value != "1":
                raise ValueError("invalid quarantine schema")
            schema = 1
            continue
        if raw == "entries: []":
            if schema != 1 or entries is not None:
                raise ValueError("invalid ci/quarantine.yaml")
            entries = []
            closed = True
            continue
        if raw == "entries:":
            if schema != 1 or entries is not None:
                raise ValueError("invalid ci/quarantine.yaml")
            entries = []
            continue
        if entries is None or closed:
            raise ValueError("invalid ci/quarantine.yaml")
        if raw.startswith("  - "):
            current = _entry_field(raw[4:], True, line_number)
            entries.append(current)
            continue
        if current is None or not raw.startswith("    "):
            raise ValueError(f"invalid quarantine yaml line {line_number}")
        _entry_field(raw[4:], False, line_number, current)
    if schema != 1 or entries is None:
        raise ValueError("invalid ci/quarantine.yaml")
    for entry in entries:
        if tuple(entry) != _ENTRY_KEYS:
            raise ValueError("invalid quarantine entry")
        nodeid = entry["id"]
        if (
            not nodeid.startswith("tests/")
            or "::" not in nodeid
            or nodeid != nodeid.strip()
            or any(character in nodeid for character in "\n\r")
        ):
            raise ValueError(f"invalid quarantine id: {nodeid}")
        if not entry["owner"].strip() or entry["owner"] != entry["owner"].strip():
            raise ValueError(f"invalid quarantine owner: {nodeid}")
        if _ISSUE.fullmatch(entry["issue"]) is None:
            raise ValueError(f"invalid quarantine issue: {nodeid}")
        if _DATE.fullmatch(entry["expires"]) is None:
            raise ValueError(f"invalid quarantine expiry: {nodeid}")
        date.fromisoformat(entry["expires"])
    return entries


def _entry_field(text, start, line_number, entry=None):
    if ": " not in text:
        raise ValueError(f"invalid quarantine yaml line {line_number}")
    key, value = text.split(": ", 1)
    index = 0 if start else len(entry)
    if index >= len(_ENTRY_KEYS):
        raise ValueError(f"invalid quarantine yaml line {line_number}")
    if key != _ENTRY_KEYS[index] or not value or value != value.strip():
        raise ValueError(f"invalid quarantine yaml line {line_number}")
    if start:
        entry = {}
    entry[key] = value
    return entry


def policy_cases(path, today=None):
    """Return active policy node ids. An expired entry fails closed."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid ci/quarantine.yaml")
    entries = parse_quarantine_yaml(path.read_text(encoding="utf-8"))
    today = today or datetime.now(timezone.utc).date()
    cases = {}
    for entry in entries:
        nodeid = entry["id"]
        expires = date.fromisoformat(entry["expires"])
        if today >= expires:
            raise ValueError(f"expired quarantine entry: {nodeid}")
        if nodeid in cases:
            raise ValueError(f"duplicate quarantine entry: {nodeid}")
        cases[nodeid] = entry["issue"]
    return cases


def known_failures(source):
    path = source / "tests/quarantine.json"
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid tests/quarantine.json")
    document = json.loads(path.read_bytes())
    if type(document.get("schema")) is not int or document["schema"] != 1 or not isinstance(document.get("entries"), list):
        raise ValueError("invalid quarantine schema")
    cases = {}
    today = datetime.now(timezone.utc).date()
    for entry in document["entries"]:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                                  for k in ("nodeid", "owner", "reason", "added", "expires")):
            raise ValueError("invalid quarantine entry")
        nodeid = entry["nodeid"]
        added, expires = (date.fromisoformat(entry[k]) for k in ("added", "expires"))
        if not added <= today < expires:
            raise ValueError(f"inactive or expired quarantine entry: {nodeid}")
        if not nodeid.startswith("tests/") or "::" not in nodeid or nodeid in cases:
            raise ValueError(f"invalid or duplicate quarantine nodeid: {nodeid}")
        cases[nodeid] = entry["reason"]
    return cases


def pytest_configure(config):
    source = Path(os.environ["YUETO_OPS_TEST_SOURCE"])
    if config.rootpath.resolve() != source.resolve():
        return
    policy_path = Path(os.environ["YUETO_CI_QUARANTINE"]) if os.environ.get("YUETO_CI_QUARANTINE") else POLICY_FILE
    cases = policy_cases(policy_path)
    cases.update(known_failures(source))
    selected = json.loads(os.environ.get("YUETO_SHARED_SELECTION") or "[]")
    prefixes = {}
    if selected:
        manifest = json.loads((Path(__file__).resolve().parents[1] / "ops-service-scope.json").read_bytes())
        prefixes = {row["service"]: tuple(manifest["tests"][row["service"]]) for row in selected}
    config.pluginmanager.register(FailurePolicy(cases, prefixes))


class FailurePolicy:
    def __init__(self, cases, prefixes):
        self.cases = cases
        self.prefixes = prefixes

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        report = (yield).get_result()
        if not report.failed:
            return
        reason = self.cases.get(item.nodeid) if call.when == "call" and call.excinfo is not None else None
        if reason is None:
            module = item.nodeid.split("::", 1)[0]
            for service, prefixes in self.prefixes.items():
                if module.startswith(prefixes):
                    (Path(os.environ["YUETO_OWNED_FAILURES"]) / service).touch()
                    reason = f"owned validation failed for {service}"
                    break
        if reason:
            report.outcome = "skipped"
            report.wasxfail = reason
            report.longrepr = (str(item.path), item.location[1], reason)
