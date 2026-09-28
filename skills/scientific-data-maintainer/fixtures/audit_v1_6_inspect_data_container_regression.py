#!/usr/bin/env python3
"""Regression tests for inspect_data_container.py."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "inspect_data_container.py"


def run_cmd(args: list[str], cwd: Path, expect_ok: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Unexpected traceback for {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command succeeded unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}")
    return completed


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_npz_success(tmp: Path) -> None:
    path = tmp / "arrays.npz"
    summary = tmp / "arrays.json"
    np.savez(path, flux=np.linspace(0.0, 1.0, 6), image=np.arange(9).reshape(3, 3))
    run_cmd([sys.executable, str(TOOL), str(path), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    assert payload["status"] == "ok"
    assert payload["results"]["method"] == "numpy"
    assert "flux" in payload["results"]["arrays"]


def check_sqlite_success(tmp: Path) -> None:
    path = tmp / "measurements.sqlite"
    summary = tmp / "measurements.json"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE measurements (id INTEGER PRIMARY KEY, value REAL)")
        conn.executemany("INSERT INTO measurements (value) VALUES (?)", [(1.0,), (2.0,), (3.0,)])
        conn.commit()
    finally:
        conn.close()
    run_cmd([sys.executable, str(TOOL), str(path), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    assert payload["status"] == "ok"
    assert payload["results"]["tables"]["measurements"]["row_count"] == 3


def check_unsafe_archive_warns(tmp: Path) -> None:
    path = tmp / "unsafe.zip"
    summary = tmp / "unsafe.json"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("data/table.csv", "x,y\n1,2\n")
        zf.writestr("../outside.txt", "unsafe")
        zf.writestr("/absolute/path.txt", "unsafe")
    run_cmd([sys.executable, str(TOOL), str(path), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    assert payload["status"] == "warning"
    assert payload["qa"]["status"] == "warning"
    assert "../outside.txt" in payload["results"]["unsafe_members"]


def check_corrupt_archive_falls_back(tmp: Path) -> None:
    path = tmp / "corrupt.zip"
    summary = tmp / "corrupt.json"
    path.write_bytes(b"PK\x03\x04truncated")
    run_cmd([sys.executable, str(TOOL), str(path), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    assert payload["status"] == "warning"
    assert payload["results"]["method"] == "recovery_fallback"


def check_unsupported_and_missing_block_with_json(tmp: Path) -> None:
    unsupported = tmp / "table.csv"
    unsupported_summary = tmp / "unsupported.json"
    unsupported.write_text("a,b\n1,2\n", encoding="utf-8")
    run_cmd(
        [sys.executable, str(TOOL), str(unsupported), "--summary-json", str(unsupported_summary)],
        tmp,
        expect_ok=False,
    )
    payload = read_json(unsupported_summary)
    assert payload["status"] == "blocked"
    assert "Unsupported container type" in payload["results"]["error"]

    missing_summary = tmp / "missing.json"
    run_cmd(
        [sys.executable, str(TOOL), str(tmp / "missing.zip"), "--summary-json", str(missing_summary)],
        tmp,
        expect_ok=False,
    )
    payload = read_json(missing_summary)
    assert payload["status"] == "blocked"
    assert "File not found" in payload["results"]["error"]


def main() -> None:
    checks = [
        check_npz_success,
        check_sqlite_success,
        check_unsafe_archive_warns,
        check_corrupt_archive_falls_back,
        check_unsupported_and_missing_block_with_json,
    ]
    with tempfile.TemporaryDirectory(prefix="sda_inspect_container_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All inspect_data_container regressions passed.")


if __name__ == "__main__":
    main()
