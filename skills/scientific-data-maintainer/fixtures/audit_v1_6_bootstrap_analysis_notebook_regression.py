#!/usr/bin/env python3
"""Regression tests for bootstrap_analysis_notebook.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "bootstrap_analysis_notebook.py"


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


def check_success_summary_manifest_and_metadata(tmp: Path) -> None:
    data = tmp / "measurements.csv"
    data.write_text("id,value\nA,1\nB,2\n", encoding="utf-8")
    notebook = tmp / "success.ipynb"
    summary = tmp / "success.json"
    manifest = tmp / "success_manifest.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(notebook),
            "--title",
            "Regression Notebook",
            "--domain",
            "general",
            "--language",
            "es",
            "--data-path",
            str(data),
            "--summary-json",
            str(summary),
            "--manifest-json",
            str(manifest),
        ],
        tmp,
    )
    payload = read_json(summary)
    assert payload["status"] == "warning"
    assert payload["qa"]["metrics"]["cell_count"] >= 10
    assert notebook.exists()
    assert manifest.exists()
    nb = read_json(notebook)
    assert nb["nbformat"] == 4
    assert nb["metadata"]["scientific_data_analysis"]["tool"] == "bootstrap_analysis_notebook.py"
    sources = "\n".join("".join(cell.get("source", [])) for cell in nb["cells"])
    assert "## Carga inicial de datos" in sources
    assert "Data path is absolute" in "\n".join(payload["results"]["warnings"])


def check_existing_output_blocks_without_overwrite(tmp: Path) -> None:
    notebook = tmp / "existing.ipynb"
    summary = tmp / "existing_summary.json"
    notebook.write_text('{"sentinel": true}\n', encoding="utf-8")
    before = notebook.read_text(encoding="utf-8")
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(notebook),
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    payload = read_json(summary)
    assert payload["status"] == "blocked"
    assert notebook.read_text(encoding="utf-8") == before


def check_invalid_parent_fails_cleanly(tmp: Path) -> None:
    blocked_parent = tmp / "not_a_directory"
    blocked_parent.write_text("file, not directory", encoding="utf-8")
    summary = tmp / "bad_parent_summary.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(blocked_parent / "child.ipynb"),
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    payload = read_json(summary)
    assert payload["status"] == "fail"
    assert "Output parent exists but is not a directory" in "\n".join(payload["results"]["blockers"])


def check_unsafe_output_dir_name_blocks(tmp: Path) -> None:
    summary = tmp / "unsafe_output_dir.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(tmp / "unsafe.ipynb"),
            "--output-dir-name",
            "../outside",
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    payload = read_json(summary)
    assert payload["status"] == "fail"
    assert ".." in "\n".join(payload["results"]["blockers"])


def check_notebook_data_path_warns(tmp: Path) -> None:
    source_nb = tmp / "professor.ipynb"
    source_nb.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}\n', encoding="utf-8")
    notebook = tmp / "student_scaffold.ipynb"
    summary = tmp / "student_scaffold.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(notebook),
            "--data-path",
            str(source_nb),
            "--summary-json",
            str(summary),
        ],
        tmp,
    )
    payload = read_json(summary)
    assert payload["status"] == "warning"
    warnings = "\n".join(payload["results"]["warnings"])
    assert "professor-provided notebook" in warnings
    nb = read_json(notebook)
    assert any("professor-provided notebook" in item for item in nb["metadata"]["scientific_data_analysis"]["warnings"])


def main() -> None:
    checks = [
        check_success_summary_manifest_and_metadata,
        check_existing_output_blocks_without_overwrite,
        check_invalid_parent_fails_cleanly,
        check_unsafe_output_dir_name_blocks,
        check_notebook_data_path_warns,
    ]
    with tempfile.TemporaryDirectory(prefix="sda_bootstrap_notebook_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All bootstrap_analysis_notebook regressions passed.")


if __name__ == "__main__":
    main()
