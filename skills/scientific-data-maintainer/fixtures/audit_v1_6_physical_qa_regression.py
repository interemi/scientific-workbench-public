#!/usr/bin/env python3
"""Regression checks for physical_qa.py v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "physical_qa.py"


def write_text(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def run_physical_qa(tmp: Path, input_path: Path, summary_name: str = "summary.json"):
    summary = tmp / summary_name
    cmd = [sys.executable, str(TOOL), str(input_path), "--summary-json", str(summary)]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    payload = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    return completed, payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def messages(payload: dict) -> str:
    return "\n".join(str(item.get("message", "")) for item in payload["results"].get("issues", []))


def assert_no_traceback(completed: subprocess.CompletedProcess[str]) -> None:
    combined = completed.stdout + "\n" + completed.stderr
    require("Traceback" not in combined, "physical_qa leaked a traceback")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical_qa_v1_6_") as raw_tmp:
        tmp = Path(raw_tmp)

        clean_iso_time = write_text(
            tmp / "clean_iso_time.csv",
            """
            ra,dec,flux,airmass,obs_time,flux_err
            120.0,22.0,1000.0,1.2,2026-05-01T00:00:00,2.0
            120.1,22.1,1005.0,1.3,2026-05-01T00:01:00,2.1
            """,
        )
        completed, payload = run_physical_qa(tmp, clean_iso_time, "clean_iso_time.json")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "ok", payload)
        require("obs_time' contains non-numeric" not in messages(payload), payload)
        require("obs_time' looks physically relevant" not in messages(payload), payload)

        nonfinite_ra = write_text(
            tmp / "nonfinite_ra.csv",
            """
            ra,dec,flux
            120.0,22.0,10.0
            Inf,22.1,11.0
            """,
        )
        completed, payload = run_physical_qa(tmp, nonfinite_ra, "nonfinite_ra.json")
        require(completed.returncode == 0, completed.stderr)
        require(payload["status"] == "warning", payload)
        require("non-finite numeric values" in messages(payload), payload)

        missing = tmp / "does_not_exist.csv"
        completed, payload = run_physical_qa(tmp, missing, "missing.json")
        require(completed.returncode != 0, "missing input should be a controlled block")
        assert_no_traceback(completed)
        require(payload["status"] == "blocked", payload)
        require("File not found" in messages(payload), payload)

        parent_file = tmp / "occupied"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        summary = parent_file / "summary.json"
        completed = subprocess.run(
            [sys.executable, str(TOOL), str(clean_iso_time), "--summary-json", str(summary)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(completed.returncode != 0, "summary parent conflict should fail cleanly")
        assert_no_traceback(completed)
        require("summary-json parent is not a directory" in completed.stdout, completed.stdout + completed.stderr)

    print("physical_qa v1.6 regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
