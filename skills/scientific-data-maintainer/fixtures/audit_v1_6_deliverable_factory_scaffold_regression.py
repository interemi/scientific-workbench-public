#!/usr/bin/env python3
"""Regression tests for deliverable_factory.py scaffold."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "deliverable_factory.py"


def run_cmd(args: list[str], cwd: Path, expect_ok: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Unexpected traceback for {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command succeeded unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}")
    return completed


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_spanish_latex_and_escaping(tmp: Path) -> None:
    out = tmp / "latex_spanish"
    summary = tmp / "latex_spanish.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(out),
            "--kind",
            "academic-report",
            "--format",
            "latex",
            "--title",
            "R&D 100%_calibracion #1",
            "--language",
            "spanish",
            "--summary-json",
            str(summary),
        ],
        tmp,
    )
    content = (out / "main.tex").read_text(encoding="utf-8")
    assert r"\title{R\&D 100\%\_calibracion \#1}" in content
    assert r"\section{Datos y metodologia}" in content
    assert "Completa esta seccion." in content
    payload = read_json(summary)
    assert payload["status"] == "ok"
    assert payload["results"]["created_files"]


def check_html_escapes_title_and_bilingual(tmp: Path) -> None:
    out = tmp / "html_bilingual"
    summary = tmp / "html_bilingual.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(out),
            "--kind",
            "presentation",
            "--format",
            "html",
            "--title",
            "Handoff <Scientific> & Review",
            "--language",
            "bilingual",
            "--summary-json",
            str(summary),
        ],
        tmp,
    )
    content = (out / "deliverable.html").read_text(encoding="utf-8")
    assert "Handoff &lt;Scientific&gt; &amp; Review" in content
    assert "Audience / Audiencia" in content
    assert "Fill in this section. / Completa esta seccion." in content


def check_existing_file_blocks_and_overwrite_is_explicit(tmp: Path) -> None:
    out = tmp / "existing"
    out.mkdir()
    target = out / "deliverable.md"
    target.write_text("USER CONTENT\n", encoding="utf-8")
    summary = tmp / "blocked.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(out),
            "--kind",
            "status-report",
            "--format",
            "markdown",
            "--title",
            "Should Block",
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    assert target.read_text(encoding="utf-8") == "USER CONTENT\n"
    blocked_payload = read_json(summary)
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["qa"]["status"] == "blocked"

    overwrite_summary = tmp / "overwrite.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(out),
            "--kind",
            "status-report",
            "--format",
            "markdown",
            "--title",
            "Overwrite Allowed",
            "--summary-json",
            str(overwrite_summary),
            "--overwrite",
        ],
        tmp,
    )
    assert "Overwrite Allowed" in target.read_text(encoding="utf-8")
    assert read_json(overwrite_summary)["results"]["overwrote_existing_files"] is True


def check_bad_paths_fail_cleanly(tmp: Path) -> None:
    output_file = tmp / "not_a_dir"
    output_file.write_text("file, not dir", encoding="utf-8")
    summary = tmp / "output_file.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(output_file),
            "--kind",
            "report",
            "--format",
            "markdown",
            "--title",
            "Bad",
            "--summary-json",
            str(summary),
        ],
        tmp,
        expect_ok=False,
    )
    assert read_json(summary)["status"] == "fail"

    invalid_parent = tmp / "manifest_parent_file"
    invalid_parent.write_text("file parent", encoding="utf-8")
    summary2 = tmp / "invalid_manifest_parent.json"
    run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(tmp / "bad_manifest_out"),
            "--kind",
            "report",
            "--format",
            "markdown",
            "--title",
            "Bad Manifest",
            "--manifest-json",
            str(invalid_parent / "manifest.json"),
            "--summary-json",
            str(summary2),
        ],
        tmp,
        expect_ok=False,
    )
    assert read_json(summary2)["status"] == "fail"


def check_auxiliary_output_cannot_overwrite_scaffold(tmp: Path) -> None:
    out = tmp / "aux_collision"
    completed = run_cmd(
        [
            sys.executable,
            str(TOOL),
            "scaffold",
            str(out),
            "--kind",
            "report",
            "--format",
            "markdown",
            "--title",
            "Aux Collision",
            "--summary-json",
            str(out / "deliverable.md"),
        ],
        tmp,
        expect_ok=False,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "fail"
    assert not (out / "deliverable.md").exists()


def main() -> None:
    checks = [
        check_spanish_latex_and_escaping,
        check_html_escapes_title_and_bilingual,
        check_existing_file_blocks_and_overwrite_is_explicit,
        check_bad_paths_fail_cleanly,
        check_auxiliary_output_cannot_overwrite_scaffold,
    ]
    with tempfile.TemporaryDirectory(prefix="sda_deliverable_scaffold_") as raw_tmp:
        tmp = Path(raw_tmp)
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All deliverable_factory scaffold regressions passed.")


if __name__ == "__main__":
    main()
