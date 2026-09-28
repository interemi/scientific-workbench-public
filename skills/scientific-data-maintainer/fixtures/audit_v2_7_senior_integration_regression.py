#!/usr/bin/env python3
"""Validate v2.7 senior integration hardening for the skill family."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any


SKILLS = [
    "scientific-data-analysis",
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
]

REQUIRED_DOC_TERMS = [
    "canonical_registry",
    "multi-root",
    "smoke/regression coverage",
    "ScientificWorkbench",
]


def _skill_base() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if all((parent / skill).exists() for skill in SKILLS):
            return parent
    raise RuntimeError("could not locate skill family base")


def _app_root(skill_base: Path) -> Path | None:
    candidates = [
        skill_base.parent / "ScientificWorkbench",
        Path.home() / "Documents" / "Skills para Master" / "ScientificWorkbench",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_simple_yaml_key(path: Path, key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def _resolve_registry(stub: Path) -> tuple[Path, list[str]]:
    visited: list[str] = []
    current = stub
    for _ in range(6):
        visited.append(str(current))
        text = current.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\s*entries\s*:", text, re.MULTILINE):
            return current, visited
        target = _read_simple_yaml_key(current, "canonical_registry")
        if not target:
            raise RuntimeError(f"{current} has neither entries nor canonical_registry")
        next_path = (current.parent / target).resolve()
        if not next_path.exists():
            raise FileNotFoundError(f"canonical registry target missing: {next_path}")
        current = next_path
    raise RuntimeError(f"canonical registry chain too deep: {stub}")


def _entry_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"^\s*-\s+id\s*:", text, re.MULTILINE))


def _coverage_ok(path: Path) -> tuple[bool, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid coverage json: {type(exc).__name__}: {exc}"
    marker = payload.get("scientific_data_analysis", {})
    if marker.get("coverage_kind") != "smoke_observed_lines":
        return False, "coverage_kind is not smoke_observed_lines"
    if marker.get("not_exhaustive_project_coverage") is not True:
        return False, "coverage artifact must declare not_exhaustive_project_coverage=true"
    return True, None


def _broken_reference_symlinks(root: Path) -> list[str]:
    refs = root / "references"
    if not refs.exists():
        return []
    broken: list[str] = []
    for item in refs.iterdir():
        if item.is_symlink() and not item.exists():
            broken.append(str(item))
    return broken


def _doc_terms(path: Path) -> tuple[bool, list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    missing = [term for term in REQUIRED_DOC_TERMS if term not in text]
    return not missing, missing


def _app_single_root_warning(skill_base: Path) -> dict[str, Any]:
    app = _app_root(skill_base)
    if app is None:
        return {"status": "WARNING", "message": "ScientificWorkbench app path not found; app sync plan still applies."}
    default_paths = app / "Sources/ScientificWorkbench/Support/DefaultPaths.swift"
    if not default_paths.exists():
        return {"status": "WARNING", "message": "ScientificWorkbench app path not found; app sync plan still applies."}
    text = default_paths.read_text(encoding="utf-8", errors="ignore")
    single_root = "static var skillRoot" in text and "scientific-data-analysis" in text
    return {
        "status": "WARNING" if single_root else "PASS",
        "single_skill_root_assumption_detected": single_root,
        "message": (
            "App still appears to use one skillRoot; close this during app sync."
            if single_root
            else "No obvious single skillRoot assumption detected."
        ),
        "path": str(default_paths),
    }


def main() -> int:
    skill_base = _skill_base()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []

    for skill in SKILLS:
        root = skill_base / skill
        record: dict[str, Any] = {"skill": skill, "root": str(root), "exists": root.exists()}
        if not root.exists():
            errors.append({"skill": skill, "error": "skill root missing"})
            roots.append(record)
            continue

        for rel in ["SKILL.md", "public_surface_registry.yaml", "coverage-summary.json"]:
            if not (root / rel).exists():
                errors.append({"skill": skill, "error": f"{rel} missing"})

        registry_stub = root / "public_surface_registry.yaml"
        if registry_stub.exists():
            try:
                canonical, chain = _resolve_registry(registry_stub)
                count = _entry_count(canonical)
                record["canonical_registry"] = str(canonical)
                record["registry_chain"] = chain
                record["registry_entry_count"] = count
                if count < 61:
                    errors.append({"skill": skill, "error": f"registry has only {count} entries"})
            except Exception as exc:
                errors.append({"skill": skill, "error": f"registry resolution failed: {type(exc).__name__}: {exc}"})

        coverage = root / "coverage-summary.json"
        if coverage.exists():
            ok, detail = _coverage_ok(coverage)
            record["coverage_summary"] = str(coverage)
            record["coverage_smoke_regression_only"] = ok
            if not ok:
                errors.append({"skill": skill, "error": detail or "coverage summary invalid"})

        broken = _broken_reference_symlinks(root)
        record["broken_reference_symlinks"] = broken
        if broken:
            errors.append({"skill": skill, "error": f"broken reference symlinks: {len(broken)}"})

        roots.append(record)

    mother = skill_base / "scientific-data-analysis"
    required_docs = [
        mother / "references/v2-7-senior-integration-hardening.md",
        mother / "references/v2-7-scientificworkbench-sync-plan.md",
    ]
    for doc in required_docs:
        if not doc.exists():
            errors.append({"skill": "scientific-data-analysis", "error": f"missing v2.7 doc: {doc.name}"})
            continue
        ok, missing = _doc_terms(doc)
        if not ok:
            errors.append({"skill": "scientific-data-analysis", "error": f"{doc.name} missing terms: {', '.join(missing)}"})

    warnings.append(_app_single_root_warning(skill_base))

    status = "PASS" if not errors else "FAIL"
    payload = {
        "tool": "audit_v2_7_senior_integration_regression",
        "status": status,
        "roots": roots,
        "warnings": warnings,
        "errors": errors,
        "original_modified": False,
        "next_actions": [
            "Use v2-7-scientificworkbench-sync-plan.md before editing ScientificWorkbench.",
            "Keep coverage language as smoke/regression coverage, not exhaustive coverage.",
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
