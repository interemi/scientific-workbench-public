#!/usr/bin/env python3
"""Regression checks for photometric_solution.py v1.6 edge behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT = Path(__file__).resolve().with_name("photometric_solution.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_solution(input_table: Path, out_dir: Path, *, extra: list[str] | None = None, summary: Path | None = None) -> tuple[int, dict | None, str]:
    summary = summary or out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        str(input_table),
        "--summary-json",
        str(summary),
    ]
    if extra:
        cmd.extend(extra)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(out_dir / "mplconfig")
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    payload = None
    if summary.exists():
        payload = json.loads(summary.read_text(encoding="utf-8"))
    return proc.returncode, payload, (proc.stdout or "") + "\n" + (proc.stderr or "")


def assert_strict_json(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


def write_happy_table(path: Path) -> None:
    airmass = np.linspace(1.0, 1.8, 10)
    inst_mag = np.linspace(-14.0, -12.2, 10)
    offset = 24.5 - 0.18 * airmass
    std_mag = inst_mag + offset
    pd.DataFrame({"std_mag": std_mag, "inst_mag": inst_mag, "airmass": airmass}).to_csv(path, index=False)


def write_color_table(path: Path) -> None:
    airmass = np.array([1.02, 1.25, 1.48, 1.73, 1.10, 1.92, 1.37, 1.64, 2.04, 1.55])
    color = np.array([-0.10, 0.65, 0.20, 1.10, 0.90, 0.35, 1.35, 0.05, 0.75, 1.55])
    inst_mag = -14.4 + np.linspace(0, 1.8, len(airmass))
    offset = 24.1 - 0.13 * airmass + 0.055 * color
    std_mag = inst_mag + offset
    pd.DataFrame(
        {
            "std_mag": std_mag,
            "inst_mag": inst_mag,
            "airmass": airmass,
            "b_minus_v": color,
            "offset_err": np.full(len(airmass), 0.015),
        }
    ).to_csv(path, index=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="photometric_solution_v16_") as raw_tmp:
        root = Path(raw_tmp)

        happy = root / "happy.csv"
        write_happy_table(happy)
        nested_summary = root / "nested" / "summary" / "photometric.json"
        rc, payload, text = run_solution(
            happy,
            root / "happy_out",
            summary=nested_summary,
            extra=[
                "--coefficients-csv",
                str(root / "happy_out" / "coefficients.csv"),
                "--residual-csv",
                str(root / "happy_out" / "residuals.csv"),
                "--residual-plot",
                str(root / "happy_out" / "residuals.png"),
                "--report-md",
                str(root / "happy_out" / "report.md"),
            ],
        )
        require(rc == 0, f"happy fit should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "happy fit should emit ok payload")
        require(nested_summary.exists(), "summary-json parent directories should be created")
        require((root / "happy_out" / "coefficients.csv").exists(), "coefficients CSV should exist")
        require((root / "happy_out" / "residuals.png").exists(), "residual plot should exist")
        assert_strict_json(payload)
        print("PASS check_happy_solution_outputs")

        color = root / "color.csv"
        write_color_table(color)
        rc, payload, text = run_solution(
            color,
            root / "color_out",
            extra=["--color-col", "b_minus_v", "--include-color-term", "--error-col", "offset_err"],
        )
        require(rc == 0, f"color fit should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "color fit should be ok")
        require("color_term" in payload.get("results", {}).get("parameters", {}), "color term should be fitted")
        assert_strict_json(payload)
        print("PASS check_color_solution_ok")

        narrow = root / "narrow.csv"
        pd.DataFrame(
            {
                "std_mag": [10.1, 10.3, 10.5, 10.7],
                "inst_mag": [-14.1, -13.9, -13.7, -13.5],
                "airmass": [1.10, 1.12, 1.13, 1.14],
                "b_minus_v": [0.50, 0.53, 0.55, 0.56],
                "offset_err": [0.02, 0.02, 0.02, 0.02],
            }
        ).to_csv(narrow, index=False)
        rc, payload, text = run_solution(narrow, root / "narrow_out", extra=["--color-col", "b_minus_v", "--include-color-term", "--error-col", "offset_err"])
        require(rc == 0, f"narrow coverage should exit 0 with warning: {text}")
        require(payload is not None and payload.get("status") == "warning", "narrow coverage should warn")
        assert_strict_json(payload)
        print("PASS check_narrow_coverage_warns")

        missing = root / "missing_columns.csv"
        pd.DataFrame({"instrumental": [1.0, 1.2, 1.4], "standard": [11.0, 11.1, 11.2], "secz": [1.1, 1.2, 1.3]}).to_csv(missing, index=False)
        rc, payload, text = run_solution(missing, root / "missing_out")
        require(rc != 0, "missing columns should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "missing columns should emit blocked payload")
        require("Traceback" not in text, "missing columns should not traceback")
        assert_strict_json(payload)
        print("PASS check_missing_columns_blocks_cleanly")

        bad_numeric = root / "bad_numeric.csv"
        pd.DataFrame({"std_mag": [10.0, 10.1, 10.2], "inst_mag": [-14.0, "bad", -13.8], "airmass": [1.0, 1.2, 1.4]}).to_csv(bad_numeric, index=False)
        rc, payload, text = run_solution(bad_numeric, root / "bad_numeric_out")
        require(rc != 0, "bad numeric input should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "bad numeric input should emit blocked payload")
        require("Traceback" not in text, "bad numeric input should not traceback")
        assert_strict_json(payload)
        print("PASS check_bad_numeric_blocks_cleanly")

        nonfinite = root / "nonfinite.csv"
        pd.DataFrame({"std_mag": [10.0, 10.1, 10.2], "inst_mag": [-14.0, -13.9, -13.8], "airmass": [1.0, np.inf, 1.4]}).to_csv(nonfinite, index=False)
        rc, payload, text = run_solution(nonfinite, root / "nonfinite_out")
        require(rc != 0, "non-finite input should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "non-finite input should emit blocked payload")
        require("Traceback" not in text, "non-finite input should not traceback")
        assert_strict_json(payload)
        print("PASS check_nonfinite_blocks_cleanly")

        ill = root / "ill_conditioned.csv"
        airmass = np.linspace(1.0, 1.8, 8)
        color = 2.0 * airmass + 0.3
        inst_mag = np.linspace(-14.0, -13.0, 8)
        std_mag = inst_mag + 24.0 - 0.1 * airmass + 0.05 * color
        pd.DataFrame({"std_mag": std_mag, "inst_mag": inst_mag, "airmass": airmass, "b_minus_v": color}).to_csv(ill, index=False)
        rc, payload, text = run_solution(ill, root / "ill_out", extra=["--color-col", "b_minus_v", "--include-color-term"])
        require(rc != 0, "ill-conditioned fit should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "ill-conditioned fit should emit blocked payload")
        require("Traceback" not in text, "ill-conditioned fit should not traceback")
        assert_strict_json(payload)
        print("PASS check_ill_conditioned_blocks_cleanly")

        negative_sigma = root / "negative_sigma.csv"
        write_color_table(negative_sigma)
        frame = pd.read_csv(negative_sigma)
        frame.loc[0, "offset_err"] = -0.1
        frame.to_csv(negative_sigma, index=False)
        rc, payload, text = run_solution(negative_sigma, root / "negative_sigma_out", extra=["--color-col", "b_minus_v", "--include-color-term", "--error-col", "offset_err"])
        require(rc != 0, "negative sigma should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "negative sigma should emit blocked payload")
        require("Traceback" not in text, "negative sigma should not traceback")
        assert_strict_json(payload)
        print("PASS check_negative_sigma_blocks_cleanly")

    print("All photometric_solution v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
