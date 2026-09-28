#!/usr/bin/env python3
"""Validate the v1.8 app-ready backend charter."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSTALLED_ROOT = Path.home() / ".codex/skills/scientific-data-analysis"
APP_ROOT = Path(__file__).resolve().parents[3]
CHARTER = ROOT / "references" / "v1-8-app-ready-backend.md"


def labels_from_registry(root: Path) -> list[str]:
    labels: list[str] = []
    for line in (root / "public_surface_registry.yaml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("label: "):
            labels.append(stripped.split("label: ", 1)[1].strip())
    return labels


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def required_terms(path: Path, terms: list[str], failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for term in terms:
        require(term in text, f"{path.relative_to(ROOT)} missing term: {term}", failures)


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    require(CHARTER.exists(), "v1.8 charter reference is missing", failures)
    if CHARTER.exists():
        required_terms(
            CHARTER,
            [
                "App-ready backend / Workflow Contract Release",
                "Product Objective",
                "Non-Goals",
                "Boundary With ScientificWorkbench",
                "Relationship To v1.7, v1.9, And v2.0",
                "Do not edit ScientificWorkbench",
                "Closure Criteria",
                "registry currently exposes 61 labels",
                "legacy_spectroscopy_report_builder.py populate",
                "latex_workbench.py compile",
            ],
            failures,
        )

    required_terms(
        ROOT / "SKILL.md",
        ["v1.7 stable", "classification matrix for all 59 public capabilities"],
        failures,
    )
    required_terms(
        ROOT / "README.txt",
        ["v1.7 stable over v1.6 stable", "explicit not-applicable criteria"],
        failures,
    )
    required_terms(
        ROOT / "RELEASE-v1.txt",
        ["Release v1.7 stable / v1.6 stable baseline", "v1.7 is the installed stable"],
        failures,
    )

    editable_labels = labels_from_registry(ROOT)
    require(len(editable_labels) == 61, f"editable registry should expose 61 labels, got {len(editable_labels)}", failures)

    installed_labels: list[str] = []
    if (INSTALLED_ROOT / "public_surface_registry.yaml").exists():
        installed_labels = labels_from_registry(INSTALLED_ROOT)
        if installed_labels != editable_labels:
            installed_only = [label for label in installed_labels if label not in editable_labels]
            editable_only = [label for label in editable_labels if label not in installed_labels]
            warnings.append(
                "installed public surface differs from editable source of truth: "
                f"installed_count={len(installed_labels)}, editable_count={len(editable_labels)}, "
                f"installed_only={installed_only}, editable_only={editable_only}"
            )
    else:
        warnings.append(f"installed registry not found at {INSTALLED_ROOT}")

    app_files = [
        APP_ROOT / "ROADMAP.md",
        APP_ROOT / "ARCHITECTURE.md",
        APP_ROOT / "DECISIONS" / "0001-ai-plans-local-capabilities-execute.md",
        APP_ROOT / "DECISIONS" / "0002-local-first-zero-cost-ai.md",
        APP_ROOT / "Sources" / "ScientificWorkbench" / "Services" / "CapabilityCommandBuilder.swift",
        APP_ROOT / "Sources" / "ScientificWorkbench" / "Services" / "ToolEnvelopeParser.swift",
    ]
    for path in app_files:
        require(path.exists(), f"ScientificWorkbench context file missing: {path}", failures)

    if app_files[1].exists():
        architecture = app_files[1].read_text(encoding="utf-8")
        for term in ("Runner --> Skill", "ToolEnvelopeParser", "AI can choose and explain", "Local capabilities execute"):
            require(term in architecture, f"ScientificWorkbench architecture missing term: {term}", failures)

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    payload = {
        "status": status,
        "phase": "v1.8 phase 0 charter",
        "editable_registry_count": len(editable_labels),
        "installed_registry_count": len(installed_labels) if installed_labels else None,
        "warnings": warnings,
        "failures": failures,
        "charter": str(CHARTER),
        "scientificworkbench_root": str(APP_ROOT),
        "installed_root": str(INSTALLED_ROOT),
        "notes": [
            "Fase 0 intentionally reads ScientificWorkbench for compatibility context only.",
            "Fase 0 does not synchronize the installed skill.",
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
