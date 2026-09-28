#!/usr/bin/env python3
"""Regression checks for env_doctor.py v1.6 hardening."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "env_doctor.py"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=SKILL_ROOT, env=env, text=True, capture_output=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def combined_output(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + "\n" + (completed.stderr or "")


def assert_no_traceback(completed: subprocess.CompletedProcess, label: str) -> None:
    if "Traceback" in combined_output(completed):
        raise AssertionError(f"{label}: command emitted a traceback")


def assert_no_success_payload(completed: subprocess.CompletedProcess, label: str) -> None:
    if (completed.stdout or "").lstrip().startswith("{"):
        raise AssertionError(f"{label}: command printed a JSON payload before failing")


def first_json_payload(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise AssertionError(f"No JSON payload found: {text[:300]}")
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    return payload


def assert_blocked_payload(completed: subprocess.CompletedProcess, label: str, expected_kind: str) -> dict:
    payload = first_json_payload(completed.stdout)
    assert payload["status"] == "blocked", payload
    assert payload["app_status"] == "BLOCKED_CONTROLADO", payload
    assert payload["original_modified"] is False, payload
    assert payload["next_actions"], payload
    kinds = {item.get("kind") for item in payload.get("errors", [])}
    assert expected_kind in kinds, f"{label}: expected {expected_kind}, got {kinds}"
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_env_doctor_") as tmp_raw:
        tmp = Path(tmp_raw)

        happy_summary = tmp / "nested dir" / "env_doctor.json"
        happy_manifest = tmp / "nested dir" / "env_doctor_manifest.json"
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--summary-json",
                str(happy_summary),
                "--manifest-json",
                str(happy_manifest),
            ]
        )
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(happy_summary)
        assert payload["tool"] == "env_doctor"
        assert payload["capabilities"]["core_ready"] is True
        assert happy_manifest.exists()
        if payload["optional_groups"]["general_timeseries"]["modules"]["sklearn"]["installed"]:
            assert payload["optional_groups"]["general_timeseries"]["modules"]["sklearn"]["version"]
        results.append({"case": "nested_summary_and_manifest", "status": "PASS"})

        fake_home = tmp / "fake_home"
        fake_python = fake_home / "anaconda3" / "envs" / "datanalysis" / "bin" / "python"
        fake_python.parent.mkdir(parents=True)
        fake_python.write_text("# fake python marker\n", encoding="utf-8")
        fake_home_summary = tmp / "fake_home_detects_datanalysis.json"
        env = os.environ.copy()
        env.update({"HOME": str(fake_home), "PATH": "/usr/bin:/bin"})
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--summary-json",
                str(fake_home_summary),
            ],
            env=env,
        )
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(fake_home_summary)
        assert payload["capabilities"]["datanalysis_env_found"] is True
        assert payload["dedicated_environment"]["python"].endswith("/envs/datanalysis/bin/python")
        results.append({"case": "home_anaconda3_environment_detected", "status": "PASS"})

        system_python = Path("/usr/bin/python3")
        if system_python.exists():
            system_summary = tmp / "system_python_strict_core.json"
            completed = run(
                [str(system_python), str(SCRIPT), "--strict-core", "--summary-json", str(system_summary)]
            )
            assert completed.returncode != 0
            assert_no_traceback(completed, "system_python_strict_core")
            payload = read_json(system_summary)
            assert payload["status"] == "blocked"
            assert payload["dedicated_environment"]["found"] is True
            results.append({"case": "system_python_blocks_but_finds_datanalysis", "status": "PASS"})
        else:
            results.append({"case": "system_python_blocks_but_finds_datanalysis", "status": "NO_APLICA"})

        summary_dir = tmp / "summary_dir"
        summary_dir.mkdir()
        completed = run([sys.executable, str(SCRIPT), "--summary-json", str(summary_dir)])
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_directory")
        assert_blocked_payload(completed, "summary_json_directory", "output_conflict")
        results.append({"case": "summary_json_directory_clean_error", "status": "PASS"})

        manifest_dir = tmp / "manifest_dir"
        manifest_dir.mkdir()
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                "--summary-json",
                str(tmp / "manifest_error_summary.json"),
                "--manifest-json",
                str(manifest_dir),
            ]
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "manifest_json_directory")
        payload = assert_blocked_payload(completed, "manifest_json_directory", "output_conflict")
        written_payload = read_json(tmp / "manifest_error_summary.json")
        assert written_payload["app_status"] == payload["app_status"]
        results.append({"case": "manifest_json_directory_clean_error", "status": "PASS"})

        parent_file = tmp / "not_a_dir_parent"
        parent_file.write_text("not a dir\n", encoding="utf-8")
        completed = run([sys.executable, str(SCRIPT), "--summary-json", str(parent_file / "out.json")])
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_parent_file")
        assert_blocked_payload(completed, "summary_json_parent_file", "output_conflict")
        results.append({"case": "summary_json_parent_file_clean_error", "status": "PASS"})

    report = {
        "tool": "audit_v1_6_env_doctor_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
