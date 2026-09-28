#!/usr/bin/env python3
"""Regression checks for legacy_external_reference_check input and QA guardrails."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "legacy_external_reference_check.py"
MINI_FITS = ROOT / "examples" / "science" / "legacy_spectroscopy_mini" / "mini_multispec.fits"


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def write_fits(path: Path) -> Path:
    from astropy.io import fits

    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MINI_FITS, path)
    with fits.open(path, mode="update") as hdul:
        hdul[0].header["MJD-OBS"] = 49052.14725
        hdul[0].header["DATE-OBS"] = "1993-02-01T00:00:00"
        hdul.flush()
    return path


def rv_payload(*, pw_rv=-11.0) -> dict:
    return {
        "tool": "legacy_rv_coursework_workbench.analyze",
        "status": "ok",
        "results": {
            "rv_summaries": [
                {"case_id": "pwand_rv", "vhelio_media_kms": pw_rv},
                {"case_id": "rej_compA_rv", "vhelio_media_kms": 80.0},
                {"case_id": "rej_compB_rv", "vhelio_media_kms": -70.0},
            ],
            "vsini_rows": [
                {"case_id": "pwand_vsini36", "vsini_interp_kms": 22.1},
                {"case_id": "rej_vsini36_compA_k0", "vsini_interp_kms": 26.0},
                {"case_id": "rej_vsini36_compB_k1", "vsini_interp_kms": 27.5},
            ],
        },
    }


def li_payload() -> dict:
    return {
        "tool": "li6708_equivalent_width_workbench.measure",
        "status": "ok",
        "results": {"ew_milliangstrom": 272.0},
    }


def istarmod_payload(log_path: Path) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("V_rad = -11.2\nV_rot = 22.4\nEW = 0.273 +- 0.010\n", encoding="utf-8")
    return {"tool": "istarmod_workbench.run-sm", "status": "ok", "artifacts": {"log_path": str(log_path)}}


def run_check(
    rv_summary: Path,
    output_dir: Path,
    summary_json: Path,
    *,
    gzleo_fits: Path | None = None,
    li_summary: Path | None = None,
    istarmod_summary: Path | None = None,
) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "check",
        "--rv-summary",
        str(rv_summary),
        "--output-dir",
        str(output_dir),
        "--summary-json",
        str(summary_json),
    ]
    if gzleo_fits:
        cmd.extend(["--gzleo-fits", str(gzleo_fits)])
    if li_summary:
        cmd.extend(["--li-summary", str(li_summary)])
    if istarmod_summary:
        cmd.extend(["--istarmod-summary", str(istarmod_summary)])
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=80,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    payload = None
    for text in [summary_json.read_text(encoding="utf-8") if summary_json.is_file() else "", completed.stdout]:
        stripped = text.strip()
        marker = stripped.find('{\n  "tool"')
        candidate = stripped[marker:] if marker >= 0 else stripped
        if candidate.startswith("{"):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
    return {"rc": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "payload": payload}


def assert_no_traceback(result: dict) -> None:
    text = f"{result['stdout']}\n{result['stderr']}"
    assert "Traceback (most recent call last)" not in text, text


def assert_blocked_clean(result: dict, output_dir: Path) -> None:
    assert result["rc"] == 2, result
    assert isinstance(result["payload"], dict), result
    assert result["payload"]["status"] == "blocked", result["payload"]
    assert_no_traceback(result)
    assert not (output_dir / "external_reference_check.md").exists(), f"Producto parcial inesperado: {output_dir}"


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="legacy-external-reference-regression-"))
    try:
        fixtures = base / "fixtures"
        outputs = base / "outputs"
        summaries = base / "summaries"
        rv_good = write_json(fixtures / "rv_good.json", rv_payload())
        rv_nan = write_json(fixtures / "rv_nan.json", rv_payload(pw_rv=float("nan")))
        li_good = write_json(fixtures / "li_good.json", li_payload())
        istarmod_good = write_json(fixtures / "istarmod.json", istarmod_payload(fixtures / "istarmod.log"))
        gzleo_fits = write_fits(fixtures / "gzleo.fits")

        happy = run_check(
            rv_good,
            outputs / "happy",
            summaries / "happy.json",
            gzleo_fits=gzleo_fits,
            li_summary=li_good,
            istarmod_summary=istarmod_good,
        )
        assert happy["rc"] == 0, happy
        assert happy["payload"]["status"] == "ok", happy["payload"]
        assert (outputs / "happy" / "external_reference_check.md").is_file()

        nan_case = run_check(rv_nan, outputs / "nan", summaries / "nan.json")
        assert nan_case["rc"] == 0, nan_case
        assert nan_case["payload"]["status"] == "warning", nan_case["payload"]
        assert "NaN" not in nan_case["stdout"], nan_case["stdout"]
        assert "NaN" not in (summaries / "nan.json").read_text(encoding="utf-8")

        assert_blocked_clean(
            run_check(fixtures / "missing.json", outputs / "missing", summaries / "missing.json"),
            outputs / "missing",
        )

        corrupt = fixtures / "corrupt.json"
        corrupt.write_text("{not-json", encoding="utf-8")
        assert_blocked_clean(run_check(corrupt, outputs / "corrupt", summaries / "corrupt.json"), outputs / "corrupt")

        bad_parent = outputs / "summary_parent_is_file"
        bad_parent.parent.mkdir(parents=True, exist_ok=True)
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        assert_blocked_clean(run_check(rv_good, outputs / "bad_summary", bad_parent / "summary.json"), outputs / "bad_summary")
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
