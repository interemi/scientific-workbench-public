#!/usr/bin/env python3
"""Regression checks for v1.6 profile_table edge handling."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_TABLE = SCRIPT_DIR / "profile_table.py"


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


def run_profile(tmp: Path, name: str, path: Path) -> tuple[subprocess.CompletedProcess, dict, str]:
    summary = tmp / f"{name}.json"
    command = [sys.executable, str(PROFILE_TABLE), str(path), "--summary-json", str(summary)]
    result = subprocess.run(command, cwd=SCRIPT_DIR.parent, capture_output=True, text=True)
    assert "Traceback (most recent call last)" not in result.stdout
    assert "Traceback (most recent call last)" not in result.stderr
    assert summary.exists(), f"summary was not written for {name}"
    raw = summary.read_text(encoding="utf-8")
    return result, json.loads(raw), raw


def check_simple_csv_passes(tmp: Path) -> None:
    path = write_csv(tmp / "simple.csv", [["id", "flux"], ["A", "1.0"], ["B", "2.0"]])
    result, payload, _ = run_profile(tmp, "simple", path)
    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert payload["results"]["rows"] == 2
    assert payload["results"]["columns"] == 2


def check_duplicate_and_infinite_values_warn_without_nonstandard_json(tmp: Path) -> None:
    path = write_csv(
        tmp / "edge.csv",
        [["id", "flux", "flux"], ["A", "1.0", "NaN"], ["B", "inf", "2.0"]],
    )
    result, payload, raw = run_profile(tmp, "edge", path)
    assert result.returncode == 0
    assert payload["status"] == "warning"
    assert payload["qa"]["status"] == "warning"
    assert payload["qa"]["metrics"]["suspected_duplicate_column_count"] == 1
    assert payload["qa"]["metrics"]["infinite_value_count"] == 1
    assert ": NaN" not in raw
    assert ": Infinity" not in raw
    assert ": -Infinity" not in raw


def check_malformed_csv_fails_cleanly(tmp: Path) -> None:
    path = tmp / "broken.csv"
    path.write_text('"id,flux\nA,1.0\nB,"unterminated', encoding="utf-8")
    result, payload, _ = run_profile(tmp, "broken", path)
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"
    assert "line break" in payload["results"]["error"]


def check_misleading_extension_fails_with_summary(tmp: Path) -> None:
    path = tmp / "misleading.xlsx"
    path.write_text("id,flux\nA,1.0\n", encoding="utf-8")
    result, payload, _ = run_profile(tmp, "misleading", path)
    assert result.returncode == 2
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"


def check_datetime_xlsx_is_serializable(tmp: Path) -> None:
    try:
        import pandas as pd
    except ImportError:
        print("SKIP check_datetime_xlsx_is_serializable: pandas unavailable")
        return

    path = tmp / "dates.xlsx"
    pd.DataFrame(
        {
            "id": ["A", "B"],
            "observed_at": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "value": [1.0, 2.0],
        }
    ).to_excel(path, index=False)
    result, payload, raw = run_profile(tmp, "dates", path)
    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert "2026-01-01T00:00:00" in raw or "2026-01-01 00:00:00" in raw


def main() -> int:
    checks = [
        check_simple_csv_passes,
        check_duplicate_and_infinite_values_warn_without_nonstandard_json,
        check_malformed_csv_fails_cleanly,
        check_misleading_extension_fails_with_summary,
        check_datetime_xlsx_is_serializable,
    ]
    with tempfile.TemporaryDirectory(prefix="profile_table_v1_6_") as raw:
        tmp = Path(raw)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All profile_table v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
