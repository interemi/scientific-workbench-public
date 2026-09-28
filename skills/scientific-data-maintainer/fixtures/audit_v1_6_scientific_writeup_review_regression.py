#!/usr/bin/env python3
"""Regression tests for scientific_writeup_review.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "scientific_writeup_review.py"


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
    return {item.get("title", "") for item in payload.get("qa", {}).get("findings", [])}


def check_good_markdown_runs(tmp: Path) -> None:
    path = tmp / "good.md"
    summary = tmp / "good.json"
    report = tmp / "good_report.md"
    write(
        path,
        """
        # Methodology
        We used calibrated spectra with wavelength in Angstrom and radial velocity in km/s.
        The uncertainty was estimated from order-to-order dispersion and is reported as +/- 2.0 km/s.

        # Results
        The measured radial velocity is -12.1 km/s and the equivalent width is 280 mA.
        The values are consistent with the literature reference within the stated uncertainty.

        # Discussion
        The result suggests a physically plausible active late-type star, but the conclusion is limited by
        continuum placement, manual order selection, and the coursework-level sample size.

        # Conclusions
        The main claim is cautious and the limitations remain visible.
        """,
    )
    run_cmd([sys.executable, str(TOOL), str(path), "--report-md", str(report), "--summary-json", str(summary)], tmp)
    payload = read_json(summary)
    assert payload["status"] in {"ok", "warning"}
    assert report.exists()
    assert payload["results"]["metrics"]["word_count"] > 60


def check_tex_source_marker_does_not_create_absolute_path_warning(tmp: Path) -> None:
    main = tmp / "tex_project" / "main.tex"
    summary = tmp / "tex_project.json"
    write(
        main,
        r"""
        \documentclass{article}
        \begin{document}
        \section{Metodologia}
        \input{sections/method}
        \section{Resultados}
        La velocidad radial fue $-11.8\,\mathrm{km/s}$ con incertidumbre $\pm 2.1\,\mathrm{km/s}$.
        \section{Discusion}
        El resultado es compatible con literatura, pero queda limitado por la seleccion manual.
        \section{Conclusiones}
        La conclusion es cauta y no definitiva.
        \end{document}
        """,
    )
    write(main.parent / "sections" / "method.tex", "Se usaron espectros calibrados y trazabilidad de parametros.")
    run_cmd([sys.executable, str(TOOL), str(main), "--summary-json", str(summary)], tmp)
    assert "Rutas absolutas detectadas" not in finding_titles(read_json(summary))


def check_missing_input_blocks_with_nonzero_exit(tmp: Path) -> None:
    summary = tmp / "missing.json"
    run_cmd([sys.executable, str(TOOL), str(tmp / "missing.md"), "--summary-json", str(summary)], tmp, expect_ok=False)
    payload = read_json(summary)
    assert payload["status"] == "blocked"
    assert payload["qa"]["status"] == "blocked"
    assert "Archivo no encontrado" in finding_titles(payload)


def check_unsupported_binary_blocks(tmp: Path) -> None:
    path = tmp / "not_writeup.pdf"
    summary = tmp / "unsupported.json"
    path.write_bytes(b"%PDF-1.4 broken binary-ish content\n" * 30)
    run_cmd([sys.executable, str(TOOL), str(path), "--summary-json", str(summary)], tmp, expect_ok=False)
    payload = read_json(summary)
    assert payload["status"] == "blocked"
    assert "Entrada no revisable" in finding_titles(payload)


def check_invalid_output_path_fails_cleanly(tmp: Path) -> None:
    path = tmp / "valid.md"
    blocked_parent = tmp / "not_a_directory"
    blocked_parent.write_text("file, not directory", encoding="utf-8")
    summary = tmp / "invalid_report_parent.json"
    write(path, "# Results\nTexto suficiente con km/s, incertidumbre +/- 1 km/s y limitaciones visibles.")
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            str(path),
            "--report-md",
            str(blocked_parent / "report.md"),
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    payload = read_json(summary)
    assert payload["status"] == "fail"
    assert payload["qa"]["status"] == "fail"

    completed = run_cmd(
        [sys.executable, str(TOOL), str(path), "--summary-json", str(blocked_parent / "summary.json")],
        tmp,
        expect_ok=False,
    )
    parsed = json.loads(completed.stdout)
    assert parsed["status"] == "fail"


def main() -> None:
    checks = [
        check_good_markdown_runs,
        check_tex_source_marker_does_not_create_absolute_path_warning,
        check_missing_input_blocks_with_nonzero_exit,
        check_unsupported_binary_blocks,
        check_invalid_output_path_fails_cleanly,
    ]
    with tempfile.TemporaryDirectory(prefix="sda_writeup_review_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All scientific_writeup_review regressions passed.")


if __name__ == "__main__":
    main()
