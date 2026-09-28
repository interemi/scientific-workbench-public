#!/usr/bin/env python3
"""Regression for the v2.0 formal app + skill planner priority."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_priority_formal_planner"
SUMMARY = TMP / "formal_planner_summary.json"
PHASE5 = ROOT / "scripts" / "audit_v2_0_phase5_planner_regression.py"
PHASE5_SUMMARY = ROOT / "tmp" / "v2_0_phase5_planner" / "phase5_planner_summary.json"
REFERENCE = ROOT / "references" / "v2-0-workflow-planner.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_phase5() -> dict:
    completed = subprocess.run(
        [sys.executable, str(PHASE5)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"phase5 planner regression failed: {completed.stderr or completed.stdout}")
    require("Traceback" not in completed.stdout + completed.stderr, "phase5 planner regression emitted traceback")
    require(PHASE5_SUMMARY.exists(), "phase5 planner summary was not created")
    return json.loads(PHASE5_SUMMARY.read_text(encoding="utf-8"))


def validate_app_sources() -> None:
    capability = APP / "Sources/ScientificWorkbench/Models/CapabilityEntry.swift"
    router = APP / "Sources/ScientificWorkbench/Services/SkillWorkflowRouterClient.swift"
    planner = APP / "Sources/ScientificWorkbench/Services/AgentPlanner.swift"
    card = APP / "Sources/ScientificWorkbench/Views/EditablePlanCard.swift"
    tests = [
        APP / "Tests/ScientificWorkbenchTests/SkillWorkflowRouterClientTests.swift",
        APP / "Tests/ScientificWorkbenchTests/AgentPlannerTests.swift",
        APP / "Tests/ScientificWorkbenchTests/WorkflowDryRunServiceTests.swift",
        APP / "Tests/ScientificWorkbenchTests/WorkflowExecutionCoordinatorTests.swift",
    ]
    for path in [capability, router, planner, card, *tests]:
        require(path.exists(), f"missing app source/test: {path}")

    capability_text = capability.read_text(encoding="utf-8")
    for value in [
        "app_ready",
        "app_ready_partial",
        "cli_only",
        "blocked_optional",
        "maintainer_only",
        "not_applicable_to_app",
    ]:
        require(value in capability_text, f"CapabilityEntry missing app-readiness class {value}")
    require("allowsAutomaticEnablement" in capability_text, "app-readiness lacks automatic-enablement policy")
    require("plannerVisible" in capability_text, "app-readiness lacks planner visibility policy")

    router_text = router.read_text(encoding="utf-8")
    require('case appReadiness = "app_readiness"' in router_text, "router client does not decode app_readiness")
    require("!appReadiness.allowsAutomaticEnablement" in router_text, "router client does not enforce app-readiness")

    planner_text = planner.read_text(encoding="utf-8")
    require("capabilities.plannerVisible" in planner_text, "cloud planner still exposes restricted capabilities")
    require('case appReadiness = "app_readiness"' in planner_text, "cloud planner payload omits app_readiness")

    require("capability.appReadiness.rawValue" in card.read_text(encoding="utf-8"), "editable plan does not show app-readiness")
    require(
        "routerDisablesNormalStepWhenAppReadinessIsPartial" in tests[0].read_text(encoding="utf-8"),
        "missing partial-readiness plan test",
    )


def validate_reference(summary: dict) -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    require("| # | capability_id | workflow_mode | app_readiness |" in text, "route matrix lacks app-readiness column")
    require(text.count("| `app_ready` |") >= 17, "route matrix does not record app-ready rows")
    require(summary.get("registry_rows") == 61, "formal matrix does not cover 61 registry rows")
    require(
        summary.get("app_readiness_counts")
        == {
            "app_ready": 17,
            "app_ready_partial": 19,
            "blocked_optional": 7,
            "cli_only": 10,
            "maintainer_only": 6,
            "not_applicable_to_app": 2,
        },
        f"unexpected app-readiness counts: {summary.get('app_readiness_counts')}",
    )


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    phase5_summary = run_phase5()
    validate_app_sources()
    validate_reference(phase5_summary)
    cases = phase5_summary.get("cases", [])
    require(len(cases) == 8, f"expected 8 dry-run cases, found {len(cases)}")
    require(all(case.get("status") in {"PASS", "WARNING", "BLOCKED_CONTROLADO"} for case in cases), "invalid dry-run status")
    require(phase5_summary.get("originals_modified") is False, "dry-run modified an original")

    payload = {
        "tool": "audit_v2_0_priority_formal_planner_regression",
        "status": "PASS",
        "registry_rows": phase5_summary["registry_rows"],
        "workflow_mode_counts": phase5_summary["workflow_mode_counts"],
        "app_readiness_counts": phase5_summary["app_readiness_counts"],
        "dry_run_cases": cases,
        "optional_backend_absent": phase5_summary["optional_backend_absent"],
        "originals_modified": False,
        "app_root": str(APP),
        "reference": str(REFERENCE),
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
