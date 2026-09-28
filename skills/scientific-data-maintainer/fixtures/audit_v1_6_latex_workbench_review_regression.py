#!/usr/bin/env python3
"""Regression tests for latex_workbench.py review."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TOOL = SCRIPTS / "latex_workbench.py"


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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def finding_titles(payload: dict) -> set[str]:
    return {item.get("title", "") for item in payload.get("results", {}).get("findings", [])}


def check_documentclass_options(tmp: Path) -> None:
    plain = tmp / "plain.tex"
    options = tmp / "options.tex"
    plain_json = tmp / "plain.json"
    options_json = tmp / "options.json"
    write(
        plain,
        r"""
        \documentclass{article}
        \begin{document}
        \begin{abstract}Resumen corto.\end{abstract}
        \section{Intro}
        Texto minimo.
        \end{document}
        """,
    )
    write(
        options,
        r"""
        \documentclass[12pt,a4paper]{article}
        \begin{document}
        \begin{abstract}Resumen corto.\end{abstract}
        \section{Intro}
        Texto minimo.
        \end{document}
        """,
    )
    run_cmd([sys.executable, str(TOOL), "review", str(plain), "--summary-json", str(plain_json)], tmp)
    run_cmd([sys.executable, str(TOOL), "review", str(options), "--summary-json", str(options_json)], tmp)
    assert read_json(plain_json)["results"]["inspection"]["documentclass_options"] == []
    assert read_json(options_json)["results"]["inspection"]["documentclass_options"] == ["12pt", "a4paper"]


def check_missing_project_assets(tmp: Path) -> None:
    tex = tmp / "missing_assets" / "main.tex"
    summary = tmp / "missing_assets.json"
    write(
        tex,
        r"""
        \documentclass{article}
        \usepackage{graphicx}
        \begin{document}
        \section{Intro}
        This proves that a missing project asset should be noticed \cite{missing}.
        \input{tables/missing_table}
        \includegraphics{figures/missing_plot}
        \bibliography{refs}
        \end{document}
        """,
    )
    run_cmd([sys.executable, str(TOOL), "review", str(tex), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    titles = finding_titles(payload)
    required = {
        "Included TeX files do not resolve",
        "Figure files do not resolve",
        "Bibliography files do not resolve",
    }
    missing = required - titles
    if missing:
        raise AssertionError(f"Missing expected findings: {sorted(missing)}")
    results = payload["results"]
    assert results["missing_includes"] == ["tables/missing_table"]
    assert results["missing_figures"] == ["figures/missing_plot"]
    assert results["missing_bibliography_files"] == ["refs"]


def check_corrupt_tex_structure(tmp: Path) -> None:
    tex = tmp / "corrupt.tex"
    summary = tmp / "corrupt.json"
    tex.write_bytes(b"not really latex\\x00\\xff\\x00")
    run_cmd([sys.executable, str(TOOL), "review", str(tex), "--summary-json", str(summary)], tmp, expect_ok=False)
    payload = read_json(summary)
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"
    titles = finding_titles(payload)
    assert "Missing documentclass" in titles
    assert "Missing document environment boundary" in titles


def check_missing_input_emits_fail_payload(tmp: Path) -> None:
    summary = tmp / "missing_input.json"
    completed = run_cmd(
        [sys.executable, str(TOOL), "review", str(tmp / "no_such_file.tex"), "--summary-json", str(summary)],
        tmp,
        expect_ok=False,
    )
    payload = read_json(summary)
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"
    assert "Could not find a main .tex file" in json.dumps(payload)
    assert "Traceback" not in completed.stdout + completed.stderr


def check_invalid_output_paths_fail_cleanly(tmp: Path) -> None:
    tex = tmp / "valid.tex"
    write(
        tex,
        r"""
        \documentclass{article}
        \begin{document}
        \begin{abstract}Resumen corto.\end{abstract}
        \section{Intro}
        Texto minimo.
        \end{document}
        """,
    )
    blocked_parent = tmp / "not_a_directory"
    blocked_parent.write_text("file, not directory", encoding="utf-8")
    summary = tmp / "invalid_report_parent.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "review",
            str(tex),
            "--report-md",
            str(blocked_parent / "review.md"),
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    assert read_json(summary)["status"] == "fail"

    completed = run_cmd(
        [
            sys.executable,
            str(TOOL),
            "review",
            str(tex),
            "--summary-json",
            str(blocked_parent / "summary.json"),
        ],
        tmp,
        expect_ok=False,
    )
    parsed_stdout = json.loads(completed.stdout)
    assert parsed_stdout["status"] == "fail"
    assert parsed_stdout["qa"]["status"] == "fail"


def main() -> None:
    checks = [
        check_documentclass_options,
        check_missing_project_assets,
        check_corrupt_tex_structure,
        check_missing_input_emits_fail_payload,
        check_invalid_output_paths_fail_cleanly,
    ]
    with tempfile.TemporaryDirectory(prefix="sda_latex_review_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All latex_workbench review regressions passed.")


if __name__ == "__main__":
    main()
