#!/usr/bin/env python3
"""Regression checks for post-audit public JSON contract hardening.

The fixtures are synthetic and temporary. This is a maintainer check, not a
normal user entrypoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


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


def assert_envelope(path: Path, expected_tool: str) -> dict:
    payload = load_json(path)
    missing = [key for key in ["tool", "status", "notes", "artifacts", "results", "qa"] if key not in payload]
    if missing:
        raise AssertionError(f"{path} missing standard keys: {missing}")
    if payload["tool"] != expected_tool:
        raise AssertionError(f"{path} tool={payload['tool']!r}, expected {expected_tool!r}")
    if payload["status"] not in {"ok", "warning", "blocked", "fail"}:
        raise AssertionError(f"{path} has invalid status: {payload['status']!r}")
    if not isinstance(payload["qa"], dict) or "findings" not in payload["qa"] or "metrics" not in payload["qa"]:
        raise AssertionError(f"{path} has invalid qa block")
    return payload


def create_fits(path: Path) -> None:
    import numpy as np
    from astropy.io import fits

    yy, xx = np.indices((80, 80))
    data = 100.0 + 4000.0 * np.exp(-0.5 * (((xx - 40.0) / 3.0) ** 2 + ((yy - 39.0) / 3.0) ** 2))
    header = fits.Header()
    header["EXPTIME"] = 30.0
    header["DATE-OBS"] = "2026-04-25T00:00:00"
    fits.PrimaryHDU(data.astype("float32"), header=header).writeto(path)


def create_spectrum(path: Path) -> None:
    import numpy as np

    wavelength = np.linspace(6500.0, 6510.0, 120)
    flux = 1.0 - 0.2 * np.exp(-0.5 * ((wavelength - 6505.0) / 0.25) ** 2)
    path.write_text("wavelength flux\n" + "\n".join(f"{x:.5f} {y:.7f}" for x, y in zip(wavelength, flux)) + "\n")


def create_pdf(path: Path) -> None:
    from matplotlib.figure import Figure

    figure = Figure(figsize=(300 / 72, 180 / 72))
    figure.text(0.12, 0.6, "Synthetic PDF for recovery contract regression.", fontsize=8)
    figure.savefig(path, format="pdf")


def create_iwork_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Index/Document.iwa", b"Synthetic IWA hint: flux table")
        zf.writestr("Metadata/Properties.plist", b"<?xml version='1.0'?><plist version='1.0'><dict></dict></plist>")


def check_contracts(tmp: Path) -> None:
    csv_path = tmp / "bad_physical.csv"
    csv_path.write_text("flux,airmass\n-1.0,0.5\n2.0,1.2\n", encoding="utf-8")
    physical_json = tmp / "physical_qa.json"
    run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(csv_path), "--summary-json", str(physical_json)], tmp=tmp)
    assert_envelope(physical_json, "physical_qa")

    fits_path = tmp / "image.fits"
    create_fits(fits_path)
    aperture_json = tmp / "aperture_summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "aperture_photometry.py"),
            str(fits_path),
            "--auto-brightest",
            "1",
            "--summary-json",
            str(aperture_json),
        ],
        tmp=tmp,
    )
    assert_envelope(aperture_json, "aperture_photometry")

    spectrum_path = tmp / "spectrum.dat"
    create_spectrum(spectrum_path)
    spectral_json = tmp / "spectral_summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "spectral_workbench.py"),
            str(spectrum_path),
            "--summary-json",
            str(spectral_json),
            "--line-window",
            "6505",
            "1.0",
        ],
        tmp=tmp,
    )
    assert_envelope(spectral_json, "spectral_workbench")

    ts_json = tmp / "timeseries_summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "timeseries_forecasting_workbench.py"),
            "--output-dir",
            str(tmp / "ts"),
            "--summary-json",
            str(ts_json),
            "--overwrite",
        ],
        tmp=tmp,
    )
    assert_envelope(ts_json, "timeseries_forecasting_workbench")

    text_path = tmp / "note.txt"
    text_path.write_text("Method. Results. Limitations.\n", encoding="utf-8")
    semantics_json = tmp / "document_semantics.json"
    run_cmd([sys.executable, str(SCRIPTS / "document_semantics.py"), str(text_path), "--output-json", str(semantics_json)], tmp=tmp)
    assert_envelope(semantics_json, "document_semantics")

    pdf_path = tmp / "sample.pdf"
    create_pdf(pdf_path)
    pdf_json = tmp / "pdf_recovery" / "summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "pdf_recover_extract.py"),
            str(pdf_path),
            "--output-dir",
            str(tmp / "pdf_recovery"),
            "--summary-json",
            str(pdf_json),
        ],
        tmp=tmp,
    )
    assert_envelope(pdf_json, "pdf_recover_extract")

    iwork_path = tmp / "sample.pages"
    create_iwork_zip(iwork_path)
    iwork_json = tmp / "iwork" / "summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "iwork_workbench.py"),
            str(iwork_path),
            "--output-dir",
            str(tmp / "iwork"),
            "--output-json",
            str(iwork_json),
        ],
        tmp=tmp,
    )
    assert_envelope(iwork_json, "iwork_workbench")

    tea_json = tmp / "teareduce_health.json"
    run_cmd([sys.executable, str(SCRIPTS / "teareduce_healthcheck.py"), "--summary-json", str(tea_json)], tmp=tmp)
    assert_envelope(tea_json, "teareduce_healthcheck")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_step2_contract_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_contracts(tmp)
    print("All audit step 2 contract regressions passed.")


if __name__ == "__main__":
    main()
