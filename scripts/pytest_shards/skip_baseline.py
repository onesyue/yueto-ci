"""Read and generate the ops pytest skip baseline."""
from __future__ import annotations

import ast
import json
import xml.etree.ElementTree as ET

from .config import (
    NATIVE_INPUTS,
    RETIRED_HOST_AFTER_BLOB,
    RETIRED_HOST_SECOND_AFTER_BLOB,
    RETIRED_HOST_THIRD_AFTER_BLOB,
    SHA,
    SKIP_BASELINE,
)
from .support import (
    RETIRED_HOST_SECOND_IDS,
    RETIRED_HOST_THIRD_IDS,
    ROOT,
    read_json,
    require,
    safe_module,
    sha,
    shared_inputs,
    tree_inputs,
)
from .transitions_native import required_native_inputs


def retired_host_case_admitted(retirement, sealed_cases, nodeid, row, live_blob):
    if nodeid not in retirement["surviving_ids"]:
        return False
    sealed = sealed_cases.get(nodeid)
    if live_blob in (RETIRED_HOST_SECOND_AFTER_BLOB, RETIRED_HOST_THIRD_AFTER_BLOB):
        absent = RETIRED_HOST_SECOND_IDS | (
            RETIRED_HOST_THIRD_IDS if live_blob == RETIRED_HOST_THIRD_AFTER_BLOB else set())
        return (nodeid not in absent and isinstance(sealed, dict)
                and sealed.get("module_blob") == RETIRED_HOST_AFTER_BLOB
                and {"outcome": row["outcome"], "reason": row.get("reason")}
                == {"outcome": sealed.get("outcome"), "reason": sealed.get("reason")})
    return {"outcome": row["outcome"], "reason": row.get("reason"),
            "module_blob": live_blob} == sealed


def collection_skips(path, modules):
    require(path.is_file() and not path.is_symlink(), "missing native JUnit evidence")
    data = path.read_bytes()
    require(len(data) <= 32 * 1024 * 1024
            and b"<!DOCTYPE" not in data and b"<!ENTITY" not in data, "unsafe JUnit evidence")
    root = ET.fromstring(data)
    require(root.tag == "testsuites" and len(root.findall("testsuite")) == 1,
            "unexpected JUnit document")
    suite = root.find("testsuite")
    require(suite.get("errors") == "0" and suite.get("failures") == "0",
            "failed JUnit evidence")
    result = {}
    for case in suite.findall("testcase"):
        skipped = case.find("skipped")
        if skipped is None or skipped.get("message") != "collection skipped":
            continue
        matches = [m for m in modules if m[:-3].replace("/", ".") == case.get("name")]
        require(case.get("classname") == "" and len(matches) == 1, "unbound collection skip")
        module = matches[0]
        detail = ast.literal_eval(skipped.text or "")
        require(isinstance(detail, tuple) and len(detail) == 3
                and isinstance(detail[0], str) and isinstance(detail[1], int)
                and isinstance(detail[2], str) and detail[2]
                and (detail[0] == module or detail[0].endswith("/" + module))
                and module not in result, "invalid collection skip identity")
        result[module] = detail[2]
    return result


def baseline_events(path, allowed_exit=(0,)):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    starts = [r for r in rows if r.get("event") == "start"]
    ends = [r for r in rows if r.get("event") == "finish"]
    timings = [r for r in rows if r.get("event") == "session_timing"]
    require(rows and rows[0].get("event") == "start" and rows[-1].get("event") == "finish"
            and len(starts) == len(ends) == len(timings) == 1
            and ends[0].get("exitstatus") in allowed_exit
            and timings[0].get("exitstatus") == ends[0]["exitstatus"]
            and timings[0].get("terminal") == "finished" and timings[0].get("lost_records") == 0
            and not any(r.get("event") == "collect_error" or r.get("outcome") == "failed"
                        for r in rows), "incomplete or failed skip baseline")
    context = {k: starts[0].get(k) for k in ("platform", "uid")}
    require(isinstance(context["platform"], str) and type(context["uid"]) is int
            and context["uid"] > 0, "baseline context must be actual nonroot execution")
    return rows, context


def generate_skip_baseline(source, revision, events, collection_xml, collection_events,
                           collection_revision, collection_at):
    """Generate reviewed historical SKIP data; never infer PASS or refresh during a run."""
    files = tree_inputs(source, revision)
    rows, context = baseline_events(events)
    _, collection_context = baseline_events(collection_events, (0, 5))
    require(context == collection_context, "historical collection context differs")
    common = shared_inputs(source, revision)
    require(common == shared_inputs(source, collection_revision),
            "historical collection shared inputs differ")
    historical_files = tree_inputs(source, collection_revision)
    modules = {p for p in files if safe_module(p)}
    collected = collection_skips(collection_xml, modules)
    cases = {}
    for row in rows:
        if "event" in row or row.get("outcome") not in ("skipped", "xfail"):
            continue
        nodeid, reason = row.get("nodeid"), row.get("reason")
        require(isinstance(nodeid, str) and isinstance(reason, str) and reason,
                "unidentified baseline skip")
        module = nodeid.split("::", 1)[0]
        require(module in modules and files[module][0] in ("100644", "100755"),
                "baseline skip module is not owned")
        record = {"outcome": row["outcome"], "reason": reason, "module_blob": files[module][1]}
        require(nodeid not in cases or cases[nodeid] == record, "contradictory baseline skip")
        cases[nodeid] = record
    require(cases or collected, "empty skip baseline")
    collection = {}
    for module, reason in collected.items():
        require(files[module] == historical_files.get(module), "historical skipped module differs")
        collection[module] = {"reason": reason, "module_blob": files[module][1]}
    require(isinstance(collection_at, str) and collection_at.strip(),
            "historical collection timestamp missing")
    return {
        "schema": 1, "status": "HISTORICAL_SKIPS_NOT_PASSES", "source_revision": revision,
        "events_sha256": sha(events.read_bytes()), "context": context, "common_inputs": common,
        "cases": cases, "collection_skips": collection,
        "collection_evidence": {
            "source_revision": collection_revision, "recorded_at": collection_at,
            "xml_sha256": sha(collection_xml.read_bytes()),
            "events_sha256": sha(collection_events.read_bytes()), "context": collection_context,
            "inheritance": "Exact module and shared inputs only; not a new source execution.",
        },
    }


def skip_baseline():
    value = read_json(ROOT / SKIP_BASELINE)
    require(value.get("schema") == 1 and value.get("status") == "HISTORICAL_SKIPS_NOT_PASSES"
            and SHA.fullmatch(value.get("source_revision", ""))
            and value.get("common_inputs") and isinstance(value.get("cases"), dict)
            and isinstance(value.get("collection_skips"), dict), "invalid skip baseline")
    _, required = required_native_inputs(value)
    require(not required or required == NATIVE_INPUTS,
            "required native input successor missing")
    return value
