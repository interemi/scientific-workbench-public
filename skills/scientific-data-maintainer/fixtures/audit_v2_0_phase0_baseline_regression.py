#!/usr/bin/env python3
"""Validate the v2.0 Phase 0 dual baseline.

This check is intentionally lightweight. Phase 0 is a charter/baseline phase:
it validates the installed v1.9 skill, the eight v2.0 deferrals, the existence
of ScientificWorkbench integration surfaces, and the read-only app boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


EDITABLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALLED_ROOT = Path.home() / ".codex/skills/scientific-data-analysis"
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]
PHASE_TMP = EDITABLE_ROOT / "tmp" / "v2_0_phase0_charter"
APP_HASH_MANIFEST = PHASE_TMP / "scientificworkbench_readonly_hashes_before.sha256"

EXPECTED_DEFERRED = {
    8: "fits_rgb_batch.py",
    10: "stilts_workbench.py",
    13: "radial_velocity_workbench.py inspect",
    26: "photometric_solution.py",
    28: "apt_workbench.py",
    34: "office_roundtrip.py docx-style-inventory",
    35: "office_roundtrip.py docx-styled-replace",
    37: "keynote_export.py",
}

APP_REQUIRED_RELATIVE_FILES = [
    "ROADMAP.md",
    "ARCHITECTURE.md",
    "DECISIONS/0001-ai-plans-local-capabilities-execute.md",
    "DECISIONS/0002-local-first-zero-cost-ai.md",
    "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift",
    "Sources/ScientificWorkbench/Services/ToolEnvelopeParser.swift",
    "Sources/ScientificWorkbench/Services/ArtifactDiscovery.swift",
    "Tests/ScientificWorkbenchTests/RegistryAndCapabilityTests.swift",
    "Tests/ScientificWorkbenchTests/ArtifactAndJobModelTests.swift",
    "Tests/ScientificWorkbenchTests/WorkflowDryRunServiceTests.swift",
    "Tests/ScientificWorkbenchTests/WorkflowExecutionCoordinatorTests.swift",
    "Tests/ScientificWorkbenchTests/WorkflowRecoveryServiceTests.swift",
]

CHARTER_REQUIRED_TERMS = [
    "v2.0",
    "ScientificWorkbench",
    "eight P1 rows",
    "Backend/App Boundary",
    "Closure Criteria",
    "Phase 0 Read-Only App Policy",
    "Phase 11",
]


def read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text()
    match = re.search(r"Canonical fixture:\s*`([^`]+)`", text)
    if match:
        archived = EDITABLE_ROOT / match.group(1)
        if archived.exists():
            return archived.read_text(encoding="utf-8")
    return text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_hash_manifest(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not path.exists():
        return hashes
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, file_path = parts
        hashes[file_path.strip()] = digest.strip()
    return hashes


def extract_deferral_rows(text: str) -> dict[int, str]:
    rows: dict[int, str] = {}
    for line in text.splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*`?P1`?\s*\|", line)
        if match:
            rows[int(match.group(1))] = match.group(2)
    return rows


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def validate(args: argparse.Namespace) -> dict[str, object]:
    installed_root = Path(args.installed_root)
    app_root = Path(args.app_root)
    failures: list[str] = []
    warnings: list[str] = []

    installed_docs = {
        "SKILL.md": installed_root / "SKILL.md",
        "README.txt": installed_root / "README.txt",
        "RELEASE-v1.txt": installed_root / "RELEASE-v1.txt",
        "public_surface_registry.yaml": installed_root / "public_surface_registry.yaml",
        "references/v1-9-debt-inventory.md": installed_root / "references" / "v1-9-debt-inventory.md",
        "references/v1-9-v2-0-deferrals.md": installed_root / "references" / "v1-9-v2-0-deferrals.md",
    }
    for label, path in installed_docs.items():
        if not path.exists():
            fail(failures, f"Missing installed baseline file: {label}")

    if installed_docs["SKILL.md"].exists():
        skill_text = read_text(installed_docs["SKILL.md"])
        if "v1.9 stable" not in skill_text and "v2.0 integrated" not in skill_text:
            fail(failures, "Installed SKILL.md declares neither the v1.9 pre-sync baseline nor the v2.0 post-sync release.")
        if "ScientificWorkbench" not in skill_text:
            fail(failures, "Installed SKILL.md does not mention the ScientificWorkbench boundary.")

    debt_text = read_text(installed_docs["references/v1-9-debt-inventory.md"]) if installed_docs["references/v1-9-debt-inventory.md"].exists() else ""
    deferral_text = read_text(installed_docs["references/v1-9-v2-0-deferrals.md"]) if installed_docs["references/v1-9-v2-0-deferrals.md"].exists() else ""

    if debt_text:
        if "| `v2_0` | 8 |" not in debt_text:
            fail(failures, "Debt inventory does not declare exactly 8 v2_0 capability rows.")
        if "Dejar para v2.0" not in debt_text:
            fail(failures, "Debt inventory is missing the v2.0 deferral statement.")
        for row, target in EXPECTED_DEFERRED.items():
            pattern = rf"\|\s*{row}\s*\|\s*`{re.escape(target)}`\s*\|\s*`P1`\s*\|.*\|\s*`v2_0`\s*\|"
            if not re.search(pattern, debt_text):
                fail(failures, f"Debt inventory missing deferred P1 row {row}: {target}")

    rows = extract_deferral_rows(deferral_text)
    if rows != EXPECTED_DEFERRED:
        fail(failures, f"v1-9-v2-0-deferrals rows mismatch: {rows!r}")
    for forbidden in [
        "UI-driven workflow implementation",
        "interactive selectors",
        "job history",
        "ScientificWorkbench edits",
    ]:
        if forbidden not in deferral_text:
            fail(failures, f"Deferral guardrail missing forbidden-scope term: {forbidden}")

    app_missing = [rel for rel in APP_REQUIRED_RELATIVE_FILES if not (app_root / rel).exists()]
    if app_missing:
        fail(failures, f"ScientificWorkbench missing required compatibility files: {app_missing}")

    # Check app files read in Phase 0 were not modified after the stored baseline.
    stored_hashes = parse_hash_manifest(APP_HASH_MANIFEST)
    if not stored_hashes:
        warnings.append(f"No read-only app hash manifest found at {APP_HASH_MANIFEST}")
    else:
        changed: list[str] = []
        missing: list[str] = []
        for file_path, expected_digest in stored_hashes.items():
            path = Path(file_path)
            if not path.exists():
                missing.append(file_path)
                continue
            actual = sha256(path)
            if actual != expected_digest:
                changed.append(file_path)
        if missing:
            fail(failures, f"ScientificWorkbench files missing since read-only baseline: {missing}")
        if changed:
            message = f"ScientificWorkbench files changed since read-only Phase 0 baseline: {changed}"
            if args.enforce_readonly_app_baseline:
                fail(failures, message)
            else:
                warnings.append(message)

    charter = EDITABLE_ROOT / "references" / "v2-0-integrated-release-charter.md"
    if not charter.exists():
        fail(failures, "Missing editable v2.0 charter.")
    else:
        charter_text = read_text(charter)
        missing_terms = [term for term in CHARTER_REQUIRED_TERMS if term not in charter_text]
        if missing_terms:
            fail(failures, f"v2.0 charter missing required terms: {missing_terms}")
        for target in EXPECTED_DEFERRED.values():
            if target not in charter_text:
                fail(failures, f"v2.0 charter missing deferred target: {target}")

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_phase0_baseline_regression",
        "status": status,
        "editable_root": str(EDITABLE_ROOT),
        "installed_root": str(installed_root),
        "app_root": str(app_root),
        "deferred_v2_0_rows": [
            {"row": row, "target": target, "severity": "P1"}
            for row, target in sorted(EXPECTED_DEFERRED.items())
        ],
        "app_required_file_count": len(APP_REQUIRED_RELATIVE_FILES),
        "app_hash_manifest": str(APP_HASH_MANIFEST),
        "warnings": warnings,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-root", default=str(DEFAULT_INSTALLED_ROOT))
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--summary-json", default=None)
    parser.add_argument(
        "--enforce-readonly-app-baseline",
        action="store_true",
        help="Fail if files read from ScientificWorkbench during Phase 0 changed. Later v2.0 phases should omit this flag.",
    )
    args = parser.parse_args(argv)

    payload = validate(args)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(text + "\n", encoding="utf-8")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
