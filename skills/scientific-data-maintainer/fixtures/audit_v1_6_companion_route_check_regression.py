#!/usr/bin/env python3
"""Focused v1.6 regression for companion_route_check output safety."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "companion_route_check.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_stdout_json(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout is not a single JSON payload: {exc}\n{result.stdout[:500]}") from exc


def companions(payload: dict) -> set[str]:
    return {item["companion"] for item in payload["results"]["recommendations"]}


def excluded_ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["results"]["excluded_by_policy"]}


def check_normal_summary_write(tmp: Path) -> None:
    summary = tmp / "normal" / "route.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Revisar visualmente un PDF cientifico",
            "--file",
            "report.pdf",
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 0, result.stderr)
    require(summary.exists(), "summary JSON was not written")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    require(payload["status"] == "ok", "PDF route should be ok")
    require("pdf" in companions(payload), "PDF route should recommend pdf")
    require(payload["results"]["policy"]["file_inputs_are_hints_only"] is True, "missing file-hint policy marker")


def check_summary_directory_fails_cleanly(tmp: Path) -> None:
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Revisar PDF",
            "--file",
            "report.pdf",
            "--summary-json",
            str(tmp),
        ]
    )
    require(result.returncode != 0, "summary path directory should not return success")
    require("Traceback" not in result.stderr + result.stdout, "summary path directory should not traceback")
    payload = parse_stdout_json(result)
    require(payload["status"] == "fail", "summary path directory should emit fail status")
    require("directory" in payload["results"]["error"], "failure should explain directory problem")


def check_summary_parent_file_fails_cleanly(tmp: Path) -> None:
    parent_file = tmp / "not_a_dir"
    parent_file.write_text("I am a file, not a directory.\n", encoding="utf-8")
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Editar DOCX",
            "--file",
            "report.docx",
            "--summary-json",
            str(parent_file / "route.json"),
        ]
    )
    require(result.returncode != 0, "summary parent file should not return success")
    require("Traceback" not in result.stderr + result.stdout, "summary parent file should not traceback")
    payload = parse_stdout_json(result)
    require(payload["status"] == "fail", "summary parent file should emit fail status")
    require("Could not write --summary-json" in payload["results"]["error"], "failure should explain write error")


def check_warning_and_policy_exclusions(tmp: Path) -> None:
    warning_summary = tmp / "warning.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Calcular medias en una tabla simple",
            "--file",
            "plain.unknown",
            "--summary-json",
            str(warning_summary),
        ]
    )
    require(result.returncode == 0, result.stderr)
    payload = json.loads(warning_summary.read_text(encoding="utf-8"))
    require(payload["status"] == "warning", "unmatched route should be a controlled warning")
    require(payload["results"]["recommendations"] == [], "unmatched route should not recommend companions")

    excluded_summary = tmp / "excluded.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Buscar en Gmail, Google Drive y Zotero para un informe",
            "--summary-json",
            str(excluded_summary),
        ]
    )
    require(result.returncode == 0, result.stderr)
    payload = json.loads(excluded_summary.read_text(encoding="utf-8"))
    require({"gmail", "google_drive", "zotero"} <= excluded_ids(payload), "excluded companions should be explicit")
    require(payload["results"]["recommendations"] == [], "excluded companions must not be recommended")


def check_multiroute_recommendations(tmp: Path) -> None:
    summary = tmp / "multi.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            "--task",
            "Notebook con Plotly blanco y presentacion editable",
            "--file",
            "analysis.ipynb",
            "--file",
            "preview.html",
            "--file",
            "slides.pptx",
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 0, result.stderr)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    recs = companions(payload)
    require("jupyter-notebook" in recs, "notebook route should recommend jupyter-notebook")
    require("Browser Use / playwright" in recs, "HTML/Plotly route should recommend browser QA")
    require("Presentations" in recs, "PPTX route should recommend Presentations")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-6-companion-") as raw:
        tmp = Path(raw)
        checks = [
            check_normal_summary_write,
            check_summary_directory_fails_cleanly,
            check_summary_parent_file_fails_cleanly,
            check_warning_and_policy_exclusions,
            check_multiroute_recommendations,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All v1.6 companion_route_check regressions passed.")


if __name__ == "__main__":
    main()
