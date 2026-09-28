#!/usr/bin/env python3
"""Regression checks for v1.6 portable_smoke_test hardening."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "portable_smoke_test.py"


def run_cmd(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, env=env)


def parse_stdout_json(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except Exception as exc:
        raise AssertionError(f"stdout was not a JSON object: {exc}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}") from exc


def test_help_does_not_import_optional_registry_dependencies(tmp: Path) -> None:
    blocker = tmp / "blocker"
    blocker.mkdir(parents=True)
    (blocker / "yaml.py").write_text("raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(blocker)
    result = run_cmd([sys.executable, str(SCRIPT), "--help"], env=env)
    assert result.returncode == 0, result.stderr
    assert "portable_smoke_test.py" in result.stdout


def test_output_dir_file_fails_cleanly(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    output_file = tmp / "output_dir_is_file"
    output_file.write_text("not a directory\n", encoding="utf-8")
    summary = tmp / "summary.json"
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "core",
            "--output-dir",
            str(output_file),
            "--summary-json",
            str(summary),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["tool"] == "portable_smoke_test"
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "FileExistsError"


def test_missing_examples_dir_fails_cleanly(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    summary = tmp / "missing_examples.json"
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "core",
            "--examples-dir",
            str(tmp / "does_not_exist"),
            "--output-dir",
            str(tmp / "out"),
            "--summary-json",
            str(summary),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "RuntimeError"
    assert "Examples directory not found" in payload["results"]["error"]


def test_examples_dir_file_fails_cleanly(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    examples_file = tmp / "examples_file.txt"
    examples_file.write_text("not an examples directory\n", encoding="utf-8")
    summary = tmp / "examples_file_summary.json"
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "core",
            "--examples-dir",
            str(examples_file),
            "--output-dir",
            str(tmp / "out"),
            "--summary-json",
            str(summary),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "RuntimeError"
    assert "not a directory" in payload["results"]["error"]


def test_summary_json_directory_failure_still_prints_envelope(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    output_file = tmp / "output_dir_is_file"
    output_file.write_text("not a directory\n", encoding="utf-8")
    summary_dir = tmp / "summary_dir"
    summary_dir.mkdir()
    result = run_cmd(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "core",
            "--output-dir",
            str(output_file),
            "--summary-json",
            str(summary_dir),
        ]
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = parse_stdout_json(result)
    assert payload["status"] == "fail"
    assert payload["results"]["error_type"] == "FileExistsError"
    assert "summary_json_error" in payload["results"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="portable_smoke_v16_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        tests = [
            test_help_does_not_import_optional_registry_dependencies,
            test_output_dir_file_fails_cleanly,
            test_missing_examples_dir_fails_cleanly,
            test_examples_dir_file_fails_cleanly,
            test_summary_json_directory_failure_still_prints_envelope,
        ]
        for test in tests:
            test(tmp / test.__name__)
    print("portable_smoke_test v1.6 regression checks passed")


if __name__ == "__main__":
    main()
