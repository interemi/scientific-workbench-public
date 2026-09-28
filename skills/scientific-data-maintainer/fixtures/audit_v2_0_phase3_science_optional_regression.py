#!/usr/bin/env python3
"""Validate the v2.0 Phase 3 science/astro/optional prep boundary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]

PLAN = ROOT / "references" / "v2-0-phase3-science-optional-plan.md"
DEFERRALS = ROOT / "references" / "v1-9-v2-0-deferrals.md"
CHARTER = ROOT / "references" / "v2-0-integrated-release-charter.md"

EXPECTED_TARGETS = {
    8: {
        "prompt": "P1-8",
        "target": "fits_rgb_batch.py",
        "exposure": "expert_science",
    },
    10: {
        "prompt": "P1-10",
        "target": "stilts_workbench.py",
        "exposure": "optional_panel",
    },
    13: {
        "prompt": "P1-13",
        "target": "radial_velocity_workbench.py inspect",
        "exposure": "expert_science",
    },
    26: {
        "prompt": "P1-26",
        "target": "photometric_solution.py",
        "exposure": "expert_science",
    },
    28: {
        "prompt": "P1-28",
        "target": "apt_workbench.py",
        "exposure": "optional_panel",
    },
}

REQUIRED_PLAN_TERMS = [
    "preparatory",
    "does not close",
    "individual P1",
    "No installed skill synchronization",
    "No ScientificWorkbench source file is edited",
    "No optional backend is made mandatory",
    "No original user data may be modified",
    "expert_science",
    "optional_panel",
    "Native Alternatives",
    "BLOCKED_CONTROLADO",
    "catalog_workbench.py crossmatch-sky",
    "aperture-photometry",
]

FORBIDDEN_NORMAL_PROMISES = [
    "normal general-purpose",
    "general-purpose workflow",
]

APP_PHASE2_PREREQUISITES = [
    "Sources/ScientificWorkbench/Services/ToolEnvelopeParser.swift",
    "Sources/ScientificWorkbench/Services/ArtifactDiscovery.swift",
    "Sources/ScientificWorkbench/Models/RunModels.swift",
    "Tests/ScientificWorkbenchTests/ArtifactAndJobModelTests.swift",
]


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def validate_deferrals(text: str, failures: list[str]) -> None:
    for row, spec in EXPECTED_TARGETS.items():
        pattern = rf"\|\s*{row}\s*\|\s*`{re.escape(spec['target'])}`\s*\|\s*`P1`\s*\|"
        if not re.search(pattern, text):
            fail(failures, f"v1.9 deferrals missing row {row}: {spec['target']}")
        if "decision=v2_0" not in text:
            fail(failures, "v1.9 deferrals must keep decision=v2_0 language")


def validate_plan(text: str, failures: list[str]) -> None:
    for term in REQUIRED_PLAN_TERMS:
        if term not in text:
            fail(failures, f"Phase 3 plan missing required term: {term}")

    for row, spec in EXPECTED_TARGETS.items():
        for term in (str(row), spec["prompt"], spec["target"], spec["exposure"]):
            if term not in text:
                fail(failures, f"Phase 3 plan missing {term!r} for row {row}")

    # The plan may describe rejecting normal mode, but must not promise these as
    # normal generic workflows.
    lower_text = text.lower()
    for phrase in FORBIDDEN_NORMAL_PROMISES:
        if f"exposure for app | {phrase}" in lower_text:
            fail(failures, f"Phase 3 plan appears to expose targets as {phrase}")

    order = [text.find(spec["prompt"]) for spec in EXPECTED_TARGETS.values()]
    if any(index < 0 for index in order) or order != sorted(order):
        fail(failures, "Prompt order is missing or not P1-8, P1-10, P1-13, P1-26, P1-28")


def validate_charter(text: str, failures: list[str]) -> None:
    for spec in EXPECTED_TARGETS.values():
        if spec["target"] not in text:
            fail(failures, f"v2.0 charter missing Phase 3 target: {spec['target']}")


def validate_app_prerequisites(app_root: Path, failures: list[str], warnings: list[str]) -> None:
    missing = [rel for rel in APP_PHASE2_PREREQUISITES if not (app_root / rel).exists()]
    if missing:
        fail(failures, f"ScientificWorkbench missing Phase 2 parser/artifact prerequisites: {missing}")
        return

    parser = read_text(app_root / "Sources/ScientificWorkbench/Services/ToolEnvelopeParser.swift")
    discovery = read_text(app_root / "Sources/ScientificWorkbench/Services/ArtifactDiscovery.swift")
    tests = read_text(app_root / "Tests/ScientificWorkbenchTests/ArtifactAndJobModelTests.swift")
    for term in ("typedArtifacts", "nextActions", "originalModified", "appHints"):
        if term not in parser:
            fail(failures, f"ToolEnvelopeParser missing prerequisite term: {term}")
    for term in ("typed_artifacts", "summary.json", "manifest.json", "artifactType"):
        if term not in discovery:
            fail(failures, f"ArtifactDiscovery missing prerequisite term: {term}")
    if "artifactDiscoveryReadsTypedRunBundleMetadata" not in tests:
        warnings.append("Phase 2 artifact discovery test name not found in app tests.")


def validate(args: argparse.Namespace) -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []

    try:
        plan_text = read_text(PLAN)
    except FileNotFoundError:
        plan_text = ""
        fail(failures, f"Missing Phase 3 plan: {PLAN}")
    try:
        deferrals_text = read_text(DEFERRALS)
    except FileNotFoundError:
        deferrals_text = ""
        fail(failures, f"Missing v1.9 deferrals reference: {DEFERRALS}")
    try:
        charter_text = read_text(CHARTER)
    except FileNotFoundError:
        charter_text = ""
        fail(failures, f"Missing v2.0 charter: {CHARTER}")

    if plan_text:
        validate_plan(plan_text, failures)
    if deferrals_text:
        validate_deferrals(deferrals_text, failures)
    if charter_text:
        validate_charter(charter_text, failures)

    validate_app_prerequisites(Path(args.app_root), failures, warnings)

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_phase3_science_optional_regression",
        "status": status,
        "phase": "v2.0 Phase 3 preparatory",
        "plan": str(PLAN),
        "deferrals": str(DEFERRALS),
        "charter": str(CHARTER),
        "targets": [
            {
                "row": row,
                "prompt": spec["prompt"],
                "target": spec["target"],
                "exposure": spec["exposure"],
            }
            for row, spec in EXPECTED_TARGETS.items()
        ],
        "app_root": str(Path(args.app_root)),
        "individual_p1_closure": "not_performed_in_phase3_prep",
        "installed_sync": "not_performed",
        "warnings": warnings,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
