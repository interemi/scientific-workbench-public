#!/usr/bin/env python3
"""v1.6 regression checks for photometry_noise_budget.py edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "photometry_noise_budget.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def run_tool(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def read_json_strict(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(
        text,
        parse_constant=lambda token: fail(f"non-strict JSON constant emitted: {token}"),
    )


def require_envelope(path: Path, status: str) -> dict:
    payload = read_json_strict(path)
    if payload.get("tool") != "photometry_noise_budget":
        fail(f"unexpected tool id: {payload.get('tool')}")
    if payload.get("status") != status:
        fail(f"expected status {status}, got {payload.get('status')}")
    qa = payload.get("qa")
    if not isinstance(qa, dict) or qa.get("status") != status:
        fail(f"expected qa.status {status}, got {qa}")
    return payload


def check_happy_electrons(tmp: Path) -> None:
    summary = tmp / "happy" / "summary.json"
    report = tmp / "happy" / "report.md"
    manifest = tmp / "happy" / "manifest.json"
    proc = run_tool(
        [
            "--source",
            "25000",
            "--sky-per-pixel",
            "42",
            "--dark-per-pixel",
            "0.2",
            "--read-noise",
            "4.3",
            "--n-pixels",
            "80",
            "--sky-estimate-pixels",
            "600",
            "--n-frames",
            "3",
            "--summary-json",
            str(summary),
            "--report-md",
            str(report),
            "--manifest-json",
            str(manifest),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["snr"] <= 0:
        fail("happy path SNR should be positive")
    if not report.exists() or not manifest.exists():
        fail("report and manifest should be written")


def check_happy_adu(tmp: Path) -> None:
    summary = tmp / "adu" / "summary.json"
    proc = run_tool(
        [
            "--source",
            "18000",
            "--sky-per-pixel",
            "30",
            "--dark-per-pixel",
            "0.05",
            "--read-noise",
            "5",
            "--n-pixels",
            "100",
            "--sky-estimate-pixels",
            "900",
            "--n-frames",
            "5",
            "--units",
            "adu",
            "--gain",
            "1.7",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["gain_e_per_adu"] != 1.7:
        fail("ADU gain should be preserved in results")


def check_zero_variance_warning(tmp: Path) -> None:
    summary = tmp / "zero_variance" / "summary.json"
    proc = run_tool(
        [
            "--source",
            "0",
            "--sky-per-pixel",
            "0",
            "--dark-per-pixel",
            "0",
            "--read-noise",
            "0",
            "--n-pixels",
            "12",
            "--sky-estimate-pixels",
            "50",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "warning")
    if payload["results"]["snr"] is not None:
        fail("undefined zero-variance SNR should be null")


def check_missing_sky_estimate_warning(tmp: Path) -> None:
    summary = tmp / "missing_sky_estimate" / "summary.json"
    proc = run_tool(
        [
            "--source",
            "12000",
            "--sky-per-pixel",
            "80",
            "--dark-per-pixel",
            "0.1",
            "--read-noise",
            "6",
            "--n-pixels",
            "95",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "warning")
    findings = " ".join(payload.get("qa", {}).get("findings", []))
    if "background-estimation" not in findings:
        fail("missing sky-estimate warning should be explicit")


def check_invalid_numeric_blocked(tmp: Path) -> None:
    invalid_cases = [
        ("negative_source", ["--source", "-1", "--sky-per-pixel", "1", "--dark-per-pixel", "0", "--read-noise", "1", "--n-pixels", "5"]),
        ("negative_sky", ["--source", "1", "--sky-per-pixel", "-10", "--dark-per-pixel", "0", "--read-noise", "0", "--n-pixels", "10", "--sky-estimate-pixels", "10"]),
        ("nan_source", ["--source", "nan", "--sky-per-pixel", "1", "--dark-per-pixel", "0", "--read-noise", "1", "--n-pixels", "5"]),
        ("negative_read_noise", ["--source", "1", "--sky-per-pixel", "1", "--dark-per-pixel", "0", "--read-noise", "-2", "--n-pixels", "5"]),
        ("zero_pixels", ["--source", "1", "--sky-per-pixel", "1", "--dark-per-pixel", "0", "--read-noise", "1", "--n-pixels", "0"]),
    ]
    for name, base_args in invalid_cases:
        summary = tmp / "blocked" / f"{name}.json"
        proc = run_tool([*base_args, "--summary-json", str(summary)])
        if proc.returncode == 0:
            fail(f"{name} should return non-zero")
        if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
            fail(f"{name} emitted traceback")
        payload = require_envelope(summary, "blocked")
        if not payload.get("qa", {}).get("findings"):
            fail(f"{name} should include a blocking finding")


def check_output_path_blocked(tmp: Path) -> None:
    parent_file = tmp / "not_a_directory"
    parent_file.write_text("sentinel", encoding="utf-8")
    summary = tmp / "output_path" / "summary.json"
    proc = run_tool(
        [
            "--source",
            "100",
            "--sky-per-pixel",
            "10",
            "--dark-per-pixel",
            "0",
            "--read-noise",
            "2",
            "--n-pixels",
            "20",
            "--summary-json",
            str(summary),
            "--report-md",
            str(parent_file / "report.md"),
        ]
    )
    if proc.returncode == 0:
        fail("bad output path should return non-zero")
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        fail("bad output path emitted traceback")
    payload = require_envelope(summary, "blocked")
    if "--report-md parent is not a directory" not in payload["results"]["blocked_reason"]:
        fail("blocked reason should name the invalid output path")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_noise_budget_regression_") as tmp_name:
        tmp = Path(tmp_name)
        check_happy_electrons(tmp)
        print("PASS check_happy_electrons")
        check_happy_adu(tmp)
        print("PASS check_happy_adu")
        check_zero_variance_warning(tmp)
        print("PASS check_zero_variance_warning")
        check_missing_sky_estimate_warning(tmp)
        print("PASS check_missing_sky_estimate_warning")
        check_invalid_numeric_blocked(tmp)
        print("PASS check_invalid_numeric_blocked")
        check_output_path_blocked(tmp)
        print("PASS check_output_path_blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
