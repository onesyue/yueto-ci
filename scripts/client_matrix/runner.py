"""Cell plans and the report. Dial failures stay in the report."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from client_matrix.catalog import (
    CLIENTS,
    PROTOCOLS,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNSUPPORTED,
    client_speaks,
    node_group,
)

_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_SECRET = re.compile(r"\b(?:[0-9a-fA-F]{16,}|[A-Za-z0-9_-]{24,}={0,2})\b")
Dial = Callable[["CellPlan"], tuple[str, str]]


@dataclass(frozen=True)
class CellPlan:
    client_id: str
    protocol: str
    group: str
    supported: bool
    reason: str


@dataclass(frozen=True)
class CellResult:
    client_id: str
    protocol: str
    status: str
    detail: str


def plans() -> tuple[CellPlan, ...]:
    found: list[CellPlan] = []
    for protocol in PROTOCOLS:
        for pin in CLIENTS:
            speaks = client_speaks(pin, protocol)
            reason = "" if speaks else f"{pin.client_id} does not speak {protocol}"
            found.append(
                CellPlan(
                    client_id=pin.client_id,
                    protocol=protocol,
                    group=node_group(protocol),
                    supported=speaks,
                    reason=reason,
                )
            )
    return tuple(found)


def execute(cell_plans: tuple[CellPlan, ...], dial: Dial) -> tuple[CellResult, ...]:
    results: list[CellResult] = []
    for plan in cell_plans:
        if not plan.supported:
            results.append(_result(plan, STATUS_UNSUPPORTED, plan.reason))
            continue
        status, detail = dial(plan)
        detail = redact(detail)
        if status not in {STATUS_PASS, STATUS_FAIL, STATUS_UNSUPPORTED}:
            status = STATUS_FAIL
            detail = "dial returned an unknown status"
        results.append(_result(plan, status, detail))
    return tuple(results)


def strict_exit(results: tuple[CellResult, ...]) -> int:
    if any(item.status == STATUS_FAIL for item in results):
        return 1
    return 0


def build_report(
    yue_node_ref: str,
    report_only: bool,
    results: tuple[CellResult, ...],
) -> dict:
    summary = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_UNSUPPORTED: 0, "total": len(results)}
    cells = []
    for item in results:
        summary[item.status] = summary.get(item.status, 0) + 1
        cells.append(
            {
                "client": item.client_id,
                "protocol": item.protocol,
                "status": item.status,
                "detail": item.detail,
            }
        )
    return {
        "yue_node_ref": yue_node_ref,
        "report_only": report_only,
        "clients": [
            {
                "client_id": pin.client_id,
                "version": pin.version,
                "repository": pin.repository,
                "commit": pin.commit,
                "asset": pin.asset,
                "sha256": pin.sha256,
                "archive": pin.archive,
            }
            for pin in CLIENTS
        ],
        "summary": summary,
        "cells": cells,
    }


def write_report(prefix: Path, report: dict) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    prefix.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict) -> str:
    lines = [
        "# Client core interop matrix",
        "",
        f"yue-node `{report['yue_node_ref']}`",
        "",
        "| Client | Protocol | Status | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for cell in report["cells"]:
        detail = str(cell["detail"]).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {cell['client']} | {cell['protocol']} | {cell['status']} | {detail} |"
        )
    summary = report["summary"]
    lines.extend(
        [
            "",
            (
                "Summary: "
                f"pass={summary[STATUS_PASS]} "
                f"fail={summary[STATUS_FAIL]} "
                f"unsupported={summary[STATUS_UNSUPPORTED]} "
                f"total={summary['total']}"
            ),
            "",
            "Gating is off. A failing cell does not fail this job.",
            "",
        ]
    )
    return "\n".join(lines)


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    redacted = _UUID.sub("[redacted]", redacted)
    redacted = _SECRET.sub("[redacted]", redacted)
    return redacted[:400]


def _result(plan: CellPlan, status: str, detail: str) -> CellResult:
    return CellResult(
        client_id=plan.client_id,
        protocol=plan.protocol,
        status=status,
        detail=detail,
    )
