#!/usr/bin/env python3
"""Regression checks for inspect_fits.py v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "inspect_fits.py"


def run_inspect(input_path: Path, summary: Path, *extra: str):
    summary.unlink(missing_ok=True)
    cmd = [sys.executable, str(TOOL), str(input_path), "--summary-json", str(summary), *extra]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    payload = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    return completed, payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_no_traceback(completed: subprocess.CompletedProcess[str]) -> None:
    combined = completed.stdout + "\n" + completed.stderr
    require("Traceback" not in combined, "inspect_fits leaked a traceback")


def make_fixtures(tmp: Path) -> tuple[Path, Path, Path, Path]:
    import numpy as np
    from astropy.io import fits
    from astropy.table import Table

    good = tmp / "good.fits"
    header = fits.Header()
    header["OBJECT"] = "GOOD"
    header["EXPTIME"] = 30.0
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 8.0
    header["CRPIX2"] = 8.0
    header["CRVAL1"] = 120.0
    header["CRVAL2"] = 22.0
    header["CDELT1"] = -0.00027
    header["CDELT2"] = 0.00027
    fits.HDUList(
        [
            fits.PrimaryHDU(np.ones((16, 16), dtype="float32"), header=header),
            fits.BinTableHDU(Table({"source_id": [1, 2], "ra": [120.0, 120.1]}), name="CATALOG"),
        ]
    ).writeto(good)

    all_nan = tmp / "all_nan.fits"
    fits.PrimaryHDU(np.full((10, 10), np.nan, dtype="float32")).writeto(all_nan)

    corrupt = tmp / "corrupt.fits"
    corrupt.write_text("not a fits file\n", encoding="utf-8")

    no_primary_image = tmp / "no_primary_image.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((8, 8), dtype="float32"), name="SCI")]).writeto(no_primary_image)

    return good, all_nan, corrupt, no_primary_image


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="inspect_fits_v1_6_") as raw_tmp:
        tmp = Path(raw_tmp)
        good, all_nan, corrupt, no_primary_image = make_fixtures(tmp)

        preview = tmp / "good.png"
        completed, payload = run_inspect(good, tmp / "good.json", "--preview", str(preview), "--extension", "0")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "ok", payload)
        require(payload["qa"]["metrics"]["image_hdu_count"] == 1, payload)
        require(payload["qa"]["metrics"]["table_hdu_count"] == 1, payload)
        require(preview.exists() and preview.stat().st_size > 0, "preview was not written")

        completed, payload = run_inspect(all_nan, tmp / "all_nan.json")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "warning", payload)
        require(any("no finite image pixels" in item for item in payload["qa"]["findings"]), payload)

        completed, payload = run_inspect(corrupt, tmp / "corrupt.json")
        require(completed.returncode != 0, "corrupt FITS should block")
        assert_no_traceback(completed)
        require(payload["status"] == "blocked", payload)

        completed, payload = run_inspect(good, tmp / "bad_crop.json", "--preview", str(tmp / "bad_crop.png"), "--crop", "999,999,3,3")
        require(completed.returncode != 0, "outside crop should block")
        assert_no_traceback(completed)
        require(payload["status"] == "blocked", payload)

        completed, payload = run_inspect(no_primary_image, tmp / "fallback_blocked.json", "--force-simple-fallback")
        require(completed.returncode != 0, "simple fallback without primary image should block")
        assert_no_traceback(completed)
        require(payload["status"] == "blocked", payload)

        parent_file = tmp / "occupied"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(TOOL), str(good), "--summary-json", str(parent_file / "summary.json")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(completed.returncode != 0, "summary parent conflict should fail cleanly")
        assert_no_traceback(completed)
        require("summary-json parent is not a directory" in completed.stderr, completed.stdout + completed.stderr)

    print("inspect_fits v1.6 regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
