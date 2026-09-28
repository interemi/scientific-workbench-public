#!/usr/bin/env python3
"""Regression for the v2.0 formal skill + app workflow planner."""

from __future__ import annotations

import csv
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_phase5_planner"
FIXTURES = TMP / "fixtures"
RUNS = TMP / "runs"
SUMMARY = TMP / "phase5_planner_summary.json"
REPORT = TMP / "phase5_planner_report.md"
REFERENCE = ROOT / "references" / "v2-0-workflow-planner.md"
REGISTRY = ROOT / "public_surface_registry.yaml"
ROUTER = ROOT / "scripts" / "scientific_workflow_router.py"
APP_READINESS_VALUES = {
    "app_ready",
    "app_ready_partial",
    "cli_only",
    "blocked_optional",
    "maintainer_only",
    "not_applicable_to_app",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def hash_tree(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_file():
        return {path.name: digest(path)}
    return {
        str(item.relative_to(path)): digest(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def reset_tmp() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    FIXTURES.mkdir(parents=True)
    RUNS.mkdir(parents=True)


def make_fixtures() -> dict[str, Path]:
    table = FIXTURES / "professional_metrics.csv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "metric", "value"])
        writer.writerow(["2026-01-01", "throughput", "12.5"])

    mixed = FIXTURES / "mixed administrative package"
    mixed.mkdir()
    shutil.copy2(table, mixed / "metrics.csv")
    (mixed / "notes.txt").write_text("Anonymized project notes.\n", encoding="utf-8")
    (mixed / "brief.pdf").write_bytes(b"%PDF-1.4\n% planner fixture\n")
    with zipfile.ZipFile(mixed / "attachments.zip", "w") as archive:
        archive.writestr("readme.txt", "sidecar")

    notebook = FIXTURES / "inherited_notebook.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": ["print('copied execution only')\n"],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    fits = FIXTURES / "science_image.fits"
    fits.write_bytes(b"SIMPLE  =                    T" + b" " * 64)
    document = FIXTURES / "administrative_report.pdf"
    document.write_bytes(b"%PDF-1.4\n% planner document fixture\n")
    missing = FIXTURES / "missing.csv"
    return {
        "table": table,
        "mixed": mixed,
        "notebook": notebook,
        "fits": fits,
        "document": document,
        "optional": table,
        "missing": missing,
    }


def run_router(name: str, path: Path, task: str) -> dict:
    run_dir = RUNS / name
    run_dir.mkdir(parents=True)
    before = hash_tree(path)
    command = [
        sys.executable,
        str(ROUTER),
        "plan",
        str(path),
        "--task",
        task,
        "--summary-json",
        str(run_dir / "summary.json"),
        "--manifest-json",
        str(run_dir / "manifest.json"),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    after = hash_tree(path)
    require(before == after, f"{name}: original input changed")
    require(completed.returncode == 0, f"{name}: router exit {completed.returncode}: {completed.stderr}")
    require("Traceback" not in completed.stdout + completed.stderr, f"{name}: raw traceback")
    payload = json.loads(completed.stdout)
    for route in payload["recommended_capabilities"]:
        require(route.get("workflow_mode") in {"normal", "expert", "optional", "legacy", "maintainer"}, f"{name}: missing workflow_mode")
        require(route.get("app_readiness") in APP_READINESS_VALUES, f"{name}: missing or invalid app_readiness")
        require(isinstance(route.get("requires_confirmation"), bool), f"{name}: missing confirmation policy")
    return {
        "name": name,
        "payload": payload,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_registry() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if line.startswith("  - id: "):
            if current:
                entries.append(current)
            current = {"id": line.split(": ", 1)[1]}
        elif current and line.startswith("    ") and ": " in line:
            key, value = line.strip().split(": ", 1)
            if key in {"label", "visible_block", "kind", "support_level"}:
                current[key] = value
    if current:
        entries.append(current)
    return entries


def workflow_mode(entry: dict[str, str]) -> str:
    legacy = {
        "legacy_spectroscopy_envcheck",
        "fxcor_iraf_workbench.prepare-session",
        "fxcor_iraf_workbench.run-auto",
        "legacy_rv_coursework_workbench.analyze",
        "legacy_external_reference_check",
        "istarmod_workbench.inspect-tree",
        "istarmod_workbench.prepare-copy",
        "legacy_spectroscopy_report_builder.scaffold",
        "legacy_spectroscopy_report_builder.populate",
    }
    optional = {"iwork_workbench", "quicklook_bridge", "keynote_export"}
    normal_science = {"photometry_noise_budget", "physical_qa"}
    expert = {"catalog_workbench.crossmatch-sky", "spectra_ascii_coursework_workbench"}
    if entry["kind"] == "maintainer_only":
        return "maintainer"
    if entry["id"] in legacy:
        return "legacy"
    if entry["support_level"] == "optional" or entry["id"] in optional:
        return "optional"
    if entry["id"] in expert:
        return "expert"
    if entry["visible_block"] == "astronomy observational" and entry["id"] not in normal_science:
        return "expert"
    return "normal"


def app_readiness(entry: dict[str, str]) -> str:
    blocked_optional = {
        "external_astro_tools_preflight",
        "stilts_workbench",
        "apt_workbench",
        "teareduce_router",
        "iwork_workbench",
        "keynote_export",
        "duckdb_workbench",
    }
    cli_only = {
        "legacy_spectroscopy_envcheck",
        "fxcor_iraf_workbench.prepare-session",
        "fxcor_iraf_workbench.run-auto",
        "legacy_rv_coursework_workbench.analyze",
        "sb2_double_gaussian_workbench.fit",
        "istarmod_workbench.inspect-tree",
        "istarmod_workbench.prepare-copy",
        "legacy_spectroscopy_report_builder.scaffold",
        "legacy_spectroscopy_report_builder.populate",
        "spectra_ascii_coursework_workbench",
    }
    not_applicable = {
        "li6708_equivalent_width_workbench.measure",
        "legacy_external_reference_check",
    }
    partial = {
        "fits_rgb_batch",
        "rgb_visual_fits_export",
        "astrometry_net_workbench.preflight",
        "astrometry_net_workbench.verify-existing-wcs",
        "radial_velocity_workbench.inspect",
        "radial_velocity_workbench.validate-manifest",
        "echelle_multispec_inventory",
        "photometric_solution",
        "presentation_workbench.inspect",
        "presentation_workbench.existing-deck-style-audit",
        "office_roundtrip.docx-style-inventory",
        "office_roundtrip.docx-styled-replace",
        "quicklook_bridge",
        "latex_workbench.scaffold",
        "latex_workbench.review",
        "latex_workbench.compile",
        "coursework_notebook_fidelity_check",
        "notebook_branch_compare",
        "catalog_workbench.crossmatch-sky",
    }
    if entry["kind"] == "maintainer_only":
        return "maintainer_only"
    if entry["id"] in not_applicable:
        return "not_applicable_to_app"
    if entry["id"] in cli_only:
        return "cli_only"
    if entry["id"] in blocked_optional:
        return "blocked_optional"
    if entry["id"] in partial:
        return "app_ready_partial"
    return "app_ready"


def validate_matrix() -> tuple[Counter, Counter]:
    entries = parse_registry()
    require(len(entries) == 61, f"expected 61 current registry rows, found {len(entries)}")
    text = REFERENCE.read_text(encoding="utf-8")
    for entry in entries:
        mode = workflow_mode(entry)
        readiness = app_readiness(entry)
        require(
            f"`{entry['id']}` | `{mode}` | `{readiness}`" in text,
            f"matrix missing {entry['id']} -> {mode}/{readiness}",
        )
    mode_counts = Counter(workflow_mode(entry) for entry in entries)
    readiness_counts = Counter(app_readiness(entry) for entry in entries)
    require(mode_counts == Counter({"normal": 25, "expert": 13, "optional": 8, "legacy": 9, "maintainer": 6}), f"unexpected mode counts: {mode_counts}")
    require(
        readiness_counts
        == Counter(
            {
                "app_ready": 17,
                "app_ready_partial": 19,
                "blocked_optional": 7,
                "cli_only": 10,
                "maintainer_only": 6,
                "not_applicable_to_app": 2,
            }
        ),
        f"unexpected app-readiness counts: {readiness_counts}",
    )
    return mode_counts, readiness_counts


def validate_app_integration() -> None:
    sources = {
        "router_client": APP / "Sources/ScientificWorkbench/Services/SkillWorkflowRouterClient.swift",
        "planner": APP / "Sources/ScientificWorkbench/Services/AgentPlanner.swift",
        "dry_run": APP / "Sources/ScientificWorkbench/Services/WorkflowDryRunService.swift",
        "execution": APP / "Sources/ScientificWorkbench/Services/WorkflowExecutionCoordinator.swift",
        "placeholder": APP / "Sources/ScientificWorkbench/Services/WorkflowPlaceholderValidator.swift",
        "builder": APP / "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift",
    }
    for name, path in sources.items():
        require(path.exists(), f"missing app source {name}: {path}")
    require("scientific_workflow_router.py" in sources["router_client"].read_text(), "app does not invoke the skill router")
    require("appReadiness" in sources["router_client"].read_text(), "app router client ignores app_readiness")
    require("routerPlan:" in sources["planner"].read_text(), "AI planner lacks router context")
    require("capabilities.plannerVisible" in sources["planner"].read_text(), "AI planner does not filter by app-readiness")
    require("unresolvedTokens" in sources["dry_run"].read_text(), "dry-run does not validate placeholders")
    require("unresolvedTokens" in sources["execution"].read_text(), "execution does not validate placeholders")
    builder_text = sources["builder"].read_text()
    require('case "notebook_workbench.execute-copy"' in builder_text, "execute-copy lacks guided command")
    require('case "coursework_notebook_fidelity_check"' in builder_text, "fidelity check lacks guided command")


def run_optional_backend_absent() -> dict:
    run_dir = RUNS / "optional_backend_absent"
    run_dir.mkdir(parents=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "stilts_workbench.py"),
        "preflight",
        "--stilts-command",
        "/definitely/missing/stilts",
        "--topcat-command",
        "/definitely/missing/topcat",
        "--summary-json",
        str(run_dir / "summary.json"),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    require(completed.returncode == 2, f"optional backend: expected controlled exit 2, got {completed.returncode}")
    require("Traceback" not in completed.stdout + completed.stderr, "optional backend emitted traceback")
    payload = json.loads(completed.stdout)
    require(payload.get("app_status") == "BLOCKED_CONTROLADO", "optional backend did not block cleanly")
    require(payload.get("original_modified") is False, "optional backend original_modified is not false")
    require(payload.get("next_actions"), "optional backend lacks next_actions")
    return {"status": payload["app_status"], "command": command}


def main() -> int:
    reset_tmp()
    fixtures = make_fixtures()
    cases = [
        ("table", fixtures["table"], "profile this professional table"),
        ("mixed_folder", fixtures["mixed"], "inspect this mixed administrative package"),
        ("notebook", fixtures["notebook"], "inspect inherited notebook before copied execution"),
        ("fits", fixtures["fits"], "inspect this FITS image"),
        ("document", fixtures["document"], "inspect this administrative document"),
        ("optional_route", fixtures["optional"], "use STILTS to validate a VOTable"),
        ("duckdb_route", fixtures["table"], "query this table with DuckDB SQL"),
        ("missing_path", fixtures["missing"], "inspect the missing input"),
    ]
    records = [run_router(name, path, task) for name, path, task in cases]
    by_name = {record["name"]: record["payload"] for record in records}

    require(by_name["table"]["recommended_capabilities"][0]["capability_id"] == "profile_table", "table route mismatch")
    require(any(item["capability_id"] == "cross_domain_data_workbench" for item in by_name["mixed_folder"]["recommended_capabilities"]), "mixed folder lacks cross-domain route")
    notebook_ids = [item["capability_id"] for item in by_name["notebook"]["recommended_capabilities"]]
    require(notebook_ids[:2] == ["coursework_notebook_fidelity_check", "notebook_workbench.execute-copy"], f"notebook routes mismatch: {notebook_ids}")
    notebook_inspect = by_name["notebook"]["recommended_capabilities"][0]
    require(notebook_inspect["app_readiness"] == "app_ready_partial", "notebook inspect readiness mismatch")
    require(notebook_inspect["requires_confirmation"] is True, "partial notebook inspect must require confirmation")
    notebook_execute = by_name["notebook"]["recommended_capabilities"][1]
    require(notebook_execute["requires_confirmation"] is True, "notebook execute-copy must require confirmation")
    fits_route = by_name["fits"]["recommended_capabilities"][0]
    require(fits_route["capability_id"] == "inspect_fits" and fits_route["workflow_mode"] == "expert", "FITS route must be expert")
    require(by_name["document"]["recommended_capabilities"][0]["capability_id"] == "document_intake_workbench", "document route mismatch")
    optional_route = by_name["optional_route"]["recommended_capabilities"][0]
    require(optional_route["capability_id"] == "stilts_workbench", "optional route mismatch")
    require(optional_route["workflow_mode"] == "optional" and optional_route["requires_confirmation"] is True, "optional route confirmation mismatch")
    duckdb_route = next(
        item for item in by_name["duckdb_route"]["recommended_capabilities"]
        if item["capability_id"] == "duckdb_workbench"
    )
    require(duckdb_route["workflow_mode"] == "optional", "DuckDB route must be optional")
    require(duckdb_route["app_readiness"] == "blocked_optional", "DuckDB readiness mismatch")
    require(duckdb_route["requires_confirmation"] is True, "DuckDB route must require confirmation")
    require(by_name["missing_path"]["app_status"] == "BLOCKED_CONTROLADO", "missing path must block")
    require(not by_name["missing_path"]["recommended_capabilities"], "missing path must not have executable analysis routes")

    mode_counts, readiness_counts = validate_matrix()
    validate_app_integration()
    optional_backend = run_optional_backend_absent()

    rows = []
    for record in records:
        payload = record["payload"]
        rows.append(
            {
                "case": record["name"],
                "status": payload["app_status"],
                "input_kind": payload["input_kind"],
                "routes": [item["capability_id"] for item in payload["recommended_capabilities"]],
                "command": shlex.join(record["command"]),
                "warnings": payload.get("warnings", []),
                "summary_json": str(RUNS / record["name"] / "summary.json"),
                "manifest_json": str(RUNS / record["name"] / "manifest.json"),
            }
        )
    summary = {
        "status": "PASS",
        "registry_rows": sum(mode_counts.values()),
        "workflow_mode_counts": dict(sorted(mode_counts.items())),
        "app_readiness_counts": dict(sorted(readiness_counts.items())),
        "cases": rows,
        "optional_backend_absent": optional_backend["status"],
        "originals_modified": False,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# v2.0 Phase 5 Planner Regression",
        "",
        "Status: PASS",
        "",
        "| case | status | input_kind | routes |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['case']}` | `{row['status']}` | `{row['input_kind']}` | "
            f"{', '.join(f'`{item}`' for item in row['routes']) or '`none`'} |"
        )
    lines.extend(
        [
            "",
            f"Optional backend absent: `{optional_backend['status']}`.",
            f"Registry rows: `{sum(mode_counts.values())}`.",
            f"Summary: `{SUMMARY}`.",
            "",
            "## Commands and artifacts",
            "",
        ]
    )
    for row in rows:
        lines.extend(
            [
                f"### {row['case']}",
                "",
                f"- Command: `{row['command']}`",
                f"- Warnings: `{json.dumps(row['warnings'], ensure_ascii=True)}`",
                f"- Summary: `{row['summary_json']}`",
                f"- Manifest: `{row['manifest_json']}`",
                "",
            ]
        )
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "summary": str(SUMMARY), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
