#!/usr/bin/env python3
"""Validate v1.9 documentation, guide PDF text, and rendered pages."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
TMP = ROOT / "tmp" / "v1_9_phase7_docs"
RENDER_DIR = TMP / "rendered_pages"
SUMMARY = TMP / "phase7_docs_regression.json"

GUIDE_TEX = REFERENCES / "guia_scientific_data_analysis_v1_9.tex"
GUIDE_PDF = REFERENCES / "guia_scientific_data_analysis_v1_9.pdf"

REQUIRED_DOCS = [
    REFERENCES / "v1-9-consolidation-charter.md",
    REFERENCES / "v1-9-debt-inventory.md",
    REFERENCES / "v1-9-artifact-types-freeze.md",
    REFERENCES / "v1-9-error-contract.md",
    REFERENCES / "v1-9-app-hints-next-actions.md",
    REFERENCES / "v1-9-exposure-modes.md",
    REFERENCES / "v1-9-v2-0-deferrals.md",
    REFERENCES / "v1-9-app-like-extended-regression.md",
    GUIDE_TEX,
    GUIDE_PDF,
]

DOC_TERMS = {
    REFERENCES / "v1-9-consolidation-charter.md": [
        "Contract Freeze and App-Facing Hardening Release",
        "Dejar para v2.0",
        "ScientificWorkbench is not edited",
    ],
    REFERENCES / "v1-9-debt-inventory.md": [
        "Capability Debt Counts",
        "`v1_9`",
        "`v2_0`",
        "`no_procede`",
        "Cross-Cutting Rows",
    ],
    REFERENCES / "v1-9-artifact-types-freeze.md": [
        "Frozen v1.8 Types",
        "v1.9 Compatible Additions",
        "Prohibited Aliases",
        "fits_visual",
        "preview_pdf",
    ],
    REFERENCES / "v1-9-error-contract.md": [
        "Allowed Error Kinds",
        "BLOCKED_CONTROLADO",
        "output_conflict",
        "missing_optional_backend",
    ],
    REFERENCES / "v1-9-app-hints-next-actions.md": [
        "short_summary",
        "severity",
        "preview_artifact_types",
        "next_actions",
    ],
    REFERENCES / "v1-9-exposure-modes.md": [
        "Exposure Modes Freeze",
        "normal_user_action=false",
        "maintainer_only",
        "legacy_expert_only",
    ],
    REFERENCES / "v1-9-v2-0-deferrals.md": [
        "Forbidden In v1.9",
        "ScientificWorkbench",
        "v2.0",
        "Deferred Rows",
    ],
    REFERENCES / "v1-9-app-like-extended-regression.md": [
        "tabla profesional",
        "notebook heredado",
        "contenedor corrupto",
        "backend opcional ausente",
        "output conflictivo",
    ],
}

GUIDE_TEX_TERMS = [
    "Version v1.9 contract freeze + app-facing hardening",
    "Que cambia de v1.8 a v1.9",
    "Artifact types congelados",
    "Errores y bloqueos app-facing",
    "App hints y next actions",
    "Exposicion de capabilities",
    "Cobertura app-like ampliada",
    "Limites protegidos para v2.0",
    "v1.9 consolida el backend; v2.0 sincronizara ScientificWorkbench",
]

PDF_TERMS = [
    "Version v1.9 contract freeze + app-facing hardening",
    "Que cambia de v1.8 a v1.9",
    "Artifact types congelados",
    "Errores y bloqueos app-facing",
    "App hints y next actions",
    "Exposicion de capabilities",
    "Regresiones v1.9",
    "Cobertura app-like ampliada",
    "Limites protegidos para v2.0",
    "v1.9 consolida el backend",
]

FORBIDDEN_CLAIMS = [
    "ScientificWorkbench ya esta sincronizada",
    "v1.9 instala ScientificWorkbench",
    "v2.0 ya esta instalada",
    "workflows UI-driven implementados en v1.9",
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError(f"pypdf unavailable: {exc}") from exc
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, len(reader.pages)


def render_pdf_pages(path: Path, failures: list[str], warnings: list[str]) -> list[str]:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - environment diagnostic
        warnings.append(f"PyMuPDF unavailable; page rendering skipped: {exc}")
        return []

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for old in RENDER_DIR.glob("page_*.png"):
        old.unlink()

    rendered: list[str] = []
    doc = fitz.open(path)
    zoom = 1.25
    matrix = fitz.Matrix(zoom, zoom)
    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out = RENDER_DIR / f"page_{index + 1:02d}.png"
        pix.save(out)
        rendered.append(str(out.relative_to(ROOT)))
        require(out.exists() and out.stat().st_size > 10_000, f"rendered page too small or missing: {out}", failures)
        require(pix.width > 500 and pix.height > 700, f"rendered page has suspicious dimensions: {out} {pix.width}x{pix.height}", failures)
    doc.close()
    return rendered


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []

    for path in REQUIRED_DOCS:
        require(path.exists(), f"missing required doc: {path.relative_to(ROOT)}", failures)

    for path, terms in DOC_TERMS.items():
        if not path.exists():
            continue
        text = read_text(path)
        for term in terms:
            require(term in text, f"{path.relative_to(ROOT)} missing term: {term}", failures)
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in text, f"{path.relative_to(ROOT)} contains forbidden claim: {claim}", failures)

    if GUIDE_TEX.exists():
        tex = read_text(GUIDE_TEX)
        for term in GUIDE_TEX_TERMS:
            require(term in tex, f"guide TeX missing term: {term}", failures)
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in tex, f"guide TeX contains forbidden claim: {claim}", failures)

    pdf_text = ""
    page_count: int | None = None
    rendered_pages: list[str] = []
    if GUIDE_PDF.exists():
        require(GUIDE_PDF.read_bytes()[:4] == b"%PDF", "guide PDF does not have a PDF header", failures)
        require(GUIDE_PDF.stat().st_size > 80_000, f"guide PDF looks too small: {GUIDE_PDF.stat().st_size} bytes", failures)
        try:
            pdf_text, page_count = extract_pdf_text(GUIDE_PDF)
        except Exception as exc:
            failures.append(f"could not extract PDF text: {exc}")
        normalized_pdf = normalize_space(pdf_text)
        for term in PDF_TERMS:
            require(term in normalized_pdf, f"guide PDF missing term: {term}", failures)
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in normalized_pdf, f"guide PDF contains forbidden claim: {claim}", failures)
        if page_count is not None:
            require(page_count >= 10, f"guide PDF should have at least 10 pages, got {page_count}", failures)
        rendered_pages = render_pdf_pages(GUIDE_PDF, failures, warnings)
        if page_count is not None:
            require(len(rendered_pages) == page_count, f"rendered pages mismatch: {len(rendered_pages)} vs {page_count}", failures)

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    payload = {
        "status": status,
        "phase": "v1.9 phase 7 documentation and guide",
        "docs_checked": [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS],
        "guide_tex": str(GUIDE_TEX.relative_to(ROOT)),
        "guide_pdf": str(GUIDE_PDF.relative_to(ROOT)),
        "pdf_page_count": page_count,
        "pdf_text_chars": len(pdf_text),
        "rendered_pages": rendered_pages,
        "warnings": warnings,
        "failures": failures,
        "notes": [
            "This regression validates editable-tree documentation only.",
            "It does not synchronize the installed skill.",
            "It does not edit ScientificWorkbench.",
        ],
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
