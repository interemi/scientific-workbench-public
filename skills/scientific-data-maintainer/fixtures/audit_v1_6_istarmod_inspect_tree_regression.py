#!/usr/bin/env python3
"""Regression checks for istarmod_workbench inspect-tree guardrails."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "istarmod_workbench.py"


def make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def make_tree(path: Path, *, stale: bool = False, rvvalues: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "case.sm").write_text(
        "SEC_PATH = p_est_frias/VIS\nAPERTURE = 1\nLINE = Halpha 6562.8\nRV = -12.5\n",
        encoding="utf-8",
    )
    (path / "lambdas.dat").write_text("Halpha 6562.80\n", encoding="utf-8")
    (path / "iStarmod.py").write_text("# synthetic iSTARMOD entrypoint\n", encoding="utf-8")
    (path / "p_est_frias" / "VIS").mkdir(parents=True, exist_ok=True)
    (path / "p_est_frias" / "VIS" / "mini.fits").write_text("placeholder\n", encoding="utf-8")
    make_executable(path / "starmod" / "bin" / "python3")
    if stale:
        (path / "p_est_frias" / "RES").mkdir(parents=True, exist_ok=True)
        (path / "p_est_frias" / "RES" / "old.dat").write_text("old\n", encoding="utf-8")
        (path / "syn_previous.fits").write_text("old\n", encoding="utf-8")
    if rvvalues:
        (path / "rvvalues.dat").write_text("-12.5\n", encoding="utf-8")
    return path


def run_inspect(input_path: Path, summary_json: Path) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "inspect-tree",
        str(input_path),
        "--summary-json",
        str(summary_json),
    ]
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    payload = None
    for text in [summary_json.read_text(encoding="utf-8") if summary_json.is_file() else "", completed.stdout]:
        stripped = text.strip()
        marker = stripped.find('{\n  "tool"')
        candidate = stripped[marker:] if marker >= 0 else stripped
        if candidate.startswith("{"):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
    return {"rc": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "payload": payload}


def assert_no_traceback(result: dict) -> None:
    text = f"{result['stdout']}\n{result['stderr']}"
    assert "Traceback (most recent call last)" not in text, text


def assert_blocked_clean(result: dict) -> None:
    assert result["rc"] == 2, result
    assert isinstance(result["payload"], dict), result
    assert result["payload"]["status"] == "blocked", result["payload"]
    assert result["payload"]["qa"]["status"] == "blocked", result["payload"]
    assert_no_traceback(result)


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="istarmod-inspect-tree-regression-"))
    try:
        fixtures = base / "fixtures"
        summaries = base / "summaries"

        happy = run_inspect(make_tree(fixtures / "happy"), summaries / "happy.json")
        assert happy["rc"] == 0, happy
        assert happy["payload"]["status"] == "ok", happy["payload"]
        assert happy["payload"]["qa"]["status"] == "ok", happy["payload"]
        assert happy["payload"]["results"]["old_output_count"] == 0, happy["payload"]

        stale = run_inspect(make_tree(fixtures / "stale", stale=True, rvvalues=True), summaries / "stale.json")
        assert stale["rc"] == 0, stale
        assert stale["payload"]["status"] == "warning", stale["payload"]
        findings = set(stale["payload"]["qa"]["findings"])
        assert {"stale_outputs_present", "rvvalues_cache_present"}.issubset(findings), findings

        no_sm = fixtures / "no_sm"
        no_sm.mkdir(parents=True)
        (no_sm / "iStarmod.py").write_text("# no sm\n", encoding="utf-8")
        no_sm_result = run_inspect(no_sm, summaries / "no_sm.json")
        assert no_sm_result["rc"] == 0, no_sm_result
        assert no_sm_result["payload"]["status"] == "warning", no_sm_result["payload"]
        assert "no_sm_files_found" in no_sm_result["payload"]["qa"]["findings"], no_sm_result["payload"]

        assert_blocked_clean(run_inspect(fixtures / "missing", summaries / "missing.json"))

        file_input = fixtures / "file_input.sm"
        file_input.write_text("APERTURE = 1\n", encoding="utf-8")
        assert_blocked_clean(run_inspect(file_input, summaries / "file_input.json"))

        bad_parent = summaries / "summary_parent_is_file"
        bad_parent.parent.mkdir(parents=True, exist_ok=True)
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        assert_blocked_clean(run_inspect(fixtures / "happy", bad_parent / "summary.json"))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
