#!/usr/bin/env python3
"""v1.7 stable documentation and coverage gate."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent.parent
INSTALLED_ROOT = Path.home() / ".codex/skills/scientific-data-analysis"
REGISTRY = ROOT / "public_surface_registry.yaml"
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"
MATRIX = None
GUIDE_TEX_CANDIDATES = [
    ROOT / "references" / "guia_scientific_data_analysis_v1_7.tex",
    PROJECT_ROOT / "guia_scientific_data_analysis_v1_7.tex",
]
GUIDE_PDF_CANDIDATES = [
    ROOT / "references" / "guia_scientific_data_analysis_v1_7.pdf",
    ROOT.parent / "scientific-data-maintainer" / "references" / "guia_scientific_data_analysis_v1_7.pdf",
    PROJECT_ROOT / "guia_scientific_data_analysis_v1_7.pdf",
]

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}


def canonical_reference(name: str) -> Path:
    local = REFERENCES / name
    maintainer = MAINTAINER_REFERENCES / name
    if not maintainer.exists() or not local.exists():
        return local
    text = local.read_text(encoding="utf-8", errors="ignore")
    if "scientific-data-maintainer/references" in text or "compatibility pointer" in text:
        return maintainer
    match = re.search(r"Canonical fixture:\s*`([^`]+)`", text)
    if match:
        archived = ROOT / match.group(1)
        if archived.exists():
            return archived
    return local


MATRIX = canonical_reference("real-world-capability-classification-v1-7.md")

EXPECTED_COUNTS = {
    "general": 25,
    "cross_domain_adaptable": 9,
    "domain_specific": 7,
    "legacy_specific": 12,
    "maintainer_only": 6,
}

REQUIRED_PHASE_REGRESSIONS = [
    "audit_v1_7_real_world_classification_regression.py",
    "audit_v1_7_profile_table_real_world_regression.py",
    "audit_v1_7_phase1_real_world_intake_regression.py",
    "audit_v1_7_photometry_noise_budget_transfer_regression.py",
    "audit_v1_7_phase2_measurement_noise_qa_regression.py",
    "audit_v1_7_phase3_astro_transfer_patterns_regression.py",
    "audit_v1_7_phase4_professional_personal_packages_regression.py",
    "audit_v1_7_release_candidate_regression.py",
]

REQUIRED_REFERENCES = {
    "references/real-world-capability-classification-v1-7.md": [
        "Total** | **59",
        "`general` | 25",
        "`cross_domain_adaptable` | 9",
        "`domain_specific` | 7",
        "`legacy_specific` | 12",
        "`maintainer_only` | 6",
    ],
    "references/v1-7-real-world-guide.md": [
        "Status: v1.7 stable installed release",
        "Not-Applicable Criteria",
        "Academic, Professional, And Personal Examples",
        "audit_v1_7_release_candidate_regression.py",
    ],
    "references/non-astro-start-here.md": [
        "references/v1-7-real-world-guide.md",
        "professional and personal package playbooks",
    ],
    "references/real-world-use-cases.md": [
        "Real-World Use Cases v1.7",
        "Fase 4 Professional And Personal Packages",
        "Professional route",
        "Personal route",
    ],
    "references/real-world-measurement-patterns.md": [
        "v1.7 transfer note",
        "SNR",
        "calibration",
        "QA",
    ],
    "references/astro-transferable-patterns.md": [
        "Strict domain part",
        "Reusable pattern",
        "v1.7 decision",
    ],
    "references/real-world-package-playbooks.md": [
        "Real-World Package Playbooks v1.7",
        "professional",
        "personal",
    ],
}

PUBLIC_DOC_TERMS = {
    "SKILL.md": [
        "v1.7 stable",
        "classification matrix for all 59 public capabilities",
        "references/non-astro-start-here.md",
    ],
    "README.txt": [
        "v1.7 stable over v1.6 stable",
        "explicit not-applicable criteria",
        "references/v1-7-real-world-guide.md",
    ],
    "RELEASE-v1.txt": [
        "Release v1.7 stable / v1.6 stable baseline",
        "general, cross-domain adaptable, domain-specific, legacy-specific, or maintainer-only",
        "references/v1-7-real-world-guide.md",
    ],
}


def fail(message: str) -> None:
    raise AssertionError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read_text(relative: str) -> str:
    if relative == "references/real-world-capability-classification-v1-7.md":
        return MATRIX.read_text(encoding="utf-8")
    return (ROOT / relative).read_text(encoding="utf-8")


def parse_registry_labels() -> list[str]:
    labels: list[str] = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("label: "):
            labels.append(stripped.split("label: ", 1)[1].strip())
    return [label for label in labels if label not in V2_0_ADDED_LABELS]


def parse_matrix_rows() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|(.*)\|$")
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        trailing_cells = [cell.strip() for cell in match.group(4).split("|")]
        if len(trailing_cells) != 3:
            fail(f"matrix row {match.group(1)} should have 6 columns")
        rows.append(
            {
                "number": int(match.group(1)),
                "label": match.group(2).strip(),
                "classification": match.group(3).strip(),
                "justification": trailing_cells[0],
                "examples": trailing_cells[1],
                "action": trailing_cells[2],
            }
        )
    return rows


def check_matrix() -> dict[str, int]:
    labels = parse_registry_labels()
    rows = parse_matrix_rows()
    require(len(labels) == 59, f"registry should expose 59 public capabilities, got {len(labels)}")
    require(len(rows) == 59, f"classification matrix should contain 59 rows, got {len(rows)}")
    require([row["number"] for row in rows] == list(range(1, 60)), "matrix rows should be numbered 1..59")
    require([row["label"] for row in rows] == labels, "classification matrix labels should match registry order")

    counts = dict(Counter(str(row["classification"]) for row in rows))
    require(counts == EXPECTED_COUNTS, f"classification counts changed: expected {EXPECTED_COUNTS}, got {counts}")

    for row in rows:
        examples = str(row["examples"])
        action = str(row["action"])
        for term in ("Academico:", "Profesional:", "Personal:"):
            require(term in examples, f"row {row['number']} examples missing {term}")
        require(len(str(row["justification"])) >= 20, f"row {row['number']} has a thin justification")
        require(len(action) >= 20, f"row {row['number']} has a thin v1.7 action/limit")
    return counts


def check_required_text() -> list[str]:
    checked: list[str] = []
    for relative, terms in {**REQUIRED_REFERENCES, **PUBLIC_DOC_TERMS}.items():
        text = read_text(relative)
        missing = [term for term in terms if term not in text]
        require(not missing, f"{relative} missing required v1.7 terms: {missing}")
        checked.append(relative)
    return checked


def check_regression_inventory() -> list[str]:
    missing = [name for name in REQUIRED_PHASE_REGRESSIONS if not (ROOT / "scripts" / name).exists()]
    require(not missing, f"missing v1.7 regression scripts: {missing}")
    return REQUIRED_PHASE_REGRESSIONS


def check_guide_artifacts() -> dict[str, str | int]:
    guide_tex = next((path for path in GUIDE_TEX_CANDIDATES if path.exists()), None)
    guide_pdf = next((path for path in GUIDE_PDF_CANDIDATES if path.exists() and path.stat().st_size > 20_000), None)
    require(guide_tex is not None, "guide TeX missing from references/ or project root")
    require(guide_pdf is not None, "guide PDF missing from references/ or project root")
    tex = guide_tex.read_text(encoding="utf-8")
    for term in (
        "Version v1.7 stable real-world",
        "Clasificacion de capabilities",
        "Rutas generales real-world",
        "Patrones transferibles",
        "Criterios de no aplicabilidad",
    ):
        require(term in tex, f"guide TeX missing term: {term}")

    header = guide_pdf.read_bytes()[:4]
    require(header == b"%PDF", f"guide PDF does not look like a PDF: {guide_pdf}")
    size = guide_pdf.stat().st_size
    require(size > 20_000, f"guide PDF looks too small: {size} bytes")
    return {"tex": str(guide_tex), "pdf": str(guide_pdf), "pdf_bytes": size}


def check_installed_sync_state() -> str:
    installed_skill = INSTALLED_ROOT / "SKILL.md"
    require(installed_skill.exists(), f"installed SKILL.md not found at {installed_skill}")
    text = installed_skill.read_text(encoding="utf-8")
    if ROOT.resolve() == INSTALLED_ROOT.resolve():
        require("v1.7 stable" in text, "installed skill does not advertise v1.7 stable after sync")
        require("v1.6 stable" in text, "installed v1.7 should still name the v1.6 stable baseline")
        return str(installed_skill) + " (installed_v1_7_synced)"
    require("v1.6 stable" in text, "installed skill no longer advertises v1.6 stable")
    if "v1.7 stable" in text:
        return str(installed_skill) + " (installed_v1_7_synced)"
    return str(installed_skill)


def main() -> int:
    counts = check_matrix()
    docs = check_required_text()
    regressions = check_regression_inventory()
    guide = check_guide_artifacts()
    installed_skill = check_installed_sync_state()
    payload = {
        "status": "PASS",
        "phase": "v1.7 stable release gate",
        "classification_counts": counts,
        "docs_checked": docs,
        "regressions_expected": regressions,
        "guide": guide,
        "installed_skill_sync_state": installed_skill,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
