#!/usr/bin/env python3
"""Regression checks for coursework notebook fidelity workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def module_available(module: str) -> bool:
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def datanalysis_python() -> str:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "datanalysis_env.py"), "locate"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise AssertionError(f"Could not locate datanalysis runtime:\n{completed.stderr}")
    payload = json.loads(completed.stdout)
    python_path = payload.get("selected", {}).get("python")
    if not python_path:
        raise AssertionError(f"datanalysis runtime did not report a Python executable: {payload}")
    return str(Path(python_path).expanduser())


def runtime_python() -> str:
    if module_available("nbformat") and module_available("nbconvert"):
        return sys.executable
    return datanalysis_python()


def run_cmd(args: list[str], *, tmp: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_notebook(path: Path, cells: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "cells": cells,
                "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code(source: str, outputs: list[dict] | None = None, execution_count: int | None = None) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source,
        "outputs": outputs or [],
        "execution_count": execution_count,
    }


def check_fidelity_checker(tmp: Path) -> None:
    notebook = tmp / "rossby_coursework.ipynb"
    assignment = tmp / "enunciado.md"
    (tmp / "visualizacionRo.txt").write_text("Use this Rossby visualization helper conceptually.\n", encoding="utf-8")
    assignment.write_text("El enunciado menciona visualizacionRo.txt y pide estimacion visual.\n", encoding="utf-8")
    plotly_output = {
        "output_type": "display_data",
        "metadata": {},
        "data": {"text/html": "<div>Plotly.newPlot('id', [])</div>"},
    }
    write_notebook(
        notebook,
        [
            md("# Practica\n\nPregunta 1: estima Ro visualmente?"),
            md("Respuesta:"),
            code('Ro_visual = float(input("Ro visual: "))\nprint(Ro_visual)'),
            code("import plotly.io as pio\npio.renderers.default = 'notebook_connected'\n", outputs=[plotly_output], execution_count=2),
            code("import matplotlib.pyplot as plt\np_sat = 0.2\nplt.xlabel('Ro')\nplt.axvline(p_sat)\n"),
        ],
    )
    summary = tmp / "fidelity.json"
    report = tmp / "fidelity.md"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "coursework_notebook_fidelity_check.py"),
            str(notebook),
            "--assignment-file",
            str(assignment),
            "--report-md",
            str(report),
            "--summary-json",
            str(summary),
        ],
        tmp=tmp,
    )
    payload = load_json(summary)
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
        raise AssertionError(f"Missing expected fidelity findings {missing}: {payload['results']['findings']}")
    report_text = report.read_text(encoding="utf-8") if report.exists() else ""
    if "Final Delivery Checklist" not in report_text or "Question / Answer Map" not in report_text:
        raise AssertionError("Fidelity Markdown report was not written correctly.")
    question_map = payload["results"]["signals"].get("question_answer_map") or []
    if not question_map or question_map[0].get("answer_status") != "empty":
        raise AssertionError(f"Question/answer map did not capture the empty answer cell: {question_map}")


def check_notebook_workbench_input_provider(tmp: Path) -> None:
    py = runtime_python()
    notebook = tmp / "interactive.ipynb"
    write_notebook(
        notebook,
        [
            code('value = input("value: ")\nprint("seen", value)'),
        ],
    )
    preflight = tmp / "preflight.json"
    run_cmd(
        [
            py,
            str(SCRIPTS / "notebook_workbench.py"),
            "preflight-execution",
            str(notebook),
            "--summary-json",
            str(preflight),
        ],
        tmp=tmp,
    )
    preflight_payload = load_json(preflight)
    calls = preflight_payload["results"]["preflight"]["execution_signals"].get("interactive_input_calls") or []
    if len(calls) != 1:
        raise AssertionError(f"Expected one detected input() call, got {calls}")

    output_dir = tmp / "executed"
    summary = output_dir / "summary.json"
    run_cmd(
        [
            py,
            str(SCRIPTS / "notebook_workbench.py"),
            "execute-copy",
            str(notebook),
            "--output-dir",
            str(output_dir),
            "--input-value",
            "42",
            "--summary-json",
            str(summary),
        ],
        tmp=tmp,
    )
    executed = output_dir / "interactive.ipynb"
    saved = load_json(executed)
    saved_source = "\n".join("".join(cell.get("source", "")) for cell in saved.get("cells", []))
    if "_codex_input_provider" in saved_source:
        raise AssertionError("Temporary input provider leaked into the saved notebook copy.")
    run_payload = load_json(summary)["results"]["run"]
    if run_payload.get("input_values_used") != [{"index": 1, "value": "42"}]:
        raise AssertionError(f"Input values were not documented: {run_payload.get('input_values_used')}")
    if run_payload.get("ephemeral_input_provider_cells_removed_before_save") != 2:
        raise AssertionError(f"Provider cells were not removed: {run_payload}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_coursework_notebook_fidelity_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in [check_fidelity_checker, check_notebook_workbench_input_provider]:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All coursework notebook fidelity regressions passed.")


if __name__ == "__main__":
    main()
