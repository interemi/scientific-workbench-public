#!/usr/bin/env python3
"""Focused v1.6 release gate for the completed capability audit."""

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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_docs_version() -> None:
    expected = {
        "SKILL.md": [
            "v1.6 stable",
            "59-capability audit-and-hardening baseline",
            "v1.6 release gates remain the stable baseline",
        ],
        "README.txt": [
            "v1.7 stable over v1.6 stable",
            "v1.6 remains the installed stable baseline",
            "completed 59-capability audit-and-hardening release",
            "audit_v1_6_release_regression.py",
        ],
        "RELEASE-v1.txt": [
            "Release v1.7 stable / v1.6 stable baseline",
            "v1.6 closes the 59-capability audit pass",
            "tested v1.6 hardening route for all 59 public capabilities",
        ],
        "references/architecture.md": [
            "audit_v1_6_release_regression.py",
            "v1.6 release gate",
        ],
    }
    for relative, terms in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        require(not missing, f"{relative} is missing v1.6 terms: {missing}")


def check_public_surface_count() -> None:
    registry_text = (ROOT / "public_surface_registry.yaml").read_text(encoding="utf-8")
    count = sum(1 for line in registry_text.splitlines() if line.startswith("  - id: "))
    require(count >= 59, f"Expected at least the 59-capability v1.6 baseline, found {count}")
    require(count == 61, f"Expected current v2.x public registry to expose 61 labels, found {count}")


def check_v1_6_regression_inventory() -> None:
    scripts = sorted(SCRIPTS.glob("audit_v1_6_*_regression.py"))
    names = {path.name for path in scripts}
    required = {
        "audit_v1_6_capability_probe_matrix_regression.py",
        "audit_v1_6_datanalysis_env_regression.py",
        "audit_v1_6_physical_qa_regression.py",
        "audit_v1_6_photometry_noise_budget_regression.py",
        "audit_v1_6_timeseries_forecasting_regression.py",
        "audit_v1_6_keynote_export_regression.py",
        "audit_v1_6_teareduce_router_regression.py",
        "audit_v1_6_validate_skill_samples_regression.py",
    }
    missing = sorted(required - names)
    require(not missing, f"Missing required v1.6 regression scripts: {missing}")
    require(len(scripts) >= 50, f"Expected broad v1.6 regression inventory, found {len(scripts)} scripts")


def check_portable_smoke_payload(summary_json: Path) -> None:
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    status = payload.get("overall_status") or payload.get("results", {}).get("overall_status")
    if status is None and payload.get("status") == "ok":
        status = "PASS"
    require(status == "PASS", f"portable_smoke_test core did not pass: {status}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-6-") as tmp_raw:
        tmp = Path(tmp_raw)
        checks = [
            [sys.executable, str(SCRIPTS / "sync_public_surface_docs.py"), "--check"],
            [sys.executable, str(SCRIPTS / "skill_surface_audit.py")],
            [sys.executable, str(SCRIPTS / "audit_fits_rgb_batch_regression.py")],
            [
                sys.executable,
                str(SCRIPTS / "capability_probe_matrix.py"),
                "--output-dir",
                str(tmp / "capability_probe"),
                "--summary-json",
                str(tmp / "capability_probe" / "summary.json"),
                "--timeout-sec",
                "90",
            ],
        ]
        for command in checks:
            run_cmd(command, tmp=tmp)
            print(f"PASS {Path(command[1]).name}")

        check_docs_version()
        print("PASS v1.6 docs version checks")

        check_public_surface_count()
        print("PASS public surface count")

        check_v1_6_regression_inventory()
        print("PASS v1.6 regression inventory")

        smoke_dir = tmp / "portable_smoke_core"
        summary_json = smoke_dir / "summary.json"
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS / "portable_smoke_test.py"),
                "--profile",
                "core",
                "--output-dir",
                str(smoke_dir),
                "--summary-json",
                str(summary_json),
            ],
            tmp=tmp,
        )
        check_portable_smoke_payload(summary_json)
        print("PASS portable_smoke_test core")

    print("All v1.6 release regression checks passed.")


if __name__ == "__main__":
    main()
