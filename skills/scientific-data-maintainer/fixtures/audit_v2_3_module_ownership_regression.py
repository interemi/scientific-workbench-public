#!/usr/bin/env python3
"""Validate the v2.3 module ownership matrix."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised on minimal Python installs.
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
LOCAL_MATRIX_PATH = ROOT / "references" / "v2-3-module-ownership-matrix.json"
CHILD_MATRIX_PATH = ROOT.parent / "scientific-data-maintainer" / "references" / "v2-3-module-ownership-matrix.json"
MATRIX_PATH = CHILD_MATRIX_PATH if CHILD_MATRIX_PATH.exists() else LOCAL_MATRIX_PATH
REGISTRY_PATH = ROOT / "public_surface_registry.yaml"
ALLOWED_OWNERS = {
    "mother",
    "astro",
    "documents",
    "notebooks",
    "maintainer",
    "shared",
    "archive_candidate",
    "do_not_move",
}
REQUIRED_FIELDS = {
    "path",
    "type",
    "owner_module",
    "public_id",
    "visible_block",
    "exposure",
    "reason",
    "migration_risk",
    "wrapper_required",
    "gates_required",
}
GENERATED_FILE_SUFFIXES = (
    ".aux",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".synctex.gz",
    ".toc",
)


def _load_registry_entries(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        payload = yaml.safe_load(text) or {}
        return payload.get("entries", [])

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- id:"):
            if current:
                entries.append(current)
            current = {"id": stripped.split(":", 1)[1].strip()}
        elif current is not None and stripped.startswith("script:"):
            current["script"] = stripped.split(":", 1)[1].strip()
    if current:
        entries.append(current)
    return entries


def _skill_files() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and ".cache" not in path.relative_to(ROOT).parts
        and "tmp" not in path.relative_to(ROOT).parts
        and not path.name.endswith(".pyc")
        and not path.name.endswith(GENERATED_FILE_SUFFIXES)
        and path.name != ".DS_Store"
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_matrix(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture_rel = payload.get("canonical_fixture") if isinstance(payload, dict) else None
    if payload.get("archived") and fixture_rel:
        fixture_path = ROOT / fixture_rel
        if not fixture_path.exists() and ROOT.name != "scientific-data-maintainer":
            fixture_path = ROOT.parent / "scientific-data-maintainer" / fixture_rel
        return json.loads(fixture_path.read_text(encoding="utf-8"))
    return payload


def main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    if not MATRIX_PATH.exists():
        errors.append({"kind": "missing_matrix", "message": str(MATRIX_PATH.relative_to(ROOT))})
        rows: list[dict] = []
        matrix = {}
    else:
        matrix = _load_matrix(MATRIX_PATH)
        rows = matrix.get("rows", [])

    registry_entries = _load_registry_entries(REGISTRY_PATH)
    registry_ids = [entry["id"] for entry in registry_entries]
    public_rows = [row for row in rows if row.get("type") == "public_capability"]
    public_ids = [row.get("public_id") for row in public_rows]

    if len(public_rows) != 61:
        errors.append(
            {
                "kind": "public_capability_count",
                "message": f"Expected 61 public capability rows, found {len(public_rows)}.",
            }
        )
    if public_ids != registry_ids:
        errors.append({"kind": "registry_order_mismatch", "message": "Public rows must follow registry order exactly."})

    for index, row in enumerate(rows):
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            errors.append({"kind": "missing_fields", "message": f"Row {index} missing {missing}"})
            continue
        owner = row.get("owner_module")
        if owner not in ALLOWED_OWNERS:
            errors.append({"kind": "invalid_owner", "message": f"Row {index} has invalid owner {owner!r}."})
        if not row.get("path"):
            errors.append({"kind": "empty_path", "message": f"Row {index} has empty path."})
        if row.get("type") == "public_capability" and not row.get("public_id"):
            errors.append({"kind": "missing_public_id", "message": f"Public row {index} has no public_id."})
        if not row.get("reason"):
            errors.append({"kind": "missing_reason", "message": f"Row {index} has no reason."})
        if not isinstance(row.get("gates_required"), list) or not row.get("gates_required"):
            errors.append({"kind": "missing_gates", "message": f"Row {index} has no gates_required list."})

    public_script_paths = {entry["script"] for entry in registry_entries}
    matrix_public_script_paths = {row.get("path") for row in public_rows}
    missing_public_scripts = sorted(public_script_paths - matrix_public_script_paths)
    if missing_public_scripts:
        errors.append(
            {
                "kind": "public_script_without_decision",
                "message": f"Missing public script decisions: {missing_public_scripts}",
            }
        )

    matrix_paths = {row.get("path") for row in rows if row.get("type") != "public_capability"}
    missing_files = sorted(_skill_files() - matrix_paths - public_script_paths)
    if missing_files:
        sample = ", ".join(missing_files[:12])
        errors.append({"kind": "file_inventory_gap", "message": f"Matrix misses {len(missing_files)} files: {sample}"})

    owner_counts = matrix.get("counts_by_owner", {})
    for owner in ["mother", "astro", "documents", "notebooks", "maintainer"]:
        if owner_counts.get(owner, 0) <= 0:
            errors.append({"kind": "owner_empty", "message": f"Owner {owner} has no rows."})

    if matrix.get("wrapper_required_count", 0) <= 0:
        warnings.append("No wrappers required according to matrix; unexpected for a modular migration.")

    status = "PASS" if not errors else "FAIL"
    result = {
        "tool": "audit_v2_3_module_ownership_regression",
        "status": status,
        "matrix": _display_path(MATRIX_PATH),
        "row_count": len(rows),
        "public_capability_count": len(public_rows),
        "owner_counts": owner_counts,
        "wrapper_required_count": matrix.get("wrapper_required_count"),
        "errors": errors,
        "warnings": warnings,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Regenerate or fix v2.3 ownership matrix", "priority": "high"}],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
