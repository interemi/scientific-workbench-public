#!/usr/bin/env python3
"""Regression checks for legacy_rv_coursework_workbench analyze guardrails."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "legacy_rv_coursework_workbench.py"
MINI = ROOT / "examples" / "science" / "legacy_spectroscopy_mini"

FIELDS = [
    "case_id",
    "case_label",
    "mode",
    "object_name",
    "image_name",
    "template_image",
    "template_vhelio_kms",
    "aperture",
    "shift_pix",
    "height",
    "fwhm_kms",
    "fwhm_pix",
    "tdr",
    "vrel_kms",
    "verr_kms",
    "veldisp_kms_per_pix",
    "txtonly_path",
]


def write_csv(path: Path, rows: list[dict], fields: list[str] = FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_fits_pair(root: Path) -> Path:
    from astropy.io import fits

    fits_root = root / "fits_p1"
    fits_root.mkdir(parents=True, exist_ok=True)
    for source, name, ra, dec in [
        (MINI / "mini_multispec.fits", "mini_multispec.fits", "10:00:00", "+20:00:00"),
        (MINI / "mini_template.fits", "mini_template.fits", "10:01:00", "+20:02:00"),
    ]:
        target = fits_root / name
        shutil.copy2(source, target)
        with fits.open(target, mode="update") as hdul:
            header = hdul[0].header
            header["RA"] = ra
            header["DEC"] = dec
            header["OBSERVAT"] = "DSAZ"
            header["DATE-OBS"] = "2024-01-01T00:00:00"
            header["EXPTIME"] = 120.0
            header["EQUINOX"] = 2000.0
            hdul.flush()
    return fits_root


def rv_rows(count: int = 6) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append(
            {
                "case_id": "mini_single_rv",
                "case_label": "Mini estrella simple",
                "mode": "single_rv",
                "object_name": "mini_obj",
                "image_name": "mini_multispec.fits",
                "template_image": "mini_template.fits",
                "template_vhelio_kms": -12.5,
                "aperture": index + 1,
                "shift_pix": -8.0 - 0.04 * index,
                "height": 0.6,
                "fwhm_kms": 37.5 + index,
                "fwhm_pix": 10.0 + 0.1 * index,
                "tdr": 12.0 - 0.2 * index,
                "vrel_kms": -30.0 - 0.4 * index,
                "verr_kms": 1.5 + 0.1 * index,
                "veldisp_kms_per_pix": 3.75,
                "txtonly_path": "synthetic.txt",
            }
        )
    return rows


def run_analyze(inputs: list[Path], fits_root: Path, output_dir: Path, summary_json: Path, calibration_csv: Path | None = None) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "analyze",
        *[str(path) for path in inputs],
        "--output-dir",
        str(output_dir),
        "--fits-root",
        str(fits_root),
        "--summary-json",
        str(summary_json),
    ]
    if calibration_csv:
        cmd.extend(["--calibration-csv", str(calibration_csv)])
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    payload = None
    source_texts = []
    if summary_json.exists() and summary_json.is_file():
        source_texts.append(summary_json.read_text(encoding="utf-8"))
    source_texts.append(completed.stdout)
    for text in source_texts:
        stripped = text.strip()
        marker = stripped.find('{\n  "tool"')
        candidate = stripped[marker:] if marker >= 0 else stripped
        if candidate.startswith("{"):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
    return {
        "cmd": cmd,
        "rc": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "payload": payload,
        "output_dir": output_dir,
    }


def assert_blocked_clean(result: dict, output_dir: Path) -> None:
    assert result["rc"] == 2, result
    assert isinstance(result["payload"], dict), result
    assert result["payload"]["status"] == "blocked", result["payload"]
    assert "Traceback (most recent call last)" not in result["stderr"], result["stderr"]
    for name in ["rv_orders_all.csv", "rv_orders_filtered.csv", "rv_summary.csv", "summary.md"]:
        assert not (output_dir / name).exists(), f"Producto parcial inesperado: {output_dir / name}"


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="legacy-rv-analyze-regression-"))
    try:
        fixtures = base / "fixtures"
        outputs = base / "outputs"
        summaries = base / "summaries"
        fits_root = make_fits_pair(fixtures / "practice")

        rows_csv = fixtures / "rows.csv"
        write_csv(rows_csv, rv_rows())
        calibration_csv = fixtures / "calibration.csv"
        calibration_csv.write_text("5,4\n10,12\n15,22\n", encoding="utf-8")

        happy = run_analyze([rows_csv], fits_root, outputs / "happy", summaries / "happy.json", calibration_csv)
        assert happy["rc"] == 0, happy
        assert happy["payload"]["status"] == "ok", happy["payload"]
        assert (outputs / "happy" / "rv_summary.csv").exists()

        missing_column_csv = fixtures / "missing_column.csv"
        write_csv(missing_column_csv, [{"case_id": "broken", "image_name": "mini_multispec.fits"}], ["case_id", "image_name"])
        assert_blocked_clean(
            run_analyze([missing_column_csv], fits_root, outputs / "missing_column", summaries / "missing_column.json"),
            outputs / "missing_column",
        )

        bad_calibration = fixtures / "bad_calibration.csv"
        bad_calibration.write_text("fwhm,vsini\n10,12\nbad,row\n", encoding="utf-8")
        assert_blocked_clean(
            run_analyze([rows_csv], fits_root, outputs / "bad_calibration", summaries / "bad_calibration.json", bad_calibration),
            outputs / "bad_calibration",
        )

        bad_summary_parent = outputs / "summary_parent_is_file"
        bad_summary_parent.parent.mkdir(parents=True, exist_ok=True)
        bad_summary_parent.write_text("not a directory\n", encoding="utf-8")
        assert_blocked_clean(
            run_analyze([rows_csv], fits_root, outputs / "bad_summary", bad_summary_parent / "summary.json", calibration_csv),
            outputs / "bad_summary",
        )

        assert_blocked_clean(
            run_analyze([fixtures / "missing.csv"], fits_root, outputs / "missing_input", summaries / "missing_input.json"),
            outputs / "missing_input",
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
