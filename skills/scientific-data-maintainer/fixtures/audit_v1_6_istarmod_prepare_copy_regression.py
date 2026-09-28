#!/usr/bin/env python3
"""Regression checks for istarmod_workbench prepare-copy non-destructive behavior."""

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


def make_tree(path: Path, *, stale: bool = False, no_sm: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if not no_sm:
        (path / "case.sm").write_text("SEC_PATH = p_est_frias/VIS\nAPERTURE = 1\nLINE = Halpha 6562.8\n", encoding="utf-8")
    (path / "lambdas.dat").write_text("Halpha 6562.80\n", encoding="utf-8")
    (path / "iStarmod.py").write_text("# synthetic entrypoint\n", encoding="utf-8")
    (path / "p_est_frias" / "VIS").mkdir(parents=True, exist_ok=True)
    (path / "p_est_frias" / "VIS" / "mini.fits").write_text("placeholder\n", encoding="utf-8")
    make_executable(path / "starmod" / "bin" / "python3")
    if stale:
        (path / "logs").mkdir(parents=True, exist_ok=True)
        (path / "logs" / "old.log").write_text("old\n", encoding="utf-8")
        (path / "p_est_frias" / "RES").mkdir(parents=True, exist_ok=True)
        (path / "p_est_frias" / "RES" / "old.dat").write_text("old\n", encoding="utf-8")
        for name in ["syn_old.fits", "sub_old.fits", "old_plot.png", "old_report.pdf", "residual.dat", "rvvalues.dat"]:
            (path / name).write_text("old\n", encoding="utf-8")
    return path


def run_prepare(source: Path, output_dir: Path, summary_json: Path) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "prepare-copy",
        str(source),
        "--output-dir",
        str(output_dir),
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


def bad_artifacts(output_dir: Path) -> list[str]:
    bad = []
    if not output_dir.is_dir():
        return bad
    for path in output_dir.rglob("*"):
        rel = path.relative_to(output_dir)
        parts = rel.parts
        if "__pycache__" in parts or "starmod" in parts or "venv" in parts:
            bad.append(str(rel))
        elif parts[:1] == ("logs",) or parts[:2] == ("p_est_frias", "RES"):
            bad.append(str(rel))
        elif rel.name.lower() == "rvvalues.dat":
            bad.append(str(rel))
        elif rel.name.startswith(("syn", "sub")) and rel.suffix.lower() == ".fits":
            bad.append(str(rel))
        elif len(parts) == 1 and rel.suffix.lower() in {".png", ".pdf", ".dat"} and rel.name != "lambdas.dat":
            bad.append(str(rel))
    return bad


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="istarmod-prepare-copy-regression-"))
    try:
        fixtures = base / "fixtures"
        outputs = base / "outputs"
        summaries = base / "summaries"

        happy_source = make_tree(fixtures / "happy")
        happy = run_prepare(happy_source, outputs / "happy", summaries / "happy.json")
        assert happy["rc"] == 0, happy
        assert happy["payload"]["status"] == "ok", happy["payload"]
        assert (outputs / "happy" / "case.sm").is_file()
        assert not bad_artifacts(outputs / "happy")

        stale_source = make_tree(fixtures / "stale", stale=True)
        stale = run_prepare(stale_source, outputs / "stale", summaries / "stale.json")
        assert stale["rc"] == 0, stale
        assert stale["payload"]["status"] == "warning", stale["payload"]
        assert not bad_artifacts(outputs / "stale"), bad_artifacts(outputs / "stale")
        findings = set(stale["payload"]["qa"]["findings"])
        assert {"stale_outputs_omitted", "rvvalues_cache_omitted"}.issubset(findings), findings

        no_sm = run_prepare(make_tree(fixtures / "no_sm", no_sm=True), outputs / "no_sm", summaries / "no_sm.json")
        assert no_sm["rc"] == 0, no_sm
        assert no_sm["payload"]["status"] == "warning", no_sm["payload"]
        assert "no_sm_files_copied" in no_sm["payload"]["qa"]["findings"], no_sm["payload"]

        assert_blocked_clean(run_prepare(fixtures / "missing", outputs / "missing", summaries / "missing.json"))

        existing_output = outputs / "existing"
        existing_output.mkdir(parents=True)
        sentinel = existing_output / "do_not_delete.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        assert_blocked_clean(run_prepare(happy_source, existing_output, summaries / "existing.json"))
        assert sentinel.is_file(), "prepare-copy must not delete pre-existing output contents"

        same_source = make_tree(fixtures / "same_source")
        source_marker = same_source / "source_marker.txt"
        source_marker.write_text("keep source\n", encoding="utf-8")
        assert_blocked_clean(run_prepare(same_source, same_source, summaries / "same_source.json"))
        assert source_marker.is_file() and (same_source / "case.sm").is_file(), "source tree was modified or deleted"

        summary_parent = summaries / "summary_parent_is_file"
        summary_parent.parent.mkdir(parents=True, exist_ok=True)
        summary_parent.write_text("not a directory\n", encoding="utf-8")
        assert_blocked_clean(run_prepare(happy_source, outputs / "bad_summary", summary_parent / "summary.json"))
        assert not (outputs / "bad_summary").exists(), "output should not be created when summary path is invalid"
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
