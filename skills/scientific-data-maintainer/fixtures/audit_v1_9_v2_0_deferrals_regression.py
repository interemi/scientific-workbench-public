#!/usr/bin/env python3
"""Validate v1.9 Deuda E v2.0 deferrals."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
TMP = ROOT / "tmp" / "v1_9_debt_E_v2_0_deferrals"

INVENTORY = REFERENCES / "v1-9-debt-inventory.md"
CHARTER = REFERENCES / "v1-9-consolidation-charter.md"
DEFERRALS = REFERENCES / "v1-9-v2-0-deferrals.md"

EXPECTED_DEFERRALS = {
    "8": {
        "label": "fits_rgb_batch.py",
        "family": "artifact_types",
        "app_readiness": "app_ready_partial",
        "reason": ["progreso UI", "control interactivo"],
    },
    "10": {
        "label": "stilts_workbench.py",
        "family": "exposure_modes",
        "app_readiness": "blocked_optional",
        "reason": ["panel opcional", "UX de app"],
    },
    "13": {
        "label": "radial_velocity_workbench.py inspect",
        "family": "app_hints",
        "app_readiness": "app_ready_partial",
        "reason": ["wrapper interactivo", "columnas/unidades"],
    },
    "26": {
        "label": "photometric_solution.py",
        "family": "artifact_types",
        "app_readiness": "app_ready_partial",
        "reason": ["selector interactivo", "columnas"],
    },
    "28": {
        "label": "apt_workbench.py",
        "family": "exposure_modes",
        "app_readiness": "blocked_optional",
        "reason": ["panel opcional APT", "ruta alternativa visual"],
    },
    "34": {
        "label": "office_roundtrip.py docx-style-inventory",
        "family": "artifact_types",
        "app_readiness": "app_ready_partial",
        "reason": ["selector visual", "preview de matches"],
    },
    "35": {
        "label": "office_roundtrip.py docx-styled-replace",
        "family": "artifact_types",
        "app_readiness": "app_ready_partial",
        "reason": ["confirmacion visual/diff", "edited document"],
    },
    "37": {
        "label": "keynote_export.py",
        "family": "errors",
        "app_readiness": "blocked_optional",
        "reason": ["confirmacion GUI", "preflight/bloqueo limpio"],
    },
}

REQUIRED_DOC_PHRASES = [
    "Deuda E",
    "ScientificWorkbench v2.0",
    "UI-driven workflow",
    "progress UI",
    "visual confirmation",
    "interactive selectors",
    "job history",
    "app-side parser",
    "ScientificWorkbench edits",
]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def read_text(path: Path) -> str:
    if not path.exists():
        fail(f"missing required file: {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Canonical fixture:\s*`([^`]+)`", text)
    if match:
        archived = ROOT / match.group(1)
        if archived.exists():
            return archived.read_text(encoding="utf-8")
    return text


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def normalize(value: str) -> str:
    return value.lower().replace("`", "")


def parse_inventory_rows() -> list[dict[str, str]]:
    text = read_text(INVENTORY)
    rows: list[dict[str, str]] = []
    in_section = False
    for line in text.splitlines():
        if line == "## Actionable Capability Rows":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not re.match(r"^\| \d+ \|", line):
            continue
        cells = split_row(line)
        if len(cells) != 10:
            fail(f"inventory row has {len(cells)} cells, expected 10: {line}")
        rows.append(
            {
                "n": cells[0],
                "label": cells[1].strip("`"),
                "severity": cells[2].strip("`"),
                "family": cells[3].strip("`"),
                "app_readiness": cells[4].strip("`"),
                "decision": cells[5].strip("`"),
                "phase": cells[6].strip("`"),
                "action": cells[7],
                "risk": cells[8],
                "deferred": cells[9],
            }
        )
    if len(rows) != 59:
        fail(f"expected 59 capability rows, found {len(rows)}")
    return rows


def validate_inventory(rows: list[dict[str, str]]) -> dict[str, object]:
    by_n = {row["n"]: row for row in rows}
    expected_numbers = set(EXPECTED_DEFERRALS)
    actual_v2_numbers = {row["n"] for row in rows if row["decision"] == "v2_0"}
    if actual_v2_numbers != expected_numbers:
        fail(
            "unexpected v2_0 rows: "
            f"expected {sorted(expected_numbers)}, found {sorted(actual_v2_numbers)}"
        )

    for number, spec in EXPECTED_DEFERRALS.items():
        row = by_n.get(number)
        if row is None:
            fail(f"missing expected deferral row {number}")
        for field in ("label", "family", "app_readiness"):
            if row[field] != spec[field]:
                fail(f"row {number} has {field}={row[field]!r}, expected {spec[field]!r}")
        if row["severity"] != "P1":
            fail(f"row {number} must remain P1, found {row['severity']}")
        if row["decision"] != "v2_0":
            fail(f"row {number} must remain decision=v2_0, found {row['decision']}")
        if row["phase"] != "v2_0":
            fail(f"row {number} must remain phase=v2_0, found {row['phase']}")
        if "No implementar en v1.9" not in row["action"]:
            fail(f"row {number} does not explicitly block v1.9 implementation")
        combined = normalize(f"{row['action']} {row['risk']} {row['deferred']}")
        for phrase in spec["reason"]:
            if normalize(phrase) not in combined:
                fail(f"row {number} missing deferred reason phrase: {phrase}")

    expected_labels = {spec["label"] for spec in EXPECTED_DEFERRALS.values()}
    for row in rows:
        if row["label"] in expected_labels and row["decision"] != "v2_0":
            fail(f"{row['label']} is a protected v2.0 target but is scheduled as {row['decision']}")

    return {
        "protected_rows": len(EXPECTED_DEFERRALS),
        "protected_targets": [EXPECTED_DEFERRALS[n]["label"] for n in sorted(EXPECTED_DEFERRALS, key=int)],
    }


def validate_docs() -> None:
    deferrals_text = read_text(DEFERRALS)
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase not in deferrals_text:
            fail(f"deferral reference missing required phrase: {phrase}")
    for spec in EXPECTED_DEFERRALS.values():
        if f"`{spec['label']}`" not in deferrals_text:
            fail(f"deferral reference missing target: {spec['label']}")

    charter_text = read_text(CHARTER)
    if "references/v1-9-v2-0-deferrals.md" not in charter_text:
        fail("charter does not point to the v2.0 deferrals reference")
    for phrase in ("UI-driven workflow", "interactive selectors", "ScientificWorkbench sync"):
        if phrase not in charter_text:
            fail(f"charter missing v2.0 guardrail phrase: {phrase}")

    inventory_text = read_text(INVENTORY)
    if "references/v1-9-v2-0-deferrals.md" not in inventory_text:
        fail("inventory does not point to the v2.0 deferrals reference")


def main() -> int:
    rows = parse_inventory_rows()
    summary = validate_inventory(rows)
    validate_docs()
    TMP.mkdir(parents=True, exist_ok=True)
    output = {
        "status": "PASS",
        "check": "v1.9 Deuda E v2.0 deferrals regression",
        **summary,
    }
    out_path = TMP / "v2_0_deferrals_regression_summary.json"
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
