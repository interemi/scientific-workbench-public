#!/usr/bin/env python3
"""Aggregate v1.9 release-candidate checks for editable or installed trees."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_9_release_candidate"
SUMMARY = TMP / "release_candidate_regression.json"

REGISTRY = ROOT / "public_surface_registry.yaml"
GUIDE_TEX = REFERENCES / "guia_scientific_data_analysis_v1_9.tex"
GUIDE_PDF = REFERENCES / "guia_scientific_data_analysis_v1_9.pdf"


def canonical_reference(name: str) -> Path:
    local = REFERENCES / name
    maintainer = MAINTAINER_REFERENCES / name
    if not maintainer.exists():
        return local
    if not local.exists():
        return maintainer
    try:
        local_text = local.read_text(encoding="utf-8", errors="ignore")
    except UnicodeDecodeError:
        local_text = ""
    if "scientific-data-maintainer/references" in local_text or "compatibility pointer" in local_text:
        return maintainer
    match = re.search(r"Canonical fixture:\s*`([^`]+)`", local_text)
    if match:
        archived = ROOT / match.group(1)
        if archived.exists():
            return archived
    if local.suffix.lower() == ".pdf" and local.stat().st_size < 80_000:
        return maintainer
    return local


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}

REQUIRED_DOCS = {
    REFERENCES / "v1-9-consolidation-charter.md": [
        "Contract Freeze and App-Facing Hardening Release",
        "Closure Criteria",
        "ScientificWorkbench is not edited",
    ],
    canonical_reference("v1-9-debt-inventory.md"): [
        "Capability Debt Counts",
        "P1",
        "P2",
        "`v1_9`",
        "`v2_0`",
        "`no_procede`",
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
        "errors[].kind",
        "next_actions",
    ],
    REFERENCES / "v1-9-app-hints-next-actions.md": [
        "short_summary",
        "preview_artifact_types",
        "next_actions",
    ],
    REFERENCES / "v1-9-exposure-modes.md": [
        "Exposure Modes Freeze",
        "normal_user_action=false",
        "maintainer_only",
    ],
    REFERENCES / "v1-9-v2-0-deferrals.md": [
        "Forbidden In v1.9",
        "Deferred Rows",
        "ScientificWorkbench",
    ],
    REFERENCES / "v1-9-app-like-extended-regression.md": [
        "tabla profesional",
        "notebook heredado",
        "backend opcional ausente",
        "output conflictivo",
    ],
}

REQUIRED_TOP_LEVEL_DOC_ALTERNATIVES = {
    ROOT / "SKILL.md": [
        [
            "`v1.9 stable`",
            "contract-freeze and app-facing hardening release",
            "without developing or synchronizing ScientificWorkbench",
        ],
        [
            "`v2.0 integrated`",
            "v1.9 remains the frozen artifact/error/exposure contract foundation",
            "ScientificWorkbench as the native macOS product surface",
        ],
    ],
    ROOT / "README.txt": [
        [
            "v1.9 stable over v1.8 app-ready backend",
            "v1.9 is the installed contract-freeze and app-facing hardening release",
            "ScientificWorkbench sync remains future work",
        ],
        [
            "v2.0 integrated skill + ScientificWorkbench",
            "v1.9 is the contract-freeze and app-facing hardening release",
            "the macOS app consumes the installed registry",
        ],
    ],
    ROOT / "RELEASE-v1.txt": [
        [
            "Release v2.2 evaluation-hardening / v2.1 compact-router / v2.0 integrated skill + ScientificWorkbench / v1.9 contract-freeze / v1.8 app-ready backend / v1.7 real-world / v1.6 stable baseline",
            "v1.9 is the stable contract-freeze and app-facing hardening release",
            "v2.0 is the installed integrated release when post-sync validation passes",
        ],
        [
            "Release v1.9 stable / v1.8 app-ready backend",
            "v1.9 is the installed stable contract-freeze and app-facing hardening release",
            "A v1.8/v1.9 backend contract route for future app consumers",
        ],
        [
            "Release v2.0 integrated skill + ScientificWorkbench",
            "v1.9 is the stable contract-freeze and app-facing hardening release",
            "A v1.8/v1.9/v2.0 backend and app contract route",
        ],
    ],
}

REQUIRED_V1_9_REGRESSIONS = [
    "audit_v1_9_phase0_inventory_regression.py",
    "audit_v1_9_artifact_types_regression.py",
    "audit_v1_9_error_contract_regression.py",
    "audit_v1_9_dedupe_regression.py",
    "audit_v1_9_app_hints_regression.py",
    "audit_v1_9_general_p2_regression.py",
    "audit_v1_9_exposure_modes_regression.py",
    "audit_v1_9_v2_0_deferrals_regression.py",
    "audit_v1_9_more_app_like_regression.py",
    "audit_v1_9_app_like_extended_regression.py",
    "audit_v1_9_docs_regression.py",
    "audit_v1_9_release_candidate_regression.py",
]

FORBIDDEN_CLAIMS = [
    "ScientificWorkbench ya esta sincronizada",
    "v1.9 instala ScientificWorkbench",
    "v2.0 ya esta instalada",
    "workflows UI-driven implementados en v1.9",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def registry_labels() -> list[str]:
    labels: list[str] = []
    for line in read_text(REGISTRY).splitlines():
        match = re.match(r"\s*label:\s*(.*?)\s*$", line)
        if match:
            labels.append(match.group(1).strip().strip('"'))
    return labels


def v1_9_registry_labels(labels: list[str]) -> list[str]:
    if len(labels) == 59:
        return labels
    return [label for label in labels if label not in V2_0_ADDED_LABELS]


def parse_inventory_rows() -> list[dict[str, str]]:
    path = canonical_reference("v1-9-debt-inventory.md")
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    in_rows = False
    for line in read_text(path).splitlines():
        if line == "## Actionable Capability Rows":
            in_rows = True
            continue
        if in_rows and line.startswith("## "):
            break
        if not in_rows or not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 10:
            rows.append(
                {
                    "n": cells[0],
                    "label": cells[1].strip("`"),
                    "severity": cells[2].strip("`"),
                    "family": cells[3].strip("`"),
                    "decision": cells[5].strip("`"),
                    "phase": cells[6].strip("`"),
                }
            )
    return rows


def extract_pdf_info(path: Path, failures: list[str]) -> tuple[int | None, int]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - environment diagnostic
        failures.append(f"pypdf unavailable for guide validation: {exc}")
        return None, 0
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return len(reader.pages), len(text)


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []

    require(REGISTRY.exists(), failures, "missing public_surface_registry.yaml")
    labels = registry_labels() if REGISTRY.exists() else []
    v1_9_labels = v1_9_registry_labels(labels)
    require(
        len(v1_9_labels) == 59,
        failures,
        f"v1.9 public registry subset should contain 59 labels, got {len(v1_9_labels)} from current {len(labels)}",
    )

    rows = parse_inventory_rows()
    require(len(rows) == 59, failures, f"v1.9 debt inventory should contain 59 capability rows, got {len(rows)}")
    if v1_9_labels and rows:
        require([row["label"] for row in rows] == v1_9_labels, failures, "v1.9 debt inventory order should match v1.9 registry subset")
    severity_counts = Counter(row["severity"] for row in rows)
    decision_counts = Counter(row["decision"] for row in rows)
    require(severity_counts == Counter({"P1": 25, "P2": 34}), failures, f"unexpected P1/P2 counts: {dict(severity_counts)}")
    require(decision_counts == Counter({"v1_9": 34, "v2_0": 8, "no_procede": 17}), failures, f"unexpected decision counts: {dict(decision_counts)}")

    docs_checked: list[str] = []
    for path, alternatives in REQUIRED_TOP_LEVEL_DOC_ALTERNATIVES.items():
        require(path.exists(), failures, f"missing top-level doc: {display_path(path)}")
        if not path.exists():
            continue
        text = read_text(path)
        matched = any(all(term in text for term in terms) for terms in alternatives)
        if not matched:
            alternatives_text = [" + ".join(terms) for terms in alternatives]
            failures.append(
                f"{display_path(path)} missing any supported top-level version term set: {alternatives_text}"
            )
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in text, failures, f"{display_path(path)} contains forbidden claim: {claim}")
        docs_checked.append(display_path(path))

    for path, terms in REQUIRED_DOCS.items():
        require(path.exists(), failures, f"missing v1.9 doc: {display_path(path)}")
        if not path.exists():
            continue
        text = read_text(path)
        for term in terms:
            require(term in text, failures, f"{display_path(path)} missing term: {term}")
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in text, failures, f"{display_path(path)} contains forbidden claim: {claim}")
        docs_checked.append(display_path(path))

    require(GUIDE_TEX.exists(), failures, "missing guia_scientific_data_analysis_v1_9.tex")
    guide_pdf = canonical_reference("guia_scientific_data_analysis_v1_9.pdf")
    require(guide_pdf.exists(), failures, "missing guia_scientific_data_analysis_v1_9.pdf")
    pdf_pages: int | None = None
    pdf_text_chars = 0
    if GUIDE_TEX.exists():
        tex = read_text(GUIDE_TEX)
        for term in [
            "Version v1.9 contract freeze + app-facing hardening",
            "Que cambia de v1.8 a v1.9",
            "Artifact types congelados",
            "Errores y bloqueos app-facing",
            "v1.9 consolida el backend; v2.0 sincronizara ScientificWorkbench",
        ]:
            require(term in tex, failures, f"v1.9 guide TeX missing term: {term}")
        for claim in FORBIDDEN_CLAIMS:
            require(claim not in tex, failures, f"v1.9 guide TeX contains forbidden claim: {claim}")
    if guide_pdf.exists():
        require(guide_pdf.read_bytes()[:4] == b"%PDF", failures, "v1.9 guide PDF missing PDF header")
        require(guide_pdf.stat().st_size > 80_000, failures, f"v1.9 guide PDF too small: {guide_pdf.stat().st_size}")
        pdf_pages, pdf_text_chars = extract_pdf_info(guide_pdf, failures)
        if pdf_pages is not None:
            require(pdf_pages >= 10, failures, f"v1.9 guide PDF should have at least 10 pages, got {pdf_pages}")

    regressions_present = []
    for name in REQUIRED_V1_9_REGRESSIONS:
        path = SCRIPTS / name
        require(path.exists(), failures, f"missing v1.9 regression: {name}")
        if path.exists():
            regressions_present.append(name)

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    payload = {
        "status": status,
        "phase": "v1.9 release candidate regression",
        "root": str(ROOT),
        "registry_label_count": len(labels),
        "v1_9_registry_subset_count": len(v1_9_labels),
        "severity_counts": dict(severity_counts),
        "decision_counts": dict(decision_counts),
        "docs_checked": docs_checked,
        "regressions_present": regressions_present,
        "guide": {
            "tex": str(GUIDE_TEX.relative_to(ROOT)) if GUIDE_TEX.exists() else None,
            "pdf": display_path(guide_pdf) if guide_pdf.exists() else None,
            "pdf_pages": pdf_pages,
            "pdf_text_chars": pdf_text_chars,
        },
        "warnings": warnings,
        "failures": failures,
        "notes": [
            "This gate validates the current tree and does not synchronize anything.",
            "ScientificWorkbench is intentionally outside this release-candidate gate.",
        ],
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
