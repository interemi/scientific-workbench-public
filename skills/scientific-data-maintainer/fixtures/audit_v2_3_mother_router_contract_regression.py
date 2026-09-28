#!/usr/bin/env python3
"""Validate the v2.3 mother-router contract and compact module map."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "references" / "v2-3-mother-router-contract.md"
MODULE_MAP = ROOT / "references" / "v2-3-mother-router-module-map.json"
REGISTRY = ROOT / "public_surface_registry.yaml"
ROUTER = ROOT / "scripts" / "scientific_workflow_router.py"
if ".codex/skills" in ROOT.as_posix():
    TMP = Path.home() / ".codex" / "tmp" / "v2_3_phase3_mother_router" / "router_cases"
else:
    TMP = ROOT.parent.parent / "tmp" / "v2_3_phase3_mother_router" / "router_cases"
ALLOWED_MODES = {"direct", "delegated", "multi_module_plan", "blocked_optional", "maintainer_only"}
ALLOWED_CHILDREN = {
    "scientific-data-analysis",
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
}


def _write_fixtures() -> dict[str, Path]:
    TMP.mkdir(parents=True, exist_ok=True)
    table = TMP / "professional_table.csv"
    table.write_text("date,value,segment\n2026-01-01,10,A\n2026-01-02,12,B\n", encoding="utf-8")

    mixed = TMP / "mixed_package"
    mixed.mkdir(exist_ok=True)
    (mixed / "summary.md").write_text("# Handoff\nTexto administrativo anonimo.\n", encoding="utf-8")
    (mixed / "table.csv").write_text("id,amount\n1,100\n2,150\n", encoding="utf-8")
    with zipfile.ZipFile(mixed / "archive.zip", "w") as archive:
        archive.writestr("inside.txt", "contenido anonimo")

    fits = TMP / "image.fits"
    fits.write_bytes(b"SIMPLE  =                    T" + b" " * 2880)

    notebook = TMP / "legacy.ipynb"
    notebook.write_text(
        json.dumps({"nbformat": 4, "nbformat_minor": 5, "cells": [], "metadata": {}}),
        encoding="utf-8",
    )

    empty = TMP / "empty"
    empty.mkdir(exist_ok=True)

    return {
        "table": table,
        "mixed": mixed,
        "fits": fits,
        "notebook": notebook,
        "empty": empty,
        "missing": TMP / "missing.csv",
    }


def _run_router(mode: str, path: Path, *extra: str) -> dict:
    command = [sys.executable, str(ROUTER), mode, str(path), *extra]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode not in (0, 2):
        raise AssertionError(f"router exited {completed.returncode}: {completed.stderr or completed.stdout}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"router emitted non-json output: {completed.stdout[:500]}") from exc


def _find(items: list[dict], capability_id: str) -> dict | None:
    for item in items:
        if item.get("capability_id") == capability_id:
            return item
    return None


def _registry_ids() -> list[str]:
    ids: list[str] = []
    pattern = re.compile(r"^\s*-\s+id:\s*(\S+)\s*$")
    text = REGISTRY.read_text(encoding="utf-8")
    match = re.search(r"^canonical_registry:\s*(\S+)\s*$", text, re.MULTILINE)
    if match:
        target = REGISTRY.parent / match.group(1)
        text = target.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            ids.append(match.group(1))
    return ids


def _load_module_map() -> dict:
    payload = json.loads(MODULE_MAP.read_text(encoding="utf-8"))
    if payload.get("archived") and payload.get("canonical_fixture"):
        archived = ROOT / str(payload["canonical_fixture"])
        if archived.exists():
            return json.loads(archived.read_text(encoding="utf-8"))
    return payload


def main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    for path in (CONTRACT, MODULE_MAP, REGISTRY, ROUTER):
        if not path.exists():
            errors.append({"kind": "missing_required_file", "message": str(path.relative_to(ROOT))})

    registry_ids: list[str] = []
    module_payload: dict = {}
    if not errors:
        contract_text = CONTRACT.read_text(encoding="utf-8")
        for term in ("owner_module", "delegation_mode", "wrapper_status", "blocked_optional", "maintainer_only"):
            if term not in contract_text:
                errors.append({"kind": "contract_missing_term", "message": term})

        registry_ids = _registry_ids()
        module_payload = _load_module_map()
        rows = module_payload.get("capabilities", [])
        if module_payload.get("public_capability_count") != 61:
            errors.append({"kind": "module_map_count", "message": "Expected public_capability_count=61."})
        if rows:
            ids = [row.get("capability_id") for row in rows]
            if len(rows) != 61:
                errors.append({"kind": "module_map_count", "message": f"Expected 61 rows, found {len(rows)}."})
            if ids != registry_ids:
                errors.append({"kind": "module_map_registry_order", "message": "Module map must follow registry order."})
            for index, row in enumerate(rows):
                for field in (
                    "capability_id",
                    "label",
                    "script_path_historico",
                    "owner_module",
                    "child_skill_path",
                    "delegation_mode",
                    "wrapper_status",
                ):
                    if not row.get(field):
                        errors.append({"kind": "module_map_missing_field", "message": f"Row {index} missing {field}."})
                if row.get("delegation_mode") not in ALLOWED_MODES:
                    errors.append({"kind": "invalid_delegation_mode", "message": f"Row {index}: {row.get('delegation_mode')}"})
                if row.get("child_skill_path") not in ALLOWED_CHILDREN:
                    errors.append({"kind": "invalid_child_skill", "message": f"Row {index}: {row.get('child_skill_path')}"})
        elif not module_payload.get("archived"):
            errors.append({"kind": "module_map_missing_rows", "message": "Compact stubs must declare archived=true."})

    case_results: list[dict[str, str]] = []
    if not errors:
        fixtures = _write_fixtures()
        cases = [
            ("table", "inspect", fixtures["table"], "profile_table", "notebooks", "delegated", []),
            ("mixed_folder", "plan", fixtures["mixed"], "cross_domain_data_workbench", "notebooks", "delegated", []),
            ("fits", "inspect", fixtures["fits"], "inspect_fits", "astro", "delegated", []),
            (
                "notebook",
                "inspect",
                fixtures["notebook"],
                "coursework_notebook_fidelity_check",
                "notebooks",
                "delegated",
                [],
            ),
            (
                "optional_stilts",
                "inspect",
                fixtures["table"],
                "stilts_workbench",
                "astro",
                "blocked_optional",
                ["--task", "usar STILTS para VOTable"],
            ),
        ]
        for name, mode, path, expected_id, expected_owner, expected_mode, extra in cases:
            payload = _run_router(mode, path, *extra)
            item = _find(payload.get("recommended_capabilities", []), expected_id)
            if not item:
                errors.append({"kind": "missing_recommendation", "message": f"{name}: {expected_id}"})
                continue
            if item.get("owner_module") != expected_owner or item.get("delegation_mode") != expected_mode:
                errors.append(
                    {
                        "kind": "bad_module_metadata",
                        "message": f"{name}: {expected_id} -> {item.get('owner_module')}/{item.get('delegation_mode')}",
                    }
                )
            if item.get("wrapper_status") in (None, "module_map_missing"):
                errors.append({"kind": "missing_wrapper_status", "message": f"{name}: {expected_id}"})
            case_results.append(
                {
                    "case": name,
                    "status": payload.get("status", "unknown"),
                    "capability_id": expected_id,
                    "owner_module": item.get("owner_module", "missing"),
                    "delegation_mode": item.get("delegation_mode", "missing"),
                }
            )

        missing_payload = _run_router("inspect", fixtures["missing"])
        if missing_payload.get("status") != "blocked":
            errors.append({"kind": "missing_path_not_blocked", "message": str(missing_payload.get("status"))})
        empty_payload = _run_router("inspect", fixtures["empty"])
        if empty_payload.get("status") != "blocked":
            errors.append({"kind": "empty_folder_not_blocked", "message": str(empty_payload.get("status"))})

        maintainer_payload = _run_router(
            "explain",
            fixtures["table"],
            "--capability",
            "portable_smoke_test.py",
        )
        explanation = maintainer_payload.get("results", {}).get("capability_explanation") or maintainer_payload.get(
            "capability_explanation", {}
        )
        if explanation.get("delegation_mode") != "maintainer_only":
            errors.append(
                {
                    "kind": "maintainer_not_relegated",
                    "message": f"portable_smoke_test.py -> {explanation.get('delegation_mode')}",
                }
            )

    status = "PASS" if not errors else "FAIL"
    result = {
        "tool": "audit_v2_3_mother_router_contract_regression",
        "status": status,
        "contract": str(CONTRACT.relative_to(ROOT)),
        "module_map": str(MODULE_MAP.relative_to(ROOT)),
        "public_capability_count": module_payload.get("public_capability_count"),
        "routing_states": sorted((module_payload.get("routing_states") or {}).keys()),
        "module_map_compact": not bool(module_payload.get("capabilities")),
        "case_results": case_results,
        "errors": errors,
        "warnings": warnings,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Fix v2.3 router module metadata or module map", "priority": "high"}],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
