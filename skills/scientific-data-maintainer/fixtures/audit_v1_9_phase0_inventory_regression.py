#!/usr/bin/env python3
"""Validate the v1.9 phase 0 consolidation inventory."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"
TMP = ROOT / "tmp" / "v1_9_phase0_inventory"

CHARTER = REFERENCES / "v1-9-consolidation-charter.md"
INVENTORY = REFERENCES / "v1-9-debt-inventory.md"
REGISTRY = ROOT / "public_surface_registry.yaml"

V2_0_ADDED_LABELS = {
    "legacy_spectroscopy_report_builder.py populate",
    "latex_workbench.py compile",
}

REQUIRED_FAMILIES = {
    "artifact_types",
    "app_hints",
    "errors",
    "duplicacion",
    "regressions",
    "exposure_modes",
}
REQUIRED_DECISIONS = {"v1_9", "v2_0", "no_procede"}
FORBIDDEN_V1_9_ACTION_SCOPE = {
    "UI-driven workflows completos",
    "Sincronizacion mayor con ScientificWorkbench",
    "Planificador app + skill",
    "Historial, previews y estados de jobs",
    "Documentacion conjunta skill + app",
}


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


def registry_labels() -> list[str]:
    labels: list[str] = []
    for line in read_text(REGISTRY).splitlines():
        match = re.match(r"\s*label:\s*(.*?)\s*$", line)
        if match:
            labels.append(match.group(1).strip().strip('"'))
    if len(labels) == 59:
        return labels
    filtered = [label for label in labels if label not in V2_0_ADDED_LABELS]
    if len(filtered) != 59:
        fail(f"expected 59 v1.9 registry labels after v2.0 additions, found {len(filtered)} from {len(labels)}")
    return filtered


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_inventory() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    text = read_text(INVENTORY)
    capability_rows: list[dict[str, str]] = []
    global_rows: list[dict[str, str]] = []
    section = None

    for line in text.splitlines():
        if line == "## Actionable Capability Rows":
            section = "capability"
            continue
        if line == "## Cross-Cutting Rows":
            section = "global"
            continue
        if line.startswith("## ") and section in {"capability", "global"}:
            section = None
            continue
        if section == "capability" and re.match(r"^\| \d+ \|", line):
            cells = split_row(line)
            if len(cells) != 10:
                fail(f"capability row has {len(cells)} cells, expected 10: {line}")
            capability_rows.append(
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
        elif section == "global" and re.match(r"^\| G\d+ \|", line):
            cells = split_row(line)
            if len(cells) != 9:
                fail(f"global row has {len(cells)} cells, expected 9: {line}")
            global_rows.append(
                {
                    "n": cells[0],
                    "label": cells[1].strip("`"),
                    "severity": cells[2].strip("`"),
                    "family": cells[3].strip("`"),
                    "decision": cells[4].strip("`"),
                    "phase": cells[5].strip("`"),
                    "action": cells[6],
                    "risk": cells[7],
                    "deferred": cells[8],
                }
            )

    return capability_rows, global_rows


def validate_charter() -> None:
    text = read_text(CHARTER)
    required = [
        "Contract Freeze and App-Facing Hardening Release",
        "Dejar para v2.0",
        "ScientificWorkbench is not edited",
        "`v1_9`",
        "`v2_0`",
        "`no_procede`",
    ]
    for needle in required:
        if needle not in text:
            fail(f"charter missing required phrase: {needle}")


def validate_rows(capability_rows: list[dict[str, str]], global_rows: list[dict[str, str]]) -> dict[str, object]:
    if len(capability_rows) != 59:
        fail(f"expected 59 capability rows, found {len(capability_rows)}")
    if len(global_rows) < 2:
        fail("expected at least two cross-cutting rows")

    expected_labels = registry_labels()
    labels = [row["label"] for row in capability_rows]
    if labels != expected_labels:
        fail("inventory capability order does not match public registry")

    expected_numbers = [str(n) for n in range(1, 60)]
    numbers = [row["n"] for row in capability_rows]
    if numbers != expected_numbers:
        fail("inventory row numbers are not exactly 1..59")

    severities = Counter(row["severity"] for row in capability_rows)
    if severities != Counter({"P1": 25, "P2": 34}):
        fail(f"unexpected severity counts: {dict(severities)}")

    decisions = Counter(row["decision"] for row in capability_rows)
    if set(decisions) != REQUIRED_DECISIONS:
        fail(f"missing decision classes: {REQUIRED_DECISIONS - set(decisions)}")

    families = Counter(row["family"] for row in capability_rows + global_rows)
    missing_families = REQUIRED_FAMILIES - set(families)
    if missing_families:
        fail(f"missing debt families: {sorted(missing_families)}")

    for row in capability_rows + global_rows:
        for field in ("severity", "family", "decision", "phase", "action", "risk"):
            if not row[field] or row[field] in {"-", "TBD", "TODO"}:
                fail(f"row {row['n']} has empty or placeholder {field}")
        if row["severity"] not in {"P1", "P2"}:
            fail(f"row {row['n']} has unsupported severity {row['severity']}")
        if row["decision"] not in REQUIRED_DECISIONS:
            fail(f"row {row['n']} has unsupported decision {row['decision']}")
        if row["decision"] == "v2_0" and row["phase"] != "v2_0":
            fail(f"row {row['n']} is v2_0 but phase is {row['phase']}")
        if row["decision"] == "no_procede" and row["phase"] != "5-limit-only":
            fail(f"row {row['n']} is no_procede but phase is {row['phase']}")
        if row["decision"] == "v1_9" and row["phase"] == "v2_0":
            fail(f"row {row['n']} is v1_9 but phase is v2_0")
        if row["decision"] == "v1_9":
            for forbidden in FORBIDDEN_V1_9_ACTION_SCOPE:
                if forbidden in row["action"]:
                    fail(f"row {row['n']} puts v2.0 scope in a v1.9 action")

    global_families = {row["family"] for row in global_rows}
    for family in ("duplicacion", "regressions"):
        if family not in global_families:
            fail(f"missing required global family: {family}")

    return {
        "capability_rows": len(capability_rows),
        "global_rows": len(global_rows),
        "severity_counts": dict(severities),
        "decision_counts": dict(decisions),
        "family_counts": dict(families),
    }


def main() -> int:
    validate_charter()
    capability_rows, global_rows = parse_inventory()
    summary = validate_rows(capability_rows, global_rows)
    TMP.mkdir(parents=True, exist_ok=True)
    output = {
        "status": "PASS",
        "check": "v1.9 phase 0 inventory regression",
        **summary,
    }
    out_path = TMP / "phase0_inventory_regression.json"
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
