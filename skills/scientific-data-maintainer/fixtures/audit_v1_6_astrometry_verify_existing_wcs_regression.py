#!/usr/bin/env python3
"""Regression checks for astrometry_net_workbench.py verify-existing-wcs v1.6."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


SCRIPT = Path(__file__).resolve().with_name("astrometry_net_workbench.py")


def wcs_header(nx: int = 80, ny: int = 70, *, ra: float = 187.5, dec: float = 22.0) -> fits.Header:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [nx / 2.0, ny / 2.0]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.cd = np.array([[-0.7 / 3600.0, 0.0], [0.0, 0.7 / 3600.0]])
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = wcs.to_header()
    header["OBJECT"] = "verify_existing_wcs_regression"
    return header


def write_image_wcs(path: Path, *, finite: bool = True) -> None:
    data = np.full((70, 80), np.nan if not finite else 100.0, dtype=np.float32)
    if finite:
        data[20, 25] = 1000.0
        data[44, 58] = 700.0
    fits.PrimaryHDU(data=data, header=wcs_header()).writeto(path, overwrite=True)


def write_header_only_wcs(path: Path) -> None:
    fits.PrimaryHDU(header=wcs_header()).writeto(path, overwrite=True)


def write_no_wcs(path: Path) -> None:
    fits.PrimaryHDU(data=np.ones((30, 30), dtype=np.float32)).writeto(path, overwrite=True)


def run_verify(path: Path, out_dir: Path) -> tuple[int, dict | None, str]:
    summary = out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "verify-existing-wcs",
        str(path),
        "--output-dir",
        str(out_dir / "bundle"),
        "--summary-json",
        str(summary),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    payload = None
    if summary.exists():
        payload = json.loads(summary.read_text(encoding="utf-8"))
    elif proc.stdout.strip().startswith("{"):
        payload = json.loads(proc.stdout)
    return proc.returncode, payload, (proc.stdout or "") + "\n" + (proc.stderr or "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="astrometry_verify_wcs_regression_") as tmp:
        base = Path(tmp)

        good = base / "good_wcs.fits"
        write_image_wcs(good)
        rc, payload, text = run_verify(good, base / "good")
        require(rc == 0, f"good WCS should exit 0, got {rc}: {text}")
        require(payload is not None and payload.get("status") == "ok", "good WCS should be ok")
        require((payload.get("qa") or {}).get("status") == "ok", "good WCS QA should be ok")
        require(((payload.get("results") or {}).get("field_corners") or []) and len((payload["results"]["field_corners"])) == 4, "good WCS should transform four corners")
        require((base / "good" / "bundle" / "existing_wcs_quicklook.png").exists(), "good WCS should emit quicklook")
        print("PASS check_good_wcs_ok")

        header_only = base / "header_only_wcs.fits"
        write_header_only_wcs(header_only)
        rc, payload, text = run_verify(header_only, base / "header_only")
        require(rc == 0, f"header-only WCS should exit 0 warning, got {rc}: {text}")
        require(payload is not None and payload.get("status") == "warning", "header-only WCS should be warning")
        require((payload.get("qa") or {}).get("status") == "warning", "header-only QA should be warning")
        require((payload.get("results") or {}).get("result_status") == "wcs_header_only", "header-only result_status should be explicit")
        print("PASS check_header_only_wcs_warns")

        nan_image = base / "all_nan_wcs.fits"
        write_image_wcs(nan_image, finite=False)
        rc, payload, text = run_verify(nan_image, base / "all_nan")
        require(rc == 0, f"all-NaN WCS should exit 0 warning, got {rc}: {text}")
        require(payload is not None and payload.get("status") == "warning", "all-NaN WCS should be warning, not ok")
        findings = " ".join((payload.get("qa") or {}).get("findings") or [])
        require("no finite pixels" in findings, f"all-NaN WCS should explain missing finite pixels: {findings}")
        require(not (base / "all_nan" / "bundle" / "existing_wcs_quicklook.png").exists(), "all-NaN WCS should not fake a quicklook")
        print("PASS check_all_nan_wcs_warns")

        no_wcs = base / "no_wcs.fits"
        write_no_wcs(no_wcs)
        rc, payload, text = run_verify(no_wcs, base / "no_wcs")
        require(rc != 0, "no-WCS image should block")
        require(payload is not None and payload.get("status") == "blocked", "no-WCS image should return blocked payload")
        require("Traceback" not in text, "no-WCS image should not traceback")
        print("PASS check_no_wcs_blocks")

        corrupt = base / "corrupt.fits"
        corrupt.write_text("not a fits file", encoding="utf-8")
        rc, payload, text = run_verify(corrupt, base / "corrupt")
        require(rc != 0, "corrupt FITS should block")
        require(payload is not None and payload.get("status") == "blocked", "corrupt FITS should return blocked payload")
        require("Traceback" not in text, "corrupt FITS should not traceback")
        print("PASS check_corrupt_fits_blocks")

    print("All astrometry verify-existing-wcs v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
