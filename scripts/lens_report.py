"""pytest 被动结果记录插件（Linux 镜头闸门用）。

只读、只记：不改变任何用例的收集、顺序或结果。每个用例阶段一行 JSON，追加写入
``$LENS_REPORT``。run-pytest-parallel.sh 会先后起两次 pytest（并行主体 + 串行尾巴），
所以用追加而不是覆盖（--junitxml 会被第二次覆盖，这正是不用它的原因）。

写者只有一个：
- xdist worker（有 ``workerinput``）不写——控制进程会收到同一份报告；
- 被测代码里嵌套起来的 pytest（继承了 ``LENS_REPORT_OWNER``）不写——
  否则夹具项目里的假用例会混进被测仓的结果。

每次 pytest 会话结束写一行 ``{"event": "finish", "exitstatus": N}``；分析器用它
证明「这次真的跑完了」，没有 finish 行 = 进程夭折 = FAIL。
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import sys
import time

import pytest

# 观测者不能被被测代码改写：用例会 monkeypatch os.open / json.dumps（2026-10-12 实测
# tests/test_relay_tuning_patch_release_20260905.py 把 os.open 换成 pytest.fail，记录钩子
# 在那条用例的报告阶段调到它 → INTERNALERROR → 整个会话死在 69%）。导入时就绑定原函数。
_os_open, _os_write, _os_close, _getpid = os.open, os.write, os.close, os.getpid
# Match the root predicates used by the native fixtures (effective UID).
_getuid, _platform = os.geteuid, sys.platform
_dumps = json.dumps
_isfinite = math.isfinite
_monotonic, _time_ns, _sha256 = time.monotonic, time.time_ns, hashlib.sha256
_ENV_OWNER = "LENS_REPORT_OWNER"
_active = False
_path = ""
_config = None
_nested = 0
_lost_records = 0
_started = 0.0
_session_id = ""


def _write(record: dict) -> None:
    global _lost_records
    line = _dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        fd = _os_open(_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            payload = line.encode("utf-8")
            while payload:
                written = _os_write(fd, payload)
                if written <= 0:
                    raise OSError("timing record write made no progress")
                payload = payload[written:]
        finally:
            _os_close(fd)
    except OSError:
        # Observation cannot change the test result. A later terminal record
        # exposes the loss; a missing terminal record remains partial evidence.
        _lost_records += 1


def pytest_configure(config):
    global _active, _path, _config, _nested, _started, _session_id, _lost_records
    if _active:
        _nested += 1
        return
    _path = os.environ.get("LENS_REPORT", "")
    if not _path or hasattr(config, "workerinput"):
        return
    owner = os.environ.get(_ENV_OWNER, "")
    if owner and owner != str(os.getpid()):
        return  # 被测代码里的嵌套 pytest
    os.environ[_ENV_OWNER] = str(os.getpid())
    _active = True
    _config, _lost_records = config, 0
    _started = _monotonic()
    _session_id = f"{_getpid()}-{_time_ns()}"
    _write({"event": "start", "pid": _getpid(), "platform": _platform, "uid": _getuid()})
    _write({
        "event": "session_identity", "schema": 1, "session_id": _session_id,
        "started_unix_ns": _time_ns(), "python": sys.version,
        "python_executable": sys.executable, "pytest": pytest.__version__,
        "executor": "xdist-controller" if config.getoption("numprocesses", default=0) else "serial",
        "resources": {"aggregate_peak_rss_bytes": None, "cpu_seconds": None,
                      "status": "UNKNOWN", "scope": "not_collected"},
        # Only the immutable receipt identifier is imported, never arbitrary env.
        "invocation_id": os.environ.get("LENS_INVOCATION_ID") or None,
    })


def pytest_unconfigure(config):
    global _active, _config, _nested
    if config is _config:
        _active, _config, _nested = False, None, 0
    elif _nested:
        _nested -= 1


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):
    enabled = _active and not _nested
    started = _monotonic()
    if enabled:
        _write({"event": "collection_start", "schema": 1, "session_id": _session_id})
    outcome = yield
    if enabled:
        _write({
            "event": "collection_timing", "schema": 1, "session_id": _session_id,
            "duration_seconds": _monotonic() - started,
            "scope": "controller_collection_hook",
            "status": "failed" if outcome.excinfo else "finished",
        })


def _corpus(nodeids, scope):
    _write({
        "event": "collection_corpus", "schema": 1, "session_id": _session_id,
        "scope": scope, "nodeids": nodeids, "count": len(nodeids),
        "ordered_nodeids_sha256": _sha256(_dumps(nodeids, ensure_ascii=False).encode()).hexdigest(),
    })


def pytest_collection_finish(session):
    if _active and not _nested:
        _corpus([item.nodeid for item in session.items], "controller_selected")


def pytest_deselected(items):
    if _active and not _nested:
        _corpus([item.nodeid for item in items], "controller_deselected")


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    if _active and not _nested:
        _corpus(list(ids), "worker:" + node.gateway.id)


def _reason(report) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    if longrepr is None:
        return ""
    text = str(longrepr)
    return text[-400:]


def pytest_runtest_logreport(report):
    if not _active or _nested:
        return
    # Timing is an additive event, never an outcome row: a successful teardown
    # must not replace a skip/xfail in the existing outcome consumer.
    report_class = type(report)
    report_type = f"{report_class.__module__}.{report_class.__qualname__}"
    kind = "case" if report_type == "_pytest.reports.TestReport" else (
        "subtest" if report_class.__name__.lower() == "subtestreport" else "unknown"
    )
    duration = getattr(report, "duration", None)
    try:
        measured = type(duration) in (int, float) and _isfinite(duration) and duration >= 0
    except OverflowError:
        measured = False
    _write({
        "event": "phase_timing", "schema": 1, "nodeid": report.nodeid,
        "when": report.when, "outcome": report.outcome,
        "report_type": report_type, "report_kind": kind,
        "duration_seconds": duration if measured else None,
        "duration_status": "measured" if measured else "unavailable",
    })
    # Parent call duration includes subtests. Consumers must not add child
    # durations again or combine records from separate start/finish sessions.
    if report.when == "call" or report.outcome != "passed":
        outcome = report.outcome
        if hasattr(report, "wasxfail"):
            outcome = "xfail" if report.skipped else "xpass"
        _write({
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": outcome,
            "reason": _reason(report) if outcome in ("skipped", "xfail") else "",
        })


def pytest_collectreport(report):
    if _active and not _nested and report.failed:
        _write({"event": "collect_error", "nodeid": report.nodeid})


def pytest_sessionfinish(session, exitstatus):
    if _active and not _nested:
        _write({
            "event": "session_timing", "schema": 1, "session_id": _session_id,
            "duration_seconds": _monotonic() - _started,
            "duration_scope": "pytest_configure_to_sessionfinish",
            "finished_unix_ns": _time_ns(), "lost_records": _lost_records,
            "exitstatus": int(exitstatus),
            "terminal": "finished" if int(exitstatus) in (0, 1, 5) else "interrupted_or_error",
        })
        _write({"event": "finish", "exitstatus": int(exitstatus)})
