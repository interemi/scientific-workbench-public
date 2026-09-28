#!/usr/bin/env python3
"""Focused v1.5 release gate for public capability coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_cmd(args: list[str], *, tmp: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_docs_version() -> None:
    expected = {
        "SKILL.md": ["v1.5 stable", "capability-coverage"],
        "README.txt": ["v1.5 stable", "capability_probe_matrix.py", "audit_v1_5_release_regression.py"],
        "RELEASE-v1.txt": ["Release v1.5 stable", "v1.5 closes the capability-coverage loop"],
        "references/architecture.md": ["audit_v1_5_release_regression.py", "capability_probe_matrix.py"],
    }
    for relative, terms in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        require(not missing, f"{relative} is missing v1.5 terms: {missing}")


def check_capability_matrix(tmp: Path) -> None:
    output_dir = tmp / "capability_probe"
    summary_json = output_dir / "summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "capability_probe_matrix.py"),
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
            "--timeout-sec",
            "90",
        ],
        tmp=tmp,
    )
    payload = read_json(summary_json)
    counts = payload["results"]["counts_by_probe_status"]
    require(counts.get("FAIL", 0) == 0, f"capability_probe_matrix reported FAIL entries: {counts}")
    require(counts.get("NO_PROBE", 0) == 0, f"capability_probe_matrix still has unprobed entries: {counts}")

    rows = payload["results"]["rows"]
    rgb_rows = [row for row in rows if row["id"] == "rgb_visual_fits_export"]
    require(rgb_rows and rgb_rows[0]["probe_status"] == "PASS", "rgb_visual_fits_export must be probed and PASS in v1.5")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-5-") as tmp_raw:
        tmp = Path(tmp_raw)
        checks = [
            [sys.executable, str(SCRIPTS / "sync_public_surface_docs.py"), "--check"],
            [sys.executable, str(SCRIPTS / "skill_surface_audit.py")],
            [sys.executable, str(SCRIPTS / "audit_v1_4_companion_routing_regression.py")],
            [sys.executable, str(SCRIPTS / "audit_external_astro_tools_regression.py")],
            [sys.executable, str(SCRIPTS / "audit_fits_rgb_batch_regression.py")],
        ]
        for command in checks:
            run_cmd(command, tmp=tmp)
            print(f"PASS {Path(command[1]).name}")

        check_capability_matrix(tmp)
        print("PASS capability_probe_matrix without FAIL/NO_PROBE")

        check_docs_version()
        print("PASS v1.5 docs version checks")

    print("All v1.5 capability-coverage release regressions passed.")


if __name__ == "__main__":
    main()
