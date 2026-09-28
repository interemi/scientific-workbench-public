#!/usr/bin/env python3
"""Validate the v2.3 modular architecture documentation set."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = [
    "references/v2-3-modular-architecture-charter.md",
    "references/v2-3-module-ownership-matrix.json",
    "references/v2-3-mother-router-contract.md",
    "references/v2-3-mother-router-module-map.json",
    "references/v2-3-maintainer-split.md",
    "references/v2-3-documents-split.md",
    "references/v2-3-notebooks-split.md",
    "references/v2-3-astro-split.md",
    "references/v2-3-shared-contract-and-helpers.md",
    "references/v2-3-scientificworkbench-compat.md",
    "references/v2-3-plugin-eval-modular-results.md",
    "references/guia_scientific_data_analysis_v2_3.tex",
    "references/guia_scientific_data_analysis_v2_3.pdf",
]
PDF_TERMS = [
    "Scientific Data Analysis v2.3",
    "arquitectura modular",
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
    "ScientificWorkbench",
    "plugin-eval",
    "child_skill_dispatch.py",
]


def _extract_pdf_text(path: Path) -> tuple[str, list[dict[str, str]]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - dependency message is the contract.
        return "", [{"kind": "missing_pdf_backend", "message": f"pypdf is unavailable: {exc}"}]

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages), []
    except Exception as exc:
        return "", [{"kind": "pdf_read_error", "message": str(exc)}]


def main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    for rel in REQUIRED_DOCS:
        path = ROOT / rel
        if not path.exists():
            errors.append({"kind": "missing_doc", "message": rel})
        elif path.is_file() and path.stat().st_size == 0:
            errors.append({"kind": "empty_doc", "message": rel})

    pdf_path = ROOT / "references/guia_scientific_data_analysis_v2_3.pdf"
    if pdf_path.exists():
        text, pdf_errors = _extract_pdf_text(pdf_path)
        errors.extend(pdf_errors)
        if text:
            for term in PDF_TERMS:
                if term not in text:
                    errors.append({"kind": "missing_pdf_term", "message": term})
            if len(text) < 3000:
                warnings.append("Extracted PDF text is unexpectedly short.")

    status = "PASS" if not errors else "FAIL"
    result = {
        "tool": "audit_v2_3_docs_regression",
        "status": status,
        "required_doc_count": len(REQUIRED_DOCS),
        "pdf": "references/guia_scientific_data_analysis_v2_3.pdf",
        "errors": errors,
        "warnings": warnings,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Fix missing or incomplete v2.3 documentation", "priority": "high"}],
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
