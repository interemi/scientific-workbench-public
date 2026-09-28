#!/usr/bin/env python3
"""Focused v1.3 regression gate for audit-discovered capability issues."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str], cwd: Path = ROOT) -> dict:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_table_csv(path: Path) -> None:
    path.write_text("category,value\na,1\na,2\nb,3\n", encoding="utf-8")


def write_sb2_ccf(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["velocity_kms", "ccf_value"])
        for index in range(241):
            velocity = -120.0 + index
            value = (
                0.15
                + 0.9 * math.exp(-0.5 * ((velocity + 42.0) / 9.0) ** 2)
                + 0.75 * math.exp(-0.5 * ((velocity - 38.0) / 11.0) ** 2)
            )
            writer.writerow([f"{velocity:.3f}", f"{value:.8f}"])


def write_shifted_spectrum(source: Path, target: Path) -> None:
    rows = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            continue
        rows.append((x, 0.98 * y + 0.01))
    target.write_text("\n".join(f"{x:.6f} {y:.6f}" for x, y in rows) + "\n", encoding="utf-8")


def check_duckdb_reserved_alias(tmp: Path) -> None:
    table_csv = tmp / "table.csv"
    summary_json = tmp / "duckdb.json"
    output_csv = tmp / "duckdb.csv"
    write_table_csv(table_csv)
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "duckdb_workbench.py"),
            str(table_csv),
            "--sql",
            "select category, count(*) as n from source0 group by category order by category",
            "--output",
            str(output_csv),
            "--summary-json",
            str(summary_json),
        ]
    )
    require(result["returncode"] == 0, "duckdb_workbench failed on table.csv reserved alias case")
    payload = read_json(summary_json)
    require(payload["status"] == "ok", "duckdb summary did not report ok")
    require("table" not in payload["results"]["aliases"], "reserved stem alias 'table' should be skipped")
    require("source0" in payload["results"]["aliases"], "source0 alias missing")


def check_sb2_public_fit_alias(tmp: Path) -> None:
    ccf_csv = tmp / "sb2_ccf.csv"
    output_dir = tmp / "sb2"
    summary_json = tmp / "sb2.json"
    write_sb2_ccf(ccf_csv)
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "sb2_double_gaussian_workbench.py"),
            "fit",
            str(ccf_csv),
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ]
    )
    require(result["returncode"] == 0, "sb2 public fit alias failed")
    payload = read_json(summary_json)
    require(payload["tool"] == "sb2_double_gaussian_workbench.fit", "SB2 alias did not emit public tool name")
    require(payload["results"]["accepted_count"] >= 1, "SB2 alias did not accept the synthetic order")


def check_legacy_rv_blocked_payload(tmp: Path) -> None:
    output_dir = tmp / "legacy_rv"
    summary_json = tmp / "legacy_rv.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "legacy_rv_coursework_workbench.py"),
            "analyze",
            str(ROOT / "examples/science/legacy_spectroscopy_mini/sample_fxcor_rows.csv"),
            "--fits-root",
            str(ROOT / "examples/science/legacy_spectroscopy_mini"),
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ]
    )
    require(result["returncode"] != 0, "legacy RV incomplete FITS fixture should block")
    payload = read_json(summary_json)
    require(payload["status"] == "blocked", "legacy RV validation should emit a blocked standard payload")
    require(payload["qa"]["status"] == "blocked", "legacy RV qa.status should be blocked")
    issues = payload["results"]["input_validation_issues"]
    require(any("RA" in item and "DATE-OBS" in item for item in issues), "legacy RV blocked payload missed FITS header issue")


def check_spectra_ascii_bundle(tmp: Path) -> None:
    source = ROOT / "examples/science/synthetic_spectrum.txt"
    shifted = tmp / "synthetic_spectrum_shifted.txt"
    output_dir = tmp / "spectra_ascii"
    summary_json = tmp / "spectra_ascii.json"
    write_shifted_spectrum(source, shifted)
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "spectra_ascii_coursework_workbench.py"),
            str(source),
            str(shifted),
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ]
    )
    require(result["returncode"] == 0, "spectra ASCII coursework bundle failed")
    payload = read_json(summary_json)
    report_project = payload["results"]["report_project"]
    require(report_project, "report project was not created")
    for relative in ["report_project/figures/overlay_raw.png", "report_project/figures/overlay_normalized.png"]:
        require((output_dir / relative).exists(), f"missing copied report figure: {relative}")


def check_v1_3_docs(tmp: Path) -> None:
    expected = {
        "README.txt": ["audit_v1_3_release_regression.py", "DuckDB reserved-alias safety"],
        "RELEASE-v1.txt": ["v1.3 closes the full-capability audit follow-up"],
        "references/architecture.md": ["audit_v1_3_release_regression.py"],
    }
    for relative, terms in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        require(not missing, f"{relative} is missing v1.3 release terms: {missing}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-3-") as tmp_raw:
        tmp = Path(tmp_raw)
        checks = [
            check_duckdb_reserved_alias,
            check_sb2_public_fit_alias,
            check_legacy_rv_blocked_payload,
            check_spectra_ascii_bundle,
            check_v1_3_docs,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All v1.3 release regressions passed.")


if __name__ == "__main__":
    main()
