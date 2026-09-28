#!/usr/bin/env python3
"""Regression checks for v1.6 cross_domain_data_workbench edge handling."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
WORKBENCH = SCRIPT_DIR / "cross_domain_data_workbench.py"


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


def run_workbench(tmp: Path, name: str, inputs: list[Path], *extra: str, output_as_file: bool = False) -> tuple[subprocess.CompletedProcess, dict]:
    output_dir = tmp / f"{name}_out"
    if output_as_file:
        output_dir.write_text("not a directory", encoding="utf-8")
    summary = tmp / f"{name}.json"
    command = [
        sys.executable,
        str(WORKBENCH),
        *[str(path) for path in inputs],
        "--output-dir",
        str(output_dir),
        "--summary-json",
        str(summary),
        *extra,
    ]
    result = subprocess.run(command, cwd=SCRIPT_DIR.parent, capture_output=True, text=True)
    assert "Traceback (most recent call last)" not in result.stdout
    assert "Traceback (most recent call last)" not in result.stderr
    assert summary.exists(), f"summary was not written for {name}"
    return result, json.loads(summary.read_text(encoding="utf-8"))


def check_basic_bundle(tmp: Path) -> None:
    dataset = tmp / "basic"
    write_csv(dataset / "sample.csv", [["id", "value"], ["A", "1.0"], ["B", "2.0"]])
    result, payload = run_workbench(tmp, "basic", [dataset])
    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert payload["results"]["file_count"] == 1
    assert Path(tmp / "basic_out" / "inventory.csv").exists()
    assert Path(tmp / "basic_out" / "report.md").exists()


def check_profile_failure_is_warning(tmp: Path) -> None:
    dataset = tmp / "mixed"
    write_csv(dataset / "good.csv", [["id", "value"], ["A", "1.0"]])
    (dataset / "broken.csv").write_text('"id,value\nA,1\nB,"unterminated', encoding="utf-8")
    result, payload = run_workbench(tmp, "mixed", [dataset])
    assert result.returncode == 0
    assert payload["status"] == "warning"
    assert payload["qa"]["status"] == "warning"
    assert any(not item["profile_ok"] for item in payload["results"]["files"])


def check_profile_quality_warning_propagates(tmp: Path) -> None:
    dataset = tmp / "quality_warning"
    write_csv(dataset / "sample.csv", [["id", "amount"], ["A", "1.0"], ["B", "inf"]])
    result, payload = run_workbench(tmp, "quality_warning", [dataset])
    assert result.returncode == 0
    assert payload["status"] == "warning"
    assert payload["qa"]["status"] == "warning"
    assert any("infinite numeric" in finding for finding in payload["qa"]["findings"])
    first = payload["results"]["files"][0]
    assert first["profile_status"] == "warning"
    assert any("infinite numeric" in finding for finding in first["profile_findings"])


def check_no_tables_fails_cleanly(tmp: Path) -> None:
    missing = tmp / "missing"
    result, payload = run_workbench(tmp, "missing", [missing])
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"
    assert payload["results"]["input_issues"][0]["reason"] == "missing"


def check_output_path_file_fails_cleanly(tmp: Path) -> None:
    dataset = tmp / "out_file_input"
    path = write_csv(dataset / "sample.csv", [["id", "value"], ["A", "1.0"]])
    result, payload = run_workbench(tmp, "output_file", [path], output_as_file=True)
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert "not a directory" in payload["results"]["error"]


def check_bad_sql_is_warning_not_false_success(tmp: Path) -> None:
    dataset = tmp / "bad_sql_input"
    write_csv(dataset / "sample.csv", [["id", "value"], ["A", "1.0"]])
    result, payload = run_workbench(tmp, "bad_sql", [dataset], "--sql", "SELECT * FROM missing_alias")
    assert result.returncode == 0
    assert payload["status"] == "warning"
    assert payload["qa"]["status"] == "warning"
    assert payload["results"]["sql"]["executed"] is True
    assert payload["results"]["sql"]["success"] is False


def check_sql_with_datetime_workbook_is_serializable(tmp: Path) -> None:
    try:
        import pandas as pd
    except ImportError:
        print("SKIP check_sql_with_datetime_workbook_is_serializable: pandas unavailable")
        return

    dataset = tmp / "datetime_sql"
    write_csv(dataset / "sample.csv", [["id", "value"], ["A", "1.0"], ["B", "2.0"]])
    pd.DataFrame(
        {
            "id": ["A", "B"],
            "observed_at": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "score": [1.5, 2.5],
        }
    ).to_excel(dataset / "dates.xlsx", index=False)
    result, payload = run_workbench(tmp, "datetime_sql", [dataset], "--sql", "SELECT * FROM source1 LIMIT 2")
    sql = payload["results"]["sql"]
    if sql.get("success") is False and "DuckDB is not installed" in str(sql.get("error")):
        print("SKIP check_sql_with_datetime_workbook_is_serializable: duckdb unavailable")
        return
    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert sql["success"] is True
    assert sql["result_rows"] == 2


def main() -> int:
    checks = [
        check_basic_bundle,
        check_profile_failure_is_warning,
        check_profile_quality_warning_propagates,
        check_no_tables_fails_cleanly,
        check_output_path_file_fails_cleanly,
        check_bad_sql_is_warning_not_false_success,
        check_sql_with_datetime_workbook_is_serializable,
    ]
    with tempfile.TemporaryDirectory(prefix="cross_domain_workbench_v1_6_") as raw:
        tmp = Path(raw)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All cross_domain_data_workbench v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
