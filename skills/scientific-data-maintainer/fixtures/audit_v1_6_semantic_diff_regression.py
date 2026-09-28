#!/usr/bin/env python3
"""Regression checks for v1.6 semantic_diff edge handling."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SEMANTIC_DIFF = SCRIPT_DIR / "semantic_diff.py"


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


def run_diff(tmp: Path, name: str, baseline: Path, candidate: Path, *extra: str) -> tuple[subprocess.CompletedProcess, dict]:
    summary = tmp / f"{name}.json"
    command = [
        sys.executable,
        str(SEMANTIC_DIFF),
        str(baseline),
        str(candidate),
        "--summary-json",
        str(summary),
        *extra,
    ]
    result = subprocess.run(command, cwd=SCRIPT_DIR.parent, capture_output=True, text=True)
    assert "Traceback (most recent call last)" not in result.stdout
    assert "Traceback (most recent call last)" not in result.stderr
    assert summary.exists(), f"summary was not written for {name}"
    return result, json.loads(summary.read_text(encoding="utf-8"))


def check_portable_csv_diff(tmp: Path) -> None:
    baseline = write_csv(tmp / "portable_left.csv", [["id", "flux"], ["A", "1.0"], ["B", "2.0"]])
    candidate = write_csv(tmp / "portable_right.csv", [["id", "flux", "note"], ["A", "1.0", ""], ["B", "2.4", "recalc"]])
    result, payload = run_diff(tmp, "portable_csv", baseline, candidate)
    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert payload["results"]["comparison_type"] == "table"
    assert payload["results"]["columns_added"] == ["note"]
    assert payload["results"]["cell_changes"][0]["column"] == "flux"
    assert payload["results"]["reader_backends"]["baseline"] in {"astropy", "csv"}


def check_table_warning_edges(tmp: Path) -> None:
    baseline = write_csv(tmp / "edge_left.csv", [["id", "flux"], ["A", "1.0"], ["B", "2.0"]])
    candidate = write_csv(tmp / "edge_right.csv", [["source", "mag"], ["X", "12.3"]])
    result, payload = run_diff(tmp, "edge_warning", baseline, candidate)
    assert result.returncode == 0
    assert payload["qa"]["status"] == "warning"
    assert any("Row count changed" in item for item in payload["qa"]["findings"])
    assert any("No common columns" in item for item in payload["qa"]["findings"])


def check_failures_are_clean(tmp: Path) -> None:
    bad_xlsx = tmp / "bad.xlsx"
    bad_xlsx.write_text("not a real workbook", encoding="utf-8")
    result, payload = run_diff(tmp, "bad_xlsx", bad_xlsx, bad_xlsx)
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"

    document = tmp / "note.md"
    document.write_text("# Note\n\nA short document.\n", encoding="utf-8")
    result, payload = run_diff(tmp, "mismatched_inputs", bad_xlsx, document)
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert "Input types differ" in payload["results"]["error"]


def check_markdown_parent_created(tmp: Path) -> None:
    baseline = tmp / "left.md"
    candidate = tmp / "right.md"
    baseline.write_text("Alpha\n", encoding="utf-8")
    candidate.write_text("Alpha beta\n", encoding="utf-8")
    output_md = tmp / "nested" / "reports" / "diff.md"
    result, payload = run_diff(tmp, "document_diff", baseline, candidate, "--output-md", str(output_md))
    assert result.returncode == 0
    assert payload["results"]["comparison_type"] == "document"
    assert output_md.exists()


def main() -> int:
    checks = [
        check_portable_csv_diff,
        check_table_warning_edges,
        check_failures_are_clean,
        check_markdown_parent_created,
    ]
    with tempfile.TemporaryDirectory(prefix="semantic_diff_v1_6_") as raw:
        tmp = Path(raw)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All semantic_diff v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
