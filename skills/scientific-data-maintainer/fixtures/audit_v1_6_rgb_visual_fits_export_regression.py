#!/usr/bin/env python3
"""Regression checks for rgb_visual_fits_export.py v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parent
RUN_TOOL = [sys.executable, str(SCRIPT_DIR / "datanalysis_env.py"), "run-tool", "rgb_visual_fits_export", "--"]


def write_rgb_png(path: Path, shape: tuple[int, int] = (24, 32), red_offset: int = 0) -> None:
    height, width = shape
    yy, xx = np.indices((height, width))
    red = np.clip(xx * 255 / max(1, width - 1) + red_offset, 0, 255)
    green = np.clip(yy * 255 / max(1, height - 1), 0, 255)
    blue = np.full((height, width), 80)
    Image.fromarray(np.dstack([red, green, blue]).astype("uint8"), mode="RGB").save(path)


def write_rgba_png(path: Path) -> None:
    arr = np.zeros((18, 20, 4), dtype=np.uint8)
    arr[..., 0] = 210
    arr[..., 1] = 80
    arr[..., 2] = 30
    arr[..., 3] = 0
    arr[4:14, 5:15, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(path)


def run_export(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*RUN_TOOL, *[str(item) for item in args]], text=True, capture_output=True, check=False)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_traceback(proc: subprocess.CompletedProcess[str]) -> None:
    combined = proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in combined, combined


def check_happy_export(tmp: Path) -> None:
    from astropy.io import fits

    input_png = tmp / "happy.png"
    output_fits = tmp / "happy.fits"
    summary_json = tmp / "happy.json"
    manifest_json = tmp / "happy_manifest.json"
    write_rgb_png(input_png)

    proc = run_export(input_png, output_fits, "--summary-json", summary_json, "--manifest-json", manifest_json)
    assert_no_traceback(proc)
    assert proc.returncode == 0, proc.stderr
    payload = read_json(summary_json)
    assert payload["status"] == "ok", payload
    assert payload["qa"]["status"] == "ok", payload
    assert payload["results"]["rgb_cube_shape"] == [3, 24, 32]
    with fits.open(output_fits) as hdul:
        assert hdul[0].header["IMAGETYP"] == "VISUAL_RGB"
        assert hdul["RGB_CUBE"].data.shape == (3, 24, 32)
        for name in ("RED", "GREEN", "BLUE"):
            assert hdul[name].header["BUNIT"] == "normalized_display_intensity"
    manifest = read_json(manifest_json)
    assert manifest["extra"]["input_png_sha256"]


def check_rgba_warns(tmp: Path) -> None:
    input_png = tmp / "alpha.png"
    output_fits = tmp / "alpha.fits"
    summary_json = tmp / "alpha.json"
    write_rgba_png(input_png)

    proc = run_export(input_png, output_fits, "--summary-json", summary_json)
    assert_no_traceback(proc)
    assert proc.returncode == 0, proc.stderr
    payload = read_json(summary_json)
    assert payload["status"] == "warning", payload
    assert payload["qa"]["status"] == "warning", payload
    findings = "\n".join(payload["qa"]["findings"])
    assert "alpha channel" in findings
    assert payload["results"]["input_image"]["mode"] == "RGBA"


def check_existing_output_blocks_before_writing(tmp: Path) -> None:
    input_png = tmp / "new.png"
    previous_png = tmp / "previous.png"
    output_fits = tmp / "new.fits"
    comparison_png = tmp / "before_after.png"
    summary_json = tmp / "blocked.json"
    write_rgb_png(input_png)
    write_rgb_png(previous_png, red_offset=20)
    comparison_png.write_text("existing comparison", encoding="utf-8")

    proc = run_export(
        input_png,
        output_fits,
        "--previous-png",
        previous_png,
        "--comparison-png",
        comparison_png,
        "--summary-json",
        summary_json,
    )
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    payload = read_json(summary_json)
    assert payload["status"] == "blocked", payload
    assert not output_fits.exists(), "blocked comparison collision should not leave a partial FITS output"


def check_corrupt_png_blocks(tmp: Path) -> None:
    input_png = tmp / "corrupt.png"
    output_fits = tmp / "corrupt.fits"
    summary_json = tmp / "corrupt.json"
    input_png.write_text("not a png", encoding="utf-8")

    proc = run_export(input_png, output_fits, "--summary-json", summary_json)
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    payload = read_json(summary_json)
    assert payload["status"] == "blocked", payload
    assert not output_fits.exists()


def check_bad_summary_path_blocks_without_traceback(tmp: Path) -> None:
    input_png = tmp / "input.png"
    output_fits = tmp / "bad_summary.fits"
    blocked_parent = tmp / "not_a_directory"
    blocked_parent.write_text("sentinel", encoding="utf-8")
    write_rgb_png(input_png)

    proc = run_export(input_png, output_fits, "--summary-json", blocked_parent / "summary.json")
    assert_no_traceback(proc)
    assert proc.returncode == 2, proc.stdout
    assert not output_fits.exists()
    assert '"status": "blocked"' in proc.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_rgb_visual_export_v16_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_happy_export(tmp)
        print("PASS check_happy_export")
        check_rgba_warns(tmp)
        print("PASS check_rgba_warns")
        check_existing_output_blocks_before_writing(tmp)
        print("PASS check_existing_output_blocks_before_writing")
        check_corrupt_png_blocks(tmp)
        print("PASS check_corrupt_png_blocks")
        check_bad_summary_path_blocks_without_traceback(tmp)
        print("PASS check_bad_summary_path_blocks_without_traceback")
    print("All rgb_visual_fits_export v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
