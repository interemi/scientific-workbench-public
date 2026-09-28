#!/usr/bin/env python3
"""Shared helpers for public CLI contracts in scientific-data-analysis."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .provenance_utils import (
    STANDARD_QA_STATUSES,
    STANDARD_TOOL_STATUSES,
    normalize_status,
    sanitize_payload,
    standard_qa_payload,
    standard_tool_payload,
)


def resolve_output_path(*candidates) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        return Path(candidate)
    return None


def _write_text_atomically(path: str | Path, rendered: str) -> None:
    """Replace one output path without following symlink or hard-link aliases."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def emit_payload(payload: dict, summary_json: str | Path | None = None) -> str:
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    print(rendered, end="")
    if summary_json:
        _write_text_atomically(summary_json, rendered)
    return rendered


def emit_payload_best_effort(payload: dict, summary_json: str | Path | None = None) -> str:
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    print(rendered, end="")
    if summary_json:
        try:
            _write_text_atomically(summary_json, rendered)
        except OSError:
            pass
    return rendered


def build_tool_payload(
    tool: str,
    status: str | None = None,
    notes: list[str] | None = None,
    artifacts: dict | None = None,
    results: dict | None = None,
    qa: dict | None = None,
    legacy: dict | None = None,
    include_environment: bool = False,
    command=None,
    inputs=None,
) -> dict:
    return standard_tool_payload(
        tool,
        status=status,
        notes=notes,
        artifacts=artifacts,
        results=results,
        qa=qa,
        legacy=legacy,
        include_environment=include_environment,
        command=command,
        inputs=inputs,
    )


def build_blocked_payload(
    tool: str,
    message: str,
    *,
    notes: list[str] | None = None,
    artifacts: dict | None = None,
    results: dict | None = None,
    qa_metrics: dict | None = None,
    legacy: dict | None = None,
    include_environment: bool = False,
    command=None,
    inputs=None,
) -> dict:
    merged_results = dict(results or {})
    merged_results.setdefault("blocked_reason", message)
    metrics = {"blocking_count": 1}
    metrics.update(qa_metrics or {})
    merged_legacy = {"blocked_reason": message}
    merged_legacy.update(legacy or {})
    return build_tool_payload(
        tool,
        status="blocked",
        notes=notes,
        artifacts=artifacts,
        results=merged_results,
        qa={"status": "blocked", "findings": [message], "metrics": metrics},
        legacy=merged_legacy,
        include_environment=include_environment,
        command=command,
        inputs=inputs,
    )


def build_preflight_payload(
    tool: str,
    status: str,
    capabilities: dict | None = None,
    recommendation: str | None = None,
    blocking_findings: list[str] | None = None,
    warning_findings: list[str] | None = None,
    notes: list[str] | None = None,
    artifacts: dict | None = None,
    results: dict | None = None,
    qa: dict | None = None,
    legacy: dict | None = None,
    include_environment: bool = False,
    command=None,
    inputs=None,
) -> dict:
    normalized_status = normalize_status(status) or "warning"
    report = {
        "status": normalized_status,
        "blocking_findings": list(blocking_findings or []),
        "warning_findings": list(warning_findings or []),
        "recommendation": recommendation,
        "capabilities": capabilities or {},
    }
    merged_results = dict(results or {})
    merged_results.update(report)
    qa_block = qa or standard_qa_payload(
        status="ok" if normalized_status == "ok" else "warning",
        findings=report["blocking_findings"] + report["warning_findings"],
        metrics={
            "capability_count": len(report["capabilities"]),
            "blocking_count": len(report["blocking_findings"]),
            "warning_count": len(report["warning_findings"]),
        },
    )
    return build_tool_payload(
        tool,
        status=normalized_status,
        notes=notes,
        artifacts=artifacts,
        results=merged_results,
        qa=qa_block,
        legacy=legacy,
        include_environment=include_environment,
        command=command,
        inputs=inputs,
    )


def validate_standard_envelope(payload: dict, require_qa: bool = True) -> list[str]:
    issues = []
    if not isinstance(payload, dict):
        return ["Payload is not a JSON object."]
    for key in ("tool", "status", "notes", "artifacts", "results"):
        if key not in payload:
            issues.append(f"Missing top-level key: {key}")
    status = normalize_status(payload.get("status"))
    if status not in STANDARD_TOOL_STATUSES:
        issues.append(f"Invalid top-level status: {payload.get('status')}")
    if not isinstance(payload.get("notes"), list):
        issues.append("Top-level 'notes' must be a list.")
    if not isinstance(payload.get("artifacts"), dict):
        issues.append("Top-level 'artifacts' must be an object.")
    if not isinstance(payload.get("results"), dict):
        issues.append("Top-level 'results' must be an object.")
    if require_qa:
        qa = payload.get("qa")
        if not isinstance(qa, dict):
            issues.append("Missing or invalid 'qa' block.")
        else:
            qa_status = normalize_status(qa.get("status")) or "not_applicable"
            if qa_status not in STANDARD_QA_STATUSES:
                issues.append(f"Invalid qa.status: {qa.get('status')}")
            if not isinstance(qa.get("findings"), list):
                issues.append("qa.findings must be a list.")
            if not isinstance(qa.get("metrics"), dict):
                issues.append("qa.metrics must be an object.")
    return issues
