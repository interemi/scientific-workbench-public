#!/usr/bin/env python3
"""Validate v2.3 shared helper consistency across staged child skills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT.parent
CHILDREN = [
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
]
CANONICAL_HELPERS = [
    "public_contract.py",
    "provenance_utils.py",
    "runtime_common.py",
    "tabular_io.py",
    "child_skill_dispatch.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    errors: list[str] = []
    helper_hashes: dict[str, dict[str, str]] = {}
    mother_internal = ROOT / "scripts" / "_internal"
    for helper in CANONICAL_HELPERS:
        mother_helper = mother_internal / helper
        if not mother_helper.exists():
            errors.append(f"missing mother helper: {helper}")
            continue
        expected = sha256(mother_helper)
        helper_hashes[helper] = {"scientific-data-analysis": expected}
        for child_name in CHILDREN:
            child_helper = WORK_ROOT / child_name / "scripts" / "_internal" / helper
            if not child_helper.exists():
                errors.append(f"missing {child_name} helper: {helper}")
                continue
            actual = sha256(child_helper)
            helper_hashes[helper][child_name] = actual
            if actual != expected:
                errors.append(f"{child_name}/{helper} diverges from mother helper")

    dispatch_source = (mother_internal / "child_skill_dispatch.py").read_text(encoding="utf-8")
    if "sys.modules[module_name] = module" not in dispatch_source:
        errors.append("child_skill_dispatch.py does not register modules before exec_module")

    astro_scripts = WORK_ROOT / "scientific-data-astro" / "scripts"
    for shim, child_name in {
        "latex_workbench.py": "scientific-data-documents",
        "notebook_workbench.py": "scientific-data-notebooks",
    }.items():
        shim_path = astro_scripts / shim
        if not shim_path.exists():
            errors.append(f"missing astro dependency shim: {shim}")
            continue
        source = shim_path.read_text(encoding="utf-8")
        if child_name not in source:
            errors.append(f"{shim} does not point to {child_name}")
        if "child_skill_dispatch" in source:
            errors.append(f"{shim} should be a dependency shim, not a public wrapper")

    reference = ROOT / "references" / "v2-3-shared-contract-and-helpers.md"
    if not reference.exists():
        errors.append("missing shared contract reference")

    payload = {
        "tool": "audit_v2_3_shared_helpers_regression",
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": [],
        "helper_hashes": helper_hashes,
        "children": CHILDREN,
        "reference": str(reference.relative_to(ROOT)),
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Resync divergent helpers", "kind": "maintainer_action"}],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
