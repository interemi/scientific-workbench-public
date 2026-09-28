#!/usr/bin/env python3
"""Regression for v2.0 P1-10 STILTS/TOPCAT optional app panel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "v2_0_p1_10_stilts" / "regression"
PREFLIGHT = ROOT / "scripts" / "external_astro_tools_preflight.py"
STILTS = ROOT / "scripts" / "stilts_workbench.py"
REFERENCE = ROOT / "references" / "v2-0-p1-10-stilts-topcat-panel.md"
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]


def run_json(command: list[str], summary: Path) -> tuple[int, dict]:
    summary.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [*command, "--summary-json", str(summary)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if not summary.exists():
        return completed.returncode, {
            "_missing_summary": True,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    return completed.returncode, json.loads(summary.read_text(encoding="utf-8"))


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def validate_blocked(name: str, code: int, payload: dict, failures: list[str]) -> None:
    if code != 2:
        fail(failures, f"{name}: expected exit 2, found {code}")
    if payload.get("app_status") != "BLOCKED_CONTROLADO":
        fail(failures, f"{name}: expected BLOCKED_CONTROLADO")
    errors = payload.get("errors") or []
    if not errors or errors[0].get("kind") != "missing_optional_backend":
        fail(failures, f"{name}: expected errors.kind=missing_optional_backend")
    results = payload.get("results") or {}
    alternative = results.get("native_alternative") or (results.get("native_alternatives") or {}).get("stilts")
    if not alternative or alternative.get("capability_id") != "catalog_workbench.crossmatch-sky":
        fail(failures, f"{name}: native catalog alternative missing")
    if payload.get("original_modified") is not False:
        fail(failures, f"{name}: original_modified must be false")


def validate_app_wiring(app_root: Path, failures: list[str]) -> None:
    required = {
        "Models/OptionalAstronomyBackendModels.swift": [
            "OptionalAstronomyBackendStatus",
            "OptionalBackendState",
        ],
        "Services/OptionalAstronomyBackendService.swift": [
            "external_astro_tools_preflight",
            "--require-stilts",
            "catalog_workbench.crossmatch-sky",
        ],
        "Views/OptionalAstronomyBackendsView.swift": [
            "STILTS / TOPCAT",
            "Check Backends",
            "Use Native Crossmatch",
        ],
        "Views/SettingsView.swift": ["Optional Astronomy Backends"],
        "Services/CapabilityCommandBuilder.swift": [
            'case "stilts_workbench"',
            '"preflight"',
        ],
    }
    source_root = app_root / "Sources" / "ScientificWorkbench"
    for relative, terms in required.items():
        path = source_root / relative
        if not path.exists():
            fail(failures, f"App wiring file missing: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for term in terms:
            if term not in text:
                fail(failures, f"{relative} missing term: {term}")

    tests = app_root / "Tests" / "ScientificWorkbenchTests" / "OptionalAstronomyBackendTests.swift"
    if not tests.exists():
        fail(failures, "Optional astronomy backend Swift tests are missing")


def validate(args: argparse.Namespace) -> dict[str, object]:
    TMP.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []
    python = args.python_executable

    fake_stilts = TMP / "bin" / "stilts"
    fake_stilts.parent.mkdir(parents=True, exist_ok=True)
    fake_stilts.write_text("#!/bin/sh\nprintf 'fake STILTS ready\\n'\nexit 0\n", encoding="utf-8")
    fake_stilts.chmod(fake_stilts.stat().st_mode | 0o111)

    real_code, real_payload = run_json(
        [python, str(PREFLIGHT), "--require-stilts", "--probe"],
        TMP / "real_machine.json",
    )
    fake_code, fake_payload = run_json(
        [
            python,
            str(PREFLIGHT),
            "--require-stilts",
            "--probe",
            "--stilts-command",
            str(fake_stilts),
        ],
        TMP / "fake_ready.json",
    )
    missing_code, missing_payload = run_json(
        [python, str(STILTS), "preflight", "--stilts-command", "/definitely/missing/stilts"],
        TMP / "missing_backend.json",
    )
    invalid_code, invalid_payload = run_json(
        [
            python,
            str(PREFLIGHT),
            "--require-stilts",
            "--stilts-command",
            "/definitely/missing/stilts",
        ],
        TMP / "invalid_command.json",
    )

    real_status = real_payload.get("app_status")
    if real_status not in {"PASS", "WARNING", "BLOCKED_CONTROLADO"}:
        fail(failures, f"real_machine: unexpected app_status {real_status!r}")
    if real_payload.get("original_modified") is not False:
        fail(failures, "real_machine: original_modified must be false")

    if fake_code != 0:
        fail(failures, f"fake_ready: expected exit 0, found {fake_code}")
    fake_capabilities = (fake_payload.get("results") or {}).get("capabilities") or {}
    if fake_capabilities.get("stilts_ready") is not True:
        fail(failures, "fake_ready: STILTS was not detected as ready")
    if fake_payload.get("app_status") not in {"PASS", "WARNING"}:
        fail(failures, "fake_ready: expected PASS or WARNING")

    validate_blocked("missing_backend", missing_code, missing_payload, failures)
    validate_blocked("invalid_command", invalid_code, invalid_payload, failures)
    validate_app_wiring(Path(args.app_root), failures)

    if not REFERENCE.exists():
        fail(failures, f"Missing reference: {REFERENCE}")
    else:
        reference_text = REFERENCE.read_text(encoding="utf-8")
        for term in ("optional_panel", "BLOCKED_CONTROLADO", "missing_optional_backend", "catalog_workbench.py crossmatch-sky"):
            if term not in reference_text:
                fail(failures, f"Reference missing term: {term}")

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_p1_10_stilts_panel_regression",
        "status": status,
        "real_machine": {
            "exit_code": real_code,
            "app_status": real_status,
            "capabilities": (real_payload.get("results") or {}).get("capabilities"),
        },
        "cases": [
            {"name": "fake_ready", "exit_code": fake_code, "app_status": fake_payload.get("app_status")},
            {"name": "missing_backend", "exit_code": missing_code, "app_status": missing_payload.get("app_status")},
            {"name": "invalid_command", "exit_code": invalid_code, "app_status": invalid_payload.get("app_status")},
        ],
        "native_alternative": "catalog_workbench.crossmatch-sky",
        "reference": str(REFERENCE),
        "app_root": str(Path(args.app_root)),
        "original_modified": False,
        "warnings": warnings,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--summary-json", default=None)
    args = parser.parse_args()

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
