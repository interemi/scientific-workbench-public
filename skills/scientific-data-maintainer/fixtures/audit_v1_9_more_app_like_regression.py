#!/usr/bin/env python3
"""Priority v1.9 app-like regressions with imperfect inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import os
from typing import Any

from _internal.provenance_utils import FROZEN_ARTIFACT_TYPES
from _internal.run_bundle import REQUIRED_FILES


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_9_priority_more_app_like"
INPUTS = TMP / "inputs"
RUNS = TMP / "runs"
SUMMARY = TMP / "more_app_like_regression_summary.json"
REPORT = TMP / "more_app_like_regression_report.md"
DOC = ROOT / "references" / "v1-9-more-app-like-regression.md"

DATANALYSIS = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
PYTHON = DATANALYSIS if DATANALYSIS.exists() else Path(sys.executable)
VALID_APP_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}
LEGACY_STATUS_TO_APP = {
    "ok": "PASS",
    "pass": "PASS",
    "ready": "PASS",
    "success": "PASS",
    "warning": "WARNING",
    "blocked": "BLOCKED_CONTROLADO",
    "fail": "FAIL",
    "failed": "FAIL",
    "error": "FAIL",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def write_notebook(path: Path) -> Path:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Coursework notebook\n", "Answer:\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["student_name = input('Name?')\n", "print(student_name)\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["import plotly.express as px\n"],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    if path.is_file():
        return sha256(path)
    records = []
    for item in sorted(child for child in path.rglob("*") if child.is_file()):
        records.append([str(item.relative_to(path)), sha256(item)])
    return records


def path_from_payload(raw: str | Path) -> Path:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    require(start >= 0, f"No JSON object found in output: {text[:500]}")
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    require(isinstance(payload, dict), "First JSON value is not an object")
    return payload


def load_payload(completed: subprocess.CompletedProcess[str], summary_path: Path) -> dict[str, Any]:
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return first_json_object(completed.stdout)


def app_status(payload: dict[str, Any]) -> str:
    status = payload.get("app_status")
    if status:
        return str(status)
    return LEGACY_STATUS_TO_APP.get(str(payload.get("status", "")).lower(), "FAIL")


def assert_no_traceback(completed: subprocess.CompletedProcess[str], case_id: str) -> None:
    combined = f"{completed.stdout}\n{completed.stderr}"
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        raise AssertionError(f"{case_id}: raw traceback leaked\n{combined}")


def validate_payload(
    payload: dict[str, Any],
    *,
    case_id: str,
    expected_statuses: set[str],
    require_warning: bool = True,
) -> list[str]:
    for key in ("contract_version", "tool", "status", "qa", "typed_artifacts", "app_hints", "next_actions", "original_modified"):
        require(key in payload, f"{case_id}: missing envelope field {key}")
    require(payload["contract_version"] == "1.8", f"{case_id}: unexpected contract_version")
    status = app_status(payload)
    require(status in VALID_APP_STATUSES, f"{case_id}: invalid app status {status}")
    require(status in expected_statuses, f"{case_id}: expected {expected_statuses}, got {status}")
    require(payload.get("original_modified") is False, f"{case_id}: original_modified must be false")
    require(isinstance(payload.get("next_actions"), list) and payload["next_actions"], f"{case_id}: missing next_actions")
    app_hints = payload.get("app_hints")
    require(isinstance(app_hints, dict) and app_hints.get("short_summary"), f"{case_id}: missing app_hints.short_summary")
    require(app_hints.get("severity") in {"ok", "warning", "blocked", "error"}, f"{case_id}: invalid app_hints.severity")

    typed_artifacts = payload.get("typed_artifacts")
    require(isinstance(typed_artifacts, list), f"{case_id}: typed_artifacts must be a list")
    existing_artifacts = []
    for item in typed_artifacts:
        require(isinstance(item, dict), f"{case_id}: typed_artifact item is not an object")
        artifact_type = item.get("artifact_type")
        require(artifact_type in FROZEN_ARTIFACT_TYPES, f"{case_id}: unregistered artifact_type {artifact_type!r}")
        raw_path = item.get("path")
        if isinstance(raw_path, str) and path_from_payload(raw_path).exists():
            existing_artifacts.append(str(path_from_payload(raw_path)))
    require(existing_artifacts, f"{case_id}: no existing typed artifact")

    if require_warning:
        qa = payload.get("qa") if isinstance(payload.get("qa"), dict) else {}
        findings = qa.get("findings") or []
        warnings = payload.get("warnings") or []
        require(findings or warnings or status == "WARNING", f"{case_id}: expected warnings/findings")
    return sorted(set(existing_artifacts))


def validate_run_bundle(run_dir: Path, case_id: str) -> None:
    for name in REQUIRED_FILES:
        require((run_dir / name).exists(), f"{case_id}: missing run bundle file {name}")
    for directory in ("artifacts", "previews", "reports", "tables", "logs"):
        require((run_dir / directory).is_dir(), f"{case_id}: missing run bundle dir {directory}")


def assert_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "profile_table.py",
        "cross_domain_data_workbench.py",
        "semantic_diff.py",
        "coursework_notebook_fidelity_check.py",
        "notebook_branch_compare.py",
        "timeseries_forecasting_workbench.py",
        "inspect_data_container.py",
        "Backlog",
    ]
    missing = [item for item in required if item not in text]
    require(not missing, f"priority doc missing required text: {missing}")


def make_fixtures() -> dict[str, Path]:
    if TMP.exists():
        shutil.rmtree(TMP)
    INPUTS.mkdir(parents=True)
    RUNS.mkdir(parents=True)
    fixtures: dict[str, Path] = {}

    imperfect_table = INPUTS / "tables" / "imperfect_metrics.csv"
    imperfect_table.parent.mkdir(parents=True)
    imperfect_table.write_text(
        "id,value,value,all_null\n"
        "1,10,11,\n"
        "2,inf,21,\n"
        "3,30,31,\n",
        encoding="utf-8",
    )
    fixtures["imperfect_table"] = imperfect_table

    mixed = INPUTS / "mixed_project"
    mixed.mkdir(parents=True)
    shutil.copy2(imperfect_table, mixed / "imperfect_metrics.csv")
    (mixed / "notes.txt").write_text("Operational notes; table needs cleanup before reporting.\n", encoding="utf-8")
    fixtures["mixed_project"] = mixed

    fixtures["baseline_csv"] = write_csv(
        INPUTS / "diff" / "baseline.csv",
        ["id", "amount", "status"],
        [[1, 10, "open"], [2, 20, "closed"], [3, 30, "open"]],
    )
    fixtures["candidate_csv"] = write_csv(
        INPUTS / "diff" / "candidate.csv",
        ["id", "amount", "status"],
        [[1, 10, "open"], [2, 25, "closed"]],
    )

    fixtures["risky_notebook"] = write_notebook(INPUTS / "notebooks" / "risky_received.ipynb")
    assignment = INPUTS / "notebooks" / "assignment.md"
    assignment.write_text("Use data/raw.csv and include answer cells in the submitted notebook.\n", encoding="utf-8")
    fixtures["assignment"] = assignment

    branches = INPUTS / "branches"
    (branches / "alice").mkdir(parents=True)
    (branches / "bob").mkdir(parents=True)
    shutil.copy2(fixtures["risky_notebook"], branches / "alice" / "analysis.ipynb")
    shutil.copy2(fixtures["risky_notebook"], branches / "bob" / "analysis.ipynb")
    (branches / "alice" / "result.png").write_text("fake png placeholder\n", encoding="utf-8")
    fixtures["branches"] = branches

    fixtures["time_series"] = write_csv(
        INPUTS / "series" / "sales_with_date_issues.csv",
        ["date", "value"],
        [
            ["2026-01-01", 100],
            ["2026-01-01", 105],
            ["not-a-date", 110],
            ["2026-04-01", 120],
            ["2026-05-01", 125],
            ["2026-06-01", 130],
            ["2026-07-01", 135],
            ["2026-08-01", 138],
            ["2026-09-01", 141],
            ["2026-10-01", 145],
            ["2026-11-01", 149],
            ["2026-12-01", 152],
            ["2027-01-01", 156],
            ["2027-02-01", 160],
        ],
    )

    unsafe_zip = INPUTS / "containers" / "unsafe_package.zip"
    unsafe_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(unsafe_zip, "w") as archive:
        archive.writestr("../escape.txt", "bad path\n")
        archive.writestr("normal/readme.txt", "safe member\n")
    fixtures["unsafe_zip"] = unsafe_zip
    return fixtures


def run_case(
    *,
    case_id: str,
    target: str,
    command: list[str],
    summary_path: Path,
    input_path: Path,
    extra_inputs: list[Path] | None = None,
    expected_statuses: set[str],
    expected_returncodes: set[int] = {0},
    run_dir: Path | None = None,
) -> dict[str, Any]:
    watched_inputs = [input_path, *(extra_inputs or [])]
    before = {str(path): hash_path(path) for path in watched_inputs}
    completed = run(command)
    assert_no_traceback(completed, case_id)
    require(
        completed.returncode in expected_returncodes,
        f"{case_id}: unexpected return code {completed.returncode}: {completed.stderr}",
    )
    payload = load_payload(completed, summary_path)
    artifacts = validate_payload(payload, case_id=case_id, expected_statuses=expected_statuses)
    if run_dir is not None:
        validate_run_bundle(run_dir, case_id)
    after = {str(path): hash_path(path) for path in watched_inputs}
    require(before == after, f"{case_id}: input was modified")
    return {
        "case": case_id,
        "target": target,
        "command": " ".join(command),
        "returncode": completed.returncode,
        "app_status": app_status(payload),
        "artifact_count": len(artifacts),
        "summary_json": str(summary_path),
        "input_modified": False,
        "status": "PASS",
    }


def write_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# v1.9 Priority More App-Like Regressions",
        "",
        "| Target | Case | App status | Artifacts | Input modified |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['target']}` | `{row['case']}` | `{row['app_status']}` | {row['artifact_count']} | {row['input_modified']} |"
        )
    lines.extend(
        [
            "",
            "## Backlog",
            "",
            "- Optional backend positive paths remain outside this priority pass.",
            "- GUI/platform preview flows remain targeted or v2.0 work.",
            "- Helper migration stays in Deuda F/G1.",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    assert_doc()
    fixtures = make_fixtures()
    rows: list[dict[str, Any]] = []

    profile_summary = RUNS / "profile_table_imperfect" / "summary.json"
    rows.append(
        run_case(
            case_id="profile_table_duplicate_inf_null",
            target="profile_table.py",
            command=[str(PYTHON), str(SCRIPTS / "profile_table.py"), str(fixtures["imperfect_table"]), "--summary-json", str(profile_summary)],
            summary_path=profile_summary,
            input_path=fixtures["imperfect_table"],
            expected_statuses={"WARNING"},
        )
    )

    cross_run = RUNS / "cross_domain_mixed_warning" / "run"
    rows.append(
        run_case(
            case_id="cross_domain_mixed_warning",
            target="cross_domain_data_workbench.py",
            command=[str(PYTHON), str(SCRIPTS / "cross_domain_data_workbench.py"), str(fixtures["mixed_project"]), "--run-dir", str(cross_run), "--max-files", "4"],
            summary_path=cross_run / "summary.json",
            input_path=fixtures["mixed_project"],
            expected_statuses={"PASS", "WARNING"},
            run_dir=cross_run,
        )
    )

    diff_summary = RUNS / "semantic_diff_row_change" / "summary.json"
    diff_report = RUNS / "semantic_diff_row_change" / "report.md"
    rows.append(
        run_case(
            case_id="semantic_diff_row_count_change",
            target="semantic_diff.py",
            command=[
                str(PYTHON),
                str(SCRIPTS / "semantic_diff.py"),
                str(fixtures["baseline_csv"]),
                str(fixtures["candidate_csv"]),
                "--summary-json",
                str(diff_summary),
                "--output-md",
                str(diff_report),
            ],
            summary_path=diff_summary,
            input_path=fixtures["baseline_csv"],
            extra_inputs=[fixtures["candidate_csv"]],
            expected_statuses={"WARNING"},
        )
    )

    fidelity_summary = RUNS / "notebook_fidelity_risky" / "summary.json"
    fidelity_report = RUNS / "notebook_fidelity_risky" / "report.md"
    rows.append(
        run_case(
            case_id="coursework_notebook_fidelity_risky",
            target="coursework_notebook_fidelity_check.py",
            command=[
                str(PYTHON),
                str(SCRIPTS / "coursework_notebook_fidelity_check.py"),
                str(fixtures["risky_notebook"]),
                "--assignment-file",
                str(fixtures["assignment"]),
                "--summary-json",
                str(fidelity_summary),
                "--report-md",
                str(fidelity_report),
            ],
            summary_path=fidelity_summary,
            input_path=fixtures["risky_notebook"],
            expected_statuses={"WARNING"},
        )
    )

    branch_summary = RUNS / "notebook_branch_missing_output" / "summary.json"
    branch_out = RUNS / "notebook_branch_missing_output" / "out"
    rows.append(
        run_case(
            case_id="notebook_branch_missing_output",
            target="notebook_branch_compare.py",
            command=[
                str(PYTHON),
                str(SCRIPTS / "notebook_branch_compare.py"),
                str(fixtures["branches"]),
                "--output-dir",
                str(branch_out),
                "--summary-json",
                str(branch_summary),
            ],
            summary_path=branch_summary,
            input_path=fixtures["branches"],
            expected_statuses={"WARNING"},
        )
    )

    ts_out = RUNS / "timeseries_duplicate_dates" / "out"
    ts_summary = RUNS / "timeseries_duplicate_dates" / "summary.json"
    ts_manifest = RUNS / "timeseries_duplicate_dates" / "manifest.json"
    rows.append(
        run_case(
            case_id="timeseries_duplicate_unparseable_dates",
            target="timeseries_forecasting_workbench.py",
            command=[
                str(PYTHON),
                str(SCRIPTS / "timeseries_forecasting_workbench.py"),
                "--output-dir",
                str(ts_out),
                "--data-path",
                str(fixtures["time_series"]),
                "--date-column",
                "date",
                "--value-column",
                "value",
                "--frequency",
                "MS",
                "--test-horizon",
                "2",
                "--summary-json",
                str(ts_summary),
                "--manifest-json",
                str(ts_manifest),
            ],
            summary_path=ts_summary,
            input_path=fixtures["time_series"],
            expected_statuses={"WARNING"},
        )
    )

    zip_run = RUNS / "inspect_container_unsafe_zip" / "run"
    rows.append(
        run_case(
            case_id="inspect_container_unsafe_zip",
            target="inspect_data_container.py",
            command=[str(PYTHON), str(SCRIPTS / "inspect_data_container.py"), str(fixtures["unsafe_zip"]), "--run-dir", str(zip_run)],
            summary_path=zip_run / "summary.json",
            input_path=fixtures["unsafe_zip"],
            expected_statuses={"WARNING"},
            run_dir=zip_run,
        )
    )

    write_report(rows)
    output = {
        "status": "PASS",
        "check": "v1.9 priority more app-like regression",
        "case_count": len(rows),
        "cases": rows,
        "report_md": str(REPORT),
        "backlog": [
            "Optional backend positive paths remain outside this priority pass.",
            "GUI/platform preview flows remain targeted or v2.0 work.",
            "Helper migration stays in Deuda F/G1.",
        ],
    }
    SUMMARY.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
