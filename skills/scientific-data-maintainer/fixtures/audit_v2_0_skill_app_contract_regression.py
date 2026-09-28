#!/usr/bin/env python3
"""Validate the v2.0 skill + app contract and canonical fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]

CONTRACT = ROOT / "references" / "v2-0-skill-app-contract.md"
FIXTURE_DIR = ROOT / "examples" / "contracts" / "v2_0"
FIXTURES = {
    "PASS": FIXTURE_DIR / "pass_envelope.json",
    "WARNING": FIXTURE_DIR / "warning_envelope.json",
    "BLOCKED_CONTROLADO": FIXTURE_DIR / "blocked_envelope.json",
    "FAIL": FIXTURE_DIR / "fail_envelope.json",
}

REQUIRED_FIELDS = [
    "contract_version",
    "tool",
    "capability_id",
    "capability_label",
    "status",
    "app_status",
    "command",
    "inputs",
    "outputs",
    "typed_artifacts",
    "warnings",
    "errors",
    "qa",
    "provenance",
    "next_actions",
    "original_modified",
    "app_hints",
    "job_metadata",
    "safety",
]

REQUIRED_CONTRACT_TERMS = [
    "Status Mapping",
    "Required Artifact Types",
    "Run Bundle Shape",
    "App Hints",
    "Error Contract",
    "Job Metadata",
    "Safety Policy",
    "summary_json",
    "manifest_json",
    "report_md",
    "preview_png",
    "table_csv",
    "notebook_ipynb",
    "log_txt",
    "qa_report",
    "handoff_bundle",
    "edited_document",
    "app_preview",
    "unknown",
]

ALLOWED_ARTIFACT_TYPES = {
    "summary_json",
    "manifest_json",
    "report_md",
    "preview_png",
    "table_csv",
    "notebook_ipynb",
    "log_txt",
    "qa_report",
    "handoff_bundle",
    "edited_document",
    "app_preview",
    "unknown",
    # v1.9 compatible additions remain accepted in v2.0.
    "fits_product",
    "fits_visual",
    "metadata_json",
    "preview_pdf",
}

ALLOWED_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}
ERROR_KINDS = {
    "missing_input",
    "output_conflict",
    "corrupt_input",
    "missing_optional_backend",
    "invalid_argument",
    "unsupported_format",
    "permission_denied",
    "timeout",
    "dependency_error",
    "execution_error",
    "tool_error",
}


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_fixture(status: str, path: Path, failures: list[str]) -> dict[str, object] | None:
    if not path.exists():
        fail(failures, f"Missing fixture for {status}: {path}")
        return None
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(failures, f"Fixture {path.name} is not valid JSON: {exc}")
        return None

    for field in REQUIRED_FIELDS:
        if field not in payload:
            fail(failures, f"{path.name} missing required field: {field}")

    if payload.get("contract_version") != "2.0":
        fail(failures, f"{path.name} contract_version is not 2.0")
    if payload.get("status") != status or payload.get("app_status") != status:
        fail(failures, f"{path.name} does not cover expected status {status}")
    if payload.get("status") not in ALLOWED_STATUSES:
        fail(failures, f"{path.name} has unsupported status {payload.get('status')!r}")

    typed = payload.get("typed_artifacts")
    if not isinstance(typed, list) or not typed:
        fail(failures, f"{path.name} must contain non-empty typed_artifacts")
    else:
        for artifact in typed:
            artifact_type = artifact.get("artifact_type")
            if artifact_type not in ALLOWED_ARTIFACT_TYPES:
                fail(failures, f"{path.name} has unregistered artifact_type {artifact_type!r}")
            if not artifact.get("path"):
                fail(failures, f"{path.name} has artifact without path")

    app_hints = payload.get("app_hints")
    if not isinstance(app_hints, dict):
        fail(failures, f"{path.name} app_hints must be an object")
    else:
        for field in ["short_summary", "severity", "preview_artifact_types", "tags"]:
            if field not in app_hints:
                fail(failures, f"{path.name} app_hints missing {field}")

    next_actions = payload.get("next_actions")
    if not isinstance(next_actions, list) or not next_actions:
        fail(failures, f"{path.name} must contain next_actions")

    if payload.get("original_modified") not in (False, True, "unknown"):
        fail(failures, f"{path.name} original_modified must be false/true/unknown")

    if status in {"BLOCKED_CONTROLADO", "FAIL"}:
        errors = payload.get("errors")
        if not isinstance(errors, list) or not errors:
            fail(failures, f"{path.name} must contain structured errors")
        else:
            for error in errors:
                if error.get("kind") not in ERROR_KINDS:
                    fail(failures, f"{path.name} has invalid error kind {error.get('kind')!r}")
                if not error.get("message"):
                    fail(failures, f"{path.name} has error without message")

    safety = payload.get("safety")
    if not isinstance(safety, dict) or safety.get("secrets_redacted") is not True:
        fail(failures, f"{path.name} safety.secrets_redacted must be true")

    return payload


def validate_app_parser(app_root: Path, failures: list[str]) -> None:
    parser = app_root / "Sources" / "ScientificWorkbench" / "Services" / "ToolEnvelopeParser.swift"
    tests = app_root / "Tests" / "ScientificWorkbenchTests" / "ArtifactAndJobModelTests.swift"
    if not parser.exists():
        fail(failures, "ScientificWorkbench ToolEnvelopeParser.swift not found")
        return
    if not tests.exists():
        fail(failures, "ScientificWorkbench ArtifactAndJobModelTests.swift not found")
        return

    parser_text = read_text(parser)
    test_text = read_text(tests)
    for term in [
        "contractVersion",
        "appStatus",
        "typedArtifacts",
        "ToolEnvelopeError",
        "ToolEnvelopeNextAction",
        "ToolEnvelopeAppHints",
        "originalModified",
    ]:
        if term not in parser_text:
            fail(failures, f"ToolEnvelopeParser missing v2.0 parser term: {term}")
    if "toolEnvelopeParserReadsV2ContractFields" not in test_text:
        fail(failures, "ScientificWorkbench missing v2.0 parser unit test")


def validate(args: argparse.Namespace) -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []

    if not CONTRACT.exists():
        fail(failures, f"Missing contract doc: {CONTRACT}")
    else:
        text = read_text(CONTRACT)
        for term in REQUIRED_CONTRACT_TERMS:
            if term not in text:
                fail(failures, f"Contract doc missing required term: {term}")

    fixture_payloads = {}
    for status, path in FIXTURES.items():
        payload = validate_fixture(status, path, failures)
        if payload is not None:
            fixture_payloads[status] = payload.get("tool")

    if set(fixture_payloads) != set(FIXTURES):
        fail(failures, f"Fixture status coverage mismatch: {sorted(fixture_payloads)}")

    validate_app_parser(Path(args.app_root), failures)

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_skill_app_contract_regression",
        "status": status,
        "contract_doc": str(CONTRACT),
        "fixture_dir": str(FIXTURE_DIR),
        "fixtures": fixture_payloads,
        "allowed_artifact_types": sorted(ALLOWED_ARTIFACT_TYPES),
        "app_root": str(Path(args.app_root)),
        "warnings": warnings,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--summary-json", default=None)
    args = parser.parse_args(argv)

    payload = validate(args)
    output = json.dumps(payload, indent=2, ensure_ascii=False)
    print(output)
    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
