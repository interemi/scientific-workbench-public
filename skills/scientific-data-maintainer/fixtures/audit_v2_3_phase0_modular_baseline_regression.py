#!/usr/bin/env python3
"""Validate the v2.3 modular architecture charter baseline."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term not in text]


def main() -> int:
    charter = ROOT / "references" / "v2-3-modular-architecture-charter.md"
    registry_path = ROOT / "public_surface_registry.yaml"
    skill_path = ROOT / "SKILL.md"
    required_paths = [charter, registry_path, skill_path]
    missing_paths = [str(path.relative_to(ROOT)) for path in required_paths if not path.exists()]

    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    if missing_paths:
        for path in missing_paths:
            errors.append({"kind": "missing_required_file", "message": f"Missing {path}"})
    else:
        charter_text = _read(charter)
        required_terms = [
            "v2.3",
            "modular architecture",
            "scientific-data-analysis",
            "scientific-data-astro",
            "scientific-data-documents",
            "scientific-data-notebooks",
            "scientific-data-maintainer",
            "wrappers",
            "ScientificWorkbench",
            "plugin-eval",
            "Closure Criteria",
        ]
        missing_terms = _contains_all(charter_text, required_terms)
        for term in missing_terms:
            errors.append({"kind": "missing_charter_term", "message": f"Charter missing term: {term}"})

        if "not called v3.0" not in charter_text and "not called v3" not in charter_text:
            errors.append(
                {
                    "kind": "missing_version_decision",
                    "message": "Charter must explain why this is v2.3 rather than v3.0.",
                }
            )

        payload = yaml.safe_load(_read(registry_path)) or {}
        entries = payload.get("entries", [])
        visible_blocks = sorted({entry.get("visible_block") for entry in entries})
        expected_blocks = [
            "astronomy observational",
            "core / routing",
            "documents + reporting",
            "notebooks + cross-domain",
        ]
        if len(entries) != 61:
            errors.append(
                {
                    "kind": "registry_count_changed",
                    "message": f"Expected 61 public registry entries, found {len(entries)}.",
                }
            )
        if visible_blocks != expected_blocks:
            errors.append(
                {
                    "kind": "visible_blocks_changed",
                    "message": f"Unexpected visible blocks: {visible_blocks}",
                }
            )

        skill_text = _read(skill_path)
        if "v2.2 evaluation-hardening" not in skill_text:
            warnings.append("SKILL.md no longer advertises v2.2 as current; this may be expected after a later v2.3 docs phase.")

    status = "PASS" if not errors else "FAIL"
    result = {
        "tool": "audit_v2_3_phase0_modular_baseline_regression",
        "status": status,
        "phase": "v2.3 phase 0",
        "summary": "Validate v2.3 modular architecture charter and baseline registry shape.",
        "errors": errors,
        "warnings": warnings,
        "checked_files": [str(path.relative_to(ROOT)) for path in required_paths],
        "expected_registry_entries": 61,
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Fix charter or registry baseline drift", "priority": "high"}],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
