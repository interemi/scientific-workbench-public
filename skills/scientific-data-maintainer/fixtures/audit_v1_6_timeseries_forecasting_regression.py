#!/usr/bin/env python3
"""Narrow v1.6 regression for timeseries_forecasting_workbench."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMESERIES = ROOT / "scripts" / "timeseries_forecasting_workbench.py"
NOTEBOOK = ROOT / "scripts" / "notebook_workbench.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_series(path: Path, rows: int = 40, *, duplicate: bool = False, missing: bool = False) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "value"])
        for index in range(rows):
            year = 2020 + index // 12
            month = index % 12 + 1
            value = 100.0 + 0.4 * index + 2.0 * math.sin(index / 4.0)
            row_value = "" if missing and index in {8, 15} else f"{value:.6f}"
            writer.writerow([f"{year:04d}-{month:02d}-01", row_value])
            if duplicate and index == 10:
                writer.writerow([f"{year:04d}-{month:02d}-01", f"{value + 1.0:.6f}"])


def write_missing_target(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date"])
        writer.writerow(["2020-01-01"])
        writer.writerow(["2020-02-01"])


def assert_no_traceback(result: subprocess.CompletedProcess, label: str) -> None:
    require("Traceback" not in f"{result.stdout}\n{result.stderr}", f"{label} leaked a traceback")


def assert_blocked(result: subprocess.CompletedProcess, summary: Path, expected_text: str, label: str) -> None:
    assert_no_traceback(result, label)
    require(result.returncode == 2, f"{label} should return 2")
    payload = read_json(summary)
    require(payload["status"] == "blocked", f"{label} did not emit blocked status")
    require(expected_text in payload["results"]["blocked_reason"], f"{label} missed expected reason")


def notebook_exec_sandbox_blocked(payload: dict) -> bool:
    run = payload.get("results", {}).get("run", {})
    assessment = run.get("assessment", {}) if isinstance(run, dict) else {}
    return payload.get("status") == "blocked" and assessment.get("status") == "sandbox_blocked"


def check_happy_executes(tmp: Path) -> None:
    data = tmp / "series.csv"
    write_series(data, rows=42)
    output_dir = tmp / "happy"
    summary = tmp / "happy.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(output_dir),
            "--data-path",
            str(data),
            "--date-column",
            "date",
            "--value-column",
            "value",
            "--test-horizon",
            "3",
            "--summary-json",
            str(summary),
            "--overwrite",
        ]
    )
    require(result.returncode == 0, f"happy scaffold failed: {result.stderr}")
    payload = read_json(summary)
    require(payload["status"] == "ok", "happy scaffold should be ok")
    notebook_path = output_dir / "timeseries_forecasting_notebook.ipynb"
    require(notebook_path.exists(), "happy scaffold missed notebook")

    exec_summary = tmp / "happy_exec.json"
    result = run(
        [
            sys.executable,
            str(NOTEBOOK),
            "execute-copy",
            str(notebook_path),
            "--output-dir",
            str(tmp / "happy_exec"),
            "--timeout-sec",
            "180",
            "--summary-json",
            str(exec_summary),
        ],
        timeout=240,
    )
    require(result.returncode == 0, f"generated notebook execution failed: {result.stderr}")
    assert_no_traceback(result, "generated notebook execution")
    exec_payload = read_json(exec_summary)
    if notebook_exec_sandbox_blocked(exec_payload):
        return
    workspace = Path(exec_payload["results"]["run"]["workspace_dir"])
    require((workspace / "timeseries_outputs" / "metrics_summary.csv").exists(), "executed notebook missed metrics export")
    require((workspace / "timeseries_outputs" / "future_3_step_forecast.csv").exists(), "executed notebook missed horizon-specific forecast export")


def check_warning_and_blocks(tmp: Path) -> None:
    edge = tmp / "edge.csv"
    write_series(edge, rows=36, duplicate=True, missing=True)
    edge_summary = tmp / "edge.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(tmp / "edge"),
            "--data-path",
            str(edge),
            "--test-horizon",
            "3",
            "--summary-json",
            str(edge_summary),
            "--overwrite",
        ]
    )
    require(result.returncode == 0, f"edge warning scaffold failed: {result.stderr}")
    payload = read_json(edge_summary)
    require(payload["status"] == "warning", "duplicate/missing data should promote warning status")
    require(payload["qa"]["findings"], "warning payload missed findings")

    invalid_horizon_summary = tmp / "invalid_horizon.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(tmp / "invalid_horizon"),
            "--data-path",
            str(edge),
            "--test-horizon",
            "0",
            "--summary-json",
            str(invalid_horizon_summary),
            "--overwrite",
        ]
    )
    assert_blocked(result, invalid_horizon_summary, "--test-horizon", "invalid horizon")

    bad_name_summary = tmp / "bad_name.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(tmp / "bad_name"),
            "--data-path",
            str(edge),
            "--notebook-name",
            "../escape.ipynb",
            "--summary-json",
            str(bad_name_summary),
            "--overwrite",
        ]
    )
    assert_blocked(result, bad_name_summary, "--notebook-name", "bad notebook name")

    missing_target = tmp / "missing_target.csv"
    write_missing_target(missing_target)
    missing_target_summary = tmp / "missing_target.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(tmp / "missing_target"),
            "--data-path",
            str(missing_target),
            "--date-column",
            "date",
            "--value-column",
            "value",
            "--summary-json",
            str(missing_target_summary),
            "--overwrite",
        ]
    )
    assert_blocked(result, missing_target_summary, "value column", "missing target column")

    conflict = tmp / "not_a_directory"
    conflict.write_text("not a directory\n", encoding="utf-8")
    conflict_summary = tmp / "conflict.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(conflict),
            "--data-path",
            str(edge),
            "--summary-json",
            str(conflict_summary),
            "--overwrite",
        ]
    )
    assert_blocked(result, conflict_summary, "--output-dir", "output-dir conflict")

    existing_dir = tmp / "existing"
    first = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(existing_dir),
            "--data-path",
            str(edge),
            "--summary-json",
            str(tmp / "existing_first.json"),
            "--overwrite",
        ]
    )
    require(first.returncode == 0, f"precreate existing notebook failed: {first.stderr}")
    existing_summary = tmp / "existing_second.json"
    result = run(
        [
            sys.executable,
            str(TIMESERIES),
            "--output-dir",
            str(existing_dir),
            "--data-path",
            str(edge),
            "--summary-json",
            str(existing_summary),
        ]
    )
    assert_blocked(result, existing_summary, "already exists", "existing notebook without overwrite")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="timeseries_forecasting_regression_") as raw:
        tmp = Path(raw)
        check_happy_executes(tmp)
        check_warning_and_blocks(tmp)
    print("timeseries_forecasting v1.6 regression: PASS")


if __name__ == "__main__":
    main()
