#!/usr/bin/env python3
"""Validate the v1.8 app-ready JSON contract reference and examples."""

from __future__ import annotations

import json
import re
from pathlib import Path

from _internal.public_contract import build_tool_payload, validate_standard_envelope
from _internal.provenance_utils import normalize_status


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "references" / "v1-8-app-ready-contract.md"
CHARTER = ROOT / "references" / "v1-8-app-ready-backend.md"
TMP = ROOT / "tmp" / "v1_8_phase1_contract"

APP_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}
LEGACY_TO_APP = {
    "ok": "PASS",
    "pass": "PASS",
    "success": "PASS",
    "ready": "PASS",
    "warning": "WARNING",
    "skip": "WARNING",
    "skipped": "WARNING",
    "blocked": "BLOCKED_CONTROLADO",
    "fail": "FAIL",
    "failed": "FAIL",
    "error": "FAIL",
}
ARTIFACT_TYPES = {
    "summary_json",
    "manifest_json",
    "report_md",
    "preview_png",
    "table_csv",
    "notebook_ipynb",
    "log_txt",
    "qa_report",
    "handoff_bundle",
    "unknown",
}
REQUIRED_FIELDS = [
    "contract_version",
    "tool",
    "status",
    "command",
    "inputs",
    "outputs",
    "artifacts",
    "warnings",
    "errors",
    "qa",
    "provenance",
    "next_actions",
    "original_modified",
    "app_hints",
]


def app_status(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if rendered in APP_STATUSES:
        return rendered
    normalized = normalize_status(rendered) or rendered.lower()
    return LEGACY_TO_APP.get(normalized)


def extract_json_examples(markdown: str) -> list[dict]:
    examples: list[dict] = []
    for match in re.finditer(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL):
        raw = match.group(1)
        try:
            examples.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Invalid JSON example: {exc}") from exc
    return examples


def validate_app_ready_payload(payload: dict) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            issues.append(f"missing required field: {field}")
    if payload.get("contract_version") != "1.8":
        issues.append("contract_version must be 1.8")
    status = app_status(payload.get("status"))
    if status not in APP_STATUSES:
        issues.append(f"invalid app status: {payload.get('status')}")
    if not isinstance(payload.get("tool"), str) or not payload.get("tool"):
        issues.append("tool must be a non-empty string")
    if not isinstance(payload.get("command"), dict):
        issues.append("command must be an object")
    if not isinstance(payload.get("inputs"), list):
        issues.append("inputs must be a list")
    if not isinstance(payload.get("outputs"), list):
        issues.append("outputs must be a list")
    if not isinstance(payload.get("artifacts"), list):
        issues.append("artifacts must be a list in v1.8-native examples")
    else:
        for index, artifact in enumerate(payload["artifacts"]):
            if not isinstance(artifact, dict):
                issues.append(f"artifact {index} must be an object")
                continue
            artifact_type = artifact.get("artifact_type")
            if artifact_type not in ARTIFACT_TYPES:
                issues.append(f"artifact {index} has unknown artifact_type: {artifact_type}")
    if not isinstance(payload.get("warnings"), list):
        issues.append("warnings must be a list")
    if not isinstance(payload.get("errors"), list):
        issues.append("errors must be a list")
    if not isinstance(payload.get("qa"), dict):
        issues.append("qa must be an object")
    else:
        qa_status = app_status(payload["qa"].get("status"))
        if qa_status not in APP_STATUSES:
            issues.append(f"invalid qa.status: {payload['qa'].get('status')}")
    if payload.get("original_modified") not in {True, False, "unknown"}:
        issues.append("original_modified must be true, false, or unknown")
    if not isinstance(payload.get("next_actions"), list):
        issues.append("next_actions must be a list")
    if not isinstance(payload.get("app_hints"), dict):
        issues.append("app_hints must be an object")
    else:
        for field in ("short_summary", "severity", "preview_artifact_types", "tags"):
            if field not in payload["app_hints"]:
                issues.append(f"app_hints missing {field}")
    return issues


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    TMP.mkdir(parents=True, exist_ok=True)

    if not CONTRACT.exists():
        failures.append("contract reference is missing")
        examples: list[dict] = []
    else:
        text = CONTRACT.read_text(encoding="utf-8")
        required_terms = [
            "v1.8 App-Ready JSON Contract",
            "Existing Compatibility Layer",
            "Canonical App Statuses",
            "Minimum v1.8 Envelope",
            "Artifact Taxonomy",
            "Example: PASS",
            "Example: WARNING",
            "Example: BLOCKED_CONTROLADO",
            "Example: FAIL Limpio",
            "Migration Policy",
            "Compatibility Decision",
            "`summary_json`",
            "`manifest_json`",
            "`report_md`",
            "`preview_png`",
            "`table_csv`",
            "`notebook_ipynb`",
            "`log_txt`",
            "`qa_report`",
            "`handoff_bundle`",
            "`unknown`",
        ]
        for term in required_terms:
            if term not in text:
                failures.append(f"contract reference missing term: {term}")
        examples = extract_json_examples(text)

    app_ready_examples = [item for item in examples if item.get("contract_version") == "1.8"]
    if len(app_ready_examples) < 4:
        failures.append(f"expected at least 4 v1.8 JSON examples, got {len(app_ready_examples)}")

    statuses_seen = set()
    for index, payload in enumerate(app_ready_examples):
        issues = validate_app_ready_payload(payload)
        if issues:
            failures.append(f"example {index} failed validation: {issues}")
        normalized = app_status(payload.get("status"))
        if normalized:
            statuses_seen.add(normalized)

    missing_statuses = APP_STATUSES - statuses_seen
    if missing_statuses:
        failures.append(f"missing example statuses: {sorted(missing_statuses)}")

    legacy_payload = build_tool_payload(
        "legacy_v1_7_compatible",
        status="ok",
        notes=["legacy envelope remains valid"],
        artifacts={"summary_json": TMP / "legacy_summary.json"},
        results={"rows": 3},
        qa={"status": "not_applicable", "findings": [], "metrics": {}},
    )
    legacy_issues = validate_standard_envelope(legacy_payload)
    if legacy_issues:
        failures.append(f"legacy standard envelope should remain valid: {legacy_issues}")
    if app_status(legacy_payload.get("status")) != "PASS":
        failures.append("legacy ok status should normalize to PASS")

    blocked_payload = build_tool_payload(
        "legacy_blocked_compatible",
        status="blocked",
        notes=["optional backend missing"],
        artifacts={},
        results={},
        qa={"status": "warning", "findings": ["backend missing"], "metrics": {}},
    )
    if app_status(blocked_payload.get("status")) != "BLOCKED_CONTROLADO":
        failures.append("legacy blocked status should normalize to BLOCKED_CONTROLADO")

    if CHARTER.exists():
        charter_text = CHARTER.read_text(encoding="utf-8")
        if "app-ready JSON contract" not in charter_text and "JSON contract" not in charter_text:
            warnings.append("charter does not explicitly name the JSON contract yet")
    else:
        warnings.append("v1.8 charter reference missing; Fase 0 may not have run")

    payload = {
        "status": "FAIL" if failures else ("WARNING" if warnings else "PASS"),
        "phase": "v1.8 phase 1 app-ready contract",
        "contract": str(CONTRACT),
        "examples_checked": len(app_ready_examples),
        "statuses_seen": sorted(statuses_seen),
        "artifact_types": sorted(ARTIFACT_TYPES),
        "legacy_compatibility": {
            "standard_envelope_valid": not legacy_issues,
            "legacy_ok_maps_to": app_status(legacy_payload.get("status")),
            "legacy_blocked_maps_to": app_status(blocked_payload.get("status")),
        },
        "warnings": warnings,
        "failures": failures,
    }
    (TMP / "contract_regression.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
