#!/usr/bin/env python3
"""Validate v2.0 Phase 2 parser/artifact-discovery readiness."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_phase2_parser_artifacts"

REQUIRED_PARSER_TERMS = [
    "ToolEnvelopeCommand",
    "ToolEnvelopeIORecord",
    "command:",
    "inputs:",
    "outputs:",
    "typedArtifacts",
    "ToolEnvelopeError",
    "ToolEnvelopeNextAction",
    "ToolEnvelopeAppHints",
    "originalModified",
]

REQUIRED_TEST_TERMS = [
    "toolEnvelopeParserReadsV2ContractFields",
    "artifactDiscoveryReadsTypedRunBundleMetadata",
]

REQUIRED_ARTIFACT_DISCOVERY_TERMS = [
    "loadTypedArtifactMetadata",
    "typed_artifacts",
    "manifest.json",
    "summary.json",
    "artifactType:",
]


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_profile_table_fixture(python: str, failures: list[str]) -> Path | None:
    fixture_dir = TMP / "fixtures" / "v1_9_real_generated"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    table = fixture_dir / "professional_table.csv"
    table.write_text(
        "date,value,segment\n2026-06-01,10,A\n2026-06-02,12,A\n2026-06-03,9,B\n",
        encoding="utf-8",
    )
    summary = fixture_dir / "profile_table_summary.json"
    manifest = fixture_dir / "profile_table_manifest.json"
    stdout = fixture_dir / "profile_table_stdout.txt"
    stderr = fixture_dir / "profile_table_stderr.txt"
    cmd = [
        python,
        str(ROOT / "scripts" / "profile_table.py"),
        str(table),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        fail(failures, f"profile_table fixture generation failed with {result.returncode}: {result.stderr[:500]}")
        return None
    if not summary.exists():
        fail(failures, "profile_table fixture did not create summary JSON")
        return None
    return summary


def validate_v1_9_summary(summary: Path, failures: list[str]) -> None:
    payload = read_json(summary)
    expected = {
        "contract_version": "1.8",
        "tool": "profile_table",
        "app_status": "PASS",
        "original_modified": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            fail(failures, f"v1.9/v1.8 real fixture {key} expected {value!r}, got {payload.get(key)!r}")
    for field in ["typed_artifacts", "app_hints", "next_actions", "command", "inputs", "outputs"]:
        if field not in payload:
            fail(failures, f"v1.9/v1.8 real fixture missing {field}")


def validate_v2_fixtures(failures: list[str]) -> None:
    fixture_dir = ROOT / "examples" / "contracts" / "v2_0"
    for name in ["pass_envelope.json", "warning_envelope.json", "blocked_envelope.json", "fail_envelope.json"]:
        path = fixture_dir / name
        if not path.exists():
            fail(failures, f"Missing v2.0 fixture {name}")
            continue
        payload = read_json(path)
        for field in ["command", "inputs", "outputs", "typed_artifacts", "app_hints", "next_actions", "original_modified", "errors"]:
            if field not in payload:
                fail(failures, f"{name} missing {field}")


def validate_app_sources(app_root: Path, failures: list[str]) -> None:
    parser = app_root / "Sources" / "ScientificWorkbench" / "Services" / "ToolEnvelopeParser.swift"
    discovery = app_root / "Sources" / "ScientificWorkbench" / "Services" / "ArtifactDiscovery.swift"
    models = app_root / "Sources" / "ScientificWorkbench" / "Models" / "RunModels.swift"
    tests = app_root / "Tests" / "ScientificWorkbenchTests" / "ArtifactAndJobModelTests.swift"
    for path in [parser, discovery, models, tests]:
        if not path.exists():
            fail(failures, f"Missing app source/test file: {path}")
            return

    parser_text = parser.read_text(encoding="utf-8")
    for term in REQUIRED_PARSER_TERMS:
        if term not in parser_text:
            fail(failures, f"ToolEnvelopeParser missing {term}")

    discovery_text = discovery.read_text(encoding="utf-8")
    for term in REQUIRED_ARTIFACT_DISCOVERY_TERMS:
        if term not in discovery_text:
            fail(failures, f"ArtifactDiscovery missing {term}")

    model_text = models.read_text(encoding="utf-8")
    for term in ["artifactType", "label", "primary"]:
        if term not in model_text:
            fail(failures, f"Artifact model missing {term}")

    test_text = tests.read_text(encoding="utf-8")
    for term in REQUIRED_TEST_TERMS:
        if term not in test_text:
            fail(failures, f"Artifact/parser tests missing {term}")


def validate(args: argparse.Namespace) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    summary = run_profile_table_fixture(args.python, failures)
    if summary is not None:
        validate_v1_9_summary(summary, failures)
    validate_v2_fixtures(failures)
    validate_app_sources(Path(args.app_root), failures)

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_phase2_parser_artifacts_regression",
        "status": status,
        "tmp": str(TMP),
        "v1_9_real_fixture": str(summary) if summary else None,
        "app_root": str(Path(args.app_root)),
        "warnings": warnings,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--summary-json", default=None)
    args = parser.parse_args(argv)
    payload = validate(args)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
