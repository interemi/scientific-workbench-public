#!/usr/bin/env python3
"""Validate the v1.7 real-world capability classification matrix."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "public_surface_registry.yaml"
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"


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

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}

ALLOWED = {
    "general",
    "cross_domain_adaptable",
    "domain_specific",
    "legacy_specific",
    "maintainer_only",
}

EXPECTED_COUNTS = {
    "general": 25,
    "cross_domain_adaptable": 9,
    "domain_specific": 7,
    "legacy_specific": 12,
    "maintainer_only": 6,
}


def fail(message: str) -> None:
    raise AssertionError(message)


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
        number = int(match.group(1))
        label = match.group(2).strip()
        category = match.group(3).strip()
        rest = match.group(4)
        cells = [cell.strip() for cell in rest.split("|")]
        if len(cells) != 3:
            fail(f"row {number} should have 6 columns, got trailing cells={cells!r}")
        justification, examples, action = cells
        rows.append(
            {
                "number": number,
                "label": label,
                "category": category,
                "justification": justification,
                "examples": examples,
                "action": action,
            }
        )
    return rows


def main() -> int:
    registry_labels = parse_registry_labels()
    rows = parse_matrix_rows()
    if len(registry_labels) != 59:
        fail(f"registry should expose 59 public capabilities, got {len(registry_labels)}")
    if len(rows) != 59:
        fail(f"classification matrix should contain 59 rows, got {len(rows)}")

    numbers = [int(row["number"]) for row in rows]
    expected_numbers = list(range(1, 60))
    if numbers != expected_numbers:
        fail(f"matrix row numbers are not 1..59: {numbers}")

    matrix_labels = [str(row["label"]) for row in rows]
    if matrix_labels != registry_labels:
        mismatches = [
            {"n": i + 1, "registry": reg, "matrix": mat}
            for i, (reg, mat) in enumerate(zip(registry_labels, matrix_labels))
            if reg != mat
        ]
        fail(f"matrix labels do not match registry order: {mismatches[:5]}")

    categories = [str(row["category"]) for row in rows]
    unknown = sorted(set(categories) - ALLOWED)
    if unknown:
        fail(f"unknown categories: {unknown}")

    counts = dict(Counter(categories))
    if counts != EXPECTED_COUNTS:
        fail(f"category counts changed: expected {EXPECTED_COUNTS}, got {counts}")

    for row in rows:
        for field in ("justification", "examples", "action"):
            value = str(row[field]).strip()
            if len(value) < 20:
                fail(f"row {row['number']} field {field} is too thin: {value!r}")
            if re.search(r"\bTODO\b", value, flags=re.IGNORECASE):
                fail(f"row {row['number']} contains TODO in {field}")

    payload = {
        "status": "ok",
        "capability_count": len(rows),
        "categories": counts,
        "matrix": str(MATRIX),
        "registry": str(REGISTRY),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
