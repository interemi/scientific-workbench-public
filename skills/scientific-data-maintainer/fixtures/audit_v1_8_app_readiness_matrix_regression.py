#!/usr/bin/env python3
"""Validate the v1.8 app-readiness matrix against registry and v1.7 classes."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "public_surface_registry.yaml"
REFERENCES = ROOT / "references"
MAINTAINER_REFERENCES = ROOT.parent / "scientific-data-maintainer" / "references"
REAL_WORLD = None
MATRIX = None
TMP = ROOT / "tmp" / "v1_8_phase2_app_readiness_matrix"

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}

ALLOWED_APP_READINESS = {
    "app_ready",
    "app_ready_partial",
    "cli_only",
    "blocked_optional",
    "maintainer_only",
    "not_applicable_to_app",
}

EXPECTED_COUNTS = {
    "app_ready": 17,
    "app_ready_partial": 18,
    "blocked_optional": 7,
    "cli_only": 9,
    "maintainer_only": 6,
    "not_applicable_to_app": 2,
}

CRITICAL_FIELDS = [
    "label",
    "bloque",
    "tipo",
    "soporte",
    "requiere_datanalysis",
    "real_world_v1_7",
    "app_readiness",
    "razon",
    "comando_minimo_app_like",
    "inputs_esperados",
    "outputs_esperados",
    "artifact_types",
    "side_effect_policy",
    "failure_contract",
    "P0_P1_P2_sugeridos",
]


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


REAL_WORLD = canonical_reference("real-world-capability-classification-v1-7.md")
MATRIX = canonical_reference("v1-8-app-readiness-matrix.md")


def strip_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def parse_registry() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- id: "):
            if current:
                entries.append(current)
            current = {"id": stripped.split("- id: ", 1)[1]}
            continue
        if current is None or ": " not in stripped:
            continue
        key, value = stripped.split(": ", 1)
        current[key] = value.strip()
    if current:
        entries.append(current)
    return [entry for entry in entries if entry.get("label") not in V2_0_ADDED_LABELS]


def parse_real_world_classes() -> dict[str, str]:
    rows: dict[str, str] = {}
    pattern = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")
    for line in REAL_WORLD.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def parse_matrix_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    in_matrix = False
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Matrix"):
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if not in_matrix:
            continue
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == "N":
            headers = cells
            continue
        if not cells or not cells[0].isdigit():
            continue
        if headers is None:
            raise AssertionError("matrix table rows found before header")
        if len(cells) != len(headers):
            raise AssertionError(f"row {cells[0]} has {len(cells)} cells, expected {len(headers)}: {cells}")
        row = dict(zip(headers, cells, strict=True))
        row["N"] = row["N"].strip()
        for key in ("label", "app_readiness"):
            row[key] = strip_code(row[key])
        rows.append(row)
    return rows


def parse_top_p1_labels(text: str) -> list[str]:
    labels: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## Top 10 P1"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].isdigit():
            labels.append(strip_code(cells[1]))
    return labels


def contains_forbidden_placeholder(value: str) -> bool:
    return bool(re.search(r"\b(TODO|TBD|pendiente|por definir)\b", value, flags=re.IGNORECASE))


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    TMP.mkdir(parents=True, exist_ok=True)

    registry = parse_registry()
    real_world = parse_real_world_classes()
    matrix_text = MATRIX.read_text(encoding="utf-8") if MATRIX.exists() else ""
    rows = parse_matrix_rows() if MATRIX.exists() else []

    if len(registry) != 59:
        failures.append(f"registry should expose 59 public capabilities, got {len(registry)}")
    if len(rows) != 59:
        failures.append(f"app-readiness matrix should contain 59 rows, got {len(rows)}")
    if len(real_world) != 59:
        failures.append(f"v1.7 real-world matrix should contain 59 rows, got {len(real_world)}")

    expected_numbers = [str(index) for index in range(1, 60)]
    numbers = [row.get("N", "") for row in rows]
    if numbers != expected_numbers:
        failures.append(f"matrix row numbers are not 1..59: {numbers}")

    registry_by_label = {entry.get("label", ""): entry for entry in registry}
    registry_labels = [entry.get("label", "") for entry in registry]
    matrix_labels = [row.get("label", "") for row in rows]
    if matrix_labels != registry_labels:
        mismatches = [
            {"n": index + 1, "registry": reg, "matrix": mat}
            for index, (reg, mat) in enumerate(zip(registry_labels, matrix_labels, strict=False))
            if reg != mat
        ]
        failures.append(f"matrix labels do not match registry order: {mismatches[:8]}")

    statuses = [row.get("app_readiness", "") for row in rows]
    unknown = sorted(set(statuses) - ALLOWED_APP_READINESS)
    if unknown:
        failures.append(f"unknown app_readiness values: {unknown}")
    counts = dict(Counter(statuses))
    if counts != EXPECTED_COUNTS:
        failures.append(f"app_readiness counts changed: expected {EXPECTED_COUNTS}, got {counts}")

    for row in rows:
        label = row.get("label", "")
        registry_entry = registry_by_label.get(label)
        if not registry_entry:
            failures.append(f"matrix row label not in registry: {label}")
            continue
        if row.get("bloque") != registry_entry.get("visible_block"):
            failures.append(f"{label}: bloque mismatch")
        if row.get("tipo") != registry_entry.get("kind"):
            failures.append(f"{label}: tipo mismatch")
        if row.get("soporte") != registry_entry.get("support_level"):
            failures.append(f"{label}: soporte mismatch")
        if row.get("requiere_datanalysis") != registry_entry.get("requires_datanalysis"):
            failures.append(f"{label}: requiere_datanalysis mismatch")
        expected_real_world = real_world.get(label)
        if row.get("real_world_v1_7") != expected_real_world:
            failures.append(f"{label}: real_world_v1_7 mismatch, expected {expected_real_world}")

        for field in CRITICAL_FIELDS:
            value = row.get(field, "").strip()
            if not value:
                failures.append(f"{label}: critical field is empty: {field}")
            if contains_forbidden_placeholder(value):
                failures.append(f"{label}: placeholder found in {field}: {value!r}")

        readiness = row.get("app_readiness")
        command = row.get("comando_minimo_app_like", "")
        artifacts = row.get("artifact_types", "")
        p_suggestions = row.get("P0_P1_P2_sugeridos", "")
        failure_contract = row.get("failure_contract", "")

        if readiness in {"app_ready", "app_ready_partial"}:
            if "scripts/" not in command or "--summary-json" not in command:
                failures.append(f"{label}: app-visible row lacks app-like summary-json command")
            if "summary_json" not in artifacts:
                failures.append(f"{label}: app-visible row lacks summary_json artifact type")
            if not re.search(r"\bP[012]:\s+\w+", p_suggestions):
                failures.append(f"{label}: app-visible row lacks concrete P0/P1/P2 action")

        if readiness == "app_ready":
            policy = row.get("side_effect_policy", "")
            if not any(token in policy for token in ("read_only", "copies", "writes_new", "no_input_mutation")):
                failures.append(f"{label}: app_ready side_effect_policy is not explicit enough")

        if readiness == "blocked_optional" and "BLOCKED" not in failure_contract.upper():
            failures.append(f"{label}: blocked_optional row should declare a controlled block contract")

        if registry_entry.get("kind") == "maintainer_only" and readiness != "maintainer_only":
            failures.append(f"{label}: maintainer registry entry should stay maintainer_only in app matrix")

    top_p1_labels = parse_top_p1_labels(matrix_text)
    if len(top_p1_labels) != 10:
        failures.append(f"Top 10 P1 section should contain 10 rows, got {len(top_p1_labels)}")
    missing_top_p1 = [label for label in top_p1_labels if label not in registry_by_label]
    if missing_top_p1:
        failures.append(f"Top 10 P1 contains labels outside registry: {missing_top_p1}")
    for term in (
        "No Exponer En Modo Normal",
        "Todas las filas `maintainer_only`",
        "Todas las filas `cli_only`",
        "Todas las filas `not_applicable_to_app`",
        "Todas las filas `blocked_optional`",
    ):
        if term not in matrix_text:
            failures.append(f"matrix missing normal-mode exclusion term: {term}")

    payload = {
        "status": "FAIL" if failures else ("WARNING" if warnings else "PASS"),
        "phase": "v1.8 phase 2 app-readiness matrix",
        "matrix": str(MATRIX),
        "registry": str(REGISTRY),
        "capability_count": len(rows),
        "app_readiness_counts": counts,
        "top_p1": top_p1_labels,
        "warnings": warnings,
        "failures": failures,
    }
    (TMP / "matrix_regression.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
