#!/usr/bin/env python3
"""Regression checks for v1.6 validate_skill_samples hardening."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "validate_skill_samples.py"


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def test_summary_marks_failed_feature(tmp: Path) -> None:
    from validate_skill_samples import summarize_validation_report

    report = {
        "by_extension": {".csv": [{"path": "sample.csv", "status": "ok"}]},
        "feature_runs": {
            "good": {"returncode": 0},
            "bad": {"returncode": 1},
        },
    }
    summary = summarize_validation_report(report)
    assert summary["status"] == "fail"
    assert summary["exit_code"] == 1
    assert summary["failed_features"] == ["bad"]


def test_validate_roots_blocks_missing_and_file(tmp: Path) -> None:
    from validate_skill_samples import validate_roots

    tmp.mkdir(parents=True, exist_ok=True)
    missing = tmp / "missing"
    try:
        validate_roots([str(missing)])
    except RuntimeError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing root was accepted")

    file_root = tmp / "file_root.txt"
    file_root.write_text("not a directory\n", encoding="utf-8")
    try:
        validate_roots([str(file_root)])
    except RuntimeError as exc:
        assert "not a directory" in str(exc)
    else:
        raise AssertionError("file root was accepted")


def test_missing_root_cli_fails_cleanly(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    summary = tmp / "missing_root_summary.json"
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            str(tmp / "missing_root"),
            "--validation-profile",
            "quick",
            "--output-dir",
            str(tmp / "out"),
            "--summary-json",
            str(summary),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["tool"] == "validate_skill_samples"
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "RuntimeError"
    assert "does not exist" in payload["results"]["error"]


def test_output_dir_file_fails_cleanly(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    root = tmp / "root"
    root.mkdir()
    output_file = tmp / "output_file"
    output_file.write_text("not a directory\n", encoding="utf-8")
    summary = tmp / "output_file_summary.json"
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--validation-profile",
            "quick",
            "--output-dir",
            str(output_file),
            "--summary-json",
            str(summary),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "FileExistsError"


def test_first_image_fits_rejects_non_image_spectrum(tmp: Path) -> None:
    from astropy.io import fits
    import numpy as np

    from validate_skill_samples import first_image_fits

    tmp.mkdir(parents=True, exist_ok=True)
    spectral = tmp / "mini_multispec_like.fits"
    image = tmp / "image.fits"
    fits.PrimaryHDU(np.ones((2, 32), dtype="float32")).writeto(spectral)
    assert first_image_fits({".fits": [spectral]}) is None
    fits.PrimaryHDU(np.ones((64, 64), dtype="float32")).writeto(image)
    assert first_image_fits({".fits": [spectral, image]}) == image


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="validate_skill_samples_v16_") as raw_tmp:
        tmp = Path(raw_tmp)
        tests = [
            test_summary_marks_failed_feature,
            test_validate_roots_blocks_missing_and_file,
            test_missing_root_cli_fails_cleanly,
            test_output_dir_file_fails_cleanly,
            test_first_image_fits_rejects_non_image_spectrum,
        ]
        for test in tests:
            test(tmp / test.__name__)
    print("validate_skill_samples v1.6 regression checks passed")


if __name__ == "__main__":
    main()
