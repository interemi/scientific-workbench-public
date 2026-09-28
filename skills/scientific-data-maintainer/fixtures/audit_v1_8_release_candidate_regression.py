#!/usr/bin/env python3
"""Editable-tree release-candidate gate for the v1.8 app-ready backend."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_8_phase9_release_candidate"
SUMMARY = TMP / "release_candidate_regression.json"
INSTALLED_ROOT = Path.home() / ".codex/skills/scientific-data-analysis"

REGISTRY = ROOT / "public_surface_registry.yaml"
GUIDE_TEX = REFERENCES / "guia_scientific_data_analysis_v1_8.tex"


def canonical_reference(name: str) -> Path:
    local = REFERENCES / name
    maintainer = MAINTAINER_REFERENCES / name
    if not maintainer.exists():
        return local
    if not local.exists():
        return maintainer
    if local.suffix.lower() == ".pdf" and local.stat().st_size < 50_000:
        return maintainer
    text = local.read_text(encoding="utf-8", errors="ignore")
    if "scientific-data-maintainer/references" in text or "compatibility pointer" in text:
        return maintainer
    match = re.search(r"Canonical fixture:\s*`([^`]+)`", text)
    if match:
        archived = ROOT / match.group(1)
        if archived.exists():
            return archived
    return local


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


MATRIX = canonical_reference("v1-8-app-readiness-matrix.md")
GUIDE_PDF = canonical_reference("guia_scientific_data_analysis_v1_8.pdf")

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}

EXPECTED_APP_READINESS_COUNTS = {
    "app_ready": 17,
    "app_ready_partial": 18,
    "blocked_optional": 7,
    "cli_only": 9,
    "maintainer_only": 6,
    "not_applicable_to_app": 2,
}

REQUIRED_PHASE_REGRESSIONS = [
    "audit_v1_8_charter_regression.py",
    "audit_v1_8_app_ready_contract_regression.py",
    "audit_v1_8_app_readiness_matrix_regression.py",
    "audit_v1_8_phase3_general_envelopes_regression.py",
    "audit_v1_8_phase4_run_bundles_regression.py",
    "audit_v1_8_phase5_router_regression.py",
    "audit_v1_8_phase6_app_like_general_regression.py",
    "audit_v1_8_phase7_app_like_science_astro_regression.py",
    "audit_v1_8_phase8_docs_regression.py",
    "audit_v1_8_release_candidate_regression.py",
]

REQUIRED_DOCS = {
    REFERENCES / "v1-8-app-ready-backend.md": [
        "App-ready backend / Workflow Contract Release",
        "Closure Criteria",
        "ScientificWorkbench",
    ],
    REFERENCES / "v1-8-app-ready-contract.md": [
        "v1.8 App-Ready JSON Contract",
        "Artifact Taxonomy",
        "original_modified",
        "app_hints",
    ],
    MATRIX: [
        "App-Readiness Matrix",
        "app_ready_partial",
        "not_applicable_to_app",
    ],
    REFERENCES / "v1-8-run-bundle-contract.md": [
        "v1.8 Run Bundle Contract",
        "summary.json",
        "next_steps.md",
        "Integration Note",
    ],
    REFERENCES / "v1-8-workflow-router.md": [
        "scientific_workflow_router.py",
        "dry-run",
        "ScientificWorkbench",
    ],
    REFERENCES / "v1-8-scientificworkbench-integration.md": [
        "skill-side backend contract",
        "does not mean",
        "v2.0",
        "ToolEnvelopeParser",
        "ArtifactDiscovery",
    ],
}

GUIDE_TEX_TERMS = [
    "Version v1.8 app-ready backend",
    "Que cambia de v1.7 a v1.8",
    "Que NO cambia",
    "Contrato JSON v1.8",
    "Artifact types",
    "Run bundles",
    "Router dry-run",
    "App-readiness de capabilities",
    "Como probar una capability app-like",
    "Optional, legacy y domain-specific",
    "v1.8 prepara la skill; v2.0 sincronizara la app",
]

FORBIDDEN_CLAIMS = [
    "ScientificWorkbench ya esta sincronizada",
    "v1.8 instala ScientificWorkbench",
    "v2.0 ya esta instalada",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def add_failure(failures: list[str], message: str) -> None:
    failures.append(message)


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        add_failure(failures, message)


def registry_labels(path: Path) -> list[str]:
    labels: list[str] = []
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("label: "):
            labels.append(stripped.split("label: ", 1)[1].strip().strip('"'))
    return [label for label in labels if label not in V2_0_ADDED_LABELS]


def matrix_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_matrix = False
    for line in read_text(MATRIX).splitlines():
        if line.startswith("## Matrix"):
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if not in_matrix or not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 14:
            rows.append({"_malformed": line})
            continue
        rows.append(
            {
                "number": cells[0],
                "label": cells[1].strip("`"),
                "app_readiness": cells[7].strip("`"),
                "reason": cells[8],
                "minimum_command": cells[9],
                "artifact_types": cells[12],
                "failure_contract": cells[14],
                "p_items": cells[15] if len(cells) > 15 else "",
            }
        )
    return rows


def check_docs(failures: list[str]) -> list[str]:
    checked: list[str] = []
    for path, terms in REQUIRED_DOCS.items():
        require(path.exists(), failures, f"missing required v1.8 doc: {display_path(path)}")
        if not path.exists():
            continue
        text = read_text(path)
        for term in terms:
            require(term in text, failures, f"{display_path(path)} missing term: {term}")
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in text, failures, f"{display_path(path)} contains forbidden claim: {claim}")
        checked.append(display_path(path))
    return checked


def check_matrix(failures: list[str]) -> dict[str, int]:
    labels = registry_labels(REGISTRY)
    rows = matrix_rows()
    require(len(labels) == 59, failures, f"registry should expose 59 editable capabilities, got {len(labels)}")
    require(len(rows) == 59, failures, f"app-readiness matrix should contain 59 rows, got {len(rows)}")
    if rows and "_malformed" not in rows[0]:
        require([row["label"] for row in rows] == labels, failures, "matrix labels should match registry order")
        require([int(row["number"]) for row in rows] == list(range(1, 60)), failures, "matrix rows should be numbered 1..59")
    malformed = [row["_malformed"] for row in rows if "_malformed" in row]
    require(not malformed, failures, f"malformed matrix rows: {malformed[:3]}")
    counts = Counter(row.get("app_readiness", "") for row in rows)
    require(dict(counts) == EXPECTED_APP_READINESS_COUNTS, failures, f"app-readiness counts changed: {dict(counts)}")
    for row in rows:
        if "_malformed" in row:
            continue
        for field in ("reason", "minimum_command", "artifact_types", "failure_contract", "p_items"):
            require(row[field] not in {"", "-", "`-`"}, failures, f"matrix row {row['number']} has empty {field}")
    return dict(counts)


def check_regressions(failures: list[str]) -> list[str]:
    missing = [name for name in REQUIRED_PHASE_REGRESSIONS if not (SCRIPTS / name).exists()]
    require(not missing, failures, f"missing v1.8 regression scripts: {missing}")
    return REQUIRED_PHASE_REGRESSIONS


def check_guide(failures: list[str]) -> dict[str, str | int]:
    require(GUIDE_TEX.exists(), failures, "missing guia_scientific_data_analysis_v1_8.tex")
    require(GUIDE_PDF.exists(), failures, "missing guia_scientific_data_analysis_v1_8.pdf")
    if GUIDE_TEX.exists():
        tex = read_text(GUIDE_TEX)
        for term in GUIDE_TEX_TERMS:
            require(term in tex, failures, f"guide TeX missing term: {term}")
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in tex, failures, f"guide TeX contains forbidden claim: {claim}")
    if GUIDE_PDF.exists():
        header = GUIDE_PDF.read_bytes()[:4]
        require(header == b"%PDF", failures, "guide PDF does not have a PDF header")
        require(GUIDE_PDF.stat().st_size > 50_000, failures, f"guide PDF looks too small: {GUIDE_PDF.stat().st_size} bytes")
    return {
        "tex": str(GUIDE_TEX),
        "pdf": str(GUIDE_PDF),
        "pdf_bytes": GUIDE_PDF.stat().st_size if GUIDE_PDF.exists() else 0,
    }


def installed_drift_warning() -> list[str]:
    warnings: list[str] = []
    installed_registry = INSTALLED_ROOT / "public_surface_registry.yaml"
    if not installed_registry.exists():
        warnings.append(f"installed registry not found at {installed_registry}; editable RC still checked")
        return warnings
    editable_labels = registry_labels(REGISTRY)
    installed_labels = registry_labels(installed_registry)
    if editable_labels != installed_labels:
        installed_only = [label for label in installed_labels if label not in editable_labels]
        editable_only = [label for label in editable_labels if label not in installed_labels]
        warnings.append(
            "installed public surface differs from editable source of truth: "
            f"installed_count={len(installed_labels)}, editable_count={len(editable_labels)}, "
            f"installed_only={installed_only}, editable_only={editable_only}"
        )
    return warnings


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = installed_drift_warning()
    docs_checked = check_docs(failures)
    counts = check_matrix(failures)
    regressions = check_regressions(failures)
    guide = check_guide(failures)
    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    payload = {
        "status": status,
        "phase": "v1.8 phase 9 release candidate editable tree",
        "docs_checked": docs_checked,
        "app_readiness_counts": counts,
        "regressions_expected": regressions,
        "guide": guide,
        "warnings": warnings,
        "failures": failures,
        "notes": [
            "This gate validates the editable tree before installed synchronization.",
            "It does not edit ScientificWorkbench and does not synchronize the installed skill.",
            "Run individual phase regressions and portable smoke alongside this aggregate gate.",
        ],
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
