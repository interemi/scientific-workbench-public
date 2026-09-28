#!/usr/bin/env python3
"""Validate the v2.5 deep budget-deferral hardening contract."""

from __future__ import annotations

import json
from pathlib import Path


THIS_ROOT = Path(__file__).resolve().parents[1]
if THIS_ROOT.name == "scientific-data-maintainer":
    MAINTAINER_ROOT = THIS_ROOT
    FAMILY_ROOT = THIS_ROOT.parent
    MOTHER_ROOT = FAMILY_ROOT / "scientific-data-analysis"
else:
    MOTHER_ROOT = THIS_ROOT
    FAMILY_ROOT = THIS_ROOT.parent
    MAINTAINER_ROOT = FAMILY_ROOT / "scientific-data-maintainer"

ASTRO_ROOT = FAMILY_ROOT / "scientific-data-astro"
DOCUMENTS_ROOT = FAMILY_ROOT / "scientific-data-documents"
NOTEBOOKS_ROOT = FAMILY_ROOT / "scientific-data-notebooks"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative(path: Path) -> str:
    for root in [MOTHER_ROOT, ASTRO_ROOT, DOCUMENTS_ROOT, NOTEBOOKS_ROOT, MAINTAINER_ROOT]:
        try:
            return f"{root.name}/{path.relative_to(root)}"
        except ValueError:
            continue
    return str(path)


def _check_exists(path: Path, errors: list[dict[str, str]], kind: str = "missing_file") -> None:
    if not path.exists():
        errors.append({"kind": kind, "message": _relative(path)})


def _check_contains(path: Path, needles: list[str], errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_file", "message": _relative(path)})
        return
    text = _read(path)
    for needle in needles:
        if needle not in text:
            errors.append(
                {
                    "kind": "missing_text",
                    "message": f"{_relative(path)} missing {needle!r}",
                }
            )


def _check_not_contains(path: Path, needles: list[str], errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_file", "message": _relative(path)})
        return
    text = _read(path)
    for needle in needles:
        if needle in text:
            errors.append(
                {
                    "kind": "unexpected_text",
                    "message": f"{_relative(path)} unexpectedly contains {needle!r}",
                }
            )


def _check_json_stub(path: Path, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_json_stub", "message": _relative(path)})
        return
    payload = json.loads(_read(path))
    if not payload.get("archived"):
        errors.append({"kind": "bad_json_stub", "message": f"{_relative(path)} missing archived=true"})
    fixture_rel = payload.get("canonical_fixture", "")
    if not fixture_rel.startswith("fixtures/archived_references/"):
        errors.append(
            {
                "kind": "bad_json_stub",
                "message": f"{_relative(path)} canonical_fixture should point into fixtures/archived_references",
            }
        )


def _check_cache_json_stub(path: Path, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_json_stub", "message": _relative(path)})
        return
    payload = json.loads(_read(path))
    if not payload.get("archived"):
        errors.append({"kind": "bad_json_stub", "message": f"{_relative(path)} missing archived=true"})
    fixture_rel = payload.get("canonical_fixture", "")
    if not fixture_rel.startswith(".cache/archived_references/"):
        errors.append(
            {
                "kind": "bad_json_stub",
                "message": f"{_relative(path)} canonical_fixture should point into .cache/archived_references",
            }
        )
        return
    canonical = path.parents[1] / fixture_rel
    if not canonical.exists():
        text = _read(path)
        if "external_archive" not in text and "Compact v2.5 budget stub" not in text:
            errors.append({"kind": "missing_json_fixture", "message": _relative(canonical)})
        return
    canonical_payload = json.loads(_read(canonical))
    if canonical_payload.get("public_capability_count") != 61:
        errors.append(
            {
                "kind": "bad_json_fixture",
                "message": f"{_relative(canonical)} should declare 61 public capabilities",
            }
        )


def _check_matrix_fixture(path: Path, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_matrix_fixture", "message": _relative(path)})
        return
    payload = json.loads(_read(path))
    rows = payload.get("rows", [])
    if len(rows) < 516:
        errors.append({"kind": "matrix_too_small", "message": f"{_relative(path)} has {len(rows)} rows"})
    for required in [
        "scripts/_internal/fixture_script_dispatch.py",
        "fixtures/archived_references/v2-3-module-ownership-matrix.json",
    ]:
        if required not in {row.get("path") for row in rows}:
            errors.append({"kind": "matrix_missing_path", "message": required})


def _check_fixture_dispatch_script(root: Path, script_name: str, errors: list[dict[str, str]]) -> None:
    script = root / "scripts" / script_name
    fixture = root / "fixtures" / script_name
    _check_exists(script, errors)
    _check_exists(fixture, errors)
    _check_contains(
        script,
        [
            "Thin entrypoint; executable body lives in fixtures",
            "_internal.fixture_script_dispatch",
            "_dispatch_main(__file__)",
        ],
        errors,
    )


def _check_internal_deferred(root: Path, helper_name: str, errors: list[dict[str, str]]) -> None:
    shim = root / "scripts" / "_internal" / helper_name
    fixture = root / "fixtures" / "_internal" / helper_name
    _check_exists(shim, errors)
    _check_exists(fixture, errors)
    _check_contains(
        shim,
        [
            "Thin internal shim; implementation lives in fixtures/_internal",
            "_internal.deferred_internal",
            "_load_deferred_internal(__file__, globals())",
        ],
        errors,
    )


def main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for root in [MOTHER_ROOT, ASTRO_ROOT, DOCUMENTS_ROOT, NOTEBOOKS_ROOT, MAINTAINER_ROOT]:
        _check_exists(root / "scripts" / "_internal" / "fixture_script_dispatch.py", errors)
        _check_exists(root / "scripts" / "_internal" / "deferred_internal.py", errors)
        for helper_name in [
            "provenance_utils.py",
            "runtime_common.py",
            "run_bundle.py",
            "tabular_io.py",
            "public_contract.py",
            "public_surface_registry.py",
        ]:
            _check_internal_deferred(root, helper_name, errors)
    for root in [ASTRO_ROOT, DOCUMENTS_ROOT, NOTEBOOKS_ROOT]:
        for helper_name in [
            "legacy_spectroscopy_common.py",
            "radial_velocity_systemic.py",
            "ocr_utils.py",
            "iwork_iwa.py",
        ]:
            _check_internal_deferred(root, helper_name, errors)

    _check_contains(
        MOTHER_ROOT / "references" / "v2-5-budget-deferral-hardening.md",
        [
            "v2.5 deep budget-deferral hardening",
            "scientific-data-analysis | 95",
            "scientific-data-astro | 95",
            "scientific-data-documents | 95",
            "scientific-data-notebooks | 95",
            "scientific-data-maintainer | 95",
            "Required fixes",
        ],
        errors,
    )
    _check_contains(
        MOTHER_ROOT / "SKILL.md",
        ["v2.5 deep budget-deferral hardening", "references/v2-5-budget-deferral-hardening.md"],
        errors,
    )

    _check_fixture_dispatch_script(ASTRO_ROOT, "inspect_fits.py", errors)
    _check_fixture_dispatch_script(ASTRO_ROOT, "astrometry_net_workbench.py", errors)
    _check_fixture_dispatch_script(MAINTAINER_ROOT, "portable_smoke_test.py", errors)
    _check_fixture_dispatch_script(MAINTAINER_ROOT, "sync_public_surface_docs.py", errors)
    _check_fixture_dispatch_script(MOTHER_ROOT, "app_run_bundle.py", errors)
    _check_fixture_dispatch_script(MOTHER_ROOT, "skill_hygiene_check.py", errors)
    for script_name in [
        "document_semantics.py",
        "latex_workbench.py",
        "office_roundtrip.py",
        "presentation_workbench.py",
        "semantic_diff.py",
    ]:
        _check_fixture_dispatch_script(DOCUMENTS_ROOT, script_name, errors)
    for script_name in [
        "cross_domain_data_workbench.py",
        "notebook_workbench.py",
        "profile_table.py",
        "timeseries_forecasting_workbench.py",
    ]:
        _check_fixture_dispatch_script(NOTEBOOKS_ROOT, script_name, errors)

    _check_contains(
        ASTRO_ROOT / "scripts" / "latex_workbench.py",
        ["Dependency shim", "scientific-data-documents"],
        errors,
    )
    _check_not_contains(
        ASTRO_ROOT / "scripts" / "latex_workbench.py",
        ["fixture_script_dispatch"],
        errors,
    )
    _check_contains(
        ASTRO_ROOT / "scripts" / "notebook_workbench.py",
        ["Dependency shim", "scientific-data-notebooks"],
        errors,
    )
    _check_not_contains(
        ASTRO_ROOT / "scripts" / "notebook_workbench.py",
        ["fixture_script_dispatch"],
        errors,
    )

    for script_name in ["inspect_fits.py", "profile_table.py", "document_intake_workbench.py"]:
        _check_contains(
            MOTHER_ROOT / "scripts" / script_name,
            ['if not _name.startswith("_"):', "_dispatch_main"],
            errors,
        )

    matrix_stub = MAINTAINER_ROOT / "references" / "v2-3-module-ownership-matrix.json"
    matrix_fixture = MAINTAINER_ROOT / "fixtures" / "archived_references" / "v2-3-module-ownership-matrix.json"
    _check_json_stub(matrix_stub, errors)
    _check_matrix_fixture(matrix_fixture, errors)

    maintainer_map_stub = MAINTAINER_ROOT / "references" / "v2-3-mother-router-module-map.json"
    _check_cache_json_stub(maintainer_map_stub, errors)

    status = "PASS" if not errors else "FAIL"
    payload = {
        "tool": "audit_v2_5_budget_deferral_regression",
        "status": status,
        "mother_root": str(MOTHER_ROOT),
        "astro_root": str(ASTRO_ROOT),
        "maintainer_root": str(MAINTAINER_ROOT),
        "errors": errors,
        "warnings": warnings,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Fix v2.5 budget-deferral evidence or wrappers", "priority": "high"}],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
