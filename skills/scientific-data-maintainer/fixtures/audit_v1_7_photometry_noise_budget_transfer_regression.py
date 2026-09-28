#!/usr/bin/env python3
"""v1.7 transfer-pattern regression for photometry_noise_budget.py."""

from __future__ import annotations

import json
import math
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


def check_sensor_roi_transfer_pattern(tmp: Path) -> dict:
    summary = tmp / "sensor_roi" / "summary.json"
    report = tmp / "sensor_roi" / "report.md"
    manifest = tmp / "sensor_roi" / "manifest.json"
    proc = run_tool(
        [
            "--source",
            "4200",
            "--sky-per-pixel",
            "12",
            "--dark-per-pixel",
            "0.3",
            "--read-noise",
            "2.1",
            "--n-pixels",
            "64",
            "--sky-estimate-pixels",
            "800",
            "--n-frames",
            "5",
            "--units",
            "electrons",
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
    if proc.stderr.strip():
        fail(f"unexpected stderr: {proc.stderr}")

    payload = require_envelope(summary, "ok")
    results = payload["results"]
    if not math.isclose(results["snr"], 128.33784710232533, rel_tol=0, abs_tol=1e-9):
        fail(f"unexpected transferred sensor ROI SNR: {results['snr']}")
    if results["dominant_noise_term"] != "source_shot_noise_e":
        fail(f"unexpected dominant term: {results['dominant_noise_term']}")
    if results["operating_regime"] != "source-shot-noise-limited":
        fail(f"unexpected operating regime: {results['operating_regime']}")
    if not math.isclose(results["variance_terms_e2"]["read_variance_e2"], 1411.2, rel_tol=0, abs_tol=1e-9):
        fail("read-noise variance changed unexpectedly")
    if not math.isclose(results["variance_terms_e2"]["background_estimate_variance_e2"], 427.776, rel_tol=0, abs_tol=1e-9):
        fail("background-estimate variance changed unexpectedly")
    if not report.exists() or not manifest.exists():
        fail("report and manifest should be written for transferred sensor ROI use")
    manifest_payload = read_json_strict(manifest)
    if manifest_payload.get("command") != "photometry_noise_budget.py":
        fail("manifest should preserve the command id")
    if manifest_payload.get("parameters", {}).get("n_pixels") != 64.0:
        fail("manifest should preserve transferred ROI parameters")
    return {
        "snr": results["snr"],
        "dominant_noise_term": results["dominant_noise_term"],
        "operating_regime": results["operating_regime"],
    }


def check_nonfinite_sensor_input_blocks_cleanly(tmp: Path) -> None:
    summary = tmp / "blocked" / "summary.json"
    proc = run_tool(
        [
            "--source",
            "inf",
            "--sky-per-pixel",
            "12",
            "--dark-per-pixel",
            "0.3",
            "--read-noise",
            "2.1",
            "--n-pixels",
            "64",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode == 0:
        fail("non-finite sensor signal should be blocked")
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        fail("non-finite sensor signal emitted traceback")
    payload = require_envelope(summary, "blocked")
    findings = " ".join(payload.get("qa", {}).get("findings", []))
    if "--source" not in findings or "finite" not in findings:
        fail(f"blocked finding should name the non-finite source: {findings}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_v1_7_noise_transfer_") as tmp_name:
        tmp = Path(tmp_name)
        sensor_metrics = check_sensor_roi_transfer_pattern(tmp)
        print("PASS check_sensor_roi_transfer_pattern")
        check_nonfinite_sensor_input_blocks_cleanly(tmp)
        print("PASS check_nonfinite_sensor_input_blocks_cleanly")
    print(
        json.dumps(
            {
                "status": "ok",
                "capability": "photometry_noise_budget.py",
                "pattern": "transferable_sensor_roi_noise_budget",
                "metrics": sensor_metrics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
