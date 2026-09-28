#!/usr/bin/env python3
"""Regression checks for datanalysis_healthcheck.py hardening."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "datanalysis_healthcheck.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=SKILL_ROOT, text=True, capture_output=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def combined_output(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + "\n" + (completed.stderr or "")


def assert_no_traceback(completed: subprocess.CompletedProcess, label: str) -> None:
    if "Traceback" in combined_output(completed):
        raise AssertionError(f"{label}: command emitted a traceback")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_datanalysis_healthcheck_") as tmp_raw:
        tmp = Path(tmp_raw)

        happy_summary = tmp / "nested dir" / "healthcheck.json"
        happy_manifest = tmp / "nested dir" / "healthcheck_manifest.json"
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--skip-notebook-exec",
                "--summary-json",
                str(happy_summary),
                "--manifest-json",
                str(happy_manifest),
            ]
        )
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(happy_summary)
        assert payload["status"] == "ok"
        assert payload["results"]["ready"] is True
        assert happy_manifest.exists()
        results.append({"case": "nested_summary_and_manifest", "status": "PASS"})

        full_summary = tmp / "full_healthcheck.json"
        completed = run([sys.executable, str(SCRIPT), "--summary-json", str(full_summary)])
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(full_summary)
        notebook_execution = payload["results"]["notebook_execution"]
        assert notebook_execution["attempted"] is True
        assert notebook_execution.get("workdir_retained") is False
        workdir = Path(notebook_execution["workdir"].replace("~", str(Path.home())))
        assert not workdir.exists(), f"temporary notebook workdir was retained: {workdir}"
        results.append({"case": "notebook_tempdir_cleaned", "status": "PASS"})

        bad_kernel_summary = tmp / "bad_kernel.json"
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--kernel-name",
                "definitely_missing_kernel_for_v16",
                "--summary-json",
                str(bad_kernel_summary),
            ]
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "bad_kernel")
        payload = read_json(bad_kernel_summary)
        assert payload["status"] == "blocked"
        assert payload["results"]["notebook_execution"]["success"] is False
        results.append({"case": "bad_kernel_blocks_cleanly", "status": "PASS"})

        summary_dir = tmp / "summary_dir"
        summary_dir.mkdir()
        completed = run(
            [sys.executable, str(SCRIPT), "--skip-notebook-exec", "--summary-json", str(summary_dir)]
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_directory")
        assert "Could not write JSON summary" in combined_output(completed)
        results.append({"case": "summary_json_directory_clean_error", "status": "PASS"})

        parent_file = tmp / "not_a_dir_parent"
        parent_file.write_text("not a dir\n", encoding="utf-8")
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--skip-notebook-exec",
                "--summary-json",
                str(parent_file / "out.json"),
            ]
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_parent_file")
        assert "Could not write JSON summary" in combined_output(completed)
        results.append({"case": "summary_json_parent_file_clean_error", "status": "PASS"})

        manifest_dir = tmp / "manifest_dir"
        manifest_dir.mkdir()
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--skip-notebook-exec",
                "--summary-json",
                str(tmp / "manifest_error_summary.json"),
                "--manifest-json",
                str(manifest_dir),
            ]
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "manifest_json_directory")
        assert "Could not write manifest" in combined_output(completed)
        results.append({"case": "manifest_json_directory_clean_error", "status": "PASS"})

    report = {
        "tool": "audit_v1_6_datanalysis_healthcheck_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
