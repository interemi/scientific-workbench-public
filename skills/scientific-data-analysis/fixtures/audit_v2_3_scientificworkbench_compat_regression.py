#!/usr/bin/env python3
"""Check v2.3 modular wrappers remain compatible with ScientificWorkbench."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
TMP = WORKSPACE / "tmp" / "v2_3_phase9_scientificworkbench_compat"
PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


APP_FILES = [
    "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift",
    "Sources/ScientificWorkbench/Services/ToolEnvelopeParser.swift",
    "Sources/ScientificWorkbench/Services/ArtifactDiscovery.swift",
    "Sources/ScientificWorkbench/Models/RunModels.swift",
    "Sources/ScientificWorkbench/Services/SkillWorkflowRouterClient.swift",
]


def resolve_app_root() -> Path:
    candidates = []
    env_root = os.environ.get("SCIENTIFIC_WORKBENCH_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend(
        [
            WORKSPACE / "ScientificWorkbench",
            Path(__file__).resolve().parents[3],
        ]
    )
    for candidate in candidates:
        if (candidate / "Package.swift").exists() or (candidate / "Sources" / "ScientificWorkbench").exists():
            return candidate
    return candidates[0]


APP_ROOT = resolve_app_root()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def run_command(command: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(TMP / "mplconfig")
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )


def load_summary(path: Path, label: str, errors: list[str]) -> dict:
    if not path.exists():
        errors.append(f"{label}: missing summary JSON at {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: summary JSON is not parseable: {exc}")
        return {}
    for key in ["tool", "status", "original_modified", "next_actions"]:
        require(key in payload, f"{label}: missing app-facing key {key}", errors)
    require(payload.get("app_status") or payload.get("status"), f"{label}: missing status/app_status", errors)
    require(payload.get("original_modified") is False, f"{label}: original_modified is not false", errors)
    require("Traceback" not in json.dumps(payload), f"{label}: traceback leaked into payload", errors)
    return payload


def make_fits(path: Path) -> bool:
    try:
        from astropy.io import fits
        import numpy as np
    except ModuleNotFoundError:
        path.write_text("not a real FITS file; astropy unavailable for synthetic fixture\n", encoding="utf-8")
        return False

    data = np.arange(100, dtype=float).reshape(10, 10)
    fits.PrimaryHDU(data=data).writeto(path, overwrite=True)
    return True


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    TMP.mkdir(parents=True, exist_ok=True)
    app_scan: dict[str, list[str]] = {}

    for rel in APP_FILES:
        path = APP_ROOT / rel
        require(path.exists(), f"missing app file: {rel}", errors)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        expected_terms = {
            "CapabilityCommandBuilder.swift": ["run-tool", "scriptStem", "--summary-json"],
            "ToolEnvelopeParser.swift": ["typed_artifacts", "app_hints", "original_modified", "next_actions"],
            "ArtifactDiscovery.swift": ["summary.json", "manifest.json", "typed_artifacts"],
            "RunModels.swift": ["BLOCKED_CONTROLADO", "ROTO", "JobStatus"],
            "SkillWorkflowRouterClient.swift": ["recommended_capabilities", "app_readiness", "workflow_mode"],
        }.get(path.name, [])
        app_scan[rel] = expected_terms
        for term in expected_terms:
            require(term in text, f"{rel}: missing compatibility term {term}", errors)

    fixtures = TMP / "fixtures"
    runs = TMP / "runs"
    fixtures.mkdir(exist_ok=True)
    runs.mkdir(exist_ok=True)

    table = fixtures / "ops.csv"
    table.write_text("date,value,team\n2026-01-01,10,A\n2026-01-02,12,B\n", encoding="utf-8")
    document = fixtures / "brief.txt"
    document.write_text("Proyecto anonimo\n- revisar estado\n", encoding="utf-8")
    fits_path = fixtures / "image.fits"
    fits_available = make_fits(fits_path)

    cases = [
        (
            "profile_table",
            [str(PYTHON), "scripts/profile_table.py", str(table), "--summary-json", str(runs / "profile_summary.json"), "--manifest-json", str(runs / "profile_manifest.json")],
            runs / "profile_summary.json",
        ),
        (
            "document_intake",
            [str(PYTHON), "scripts/document_intake_workbench.py", str(document), "--output-dir", str(runs / "documents"), "--summary-json", str(runs / "document_summary.json"), "--manifest-json", str(runs / "document_manifest.json")],
            runs / "document_summary.json",
        ),
    ]
    if fits_available:
        cases.append(
            (
                "inspect_fits",
                [
                    str(PYTHON),
                    "scripts/inspect_fits.py",
                    str(fits_path),
                    "--summary-json",
                    str(runs / "fits_summary.json"),
                    "--manifest-json",
                    str(runs / "fits_manifest.json"),
                ],
                runs / "fits_summary.json",
            )
        )
    else:
        warnings.append("inspect_fits execution skipped: astropy is unavailable in the active Python.")

    case_results = []
    for label, command, summary in cases:
        completed = run_command(command)
        case_results.append({"label": label, "returncode": completed.returncode, "summary": str(summary)})
        require(completed.returncode == 0, f"{label}: command failed: {completed.stderr[-800:]}", errors)
        require("Traceback" not in completed.stdout + completed.stderr, f"{label}: traceback leaked", errors)
        payload = load_summary(summary, label, errors)
        if not payload.get("typed_artifacts") and not payload.get("outputs"):
            warnings.append(f"{label}: no typed_artifacts/outputs in summary; app can still discover sidecar JSON")

    router_summary = runs / "router_summary.json"
    router_manifest = runs / "router_manifest.json"
    router = run_command(
        [
            str(PYTHON),
            "scripts/scientific_workflow_router.py",
            "plan",
            str(fits_path),
            "--task",
            "inspect FITS safely",
            "--summary-json",
            str(router_summary),
            "--manifest-json",
            str(router_manifest),
        ]
    )
    require(router.returncode == 0, f"router failed: {router.stderr[-800:]}", errors)
    try:
        router_payload = json.loads(router.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"router stdout not JSON: {exc}")
        router_payload = {}
    recommendations = router_payload.get("recommended_capabilities", [])
    require(bool(recommendations), "router returned no recommendations", errors)
    if recommendations:
        first = recommendations[0]
        for key in ["owner_module", "child_skill_path", "delegation_mode", "wrapper_status"]:
            require(key in first, f"router recommendation missing modular key {key}", errors)

    payload = {
        "tool": "audit_v2_3_scientificworkbench_compat_regression",
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "app_files_read": APP_FILES,
        "app_modified": False,
        "case_results": case_results,
        "router_first": recommendations[0] if recommendations else None,
        "evidence_dir": str(TMP),
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Fix compatibility regression", "kind": "maintainer_action"}],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
