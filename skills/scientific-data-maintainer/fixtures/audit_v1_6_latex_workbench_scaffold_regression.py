#!/usr/bin/env python3
"""Regression tests for latex_workbench.py scaffold."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _internal.public_contract import validate_standard_envelope


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_cmd(args: list[str], *, expect_ok: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command unexpectedly passed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}")
    return completed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_stdout_json(completed: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(completed.stdout)
    except Exception as exc:
        raise AssertionError(f"Expected JSON stdout, got:\n{completed.stdout}\nSTDERR:\n{completed.stderr}") from exc


def assert_standard(payload: dict, expected_status: str) -> None:
    issues = validate_standard_envelope(payload)
    if issues:
        raise AssertionError(f"Invalid standard envelope: {issues}\n{payload}")
    if payload["status"] != expected_status:
        raise AssertionError(f"Expected status={expected_status}, got {payload['status']}: {payload}")


def check_scaffold_success_language_and_escaping(tmp: Path) -> None:
    output = tmp / "Proyecto con espacios"
    summary = tmp / "summary.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "latex_workbench.py"),
            "scaffold",
            str(output),
            "--kind",
            "academic-report",
            "--language",
            "spanish",
            "--title",
            "R&D 100%_calibracion #1",
            "--author",
            "Emilio & Codex",
            "--summary-json",
            str(summary),
        ]
    )
    payload = load_json(summary)
    assert_standard(payload, "ok")
    main_tex = (output / "main.tex").read_text(encoding="utf-8")
    required = [
        r"R\&D 100\%\_calibracion \#1",
        r"Emilio \& Codex",
        r"\section{Introduccion}",
        r"\section{Datos y metodologia}",
        r"\section{Discusion}",
    ]
    missing = [item for item in required if item not in main_tex]
    if missing:
        raise AssertionError(f"Scaffold did not apply escaping/language content: {missing}\n{main_tex[:1200]}")
    if payload["created_files"] != ["main.tex", "references.bib"]:
        raise AssertionError(f"Unexpected created files: {payload}")


def check_existing_files_blocked_without_overwrite(tmp: Path) -> None:
    output = tmp / "existing"
    output.mkdir()
    protected = output / "main.tex"
    protected.write_text("% protected\n\\documentclass{article}\n\\begin{document}NO TOCAR\\end{document}\n", encoding="utf-8")
    before = sha256(protected)
    summary = tmp / "blocked.json"
    completed = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "latex_workbench.py"),
            "scaffold",
            str(output),
            "--summary-json",
            str(summary),
        ],
        expect_ok=False,
    )
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Blocked scaffold leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    if sha256(protected) != before:
        raise AssertionError("Existing main.tex was overwritten despite missing --overwrite.")
    payload = load_json(summary)
    assert_standard(payload, "blocked")
    if not payload["collisions"]:
        raise AssertionError(f"Blocked scaffold did not report collisions: {payload}")


def check_overwrite_is_explicit(tmp: Path) -> None:
    output = tmp / "overwrite"
    output.mkdir()
    protected = output / "main.tex"
    protected.write_text("% old\n", encoding="utf-8")
    summary = tmp / "overwrite.json"
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "latex_workbench.py"),
            "scaffold",
            str(output),
            "--kind",
            "proposal",
            "--overwrite",
            "--summary-json",
            str(summary),
        ]
    )
    payload = load_json(summary)
    assert_standard(payload, "ok")
    if not payload["overwrote_existing_files"]:
        raise AssertionError(f"Explicit overwrite was not recorded: {payload}")
    if "Objective" not in protected.read_text(encoding="utf-8"):
        raise AssertionError("Explicit overwrite did not replace main.tex with the proposal scaffold.")


def check_output_file_fails_cleanly(tmp: Path) -> None:
    output = tmp / "not_a_dir.tex"
    output.write_text("already a file", encoding="utf-8")
    summary = tmp / "file_target.json"
    completed = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "latex_workbench.py"),
            "scaffold",
            str(output),
            "--summary-json",
            str(summary),
        ],
        expect_ok=False,
    )
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"File-target failure leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    payload = load_json(summary)
    assert_standard(payload, "fail")


def check_invalid_summary_target_does_not_leave_project(tmp: Path) -> None:
    output = tmp / "bad_summary_project"
    summary_dir = tmp / "summary_is_dir"
    summary_dir.mkdir()
    completed = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "latex_workbench.py"),
            "scaffold",
            str(output),
            "--summary-json",
            str(summary_dir),
        ],
        expect_ok=False,
    )
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Invalid summary target leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    payload = load_stdout_json(completed)
    assert_standard(payload, "fail")
    if (output / "main.tex").exists():
        raise AssertionError("Invalid summary target left a scaffold that looks valid.")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_latex_scaffold_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_scaffold_success_language_and_escaping(tmp)
        print("PASS check_scaffold_success_language_and_escaping")
        check_existing_files_blocked_without_overwrite(tmp)
        print("PASS check_existing_files_blocked_without_overwrite")
        check_overwrite_is_explicit(tmp)
        print("PASS check_overwrite_is_explicit")
        check_output_file_fails_cleanly(tmp)
        print("PASS check_output_file_fails_cleanly")
        check_invalid_summary_target_does_not_leave_project(tmp)
        print("PASS check_invalid_summary_target_does_not_leave_project")
    print("All latex_workbench scaffold regressions passed.")


if __name__ == "__main__":
    main()
