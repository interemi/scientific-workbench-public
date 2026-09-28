#!/usr/bin/env python3
"""Verify that the public workflow requirements match the canonical registry."""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_HELPER = (
    ROOT
    / "skills/scientific-data-maintainer/fixtures/_internal/public_surface_registry.py"
)
MOTHER_REGISTRY = ROOT / "skills/scientific-data-analysis/public_surface_registry.yaml"
REQUIREMENTS_DOC = ROOT / "docs/WORKFLOW_REQUIREMENTS.md"
CAPABILITY_MATRIX_DOC = ROOT / "docs/CAPABILITY_SETUP_MATRIX.md"
CAPABILITY_EVIDENCE_DOC = ROOT / "docs/CAPABILITY_VALIDATION_EVIDENCE.md"
APP_CAPABILITY_MODEL = ROOT / "Sources/ScientificWorkbench/Models/CapabilityEntry.swift"

EXPECTED_BLOCKS = {
    "core / routing": 5,
    "astronomy observational": 24,
    "documents + reporting": 14,
    "notebooks + cross-domain": 12,
}
EXPECTED_SUPPORT = {"stable": 36, "narrow": 11, "optional": 6, "platform_bound": 2}
EXPECTED_PLATFORMS = {"portable": 44, "macos": 6, "datanalysis": 5}
EXPECTED_DATANALYSIS = {True: 14, False: 41}
EXPECTED_SMOKE = {"core": 16, "full": 10, "none": 29}
ROLE_BY_BLOCK = {
    "core / routing": "scientific-data-analysis",
    "astronomy observational": "scientific-data-astro",
    "documents + reporting": "scientific-data-documents",
    "notebooks + cross-domain": "scientific-data-notebooks",
}
ROLE_EXCEPTIONS = {
    "external_astro_tools_preflight": "scientific-data-astro",
    "spectra_ascii_coursework_workbench": "scientific-data-astro",
    "catalog_workbench.crossmatch-sky": "scientific-data-analysis",
}
APP_READINESS_SETS = {
    "blockedOptionalCapabilityIDs": "blocked_optional",
    "cliOnlyCapabilityIDs": "cli_only",
    "notApplicableCapabilityIDs": "not_applicable_to_app",
    "appReadyPartialCapabilityIDs": "app_ready_partial",
}


def fail(message: str) -> None:
    raise SystemExit(f"workflow requirements check failed: {message}")


def load_registry() -> list[dict]:
    if not REGISTRY_HELPER.is_file():
        fail(f"missing registry helper: {REGISTRY_HELPER.relative_to(ROOT)}")
    spec = importlib.util.spec_from_file_location("scientific_workbench_registry", REGISTRY_HELPER)
    if spec is None or spec.loader is None:
        fail("could not load the registry helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_public_surface_registry(MOTHER_REGISTRY, family_root=ROOT / "skills")


def require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        fail(f"{label} is {actual!r}; expected {expected!r}")


def main() -> int:
    entries = load_registry()
    user_entries = [entry for entry in entries if entry.get("kind") != "maintainer_only"]
    maintainer_entries = [entry for entry in entries if entry.get("kind") == "maintainer_only"]

    require_equal("total entry count", len(entries), 61)
    require_equal("user-facing entry count", len(user_entries), 55)
    require_equal("maintainer-only entry count", len(maintainer_entries), 6)
    require_equal(
        "workflow-family counts",
        dict(Counter(entry.get("visible_block") for entry in user_entries)),
        EXPECTED_BLOCKS,
    )
    require_equal(
        "support-level counts",
        dict(Counter(entry.get("support_level") for entry in user_entries)),
        EXPECTED_SUPPORT,
    )
    require_equal(
        "platform counts",
        dict(Counter(entry.get("platform") for entry in user_entries)),
        EXPECTED_PLATFORMS,
    )
    require_equal(
        "datanalysis requirement counts",
        dict(Counter(entry.get("requires_datanalysis") for entry in user_entries)),
        EXPECTED_DATANALYSIS,
    )
    require_equal(
        "smoke-tier counts",
        dict(Counter(entry.get("smoke_tier") for entry in user_entries)),
        EXPECTED_SMOKE,
    )

    if not REQUIREMENTS_DOC.is_file():
        fail("docs/WORKFLOW_REQUIREMENTS.md is missing")
    document = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    required_fragments = {
        "total": "The canonical registry contains 61 entries:",
        "user count": "| User-facing capabilities | 55 |",
        "maintainer count": "| Maintainer-only gates | 6 |",
        "workflow counts": "| Observational astronomy | 24 |",
        "support counts": "36 stable, 11 narrow, 6 optional, 2 platform-bound",
        "platform counts": "44 portable, 6 macOS, 5 datanalysis",
        "datanalysis counts": "14 true, 41 false",
        "smoke counts": "16 core, 10 full, 29 none",
    }
    for label, fragment in required_fragments.items():
        if fragment not in document:
            fail(f"the requirements document is missing the current {label}: {fragment!r}")

    if not CAPABILITY_MATRIX_DOC.is_file():
        fail("docs/CAPABILITY_SETUP_MATRIX.md is missing")
    matrix_document = CAPABILITY_MATRIX_DOC.read_text(encoding="utf-8")
    matrix_ids = re.findall(r"^\| `([^`]+)` \|", matrix_document, re.MULTILINE)
    if len(matrix_ids) != len(set(matrix_ids)):
        fail("the capability setup matrix has duplicate IDs")
    require_equal("capability setup matrix IDs", set(matrix_ids), {e["id"] for e in user_entries})
    matrix_preflight = dict(re.findall(
        r"^\| `([^`]+)` \| [^|]+ \| `(none|inline|explicit)` \|",
        matrix_document,
        re.MULTILINE,
    ))
    require_equal(
        "per-capability registry preflight modes",
        matrix_preflight,
        {entry["id"]: entry["preflight_mode"] for entry in user_entries},
    )
    if not APP_CAPABILITY_MODEL.is_file():
        fail("Sources/ScientificWorkbench/Models/CapabilityEntry.swift is missing")
    app_model = APP_CAPABILITY_MODEL.read_text(encoding="utf-8")
    expected_readiness = {entry["id"]: "app_ready" for entry in user_entries}
    for set_name, readiness in APP_READINESS_SETS.items():
        match = re.search(
            rf"private static let {set_name}: Set<String> = \[(.*?)\]",
            app_model,
            re.DOTALL,
        )
        if match is None:
            fail(f"could not locate Swift app-readiness set: {set_name}")
        for capability_id in re.findall(r'"([^"]+)"', match.group(1)):
            if capability_id not in expected_readiness:
                fail(f"unknown ID in Swift app-readiness set: {capability_id}")
            if expected_readiness[capability_id] != "app_ready":
                fail(f"overlapping Swift app-readiness sets: {capability_id}")
            expected_readiness[capability_id] = readiness
    matrix_readiness = {}
    for capability_id, access_cell in re.findall(
        r"^\| `([^`]+)` \| ([^|]+) \|", matrix_document, re.MULTILINE
    ):
        if "; " not in access_cell:
            fail(f"missing app-readiness label in capability matrix: {capability_id}")
        matrix_readiness[capability_id] = access_cell.rsplit("; ", 1)[-1]
    require_equal("per-capability app-readiness labels", matrix_readiness, expected_readiness)
    for entry in user_entries:
        capability_id = entry["id"]
        expected_stem = capability_id.split(".", 1)[0]
        if Path(entry["script"]).stem != expected_stem:
            fail(f"CLI script stem differs from capability ID: {capability_id}")
        owner = ROLE_EXCEPTIONS.get(capability_id, ROLE_BY_BLOCK[entry["visible_block"]])
        if not (ROOT / "skills" / owner / entry["script"]).is_file():
            fail(f"the documented CLI owner lacks the script for {capability_id}: {owner}")

    if not CAPABILITY_EVIDENCE_DOC.is_file():
        fail("docs/CAPABILITY_VALIDATION_EVIDENCE.md is missing")
    evidence_document = CAPABILITY_EVIDENCE_DOC.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| (Core smoke covered|Full smoke covered|No smoke;)[^|]*\|", evidence_document, re.MULTILINE)
    actual_tiers = {}
    for capability_id, label in rows:
        if capability_id in actual_tiers:
            fail(f"duplicate capability evidence row: {capability_id}")
        actual_tiers[capability_id] = {
            "Core smoke covered": "core",
            "Full smoke covered": "full",
            "No smoke;": "none",
        }[label]
    expected_tiers = {entry["id"]: entry["smoke_tier"] for entry in user_entries}
    require_equal("per-capability evidence tiers", actual_tiers, expected_tiers)

    print("Scientific Workbench workflow requirements match the canonical registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
