#!/usr/bin/env python3
"""Focused regressions for the physical_qa hardening pass.

The fixtures are synthetic and temporary. This is a maintainer check, not a
normal user entrypoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_cmd(args: list[str], *, tmp: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"physical_qa leaked a traceback:\n{completed.stdout}\n{completed.stderr}")
    return completed


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_messages(payload: dict, expected: list[str]) -> None:
    messages = "\n".join(issue.get("message", "") for issue in payload["results"]["issues"])
    missing = [text for text in expected if text not in messages]
    if missing:
        raise AssertionError(f"Missing expected messages {missing!r}\nMessages:\n{messages}")


def check_bad_coordinates_are_warnings(tmp: Path) -> None:
    table = tmp / "bad_coordinates.csv"
    summary = tmp / "bad_coordinates.json"
    table.write_text("ra,dec,flux,airmass\nnot_a_number,91,-1,0.7\n", encoding="utf-8")
    run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(table), "--summary-json", str(summary)], tmp=tmp)
    payload = load_json(summary)
    if payload["status"] != "warning":
        raise AssertionError(f"Expected warning status, got {payload['status']!r}")
    assert_messages(payload, ["non-numeric", "Dec values", "negative flux/count", "airmass values"])


def check_bad_fits_headers_are_warnings(tmp: Path) -> None:
    import numpy as np
    from astropy.io import fits

    path = tmp / "bad_header.fits"
    summary = tmp / "bad_header.json"
    header = fits.Header()
    header["EXPTIME"] = "bad"
    header["DATE-OBS"] = "not-a-date"
    header["AIRMASS"] = 9.0
    data = np.ones((10, 10), dtype="float32")
    data[:7, :] = np.nan
    fits.PrimaryHDU(data, header=header).writeto(path)
    run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(path), "--summary-json", str(summary)], tmp=tmp)
    payload = load_json(summary)
    if payload["status"] != "warning":
        raise AssertionError(f"Expected warning status, got {payload['status']!r}")
    assert_messages(payload, ["EXPTIME is not numeric", "AIRMASS is outside", "Could not parse FITS header DATE-OBS", "low finite pixel fraction"])


def check_spectrum_like_table(tmp: Path) -> None:
    table = tmp / "bad_spectrum.dat"
    summary = tmp / "bad_spectrum.json"
    table.write_text(
        "wavelength flux\n"
        "5000.0 1.0\n"
        "4999.0 0.9\n"
        "4999.0 nan\n"
        "-1.0 1.1\n",
        encoding="utf-8",
    )
    run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(table), "--summary-json", str(summary)], tmp=tmp)
    payload = load_json(summary)
    assert_messages(payload, ["non-positive wavelength", "duplicate wavelength", "not strictly increasing"])


def check_time_and_uncertainty_table(tmp: Path) -> None:
    table = tmp / "bad_time.csv"
    summary = tmp / "bad_time.json"
    table.write_text(
        "obs_time,flux_err,flux\n"
        "2026-04-25T00:01:00,-0.1,nan\n"
        "2026-04-25T00:01:00,0.2,nan\n"
        "2026-04-24T23:59:00,0.3,nan\n",
        encoding="utf-8",
    )
    run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(table), "--summary-json", str(summary)], tmp=tmp)
    payload = load_json(summary)
    assert_messages(payload, ["duplicate timestamps", "not monotonic", "negative uncertainty/error", "no finite numeric values"])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_physical_qa_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        checks = [
            check_bad_coordinates_are_warnings,
            check_bad_fits_headers_are_warnings,
            check_spectrum_like_table,
            check_time_and_uncertainty_table,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All physical_qa regressions passed.")


if __name__ == "__main__":
    main()
