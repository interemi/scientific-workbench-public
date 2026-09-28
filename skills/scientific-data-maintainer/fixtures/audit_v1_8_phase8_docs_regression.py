#!/usr/bin/env python3
"""Validate v1.8 documentation, guide, and integration-contract coverage."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"
TMP = ROOT / "tmp" / "v1_8_phase8_docs"
SUMMARY = TMP / "phase8_docs_regression.json"
GUIDE_TEX = REFERENCES / "guia_scientific_data_analysis_v1_8.tex"


def canonical_reference(name: str) -> Path:
    local = REFERENCES / name
    maintainer = MAINTAINER_REFERENCES / name
    candidates = [local, maintainer]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.suffix.lower() == ".pdf":
            if candidate.stat().st_size >= 50_000:
                return candidate
            continue
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"Canonical fixture:\s*`([^`]+)`", text)
        if match:
            archived = candidate.parents[1] / match.group(1)
            if archived.exists():
                return archived
        match = re.search(r"`(\.\./scientific-data-maintainer/references/[^`]+)`", text)
        if match:
            redirected = ROOT / match.group(1)
            if redirected.exists():
                redirected_text = redirected.read_text(encoding="utf-8", errors="ignore")
                redirected_match = re.search(r"Canonical fixture:\s*`([^`]+)`", redirected_text)
                if redirected_match:
                    archived = redirected.parents[1] / redirected_match.group(1)
                    if archived.exists():
                        return archived
                return redirected
        if "compatibility pointer" not in text and "maintained in the sibling maintainer skill" not in text:
            return candidate
    return local


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


MATRIX = canonical_reference("v1-8-app-readiness-matrix.md")
GUIDE_PDF = canonical_reference("guia_scientific_data_analysis_v1_8.pdf")

REQUIRED_DOCS = [
    REFERENCES / "v1-8-app-ready-backend.md",
    REFERENCES / "v1-8-app-ready-contract.md",
    MATRIX,
    REFERENCES / "v1-8-run-bundle-contract.md",
    REFERENCES / "v1-8-scientificworkbench-integration.md",
    GUIDE_TEX,
    GUIDE_PDF,
]

DOC_TERMS = {
    REFERENCES / "v1-8-app-ready-backend.md": [
        "App-ready backend / Workflow Contract Release",
        "Phase 8 Documentation Decision",
        "ScientificWorkbench",
        "v2.0",
    ],
    REFERENCES / "v1-8-app-ready-contract.md": [
        "v1.8 App-Ready JSON Contract",
        "Artifact Taxonomy",
        "BLOCKED_CONTROLADO",
        "original_modified",
        "app_hints",
    ],
    MATRIX: [
        "Fase 7 Ciencia/Astro App-Like Notes",
        "not_applicable_to_app",
        "No se cambian los counts",
    ],
    REFERENCES / "v1-8-run-bundle-contract.md": [
        "v1.8 Run Bundle Contract",
        "Integration Note",
        "summary.json",
        "next_steps.md",
    ],
    REFERENCES / "v1-8-scientificworkbench-integration.md": [
        "skill-side backend contract",
        "does not mean",
        "v2.0",
        "ToolEnvelopeParser",
        "ArtifactDiscovery",
        "typed_artifacts",
        "app_hints",
    ],
}

PDF_TERMS = [
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
    "ScientificWorkbench",
    "v1.8 prepara la skill",
    "v2.0 sincronizara la app",
    "audit_v1_8_phase8_docs_regression.py",
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError(f"pypdf unavailable: {exc}") from exc
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages), len(reader.pages)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []

    for path in REQUIRED_DOCS:
        require(path.exists(), f"missing required doc: {display_path(path)}", failures)

    for path, terms in DOC_TERMS.items():
        if not path.exists():
            continue
        text = read_text(path)
        for term in terms:
            require(term in text, f"{display_path(path)} missing term: {term}", failures)

    if GUIDE_TEX.exists():
        tex = read_text(GUIDE_TEX)
        for term in [
            "ScientificWorkbench",
            "contrato JSON",
            "artifact types",
            "run bundles",
            "router dry-run",
            "app-readiness",
            "v1.9",
            "v2.0",
        ]:
            require(term in tex, f"guide TeX missing term: {term}", failures)
        require("ya este sincronizada a v2.0" in tex, "guide TeX must avoid claiming app sync is complete", failures)

    pdf_text = ""
    page_count = None
    if GUIDE_PDF.exists():
        try:
            pdf_text, page_count = extract_pdf_text(GUIDE_PDF)
        except Exception as exc:
            failures.append(f"could not extract PDF text: {exc}")
        normalized_pdf = normalize_space(pdf_text)
        for term in PDF_TERMS:
            require(term in normalized_pdf, f"guide PDF missing term: {term}", failures)
        if page_count is not None:
            require(page_count >= 8, f"guide PDF should have at least 8 pages, got {page_count}", failures)
        forbidden_claims = [
            "ScientificWorkbench ya esta sincronizada",
            "v1.8 instala ScientificWorkbench",
            "v2.0 ya esta instalada",
        ]
        for term in forbidden_claims:
            require(term not in normalized_pdf, f"guide PDF contains forbidden claim: {term}", failures)

    matrix = MATRIX
    if matrix.exists():
        text = read_text(matrix)
        in_matrix = False
        rows: list[str] = []
        for line in text.splitlines():
            if line.startswith("## Matrix"):
                in_matrix = True
                continue
            if in_matrix and line.startswith("## "):
                break
            if in_matrix and re.match(r"^\| \d+ \|", line):
                rows.append(line)
        require(len(rows) == 59, f"matrix should still contain 59 rows, got {len(rows)}", failures)

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    payload = {
        "status": status,
        "phase": "v1.8 phase 8 docs and integration",
        "docs_checked": [display_path(path) for path in REQUIRED_DOCS],
        "guide_pdf": str(GUIDE_PDF),
        "guide_tex": str(GUIDE_TEX),
        "pdf_page_count": page_count,
        "pdf_text_chars": len(pdf_text),
        "warnings": warnings,
        "failures": failures,
        "notes": [
            "This regression validates skill-side documentation only.",
            "It does not synchronize the installed skill and does not edit ScientificWorkbench.",
        ],
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
