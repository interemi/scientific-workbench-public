#!/usr/bin/env python3
"""Narrow regression checks for fxcor_iraf_workbench.py prepare-session."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fxcor_iraf_workbench.py"
SOURCE_FITS = ROOT / "examples" / "science" / "legacy_spectroscopy_mini" / "mini_multispec.fits"
REQUIRED_FITS = [
    "npwand_n3.fits",
    "nhd161096_n3.fits",
    "nhd166620_n2.fits",
    "nrej1101_foces02_n2.fits",
    "nhd100696_n3.fits",
    "nhd97004_n4.fits",
    "nhd92588_n2.fits",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_practice(root: Path, names: list[str] | None = None, *, login: bool = True) -> None:
    fits_dir = root / "fits_p1"
    fits_dir.mkdir(parents=True, exist_ok=True)
    for name in names or REQUIRED_FITS:
        shutil.copy2(SOURCE_FITS, fits_dir / name)
    if login:
        login_dir = root / "CODEX" / "01_iraf_safe"
        login_dir.mkdir(parents=True, exist_ok=True)
        (login_dir / "login.cl").write_text("set home = .\n", encoding="utf-8")


def run_prepare(practice: Path, output_dir: Path, *, summary: Path | None = None, manifest: Path | None = None) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [sys.executable, str(SCRIPT), "prepare-session", str(practice), "--output-dir", str(output_dir)]
    if summary:
        cmd.extend(["--summary-json", str(summary)])
    if manifest:
        cmd.extend(["--manifest-json", str(manifest)])
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=30, env=env)
    payload_text = summary.read_text(encoding="utf-8") if summary and summary.exists() else result.stdout
    payload = json.loads(payload_text)
    return result, payload


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="sda_fxcor_prepare_regression_", dir="/tmp"))
    try:
        ok_practice = base / "practice_ok"
        ok_output = base / "workspace_ok"
        ok_summary = base / "ok.json"
        ok_manifest = base / "ok_manifest.json"
        make_practice(ok_practice)
        result, payload = run_prepare(ok_practice, ok_output, summary=ok_summary, manifest=ok_manifest)
        require(result.returncode == 0, result.stderr)
        require(payload["status"] == "ok", payload)
        require((ok_output / "fxcor_cases.json").exists(), "config missing")
        require((ok_output / "manual_overrides.csv").exists(), "manual override template missing")
        require(len(payload["artifacts"]["copied_fits"]) == len(REQUIRED_FITS), payload["artifacts"])
        require(ok_manifest.exists(), "manifest missing")

        risky_practice = base / "practice with spaces"
        risky_output = base / "workspace_risky"
        make_practice(risky_practice, login=False)
        result, payload = run_prepare(risky_practice, risky_output, summary=base / "risky.json")
        require(result.returncode == 0, result.stderr)
        require(payload["status"] == "warning", payload)
        findings = payload["results"]["warning_findings"]
        require(any("espacios" in item or "ASCII" in item for item in findings), findings)
        require(any("login.cl" in item for item in findings), findings)

        partial_practice = base / "practice_partial"
        make_practice(partial_practice, names=REQUIRED_FITS[:2])
        result, payload = run_prepare(partial_practice, base / "workspace_partial", summary=base / "partial.json")
        require(result.returncode == 0, result.stderr)
        require(payload["status"] == "warning", payload)
        require(any("1 de 6" in item for item in payload["results"]["warning_findings"]), payload)

        missing_fits = base / "missing_fits"
        missing_fits.mkdir()
        result, payload = run_prepare(missing_fits, base / "workspace_missing", summary=base / "missing.json")
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require(not (base / "workspace_missing").exists(), "blocked run created workspace")

        inside_original = base / "inside_original"
        make_practice(inside_original)
        unsafe_output = inside_original / "workspace"
        result, payload = run_prepare(inside_original, unsafe_output, summary=base / "inside.json")
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require(not unsafe_output.exists(), "output inside original should not be created")

        bad_parent = base / "summary_parent_is_file"
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        bad_practice = base / "bad_summary_practice"
        make_practice(bad_practice)
        result, payload = run_prepare(bad_practice, base / "bad_summary_workspace", summary=bad_parent / "summary.json")
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require("Traceback" not in result.stderr, result.stderr)
        require(not (base / "bad_summary_workspace").exists(), "invalid summary path should block before workspace creation")

        print("fxcor prepare-session regression passed")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
