#!/usr/bin/env python3
"""Regression tests for teareduce_router.py routing and clean blocking."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _internal.public_contract import validate_standard_envelope


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "teareduce_router.py"
EXAMPLE = ROOT / "examples" / "science" / "legacy_spectroscopy_mini"


def run_cmd(args: list[str | Path], *, expect_ok: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [str(item) for item in args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(str(item) for item in args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command unexpectedly passed: {' '.join(str(item) for item in args)}\nSTDOUT:\n{completed.stdout}")
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Command leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    return completed


def command(*args: str | Path) -> list[str | Path]:
    return [sys.executable, TOOL, *args]


def stdout_json(completed: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(completed.stdout)
    except Exception as exc:
        raise AssertionError(f"Expected JSON-only stdout, got:\n{completed.stdout}\nSTDERR:\n{completed.stderr}") from exc


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_standard(payload: dict, expected_status: str) -> None:
    issues = validate_standard_envelope(payload)
    if issues:
        raise AssertionError(f"Invalid standard envelope: {issues}\n{payload}")
    if payload["status"] != expected_status:
        raise AssertionError(f"Expected status={expected_status}, got {payload['status']}: {payload}")
    if payload["qa"]["status"] != expected_status:
        raise AssertionError(f"Expected qa.status={expected_status}, got {payload['qa']}: {payload}")


def assert_backend(payload: dict, backend: str) -> None:
    actual = payload["results"].get("recommended_backend")
    if actual != backend:
        raise AssertionError(f"Expected backend={backend}, got {actual}: {payload}")


def check_stdout_standard_without_summary() -> None:
    completed = run_cmd(command("--intent", "Use TEAREDUCE for wavelength calibration arcs"))
    payload = stdout_json(completed)
    assert_standard(payload, "ok")
    assert_backend(payload, "teareduce")


def check_accented_spanish_routes_to_teareduce(tmp: Path) -> None:
    summary = tmp / "accented.json"
    run_cmd(command("--intent", "Necesito calibración de longitud de onda con arcos", "--summary-json", summary))
    payload = read_json(summary)
    assert_standard(payload, "ok")
    assert_backend(payload, "teareduce")


def check_empty_intent_warns(tmp: Path) -> None:
    summary = tmp / "empty.json"
    run_cmd(command("--summary-json", summary))
    payload = read_json(summary)
    assert_standard(payload, "warning")
    assert_backend(payload, "native")
    if not payload["qa"]["findings"]:
        raise AssertionError(f"Empty route warning missed findings: {payload}")


def check_invalid_summary_parent_blocks(tmp: Path) -> None:
    parent_file = tmp / "parent_is_file"
    parent_file.write_text("not a directory\n", encoding="utf-8")
    completed = run_cmd(command("--intent", "TEAREDUCE cookbook wavecal", "--summary-json", parent_file / "summary.json"), expect_ok=False)
    payload = stdout_json(completed)
    assert_standard(payload, "blocked")
    if "parent" not in " ".join(payload["qa"]["findings"]).lower():
        raise AssertionError(f"Invalid parent was not explained: {payload}")


def check_real_arc_copy_routes_to_teareduce(tmp: Path) -> None:
    arc = tmp / "arc_lamp.fits"
    shutil.copy2(EXAMPLE / "mini_template.fits", arc)
    summary = tmp / "arc.json"
    run_cmd(command("--intent", "wavelength calibration arcs", arc, "--summary-json", summary))
    payload = read_json(summary)
    assert_standard(payload, "ok")
    assert_backend(payload, "teareduce")


def check_legacy_multispec_routes_native(tmp: Path) -> None:
    fixture = tmp / "legacy"
    shutil.copytree(EXAMPLE, fixture)
    summary = tmp / "legacy.json"
    run_cmd(
        command(
            "--intent",
            "IRAF fxcor MULTISPE legacy spectroscopy v sin i iSTARMOD",
            fixture / "mini_multispec.fits",
            fixture / "sample_case.sm",
            "--summary-json",
            summary,
        )
    )
    payload = read_json(summary)
    assert_standard(payload, "ok")
    assert_backend(payload, "native")


def check_explicit_teareduce_legacy_conflict_warns(tmp: Path) -> None:
    fixture = tmp / "legacy_conflict"
    shutil.copytree(EXAMPLE, fixture)
    summary = tmp / "conflict.json"
    run_cmd(
        command(
            "--intent",
            "Quiero usar TEAREDUCE para revisar esta practica MULTISPE IRAF",
            fixture / "mini_multispec.fits",
            "--summary-json",
            summary,
        )
    )
    payload = read_json(summary)
    assert_standard(payload, "warning")
    assert_backend(payload, "teareduce")
    if not payload["qa"]["findings"]:
        raise AssertionError(f"Explicit TEAREDUCE legacy conflict missed findings: {payload}")


def check_summary_directory_blocks(tmp: Path) -> None:
    summary_dir = tmp / "summary_is_dir"
    summary_dir.mkdir()
    completed = run_cmd(command("--intent", "TEAREDUCE notebook", "--summary-json", summary_dir), expect_ok=False)
    payload = stdout_json(completed)
    assert_standard(payload, "blocked")
    if "directory" not in " ".join(payload["qa"]["findings"]).lower():
        raise AssertionError(f"Summary directory was not explained: {payload}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_teareduce_router_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_stdout_standard_without_summary()
        print("PASS check_stdout_standard_without_summary")
        check_accented_spanish_routes_to_teareduce(tmp)
        print("PASS check_accented_spanish_routes_to_teareduce")
        check_empty_intent_warns(tmp)
        print("PASS check_empty_intent_warns")
        check_invalid_summary_parent_blocks(tmp)
        print("PASS check_invalid_summary_parent_blocks")
        check_real_arc_copy_routes_to_teareduce(tmp)
        print("PASS check_real_arc_copy_routes_to_teareduce")
        check_legacy_multispec_routes_native(tmp)
        print("PASS check_legacy_multispec_routes_native")
        check_explicit_teareduce_legacy_conflict_warns(tmp)
        print("PASS check_explicit_teareduce_legacy_conflict_warns")
        check_summary_directory_blocks(tmp)
        print("PASS check_summary_directory_blocks")


if __name__ == "__main__":
    main()
