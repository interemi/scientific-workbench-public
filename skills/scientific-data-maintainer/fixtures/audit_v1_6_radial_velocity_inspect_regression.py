#!/usr/bin/env python3
"""Regression checks for radial_velocity_workbench.py inspect v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().with_name("radial_velocity_workbench.py")


def run_inspect(path: Path, out_dir: Path) -> tuple[int, dict | None, str]:
    summary = out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "inspect",
        str(path),
        "--summary-json",
        str(summary),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    payload = None
    if summary.exists():
        payload = json.loads(summary.read_text(encoding="utf-8"))
    elif proc.stdout.strip().startswith("{"):
        payload = json.loads(proc.stdout)
    return proc.returncode, payload, (proc.stdout or "") + "\n" + (proc.stderr or "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rv_inspect_regression_") as tmp:
        base = Path(tmp)

        happy = base / "happy.vels"
        happy.write_text(
            "# value_units = m/s\n"
            "2450000.0 12.1 1.2\n"
            "2450001.0 10.5 1.0\n",
            encoding="utf-8",
        )
        rc, payload, text = run_inspect(happy, base / "happy")
        require(rc == 0, f"happy dataset should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "happy dataset should be ok")
        require((payload.get("qa") or {}).get("status") == "ok", "happy dataset QA should be ok")
        require((payload.get("qa") or {}).get("metrics", {}).get("sample_count_total") == 2, "happy dataset should count samples")
        print("PASS check_happy_dataset_ok")

        edge_dir = base / "edge"
        edge_dir.mkdir()
        (edge_dir / "valid.vels").write_text(
            "# value_units = m/s\n"
            "2450000.0 1.0 0.5\n"
            "bad row\n"
            "2450001.0 nan 0.5\n"
            "2450002.0 2.0 -1.0\n",
            encoding="utf-8",
        )
        (edge_dir / "edge.sys").write_text(
            "Name\tEdge RV\n"
            "RV[]\tvalid.vels\n"
            "RV[]\tmissing.vels\n",
            encoding="utf-8",
        )
        rc, payload, text = run_inspect(edge_dir / "edge.sys", base / "edge_out")
        require(rc == 0, f"edge system should exit 0 warning: {text}")
        require(payload is not None and payload.get("status") == "warning", "edge system should be warning")
        findings = " ".join((payload.get("qa") or {}).get("findings") or [])
        require("could not be resolved" in findings, f"missing reference should be reported: {findings}")
        require("malformed" in findings, f"malformed rows should be reported: {findings}")
        require("non-finite" in findings, f"non-finite JD/RV rows should be reported: {findings}")
        require("<= 0" in findings, f"nonpositive errors should be reported: {findings}")
        rendered = json.dumps(payload, allow_nan=False)
        require("NaN" not in rendered, "payload should be strict JSON-serializable without NaN")
        print("PASS check_edge_system_warns_strict_json")

        empty = base / "empty.vels"
        empty.write_text("# value_units = m/s\nnot numeric here\n", encoding="utf-8")
        rc, payload, text = run_inspect(empty, base / "empty")
        require(rc != 0, "empty dataset should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "empty dataset should be blocked")
        require((payload.get("qa") or {}).get("metrics", {}).get("sample_count_total") == 0, "empty dataset should have zero samples")
        print("PASS check_empty_dataset_blocks")

        unsupported = base / "unsupported.csv"
        unsupported.write_text("jd,rv,err\n2450000,1,0.1\n", encoding="utf-8")
        rc, payload, text = run_inspect(unsupported, base / "unsupported")
        require(rc != 0, "unsupported input should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "unsupported input should emit blocked payload")
        require("Traceback" not in text, "unsupported input should not traceback")
        print("PASS check_unsupported_blocks_cleanly")

        missing = base / "missing.vels"
        rc, payload, text = run_inspect(missing, base / "missing")
        require(rc != 0, "missing input should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "missing input should emit blocked payload")
        require("Traceback" not in text, "missing input should not traceback")
        print("PASS check_missing_blocks_cleanly")

    print("All radial_velocity_workbench inspect v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
