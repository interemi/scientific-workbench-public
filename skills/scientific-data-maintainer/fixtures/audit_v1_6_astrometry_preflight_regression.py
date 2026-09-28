#!/usr/bin/env python3
"""Regression checks for astrometry_net_workbench.py preflight v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


SCRIPT_DIR = Path(__file__).resolve().parent
RUN_TOOL = [sys.executable, str(SCRIPT_DIR / "datanalysis_env.py"), "run-tool", "astrometry_net_workbench", "--"]


def write_direct_image(path: Path) -> None:
    yy, xx = np.indices((64, 72))
    data = (100.0 + 800.0 * np.exp(-((xx - 38) ** 2 + (yy - 32) ** 2) / (2 * 4.0**2))).astype("float32")
    header = fits.Header()
    header["OBJECT"] = "SYNTH_ASTRO"
    header["RA"] = "12:30:00"
    header["DEC"] = "+22:00:00"
    header["PIXSCALE"] = 0.7
    header["EXPTIME"] = 30.0
    fits.PrimaryHDU(data, header=header).writeto(path, overwrite=True)


def write_wcs_image(path: Path) -> None:
    yy, xx = np.indices((64, 72))
    data = (100.0 + 900.0 * np.exp(-((xx - 36) ** 2 + (yy - 30) ** 2) / (2 * 3.5**2))).astype("float32")
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [36, 32]
    wcs.wcs.cdelt = np.array([-0.0002, 0.0002])
    wcs.wcs.crval = [150.0, 2.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = wcs.to_header()
    header["OBJECT"] = "SYNTH_WCS"
    fits.PrimaryHDU(data, header=header).writeto(path, overwrite=True)


def write_spectroscopy_like(path: Path) -> None:
    data = np.ones((10, 190), dtype="float32")
    header = fits.Header()
    header["OBJECT"] = "arc_lamp"
    header["FILTER"] = "CLEAR"
    fits.PrimaryHDU(data, header=header).writeto(path, overwrite=True)


def run_preflight(path: Path, summary_json: Path, *extra: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*RUN_TOOL, "preflight", str(path), *[str(item) for item in extra], "--summary-json", str(summary_json)],
        text=True,
        capture_output=True,
        check=False,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_traceback(proc: subprocess.CompletedProcess[str]) -> None:
    combined = proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in combined, combined


def check_direct_image_ok(tmp: Path) -> None:
    path = tmp / "direct.fits"
    summary = tmp / "direct.json"
    write_direct_image(path)
    proc = run_preflight(path, summary)
    assert_no_traceback(proc)
    assert proc.returncode == 0, proc.stderr
    payload = read_json(summary)
    assert payload["status"] == "ok", payload
    results = payload["results"]
    assert results["inferred_center"]["source"] == "RA/DEC"
    assert results["inferred_scale"]["arcsec_per_pixel"] == 0.7


def check_existing_wcs_ok(tmp: Path) -> None:
    path = tmp / "wcs.fits"
    summary = tmp / "wcs.json"
    write_wcs_image(path)
    proc = run_preflight(path, summary)
    assert_no_traceback(proc)
    assert proc.returncode == 0, proc.stderr
    payload = read_json(summary)
    assert payload["status"] == "ok", payload
    assert payload["results"]["existing_astrometric_solution"]["has_celestial_wcs"] is True
    assert payload["results"]["fit_assessment"]["recommended_action"] == "reuse_existing_wcs"


def check_spectroscopy_like_warns(tmp: Path) -> None:
    path = tmp / "arc_like.fits"
    summary = tmp / "arc_like.json"
    write_spectroscopy_like(path)
    proc = run_preflight(path, summary)
    assert_no_traceback(proc)
    assert proc.returncode == 0, proc.stderr
    payload = read_json(summary)
    assert payload["status"] == "warning", payload
    assert payload["qa"]["status"] == "warning", payload
    findings = "\n".join(payload["qa"]["findings"])
    assert "spectroscopy" in findings or "calibration" in findings


def check_corrupt_fits_blocks(tmp: Path) -> None:
    path = tmp / "corrupt.fits"
    summary = tmp / "corrupt.json"
    path.write_text("not a fits file", encoding="utf-8")
    proc = run_preflight(path, summary)
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    payload = read_json(summary)
    assert payload["status"] == "blocked", payload
    assert payload["qa"]["status"] == "blocked"


def check_missing_file_blocks(tmp: Path) -> None:
    path = tmp / "missing.fits"
    summary = tmp / "missing.json"
    proc = run_preflight(path, summary)
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    payload = read_json(summary)
    assert payload["status"] == "blocked", payload
    assert "not found" in "\n".join(payload["qa"]["findings"]).lower()


def check_bad_summary_path_blocks_without_traceback(tmp: Path) -> None:
    path = tmp / "direct_for_bad_summary.fits"
    blocked_parent = tmp / "not_a_directory"
    blocked_parent.write_text("sentinel", encoding="utf-8")
    write_direct_image(path)
    proc = run_preflight(path, blocked_parent / "summary.json")
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    assert '"status": "blocked"' in proc.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_astrometry_preflight_v16_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_direct_image_ok(tmp)
        print("PASS check_direct_image_ok")
        check_existing_wcs_ok(tmp)
        print("PASS check_existing_wcs_ok")
        check_spectroscopy_like_warns(tmp)
        print("PASS check_spectroscopy_like_warns")
        check_corrupt_fits_blocks(tmp)
        print("PASS check_corrupt_fits_blocks")
        check_missing_file_blocks(tmp)
        print("PASS check_missing_file_blocks")
        check_bad_summary_path_blocks_without_traceback(tmp)
        print("PASS check_bad_summary_path_blocks_without_traceback")
    print("All astrometry preflight v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
