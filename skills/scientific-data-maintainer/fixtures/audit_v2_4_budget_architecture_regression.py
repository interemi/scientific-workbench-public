#!/usr/bin/env python3
"""Validate the v2.4 budget-architecture hardening contract."""

from __future__ import annotations

import json
from pathlib import Path


THIS_ROOT = Path(__file__).resolve().parents[1]
if THIS_ROOT.name == "scientific-data-maintainer":
    MAINTAINER_ROOT = THIS_ROOT
    MOTHER_ROOT = THIS_ROOT.parent / "scientific-data-analysis"
else:
    MOTHER_ROOT = THIS_ROOT
    MAINTAINER_ROOT = THIS_ROOT.parent / "scientific-data-maintainer"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_exists(path: Path, label: str, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_file", "message": f"{label}: {path}"})


def _check_contains(path: Path, needles: list[str], errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_file", "message": str(path)})
        return
    text = _read(path)
    for needle in needles:
        if needle not in text:
            errors.append(
                {
                    "kind": "missing_text",
                    "message": f"{path.relative_to(path.parents[1])} missing {needle!r}",
                }
            )


def _check_pdf(path: Path, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_pdf", "message": str(path)})
        return
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        errors.append({"kind": "invalid_pdf", "message": f"{path} does not start with %PDF"})
    if len(data) < 80_000:
        errors.append({"kind": "small_pdf", "message": f"{path} is unexpectedly small: {len(data)} bytes"})


def _check_json_stub(path: Path, errors: list[dict[str, str]]) -> None:
    if not path.exists():
        errors.append({"kind": "missing_json_stub", "message": str(path)})
        return
    payload = json.loads(_read(path))
    if not payload.get("archived"):
        errors.append({"kind": "bad_json_stub", "message": f"{path} does not mark archived=true"})
    canonical = payload.get("canonical_path", "")
    if "scientific-data-maintainer" not in canonical:
        errors.append({"kind": "bad_json_stub", "message": f"{path} does not point to maintainer"})


def main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    v24_guide_tex = MOTHER_ROOT / "references" / "guia_scientific_data_analysis_v2_4.tex"
    v24_guide_pdf = MOTHER_ROOT / "references" / "guia_scientific_data_analysis_v2_4.pdf"
    v25_guide_tex = MOTHER_ROOT / "references" / "guia_scientific_data_analysis_v2_5.tex"
    v25_guide_pdf = MOTHER_ROOT / "references" / "guia_scientific_data_analysis_v2_5.pdf"
    v25_notes = MOTHER_ROOT / "references" / "v2-5-budget-deferral-hardening.md"
    v25_compact_mode = v25_guide_tex.exists() and v25_guide_pdf.exists() and v25_notes.exists()
    active_guide_tex = v25_guide_tex if v25_compact_mode else v24_guide_tex
    active_guide_pdf = v25_guide_pdf if v25_compact_mode else v24_guide_pdf

    required_mother = [
        MOTHER_ROOT / "references" / "v2-4-budget-architecture-hardening.md",
        active_guide_tex,
        active_guide_pdf,
        MOTHER_ROOT / "scripts" / "audit_v2_4_budget_architecture_regression.py",
        MOTHER_ROOT / "scripts" / "audit_v2_4_release_candidate_regression.py",
        MOTHER_ROOT / "scripts" / "_internal" / "archived_regression_runner.py",
    ]
    if v25_compact_mode:
        required_mother.append(v25_notes)
    for path in required_mother:
        _check_exists(path, "mother required file", errors)

    _check_pdf(active_guide_pdf, errors)
    if ".codex/skills" in MOTHER_ROOT.as_posix() and (MOTHER_ROOT / "tmp").exists():
        errors.append(
            {
                "kind": "installed_tmp_payload",
                "message": "Installed mother skill must not keep tmp/ artifacts; remove them after rsync.",
            }
        )

    _check_contains(
        MOTHER_ROOT / "SKILL.md",
        [
            "v2.4 budget-architecture hardening",
            "scientific-data-maintainer",
            "wrappers or pointer stubs",
        ],
        errors,
    )
    _check_contains(
        MOTHER_ROOT / "README.txt",
        ["v2.5 deep budget-deferral hardening", "compact router"]
        if v25_compact_mode
        else ["v2.4 budget-architecture hardening", "v2.3 modular architecture"],
        errors,
    )
    _check_contains(
        MOTHER_ROOT / "RELEASE-v1.txt",
        ["Release v2.4 budget-architecture hardening", "v2.3/v2.4 modular-health route"],
        errors,
    )
    _check_contains(
        MOTHER_ROOT / "references" / "v2-4-budget-architecture-hardening.md",
        ["requiredFixes: []", "deferred_cost_tokens-budget-high", "ScientificWorkbench"],
        errors,
    )
    if v25_compact_mode:
        _check_contains(
            v25_guide_tex,
            [
                "Guia de Deep Budget-Deferral",
                "ScientificWorkbench no se modifica",
                "44913",
                "46230",
            ],
            errors,
        )
        _check_contains(
            v25_notes,
            [
                "v2.5 Deep Budget-Deferral Hardening",
                "deferred_cost_tokens-budget-high",
                "No ScientificWorkbench file is edited",
            ],
            errors,
        )
    else:
        _check_contains(
            v24_guide_tex,
            [
                "Guia de Budget Architecture",
                "Final installed evaluation",
                "requiredFixes: []",
                "ScientificWorkbench no se modifica",
            ],
            errors,
        )

    for ref_name in [
        "v1-8-app-readiness-matrix.md",
        "v1-9-debt-inventory.md",
        "real-world-capability-classification-v1-7.md",
    ]:
        _check_contains(
            MOTHER_ROOT / "references" / ref_name,
            ["scientific-data-maintainer", "Canonical"],
            errors,
        )

    _check_json_stub(MOTHER_ROOT / "references" / "v2-3-module-ownership-matrix.json", errors)

    for path in [
        MAINTAINER_ROOT / "references" / "v1-8-app-readiness-matrix.md",
        MAINTAINER_ROOT / "references" / "v1-9-debt-inventory.md",
        MAINTAINER_ROOT / "references" / "real-world-capability-classification-v1-7.md",
        MAINTAINER_ROOT / "references" / "v2-3-module-ownership-matrix.json",
        MAINTAINER_ROOT / "fixtures" / "audit_v2_3_release_candidate_regression.py",
        MAINTAINER_ROOT / "fixtures" / "audit_v2_4_budget_architecture_regression.py",
    ]:
        _check_exists(path, "maintainer canonical file", errors)

    for wrapper_name in ["external_astro_tools_local_validation.py", "coursework_requirements_gate.py"]:
        _check_contains(
            MOTHER_ROOT / "scripts" / wrapper_name,
            ["scientific-data-maintainer"],
            errors,
        )
        _check_exists(MAINTAINER_ROOT / "scripts" / wrapper_name, "maintainer script body", errors)

    status = "PASS" if not errors else "FAIL"
    payload = {
        "tool": "audit_v2_4_budget_architecture_regression",
        "status": status,
        "mother_root": str(MOTHER_ROOT),
        "maintainer_root": str(MAINTAINER_ROOT),
        "errors": errors,
        "warnings": warnings,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Fix missing v2.4 budget-architecture evidence", "priority": "high"}],
    }
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
