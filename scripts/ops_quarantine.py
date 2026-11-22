"""Pytest policy for exact source-owned quarantine cases and shared Ops validation."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


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
    cases = known_failures(source)
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
