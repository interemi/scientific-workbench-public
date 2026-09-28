#!/usr/bin/env python3
"""Narrow v1.6 regression checks for legacy_spectroscopy_envcheck.py."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "legacy_spectroscopy_envcheck.py"
DATANALYSIS = ROOT / "scripts" / "datanalysis_env.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def make_practice(root: Path, *, calibration: bool = True, istarmod: bool = True, fits_count: int = 1) -> Path:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    fits_dir = root / "fits_p1"
    fits_dir.mkdir()
    for index in range(fits_count):
        (fits_dir / f"synthetic_{index + 1}.fits").write_text("synthetic fits placeholder\n", encoding="utf-8")
    if calibration:
        (root / "FWHM_vsini_datafit.csv").write_text("fwhm,vsini\n10,20\n", encoding="utf-8")
    if istarmod:
        istar = root / "iSTARMOD"
        istar.mkdir()
        (istar / "iStarmod.py").write_text("# fake iSTARMOD\n", encoding="utf-8")
        (istar / "lambdas.dat").write_text("6563\n", encoding="utf-8")
    return root


def run_envcheck(root: Path, summary: Path, *, manifest: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(DATANALYSIS), "python", str(SCRIPT), str(root), "--summary-json", str(summary)]
    if manifest:
        command.extend(["--manifest-json", str(manifest)])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, env=env)


def assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="legacy-envcheck-v1-6-") as tmp_raw:
        tmp = Path(tmp_raw)
        tools = tmp / "fake legacy tools"
        for name in ("cl", "mkiraf", "xgterm"):
            make_executable(tools / name, f"#!/bin/sh\necho fake {name}\nexit 0\n")
        env = os.environ.copy()
        env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")

        complete = make_practice(tmp / "complete")
        complete_summary = tmp / "complete.json"
        complete_manifest = tmp / "complete_manifest.json"
        complete_result = run_envcheck(complete, complete_summary, manifest=complete_manifest, env=env)
        assert complete_result.returncode == 0, complete_result.stderr
        assert_no_traceback(complete_result)
        complete_payload = read_json(complete_summary)
        assert complete_payload["status"] == "ok", complete_payload
        assert complete_payload["qa"]["status"] == "ok", complete_payload
        assert complete_manifest.exists()

        no_cal = make_practice(tmp / "no_calibration", calibration=False)
        no_cal_summary = tmp / "no_calibration.json"
        no_cal_result = run_envcheck(no_cal, no_cal_summary, env=env)
        assert no_cal_result.returncode == 0, no_cal_result.stderr
        assert_no_traceback(no_cal_result)
        no_cal_payload = read_json(no_cal_summary)
        assert no_cal_payload["status"] == "warning", no_cal_payload
        assert any("FWHM_vsini_datafit" in item for item in no_cal_payload["results"]["warning_findings"]), no_cal_payload

        missing_summary = tmp / "missing.json"
        missing_result = run_envcheck(tmp / "missing_root", missing_summary, env=env)
        assert missing_result.returncode == 2, missing_result.stderr
        assert_no_traceback(missing_result)
        assert read_json(missing_summary)["status"] == "blocked"

        root_file = tmp / "root_is_file"
        root_file.write_text("not a directory\n", encoding="utf-8")
        root_file_summary = tmp / "root_file.json"
        root_file_result = run_envcheck(root_file, root_file_summary, env=env)
        assert root_file_result.returncode == 2, root_file_result.stderr
        assert_no_traceback(root_file_result)
        assert read_json(root_file_summary)["status"] == "blocked"

        bad_parent = tmp / "summary_parent_file"
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        bad_summary = bad_parent / "summary.json"
        bad_summary_result = run_envcheck(complete, bad_summary, env=env)
        assert bad_summary_result.returncode == 2, bad_summary_result.stderr
        assert_no_traceback(bad_summary_result)
        assert "Could not write summary JSON" in bad_summary_result.stderr

        bad_manifest_parent = tmp / "manifest_parent_file"
        bad_manifest_parent.write_text("not a directory\n", encoding="utf-8")
        bad_manifest_summary = tmp / "bad_manifest.json"
        bad_manifest = bad_manifest_parent / "manifest.json"
        bad_manifest_result = run_envcheck(complete, bad_manifest_summary, manifest=bad_manifest, env=env)
        assert bad_manifest_result.returncode == 2, bad_manifest_result.stderr
        assert_no_traceback(bad_manifest_result)
        assert read_json(bad_manifest_summary)["status"] == "blocked"

    print("legacy_spectroscopy_envcheck v1.6 regression: ok")


if __name__ == "__main__":
    main()
