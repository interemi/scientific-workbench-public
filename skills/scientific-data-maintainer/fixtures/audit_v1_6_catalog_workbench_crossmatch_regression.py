#!/usr/bin/env python3
"""Regression checks for catalog_workbench.py crossmatch-sky v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "catalog_workbench.py"


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def run_crossmatch(tmp: Path, left: Path, right: Path, output_name: str, *extra: str):
    output = tmp / output_name
    summary = tmp / f"{Path(output_name).stem}_summary.json"
    cmd = [
        sys.executable,
        str(TOOL),
        "crossmatch-sky",
        str(left),
        str(right),
        str(output),
        "--left-ra",
        "ra_deg",
        "--left-dec",
        "dec_deg",
        "--right-ra",
        "ra_deg",
        "--right-dec",
        "dec_deg",
        "--summary-json",
        str(summary),
        *extra,
    ]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    payload = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    return completed, payload, output


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_clean_failure(completed: subprocess.CompletedProcess[str]) -> None:
    combined = completed.stdout + "\n" + completed.stderr
    require("Traceback" not in combined, "failure path leaked a traceback")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="catalog_crossmatch_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        left = write_csv(
            tmp / "left.csv",
            """
            source,ra_deg,dec_deg,mag
            A,120.000000,22.000000,15.1
            B,120.020000,22.010000,16.4
            """,
        )
        right = write_csv(
            tmp / "right.csv",
            """
            source,ra_deg,dec_deg,mag
            X,120.000200,22.000100,15.2
            Y,120.500000,22.500000,18.0
            """,
        )

        completed, payload, output = run_crossmatch(tmp, left, right, "matches.csv", "--radius-arcsec", "2.0")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "ok", payload)
        require(payload["results"]["matched_rows"] == 1, payload)
        require(output.exists(), "successful cross-match did not write output")

        far_right = write_csv(
            tmp / "far_right.csv",
            """
            source,ra_deg,dec_deg
            Z,140.000000,-10.000000
            """,
        )
        completed, payload, output = run_crossmatch(tmp, left, far_right, "zero.csv", "--radius-arcsec", "0.2")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "warning", payload)
        require(payload["results"]["matched_rows"] == 0, payload)
        require("No rows matched" in payload["qa"]["findings"][0], payload)
        require(output.exists(), "zero-match warning should still write an empty output table")

        missing = write_csv(
            tmp / "missing.csv",
            """
            source,ra_deg
            X,120.0
            """,
        )
        completed, payload, output = run_crossmatch(tmp, left, missing, "missing_col.csv", "--radius-arcsec", "1.0")
        require(completed.returncode != 0, "missing coordinate column should be blocked")
        assert_clean_failure(completed)
        require(payload["status"] == "blocked", payload)
        require(not output.exists(), "blocked missing-column run should not write output")

        nonfinite = write_csv(
            tmp / "nonfinite.csv",
            """
            source,ra_deg,dec_deg
            X,NaN,22.0
            """,
        )
        completed, payload, output = run_crossmatch(tmp, left, nonfinite, "nonfinite_out.csv", "--radius-arcsec", "1.0")
        require(completed.returncode != 0, "non-finite coordinates should be blocked")
        assert_clean_failure(completed)
        require(payload["status"] == "blocked", payload)
        require(not output.exists(), "blocked non-finite run should not write output")

        completed, payload, output = run_crossmatch(tmp, left, right, "bad_radius.csv", "--radius-arcsec", "nan")
        require(completed.returncode != 0, "nan radius should be blocked")
        assert_clean_failure(completed)
        require(payload["status"] == "blocked", payload)
        require(not output.exists(), "blocked radius run should not write output")

        conflict_parent = tmp / "not_a_directory"
        conflict_parent.write_text("occupied\n", encoding="utf-8")
        completed, payload, output = run_crossmatch(tmp, left, right, "not_a_directory/out.csv", "--radius-arcsec", "1.0")
        require(completed.returncode != 0, "output parent-file conflict should fail")
        assert_clean_failure(completed)
        require(payload["status"] == "fail", payload)
        require(not output.exists(), "failed parent conflict should not write output")

    print("catalog_workbench crossmatch-sky v1.6 regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
