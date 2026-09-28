#!/usr/bin/env python3
"""Regression tests for legacy_spectroscopy_report_builder.py scaffold."""

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
TOOL = SCRIPTS / "legacy_spectroscopy_report_builder.py"
SECTION_FILES = [
    "01_objetivo_materiales.tex",
    "02_entorno_trazabilidad.tex",
    "03_inventario_multispec.tex",
    "04_velocidad_radial.tex",
    "05_vsini.tex",
    "06_istarmod.tex",
    "07_anchuras_equivalentes.tex",
    "08_discusion.tex",
    "09_apendices.tex",
]


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
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Command leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
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
    if payload["qa"]["status"] not in {expected_status, "ok"}:
        raise AssertionError(f"Unexpected qa status for {expected_status}: {payload['qa']}")


def command(output: Path, summary: Path, *extra: str) -> list[str]:
    return [
        sys.executable,
        str(TOOL),
        "scaffold",
        str(output),
        "--summary-json",
        str(summary),
        *extra,
    ]


def assert_scaffold_files(output: Path) -> None:
    main_tex = output / "main.tex"
    if not main_tex.exists():
        raise AssertionError("Scaffold missed main.tex.")
    text = main_tex.read_text(encoding="utf-8")
    for needle in [r"\documentclass", r"\input{sections/01_objetivo_materiales}", r"\appendix"]:
        if needle not in text:
            raise AssertionError(f"main.tex missed required text {needle!r}.")
    missing_sections = [name for name in SECTION_FILES if not (output / "sections" / name).exists()]
    if missing_sections:
        raise AssertionError(f"Scaffold missed section files: {missing_sections}")


def check_success_and_tex_escaping(tmp: Path) -> None:
    output = tmp / "Proyecto con espacios"
    summary = tmp / "ok.json"
    run_cmd(
        command(
            output,
            summary,
            "--title",
            "PW_And & GZ Leo % #1",
            "--author",
            "Equipo {A}",
        )
    )
    payload = load_json(summary)
    assert_standard(payload, "ok")
    assert_scaffold_files(output)
    main_tex = (output / "main.tex").read_text(encoding="utf-8")
    for needle in [r"PW\_And \& GZ Leo \% \#1", r"Equipo \{A\}"]:
        if needle not in main_tex:
            raise AssertionError(f"LaTeX escaping failed for {needle!r}:\n{main_tex[:1000]}")
    if payload["results"]["section_count"] != len(SECTION_FILES):
        raise AssertionError(f"Unexpected section count: {payload}")


def check_existing_scaffold_file_blocks(tmp: Path) -> None:
    output = tmp / "partial"
    section_dir = output / "sections"
    section_dir.mkdir(parents=True)
    protected = section_dir / "01_objetivo_materiales.tex"
    protected.write_text("NO TOCAR\n", encoding="utf-8")
    before = sha256(protected)
    summary = tmp / "partial_blocked.json"
    run_cmd(command(output, summary), expect_ok=False)
    if sha256(protected) != before:
        raise AssertionError("Existing section was overwritten.")
    payload = load_json(summary)
    assert_standard(payload, "blocked")
    if not payload["results"].get("blockers"):
        raise AssertionError(f"Blocked run did not record blockers: {payload}")


def check_output_file_blocks(tmp: Path) -> None:
    output = tmp / "output_is_file"
    output.write_text("already here\n", encoding="utf-8")
    summary = tmp / "output_file_blocked.json"
    run_cmd(command(output, summary), expect_ok=False)
    payload = load_json(summary)
    assert_standard(payload, "blocked")
    if (output / "main.tex").exists():
        raise AssertionError("File output path somehow produced a scaffold.")


def check_summary_cannot_overwrite_main(tmp: Path) -> None:
    output = tmp / "summary_collides"
    summary = output / "main.tex"
    completed = run_cmd(command(output, summary), expect_ok=False)
    payload = load_stdout_json(completed)
    assert_standard(payload, "blocked")
    if (output / "main.tex").exists():
        raise AssertionError("--summary-json collision left or overwrote main.tex.")


def check_invalid_summary_parent_blocks_before_writing(tmp: Path) -> None:
    output = tmp / "bad_summary_parent_project"
    parent_file = tmp / "parent_is_file"
    parent_file.write_text("not a directory\n", encoding="utf-8")
    summary = parent_file / "summary.json"
    completed = run_cmd(command(output, summary), expect_ok=False)
    payload = load_stdout_json(completed)
    assert_standard(payload, "blocked")
    if (output / "main.tex").exists():
        raise AssertionError("Invalid summary parent left a scaffold that looks valid.")


def check_auxiliary_paths_cannot_collide(tmp: Path) -> None:
    output = tmp / "same_aux"
    summary = tmp / "same_aux.json"
    completed = run_cmd(command(output, summary, "--manifest-json", str(summary)), expect_ok=False)
    payload = load_json(summary)
    assert_standard(payload, "blocked")
    blockers = payload["results"].get("blockers", [])
    if not any("same file" in item.get("detail", "") for item in blockers):
        raise AssertionError(f"Auxiliary collision was not reported clearly: {payload}")
    if (output / "main.tex").exists():
        raise AssertionError("Auxiliary output collision left a scaffold that looks valid.")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_legacy_report_scaffold_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_success_and_tex_escaping(tmp)
        print("PASS check_success_and_tex_escaping")
        check_existing_scaffold_file_blocks(tmp)
        print("PASS check_existing_scaffold_file_blocks")
        check_output_file_blocks(tmp)
        print("PASS check_output_file_blocks")
        check_summary_cannot_overwrite_main(tmp)
        print("PASS check_summary_cannot_overwrite_main")
        check_invalid_summary_parent_blocks_before_writing(tmp)
        print("PASS check_invalid_summary_parent_blocks_before_writing")
        check_auxiliary_paths_cannot_collide(tmp)
        print("PASS check_auxiliary_paths_cannot_collide")
    print("All legacy_spectroscopy_report_builder scaffold regressions passed.")


if __name__ == "__main__":
    main()
