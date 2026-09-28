#!/usr/bin/env python3
"""Narrow v1.6 regression for spectra_ascii_coursework_workbench."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spectra_ascii_coursework_workbench.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=120)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def spectrum(path: Path, *, samples: int = 180, shift: float = 0.0, edge: bool = False) -> None:
    rows = []
    for index in range(samples):
        wavelength = 6500.0 + 100.0 * index / (samples - 1) + shift
        flux = 1.0 - 0.22 * math.exp(-0.5 * ((wavelength - 6563.0 - shift) / 2.0) ** 2)
        if edge and index % 13 == 0:
            flux += 3.5
        rows.append([wavelength, flux])
    if edge and samples > 45:
        rows[31][0] = rows[30][0]
        rows[43][0] = rows[42][0] - 0.5
    path.write_text("\n".join(f"{x:.6f} {y:.8f}" for x, y in rows) + "\n", encoding="utf-8")


def write_notebook(path: Path, code: str) -> None:
    payload = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "# Regression notebook"},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": code},
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def assert_no_traceback(result: subprocess.CompletedProcess, label: str) -> None:
    blob = f"{result.stdout}\n{result.stderr}"
    require("Traceback" not in blob, f"{label} leaked a traceback")


def check_happy_and_warning(tmp: Path) -> None:
    good = tmp / "good.txt"
    shifted = tmp / "shifted.txt"
    edge = tmp / "edge.txt"
    spectrum(good)
    spectrum(shifted, shift=0.25)
    spectrum(edge, samples=80, edge=True)

    summary = tmp / "happy.json"
    output_dir = tmp / "happy_bundle"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(good),
            str(shifted),
            "--output-dir",
            str(output_dir),
            "--line-window",
            "Halpha",
            "6558",
            "6568",
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 0, f"happy bundle failed: {result.stderr}")
    payload = read_json(summary)
    require(payload["status"] == "ok", "heuristic line-window note should not force a warning by itself")
    require((output_dir / "spectra_analysis" / "spectrum_inventory.csv").exists(), "happy bundle missed inventory")

    warning_summary = tmp / "edge.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(edge),
            "--output-dir",
            str(tmp / "edge_bundle"),
            "--skip-report-project",
            "--summary-json",
            str(warning_summary),
        ]
    )
    require(result.returncode == 0, f"edge spectrum should warn without failing: {result.stderr}")
    payload = read_json(warning_summary)
    require(payload["status"] == "warning", "edge spectrum did not promote quality flags to warning")
    require(any("Wavelength axis" in item for item in payload["qa"]["findings"]), "missing wavelength warning")


def check_notebook_execution_and_blocks(tmp: Path) -> None:
    good = tmp / "good.txt"
    spectrum(good)
    notebook = tmp / "ok.ipynb"
    input_notebook = tmp / "input.ipynb"
    write_notebook(notebook, "x = 2 + 2\nprint('x', x)")
    write_notebook(input_notebook, "name = input('name? ')\nprint(name)")

    summary = tmp / "notebook_ok.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(good),
            "--output-dir",
            str(tmp / "notebook_ok_bundle"),
            "--notebook",
            str(notebook),
            "--execute-notebook",
            "--timeout-sec",
            "30",
            "--skip-report-project",
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 0, f"simple notebook execution failed: {result.stderr}")
    payload = read_json(summary)
    require(payload["status"] == "ok", "successful copied notebook execution should stay ok")
    require(payload["results"]["notebook_execution"]["success"] is True, "notebook success was not recorded")

    blocked_summary = tmp / "input_blocked.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(good),
            "--output-dir",
            str(tmp / "input_blocked_bundle"),
            "--notebook",
            str(input_notebook),
            "--execute-notebook",
            "--skip-report-project",
            "--summary-json",
            str(blocked_summary),
        ]
    )
    assert_no_traceback(result, "input notebook block")
    require(result.returncode == 2, "input notebook should block before execution")
    payload = read_json(blocked_summary)
    require(payload["status"] == "blocked", "input notebook did not emit blocked status")
    require("input()" in payload["results"]["blocked_reason"], "blocked reason missed input()")

    low_timeout_summary = tmp / "low_timeout.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(good),
            "--output-dir",
            str(tmp / "low_timeout_bundle"),
            "--notebook",
            str(notebook),
            "--execute-notebook",
            "--timeout-sec",
            "1",
            "--skip-report-project",
            "--summary-json",
            str(low_timeout_summary),
        ]
    )
    assert_no_traceback(result, "low timeout block")
    require(result.returncode == 2, "too-low timeout should block cleanly")
    require(read_json(low_timeout_summary)["status"] == "blocked", "too-low timeout did not emit blocked status")


def check_broken_inputs_block(tmp: Path) -> None:
    good = tmp / "good.txt"
    spectrum(good)

    missing_summary = tmp / "missing.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(tmp / "missing.txt"),
            "--output-dir",
            str(tmp / "missing_bundle"),
            "--skip-report-project",
            "--summary-json",
            str(missing_summary),
        ]
    )
    assert_no_traceback(result, "missing spectrum block")
    require(result.returncode == 2, "missing spectrum should block cleanly")
    require(read_json(missing_summary)["status"] == "blocked", "missing spectrum did not emit blocked status")

    output_file = tmp / "not_a_directory"
    output_file.write_text("not a directory\n", encoding="utf-8")
    conflict_summary = tmp / "conflict.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(good),
            "--output-dir",
            str(output_file),
            "--skip-report-project",
            "--summary-json",
            str(conflict_summary),
        ]
    )
    assert_no_traceback(result, "output conflict block")
    require(result.returncode == 2, "output-dir file conflict should block cleanly")
    payload = read_json(conflict_summary)
    require(payload["status"] == "blocked", "output conflict did not emit blocked status")
    require("--output-dir" in payload["results"]["blocked_reason"], "output conflict reason missed --output-dir")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="spectra_ascii_coursework_regression_") as raw:
        tmp = Path(raw)
        check_happy_and_warning(tmp)
        check_notebook_execution_and_blocks(tmp)
        check_broken_inputs_block(tmp)
    print("spectra_ascii_coursework v1.6 regression: PASS")


if __name__ == "__main__":
    main()
