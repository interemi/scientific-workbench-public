#!/usr/bin/env python3
"""Validate v1.8 app-ready run bundles for priority general routes."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp" / "v1_8_phase4_run_bundles"
RUNS = TMP / "runs"
FIXTURES = TMP / "fixtures"
DATANALYSIS_PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
PYTHON = str(DATANALYSIS_PYTHON if DATANALYSIS_PYTHON.exists() else sys.executable)
REQUIRED_FILES = {"manifest.json", "summary.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md"}
REQUIRED_DIRS = {"artifacts", "previews", "reports", "tables", "logs"}
ARTIFACT_TYPES = {
    "summary_json",
    "manifest_json",
    "report_md",
    "preview_png",
    "table_csv",
    "notebook_ipynb",
    "log_txt",
    "qa_report",
    "handoff_bundle",
    "unknown",
}


@dataclass
class Case:
    target: str
    case_type: str
    command: list[str]
    run_dir: Path
    expected_statuses: set[str]
    input_paths: list[Path] = field(default_factory=list)
    expected_returncodes: set[int] = field(default_factory=lambda: {0})


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_fixtures() -> dict[str, Path]:
    if RUNS.exists():
        shutil.rmtree(RUNS)
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    RUNS.mkdir(parents=True)
    FIXTURES.mkdir(parents=True)
    fixtures: dict[str, Path] = {}
    fixtures["table"] = write_csv(
        FIXTURES / "tables" / "ops_metrics.csv",
        [
            {"date": "2026-01-01", "team": "ops", "tickets": 12, "hours": 4.5},
            {"date": "2026-01-02", "team": "data", "tickets": 7, "hours": 2.0},
            {"date": "2026-01-03", "team": "ops", "tickets": 14, "hours": 5.1},
        ],
    )
    fixtures["cross_dir"] = FIXTURES / "cross_domain"
    fixtures["cross_dir"].mkdir()
    shutil.copy2(fixtures["table"], fixtures["cross_dir"] / "ops_metrics.csv")
    write_text(fixtures["cross_dir"] / "ignored.txt", "not a table for this route\n")
    fixtures["docs_dir"] = FIXTURES / "docs"
    fixtures["docs_dir"].mkdir()
    write_text(fixtures["docs_dir"] / "brief.md", "# Client brief\n\nReview operational status and blockers.\n")
    write_text(fixtures["docs_dir"] / "notes.txt", "Next action: schedule review.\n")
    fixtures["safe_zip"] = FIXTURES / "containers" / "project_bundle.zip"
    fixtures["safe_zip"].parent.mkdir(parents=True)
    with zipfile.ZipFile(fixtures["safe_zip"], "w") as archive:
        archive.writestr("reports/summary.md", "# Summary\n")
        archive.writestr("tables/ops_metrics.csv", fixtures["table"].read_text(encoding="utf-8"))
    return fixtures


def wrapper_command(target: str, run_dir: Path, child: list[object]) -> list[str]:
    return [
        PYTHON,
        "scripts/app_run_bundle.py",
        "--run-dir",
        str(run_dir),
        "--tool",
        target,
        "--",
        *[str(item) for item in child],
    ]


def build_cases(fixtures: dict[str, Path]) -> list[Case]:
    missing = FIXTURES / "containers" / "missing.zip"
    return [
        Case(
            "profile_table",
            "table_happy",
            wrapper_command(
                "profile_table",
                RUNS / "profile_table",
                [PYTHON, "scripts/profile_table.py", fixtures["table"], "--run-dir", RUNS / "profile_table"],
            ),
            RUNS / "profile_table",
            {"PASS"},
            [fixtures["table"]],
        ),
        Case(
            "cross_domain_data_workbench",
            "missing_input_warning",
            wrapper_command(
                "cross_domain_data_workbench",
                RUNS / "cross_domain_data_workbench",
                [
                    PYTHON,
                    "scripts/cross_domain_data_workbench.py",
                    fixtures["cross_dir"],
                    FIXTURES / "missing_dir",
                    "--run-dir",
                    RUNS / "cross_domain_data_workbench",
                ],
            ),
            RUNS / "cross_domain_data_workbench",
            {"WARNING"},
            [fixtures["cross_dir"]],
        ),
        Case(
            "document_intake_workbench",
            "docs_happy",
            wrapper_command(
                "document_intake_workbench",
                RUNS / "document_intake_workbench",
                [PYTHON, "scripts/document_intake_workbench.py", fixtures["docs_dir"], "--run-dir", RUNS / "document_intake_workbench"],
            ),
            RUNS / "document_intake_workbench",
            {"PASS", "WARNING"},
            [fixtures["docs_dir"]],
        ),
        Case(
            "inspect_data_container",
            "missing_blocked",
            wrapper_command(
                "inspect_data_container",
                RUNS / "inspect_data_container",
                [PYTHON, "scripts/inspect_data_container.py", missing, "--run-dir", RUNS / "inspect_data_container"],
            ),
            RUNS / "inspect_data_container",
            {"BLOCKED_CONTROLADO", "FAIL"},
            [],
            {2},
        ),
    ]


def app_status(payload: dict) -> str:
    if payload.get("app_status"):
        return str(payload["app_status"])
    return {
        "ok": "PASS",
        "warning": "WARNING",
        "blocked": "BLOCKED_CONTROLADO",
        "fail": "FAIL",
    }.get(str(payload.get("status", "")).lower(), "WARNING")


def validate_case(case: Case, completed: subprocess.CompletedProcess, before_hashes: dict[Path, str | None]) -> dict:
    issues: list[str] = []
    run_dir = case.run_dir
    for name in sorted(REQUIRED_FILES):
        if not (run_dir / name).exists():
            issues.append(f"missing required file: {name}")
    for name in sorted(REQUIRED_DIRS):
        if not (run_dir / name).is_dir():
            issues.append(f"missing required directory: {name}")
    if completed.returncode not in case.expected_returncodes:
        issues.append(f"unexpected wrapper returncode {completed.returncode}")
    if "Traceback (most recent call last)" in completed.stdout or "Traceback (most recent call last)" in completed.stderr:
        issues.append("wrapper leaked raw traceback")
    stdout_txt = (run_dir / "stdout.txt").read_text(encoding="utf-8", errors="replace") if (run_dir / "stdout.txt").exists() else ""
    stderr_txt = (run_dir / "stderr.txt").read_text(encoding="utf-8", errors="replace") if (run_dir / "stderr.txt").exists() else ""
    if "Traceback (most recent call last)" in stdout_txt or "Traceback (most recent call last)" in stderr_txt:
        issues.append("captured child logs contain raw traceback")
    summary = {}
    manifest = {}
    try:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"summary.json is not parseable JSON: {exc}")
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"manifest.json is not parseable JSON: {exc}")
    actual_status = app_status(summary) if summary else "MISSING"
    if actual_status not in case.expected_statuses:
        issues.append(f"expected app status {sorted(case.expected_statuses)}, got {actual_status}")
    if summary and summary.get("contract_version") != "1.8":
        issues.append("summary contract_version is not 1.8")
    if summary and summary.get("original_modified") is not False:
        issues.append("summary original_modified is not false")
    typed_artifacts = summary.get("typed_artifacts") if isinstance(summary, dict) else None
    if not isinstance(typed_artifacts, list) or not typed_artifacts:
        issues.append("typed_artifacts missing or empty")
    else:
        seen_types = set()
        for artifact in typed_artifacts:
            artifact_type = artifact.get("artifact_type") if isinstance(artifact, dict) else None
            seen_types.add(artifact_type)
            if artifact_type not in ARTIFACT_TYPES:
                issues.append(f"invalid artifact type: {artifact_type}")
        for required_type in ("summary_json", "manifest_json", "log_txt", "report_md", "handoff_bundle"):
            if required_type not in seen_types:
                issues.append(f"missing required run artifact type: {required_type}")
    next_steps = (run_dir / "next_steps.md").read_text(encoding="utf-8", errors="replace") if (run_dir / "next_steps.md").exists() else ""
    if len(next_steps.strip()) < 40 or "Status:" not in next_steps:
        issues.append("next_steps.md is not legible enough")
    command_text = (run_dir / "command.txt").read_text(encoding="utf-8", errors="replace") if (run_dir / "command.txt").exists() else ""
    if "scripts/" not in command_text:
        issues.append("command.txt does not record the child script")
    for path, before in before_hashes.items():
        if before != sha256(path):
            issues.append(f"input was modified: {path}")
    return {
        "target": case.target,
        "case_type": case.case_type,
        "result": "PASS" if not issues else "FAIL",
        "app_status": actual_status,
        "returncode": completed.returncode,
        "issues": issues,
        "run_dir": str(run_dir),
        "artifacts": sorted({item.get("artifact_type") for item in typed_artifacts or [] if isinstance(item, dict)}),
        "manifest_has_child_manifest": bool((manifest.get("extra") or {}).get("child_manifest")) if isinstance(manifest, dict) else False,
    }


def scan_existing_output_producers() -> dict:
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    counts = Counter()
    examples = {key: [] for key in ("summary_json", "manifest_json", "logs", "output_dir")}
    for script in scripts:
        text = script.read_text(encoding="utf-8", errors="ignore")
        markers = {
            "summary_json": "--summary-json" in text or "summary_json" in text,
            "manifest_json": "--manifest-json" in text or "manifest_json" in text,
            "logs": "--log-dir" in text or "stdout" in text and "stderr" in text,
            "output_dir": "--output-dir" in text or "output_dir" in text,
        }
        for key, present in markers.items():
            if present:
                counts[key] += 1
                if len(examples[key]) < 12:
                    examples[key].append(script.name)
    return {"counts": dict(counts), "examples": examples}


def write_report(payload: dict) -> None:
    lines = [
        "# AUDITORIA v1.8 - Fase 4: run bundles",
        "",
        f"Estado: {payload['status']}",
        "",
        "| target | case | app_status | returncode | result | artifact types |",
        "|---|---|---:|---:|---:|---|",
    ]
    for result in payload["results"]:
        lines.append(
            f"| `{result['target']}` | `{result['case_type']}` | `{result['app_status']}` | `{result['returncode']}` | `{result['result']}` | {', '.join(result['artifacts'])} |"
        )
    lines.extend(["", "## Output Producers", ""])
    for key, count in sorted(payload["existing_output_producers"]["counts"].items()):
        examples = ", ".join(payload["existing_output_producers"]["examples"].get(key, [])[:8])
        lines.append(f"- `{key}`: {count} scripts. Examples: {examples}")
    lines.extend(["", "## Problems", ""])
    if payload["failures"]:
        for failure in payload["failures"]:
            lines.append(f"- {failure['target']}::{failure['case_type']}: {'; '.join(failure['issues'])}")
    else:
        lines.append("- P0/P1: ninguno abierto en la regresion Fase 4.")
        lines.append("- P2: migrar mas familias al layout directo `--run-dir` sin mover de golpe sus outputs historicos.")
    (TMP / "phase4_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    fixtures = make_fixtures()
    cases = build_cases(fixtures)
    results = []
    for case in cases:
        before_hashes = {path: sha256(path) for path in case.input_paths if path.is_file()}
        completed = subprocess.run(case.command, cwd=ROOT, text=True, capture_output=True, check=False)
        result = validate_case(case, completed, before_hashes)
        results.append(result)
    failures = [result for result in results if result["result"] != "PASS"]
    payload = {
        "phase": "v1.8 phase 4 run bundles",
        "status": "FAIL" if failures else "PASS",
        "case_count": len(results),
        "target_count": len({result["target"] for result in results}),
        "run_bundle_contract": str(ROOT / "references" / "v1-8-run-bundle-contract.md"),
        "existing_output_producers": scan_existing_output_producers(),
        "results": results,
        "failures": failures,
        "tmp": str(TMP),
    }
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "phase4_regression.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_report(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
