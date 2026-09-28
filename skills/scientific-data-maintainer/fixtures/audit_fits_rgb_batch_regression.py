#!/usr/bin/env python3
"""Regression checks for the narrow FITS RGB batch workflow."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "fits_rgb_batch.py"
VISUAL_EXPORT_TOOL = SCRIPT_DIR / "rgb_visual_fits_export.py"


def make_gaussian(shape: tuple[int, int], y0: float, x0: float) -> np.ndarray:
    yy, xx = np.indices(shape)
    data = 30.0 + 2000.0 * np.exp(-(((yy - y0) ** 2) + ((xx - x0) ** 2)) / (2.0 * 2.5**2))
    return data.astype("float32")


def write_wcs_fits(path: Path, filt: str, crpix1: float, crpix2: float) -> None:
    shape = (64, 64)
    data = make_gaussian(shape, crpix2 - 1.0, crpix1 - 1.0)
    header = fits.Header()
    header["OBJECT"] = "RGB_TEST"
    header["FILTER"] = filt
    header["EXPTIME"] = 30.0
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = 20.0
    header["CRPIX1"] = crpix1
    header["CRPIX2"] = crpix2
    header["CDELT1"] = -0.0002777778
    header["CDELT2"] = 0.0002777778
    header["BUNIT"] = "adu"
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def write_shifted_plain_fits(path: Path, filt: str, y0: float, x0: float) -> None:
    data = make_gaussian((64, 64), y0=y0, x0=x0)
    header = fits.Header()
    header["OBJECT"] = "RGB_WARNING_TEST"
    header["FILTER"] = filt
    header["EXPTIME"] = 30.0
    header["BUNIT"] = "adu"
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def run_tool(input_root: Path, output_dir: Path, summary_json: Path, extra_args: list[str] | None = None) -> dict:
    command = [
        sys.executable,
        str(TOOL),
        "--input-root",
        str(input_root),
        "--output-dir",
        str(output_dir),
        "--clean-derived",
        "--summary-json",
        str(summary_json),
    ]
    if extra_args:
        command.extend(extra_args)
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"fits_rgb_batch failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return json.loads(summary_json.read_text(encoding="utf-8"))


def run_tool_raw(input_root: Path, output_dir: Path, summary_json: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        str(TOOL),
        "--input-root",
        str(input_root),
        "--output-dir",
        str(output_dir),
        "--clean-derived",
        "--summary-json",
        str(summary_json),
    ]
    if extra_args:
        command.extend(extra_args)
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if "Traceback" in proc.stdout or "Traceback" in proc.stderr:
        raise AssertionError(f"fits_rgb_batch leaked traceback\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def check_clean_wcs_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        output_dir = tmp / "out"
        input_root.mkdir()
        write_wcs_fits(input_root / "rgb_test_B.fits", "B", crpix1=42.0, crpix2=24.0)
        write_wcs_fits(input_root / "rgb_test_V.fits", "V", crpix1=25.0, crpix2=40.0)
        write_wcs_fits(input_root / "rgb_test_R.fits", "R", crpix1=33.0, crpix2=33.0)

        payload = run_tool(input_root, output_dir, tmp / "summary.json")
        assert payload["tool"] == "fits_rgb_batch"
        assert payload["status"] == "ok", payload
        results = payload["results"]
        assert results["counts"]["fits_records"] == 3
        assert results["counts"]["groups_written"] == 1
        assert results["modes"]["true_rgb"] == 1
        assert "script_sha256" in results and results["script_sha256"]
        assert "package_versions" in results and results["package_versions"].get("astropy")

        pngs = list((output_dir / "rgb_png").glob("*.png"))
        assert len(pngs) == 1
        qa_files = list((output_dir / "reports").glob("*alignment_qa.json"))
        assert len(qa_files) == 1
        qa = json.loads(qa_files[0].read_text(encoding="utf-8"))
        assert qa["output_mode"] == "true_rgb"
        assert qa["alignment"]["R"]["method"] == "reference"
        assert qa["alignment"]["B"]["method"] == "wcs_reproject_interp"
        assert qa["alignment"]["V"]["method"] == "wcs_reproject_interp"
        assert not qa["warnings"], qa["warnings"]
        assert max(qa["peak_residuals_px"].values()) < 1.0, qa["peak_residuals_px"]

        group_csv = (output_dir / "rgb_group_summary.csv").read_text(encoding="utf-8")
        assert "true_rgb" in group_csv
        assert "RGB_TEST" in group_csv or "RGB-TEST" in group_csv
        run_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
        assert run_summary["command"]
        assert run_summary["parameters"]["alignment_mode"] == "auto"


def check_halpha_blend_is_labeled() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_ha_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        output_dir = tmp / "out"
        input_root.mkdir()
        for filt in ("B", "V", "R", "H-ALPHA"):
            write_wcs_fits(input_root / f"ha_{filt}.fits", filt, crpix1=32.0, crpix2=32.0)

        payload = run_tool(input_root, output_dir, tmp / "summary_ha.json")
        assert payload["status"] == "ok", payload
        report = payload["results"]["group_reports"][0]
        assert report["output_mode"] == "ha_rgb", report
        qa_path = Path(report["alignment_qa"].replace("~", str(Path.home())))
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        assert qa["channels"]["red"] == "R", qa["channels"]
        assert qa["channels"]["ha"] == "H-ALPHA", qa["channels"]
        assert "H-alpha" in " ".join(report["notes"])


def check_nonfinite_pixels_are_warned() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_nonfinite_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        output_dir = tmp / "out"
        input_root.mkdir()
        write_wcs_fits(input_root / "nonfinite_B.fits", "B", crpix1=32.0, crpix2=32.0)
        with fits.open(input_root / "nonfinite_B.fits", mode="update", memmap=False) as hdul:
            hdul[0].data[0, 0] = np.nan
            hdul[0].data[1, 1] = np.inf
            hdul.flush()
        write_wcs_fits(input_root / "nonfinite_V.fits", "V", crpix1=32.0, crpix2=32.0)
        write_wcs_fits(input_root / "nonfinite_R.fits", "R", crpix1=32.0, crpix2=32.0)

        payload = run_tool(input_root, output_dir, tmp / "summary_nonfinite.json")
        assert payload["status"] == "warning", payload
        findings = " ".join(str(item) for item in payload["qa"]["findings"])
        assert "non-finite" in findings and "NaN/Inf" in findings, payload["qa"]
        inventory = (output_dir / "fits_inventory.csv").read_text(encoding="utf-8")
        assert "nonfinite_pixels" in inventory


def check_warning_offset_case() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_warning_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        output_dir = tmp / "out"
        input_root.mkdir()
        write_shifted_plain_fits(input_root / "warning_B.fits", "B", y0=20.0, x0=21.0)
        write_shifted_plain_fits(input_root / "warning_V.fits", "V", y0=24.0, x0=24.0)
        write_shifted_plain_fits(input_root / "warning_R.fits", "R", y0=29.0, x0=30.0)

        payload = run_tool(
            input_root,
            output_dir,
            tmp / "summary_warning.json",
            extra_args=["--alignment-mode", "none", "--qa-residual-threshold", "1.0", "--no-stacks"],
        )
        assert payload["tool"] == "fits_rgb_batch"
        assert payload["status"] == "warning", payload
        results = payload["results"]
        assert results["counts"]["groups_written"] == 1
        assert results["counts"]["warning_groups"] == 1
        group = results["group_reports"][0]
        assert group["status"] == "warning"
        assert group["warnings"], group
        qa_files = list((output_dir / "reports").glob("*alignment_qa.json"))
        assert len(qa_files) == 1
        qa = json.loads(qa_files[0].read_text(encoding="utf-8"))
        assert qa["warnings"], qa
        assert max(qa["peak_residuals_px"].values()) > 1.0, qa["peak_residuals_px"]


def check_invalid_output_parent_blocks_cleanly() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_bad_output_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        input_root.mkdir()
        write_wcs_fits(input_root / "bad_parent_R.fits", "R", crpix1=32.0, crpix2=32.0)
        parent_file = tmp / "parent_is_file"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        summary = tmp / "bad_parent.json"

        proc = run_tool_raw(input_root, parent_file / "out", summary)
        assert proc.returncode != 0, proc.stdout
        payload = json.loads(summary.read_text(encoding="utf-8"))
        assert payload["status"] == "blocked", payload
        assert "parent is not a directory" in " ".join(payload["qa"]["findings"])


def check_output_inside_input_blocks_cleanly() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_fits_rgb_batch_inside_input_") as raw_tmp:
        tmp = Path(raw_tmp)
        input_root = tmp / "input"
        input_root.mkdir()
        for filt in ("B", "V", "R"):
            write_wcs_fits(input_root / f"inside_{filt}.fits", filt, crpix1=32.0, crpix2=32.0)
        summary = tmp / "inside.json"
        output_dir = input_root / "derived_inside_input"

        proc = run_tool_raw(input_root, output_dir, summary)
        assert proc.returncode != 0, proc.stdout
        payload = json.loads(summary.read_text(encoding="utf-8"))
        assert payload["status"] == "blocked", payload
        assert "outside input-root" in " ".join(payload["qa"]["findings"])
        assert not (output_dir / "rgb_png").exists()


def write_rgb_png(path: Path, red_offset: int = 0) -> None:
    yy, xx = np.indices((24, 32))
    red = np.clip(xx * 8 + red_offset, 0, 255).astype("uint8")
    green = np.clip(yy * 10, 0, 255).astype("uint8")
    blue = np.full_like(red, 70, dtype="uint8")
    rgb = np.dstack([red, green, blue])
    Image.fromarray(rgb, mode="RGB").save(path)


def check_visual_rgb_fits_export() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_rgb_visual_export_") as raw_tmp:
        tmp = Path(raw_tmp)
        previous_png = tmp / "previous.png"
        new_png = tmp / "new.png"
        output_fits = tmp / "visual_rgb.fits"
        comparison_png = tmp / "before_after.png"
        manifest_json = tmp / "manifest.json"
        summary_json = tmp / "summary.json"
        write_rgb_png(previous_png, red_offset=0)
        write_rgb_png(new_png, red_offset=20)

        command = [
            sys.executable,
            str(VISUAL_EXPORT_TOOL),
            str(new_png),
            str(output_fits),
            "--previous-png",
            str(previous_png),
            "--comparison-png",
            str(comparison_png),
            "--manifest-json",
            str(manifest_json),
            "--summary-json",
            str(summary_json),
            "--object-name",
            "RGB_TEST_OBJECT",
            "--reason",
            "regression visual redo",
        ]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise AssertionError(f"rgb_visual_fits_export failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")

        payload = json.loads(summary_json.read_text(encoding="utf-8"))
        assert payload["tool"] == "rgb_visual_fits_export"
        assert payload["status"] == "ok", payload
        assert payload["results"]["calibration_scope"] == "display_only_not_flux_calibrated"
        assert payload["results"]["rgb_cube_shape"] == [3, 24, 32]
        assert output_fits.exists()
        assert comparison_png.exists()
        assert manifest_json.exists()

        with fits.open(output_fits) as hdul:
            assert hdul[0].header["IMAGETYP"] == "VISUAL_RGB"
            assert hdul[0].header["CALIB"] == "DISPLAY_ONLY"
            assert hdul["RGB_CUBE"].data.shape == (3, 24, 32)
            assert hdul["RGB_CUBE"].header["BUNIT"] == "normalized_display_intensity"
            for name in ("RED", "GREEN", "BLUE"):
                assert hdul[name].data.shape == (24, 32)
                assert hdul[name].header["BUNIT"] == "normalized_display_intensity"
                assert np.nanmin(hdul[name].data) >= 0.0
                assert np.nanmax(hdul[name].data) <= 1.0

        manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
        assert manifest["extra"]["previous_png_sha256"]
        assert manifest["extra"]["comparison_png_sha256"]
        assert manifest["extra"]["warning"].startswith("Display-only")


def main() -> int:
    check_clean_wcs_pass()
    check_halpha_blend_is_labeled()
    check_nonfinite_pixels_are_warned()
    check_warning_offset_case()
    check_invalid_output_parent_blocks_cleanly()
    check_output_inside_input_blocks_cleanly()
    check_visual_rgb_fits_export()
    print("All FITS RGB batch regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
