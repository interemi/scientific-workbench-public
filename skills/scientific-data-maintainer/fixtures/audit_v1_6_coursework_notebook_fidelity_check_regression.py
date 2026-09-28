#!/usr/bin/env python3
"""v1.6 regression checks for coursework_notebook_fidelity_check.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "coursework_notebook_fidelity_check.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def run_tool(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def read_json(path: Path) -> dict:
    if not path.exists():
        fail(f"summary_json was not written: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_envelope(path: Path, status: str) -> dict:
    payload = read_json(path)
    if payload.get("tool") != "coursework_notebook_fidelity_check":
        fail(f"unexpected tool id: {payload.get('tool')}")
    if payload.get("status") != status:
        fail(f"expected status {status}, got {payload.get('status')}")
    qa = payload.get("qa")
    if not isinstance(qa, dict) or qa.get("status") != status:
        fail(f"expected qa.status {status}, got {qa}")
    return payload


def no_traceback(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if "Traceback (most recent call last)" in proc.stdout or "Traceback (most recent call last)" in proc.stderr:
        fail(f"{label} emitted a raw traceback")


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code(source: str, outputs: list[dict] | None = None) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source,
        "outputs": outputs or [],
        "execution_count": None,
    }


def write_notebook(path: Path, cells: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook(cells), indent=2), encoding="utf-8")
    return path


def write_fixtures(tmp: Path) -> dict[str, Path]:
    fixtures = tmp / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    clean = write_notebook(
        fixtures / "clean.ipynb",
        [
            md("# Coursework\n\nQuestion 1: compute the value?"),
            md("Answer: The value is 42 and the limitation is that this is synthetic."),
            code("value = 6 * 7\nprint(value)"),
        ],
    )
    plotly_output = {
        "output_type": "display_data",
        "metadata": {},
        "data": {"text/html": "<div>Plotly.newPlot('id', [])</div>"},
    }
    risky = write_notebook(
        fixtures / "risky.ipynb",
        [
            md("# Risky coursework\n\nPregunta 1: estima Ro visualmente?"),
            md("Respuesta:"),
            code("Ro_visual = float(input('Ro visual: '))\nprint(Ro_visual)"),
            code("import plotly.express as px\nfig = px.scatter(x=[1, 2], y=[3, 4])\nfig", outputs=[plotly_output]),
            code("import matplotlib.pyplot as plt\np_sat = 0.2\nplt.xlabel('Ro')\nplt.axvline(p_sat)"),
            md("See helper.csv and missing_notes.pdf."),
        ],
    )
    assignment = fixtures / "assignment.md"
    assignment.write_text("The assignment references helper.csv and calibration.fits.\n", encoding="utf-8")
    (fixtures / "helper.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    corrupt = fixtures / "corrupt.ipynb"
    corrupt.write_text('{"cells": [', encoding="utf-8")
    not_notebook = fixtures / "not_notebook.ipynb"
    not_notebook.write_text('{"not_cells": []}\n', encoding="utf-8")
    return {"clean": clean, "risky": risky, "assignment": assignment, "corrupt": corrupt, "not_notebook": not_notebook}


def check_clean_ok(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "clean" / "summary.json"
    report = tmp / "clean" / "report.md"
    proc = run_tool([str(fixtures["clean"]), "--report-md", str(report), "--summary-json", str(summary)])
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["findings"]:
        fail("clean notebook should not emit fidelity findings")
    if "Final Delivery Checklist" not in report.read_text(encoding="utf-8"):
        fail("Markdown report should include the delivery checklist")


def check_risky_warning(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "risky" / "summary.json"
    proc = run_tool([str(fixtures["risky"]), "--assignment-file", str(fixtures["assignment"]), "--summary-json", str(summary)])
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "warning")
    codes = {item["code"] for item in payload["results"]["findings"]}
    expected = {
        "interactive_input",
        "plotly_portability",
        "plotly_static_fallback_missing",
        "answer_map_incomplete",
        "empty_answer_cell",
        "traceability_missing",
        "auxiliary_file_reference",
        "axis_variable_mismatch",
        "figure_output_missing",
    }
    missing = expected - codes
    if missing:
        fail(f"missing expected warning codes: {sorted(missing)}")


def check_corrupt_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "corrupt" / "summary.json"
    proc = run_tool([str(fixtures["corrupt"]), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("corrupt notebook should return non-zero")
    no_traceback(proc, "corrupt notebook")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] != "JSONDecodeError":
        fail("corrupt notebook should report JSONDecodeError")


def check_missing_blocked(tmp: Path) -> None:
    summary = tmp / "missing" / "summary.json"
    proc = run_tool([str(tmp / "missing.ipynb"), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("missing notebook should return non-zero")
    no_traceback(proc, "missing notebook")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] != "FileNotFoundError":
        fail("missing notebook should report FileNotFoundError")


def check_not_notebook_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "not_notebook" / "summary.json"
    proc = run_tool([str(fixtures["not_notebook"]), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("non-notebook JSON should return non-zero")
    no_traceback(proc, "non-notebook JSON")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] != "SystemExit":
        fail("non-notebook JSON should preserve SystemExit-style validation")


def check_bad_report_path_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    parent_file = tmp / "not_a_directory"
    parent_file.write_text("sentinel", encoding="utf-8")
    summary = tmp / "bad_report" / "summary.json"
    proc = run_tool([str(fixtures["clean"]), "--report-md", str(parent_file / "report.md"), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("bad report path should return non-zero")
    no_traceback(proc, "bad report path")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] not in {"FileExistsError", "NotADirectoryError"}:
        fail(f"unexpected report path error type: {payload['results']['error_type']}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_coursework_fidelity_v16_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        fixtures = write_fixtures(tmp)
        check_clean_ok(tmp, fixtures)
        print("PASS check_clean_ok")
        check_risky_warning(tmp, fixtures)
        print("PASS check_risky_warning")
        check_corrupt_blocked(tmp, fixtures)
        print("PASS check_corrupt_blocked")
        check_missing_blocked(tmp)
        print("PASS check_missing_blocked")
        check_not_notebook_blocked(tmp, fixtures)
        print("PASS check_not_notebook_blocked")
        check_bad_report_path_blocked(tmp, fixtures)
        print("PASS check_bad_report_path_blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
