#!/usr/bin/env python3
"""Regression for v2.0 Phase 6 UI-driven workflow exposure and guidance."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_phase6_ui_workflows"
SUMMARY = TMP / "phase6_ui_workflows_summary.json"
TRANSCRIPT = TMP / "headless_ui_workflow_transcript.json"
REFERENCE = ROOT / "references" / "v2-0-ui-driven-workflows.md"
PLANNER_REFERENCE = ROOT / "references" / "v2-0-workflow-planner.md"
REGISTRY = ROOT / "public_surface_registry.yaml"

EXPECTED_COUNTS = {
    "normal": 25,
    "expert": 13,
    "optional": 8,
    "legacy": 9,
    "maintainer": 6,
}

MAINTAINER_IDS = {
    "external_astro_tools_local_validation",
    "capability_probe_matrix",
    "portable_smoke_test",
    "validate_skill_samples",
    "sync_public_surface_docs",
    "skill_surface_audit",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registry_ids() -> list[str]:
    return re.findall(r"^\s*-\s+id:\s+(\S+)\s*$", REGISTRY.read_text(encoding="utf-8"), re.MULTILINE)


def planner_modes() -> dict[str, str]:
    rows: dict[str, str] = {}
    pattern = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
    for capability_id, mode in pattern.findall(PLANNER_REFERENCE.read_text(encoding="utf-8")):
        rows[capability_id] = mode
    return rows


def validate_policy() -> dict[str, int]:
    ids = registry_ids()
    modes = planner_modes()
    require(len(ids) == 61, f"expected 61 registry rows, found {len(ids)}")
    require(set(ids) == set(modes), "workflow planner matrix does not cover the registry exactly")
    counts = {mode: list(modes.values()).count(mode) for mode in EXPECTED_COUNTS}
    require(counts == EXPECTED_COUNTS, f"unexpected exposure counts: {counts}")
    require({capability_id for capability_id, mode in modes.items() if mode == "maintainer"} == MAINTAINER_IDS,
            "maintainer exposure set changed")
    return counts


def require_terms(path: Path, terms: list[str]) -> None:
    require(path.exists(), f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    for term in terms:
        require(term in text, f"{path.name} missing required term: {term}")


def validate_app_sources() -> None:
    require_terms(
        APP / "Sources/ScientificWorkbench/Models/CapabilityEntry.swift",
        [
            "enum CapabilityCatalogMode",
            "case normal",
            "case expert",
            "case optional",
            "case legacy",
            "func isVisible(in mode: CapabilityCatalogMode)",
            "case twoInputs",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Views/CapabilityCatalogView.swift",
        [
            'Picker("Workflow mode"',
            "WorkflowAccessNotice",
            "OptionalAstronomyBackendsView",
            "I reviewed the domain and safety requirements",
            "GuidedCapabilityControls",
            "isMaintenance",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Views/GuidedCapabilityControls.swift",
        [
            '"photometry_noise_budget"',
            '"timeseries_forecasting_workbench"',
            '"deliverable_factory.scaffold"',
            '"bootstrap_analysis_notebook"',
            '"companion_route_check"',
            "Run Guided Workflow",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Views/ContentView.swift",
        [
            "isMaintenance: false",
            "isMaintenance: true",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift",
        [
            'case "scientific_writeup_review"',
            'case "semantic_diff"',
            'case "physical_qa"',
            'case "deliverable_factory.scaffold"',
            'case "bootstrap_analysis_notebook"',
            'case "timeseries_forecasting_workbench"',
            'case "presentation_workbench.inspect"',
            'case "presentation_workbench.existing-deck-style-audit"',
            'case "latex_workbench.scaffold"',
            'case "latex_workbench.review"',
            'case "latex_workbench.compile"',
            'case "notebook_branch_compare"',
            "firstTwoInputs",
        ],
    )
    require_terms(
        APP / "Tests/ScientificWorkbenchTests/RegistryAndCapabilityTests.swift",
        [
            "capabilityCatalogSeparatesNormalExpertOptionalLegacyAndMaintenance",
            "GuidedRunRequirement.twoInputs",
        ],
    )
    require_terms(
        APP / "Tests/ScientificWorkbenchTests/CommandBuilderAndShellWordsTests.swift",
        [
            "commandBuilderCreatesGeneralGuidedWorkflowCommands",
            "commandBuilderRejectsSemanticDiffWithOnlyOneInput",
        ],
    )
    require_terms(
        APP / "script/verify_app_bundle.sh",
        [
            '{"local", "skillRouter"}',
            "packaged user plan exposed maintainer capabilities",
        ],
    )


def build_app() -> Path:
    completed = subprocess.run(
        ["swift", "build"],
        cwd=APP,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    require(completed.returncode == 0, f"swift build failed: {completed.stderr or completed.stdout}")
    bin_path = subprocess.run(
        ["swift", "build", "--show-bin-path"],
        cwd=APP,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    require(bin_path.returncode == 0, f"could not resolve Swift bin path: {bin_path.stderr}")
    executable = Path(bin_path.stdout.strip()) / "ScientificWorkbench"
    require(executable.exists(), f"missing built executable: {executable}")
    return executable


def run_headless(executable: Path) -> dict[str, object]:
    fixture = TMP / "professional_measurements.csv"
    fixture.write_text(
        "timestamp,temperature_c,pressure_kpa\n"
        "2026-01-01T00:00:00,20.1,101.2\n"
        "2026-01-01T01:00:00,20.4,101.1\n",
        encoding="utf-8",
    )
    before = sha256(fixture)
    command = [
        str(executable),
        "--agent-input", str(fixture),
        "--agent-prompt", "Profile this professional measurement table safely and propose next steps.",
        "--agent-mode", "workflow",
        "--agent-local-planner",
        "--agent-output-root", str(TMP / "headless_output"),
        "--agent-transcript-json", str(TRANSCRIPT),
        "--agent-isolated-session",
        "--agent-exit-after-run",
    ]
    completed = subprocess.run(
        command,
        cwd=APP,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    require(completed.returncode == 0, f"headless app run failed: {completed.stderr or completed.stdout}")
    require("Traceback" not in completed.stdout + completed.stderr, "headless run emitted a traceback")
    require(TRANSCRIPT.exists(), "headless transcript was not created")
    require(sha256(fixture) == before, "headless workflow modified its input")
    transcript = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    plan = transcript.get("agent_plan") or {}
    steps = plan.get("steps") or []
    capability_ids = [step.get("capability_id") for step in steps]
    require("profile_table" in capability_ids, f"table plan omitted profile_table: {capability_ids}")
    require(not (set(capability_ids) & MAINTAINER_IDS), "headless user plan exposed a maintainer capability")
    return {
        "status": "PASS",
        "command": command,
        "input": str(fixture),
        "transcript": str(TRANSCRIPT),
        "capability_ids": capability_ids,
        "original_modified": False,
    }


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    counts = validate_policy()
    validate_app_sources()
    require_terms(
        REFERENCE,
        [
            "| Normal | 25 |",
            "| Expert | 13 |",
            "| Optional | 8 |",
            "| Legacy | 9 |",
            "| Maintenance | 6 |",
            "Maintainer-only capabilities are reachable only through Maintenance",
        ],
    )
    executable = build_app()
    headless = run_headless(executable)
    payload = {
        "tool": "audit_v2_0_phase6_ui_workflows_regression",
        "status": "PASS",
        "exposure_counts": counts,
        "guided_forms": [
            "photometry_noise_budget",
            "timeseries_forecasting_workbench",
            "deliverable_factory.scaffold",
            "bootstrap_analysis_notebook",
            "companion_route_check",
        ],
        "guided_command_routes": [
            "scientific_writeup_review",
            "semantic_diff",
            "physical_qa",
            "presentation_workbench.inspect",
            "presentation_workbench.existing-deck-style-audit",
            "latex_workbench.scaffold",
            "latex_workbench.review",
            "latex_workbench.compile",
            "notebook_branch_compare",
            "deliverable_factory.scaffold",
            "bootstrap_analysis_notebook",
            "timeseries_forecasting_workbench",
        ],
        "headless": headless,
        "reference": str(REFERENCE),
        "warnings": [
            "Some expert/optional/legacy routes remain advanced-argument workflows until a domain-safe form exists."
        ],
        "originals_modified": False,
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, subprocess.TimeoutExpired) as exc:
        payload = {
            "tool": "audit_v2_0_phase6_ui_workflows_regression",
            "status": "FAIL",
            "error": str(exc),
            "originals_modified": "unknown",
        }
        TMP.mkdir(parents=True, exist_ok=True)
        SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise SystemExit(1)
