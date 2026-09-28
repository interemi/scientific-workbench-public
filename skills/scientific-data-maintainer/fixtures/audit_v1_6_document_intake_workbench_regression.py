#!/usr/bin/env python3
"""Focused v1.6 regression for document_intake_workbench edge handling."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "document_intake_workbench.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_traceback(result: subprocess.CompletedProcess[str], payload: dict | None = None) -> None:
    rendered = result.stdout + result.stderr
    if payload is not None:
        rendered += json.dumps(payload, ensure_ascii=True)
    require("Traceback (most recent call last)" not in rendered, "raw traceback leaked into document intake output")


def check_happy_text_intake(tmp: Path) -> None:
    source = tmp / "note.txt"
    source.write_text("A small document intake note.\n", encoding="utf-8")
    out = tmp / "happy"
    summary = out / "summary.json"
    result = run([sys.executable, str(SCRIPT), str(source), "--output-dir", str(out), "--summary-json", str(summary)])
    require(result.returncode == 0, result.stderr)
    payload = read_json(summary)
    assert_no_traceback(result, payload)
    require(payload["status"] == "ok", "simple text intake should be ok")
    require(payload["results"]["intake"]["file_count"] == 1, "simple text intake should inspect one file")


def check_max_files_warns(tmp: Path) -> None:
    source = tmp / "many"
    source.mkdir()
    for index, suffix in enumerate(["txt", "md", "tex"], start=1):
        (source / f"doc_{index}.{suffix}").write_text(f"document {index}\n", encoding="utf-8")
    out = tmp / "limited"
    summary = out / "summary.json"
    result = run(
        [
            sys.executable,
            str(SCRIPT),
            str(source),
            "--max-files",
            "2",
            "--output-dir",
            str(out),
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 0, result.stderr)
    payload = read_json(summary)
    assert_no_traceback(result, payload)
    require(payload["status"] == "warning", "max-files truncation should be a warning")
    qa = payload["qa"]
    require(qa["metrics"]["limit_reached"] is True, "limit_reached metric should be true")
    require(payload["results"]["intake"]["file_count"] == 2, "limited intake should inspect two files")


def check_corrupt_pdf_warns_without_traceback(tmp: Path) -> None:
    source = tmp / "broken.pdf"
    source.write_bytes(b"%PDF-1.4\ntruncated")
    out = tmp / "broken_pdf"
    summary = out / "summary.json"
    result = run([sys.executable, str(SCRIPT), str(source), "--output-dir", str(out), "--summary-json", str(summary)])
    require(result.returncode == 0, result.stderr)
    payload = read_json(summary)
    assert_no_traceback(result, payload)
    require(payload["status"] == "warning", "corrupt PDF should not be a clean ok")
    qa = payload["qa"]
    require(qa["metrics"]["failed_item_count"] == 1, "corrupt PDF should count as one failed item")
    item = payload["results"]["intake"]["files"][0]
    require(item["method"] == "inspection_failed", "corrupt PDF should be marked inspection_failed")
    require(item["runtime_failure_count"] == 1, "corrupt PDF should expose runtime failure count")


def check_output_dir_file_fails_cleanly(tmp: Path) -> None:
    source = tmp / "note.txt"
    source.write_text("A small note.\n", encoding="utf-8")
    out = tmp / "not_a_dir"
    out.write_text("file, not dir\n", encoding="utf-8")
    summary = tmp / "failure.json"
    result = run([sys.executable, str(SCRIPT), str(source), "--output-dir", str(out), "--summary-json", str(summary)])
    require(result.returncode != 0, "output-dir file should fail")
    payload = read_json(summary)
    assert_no_traceback(result, payload)
    require(payload["status"] == "fail", "output-dir file should emit fail status")
    require("--output-dir exists and is not a directory" in payload["results"]["error"], "failure should explain output-dir problem")


def check_missing_path_fails_or_warns_cleanly(tmp: Path) -> None:
    missing = tmp / "missing.pdf"
    out = tmp / "missing_out"
    summary = out / "summary.json"
    result = run([sys.executable, str(SCRIPT), str(missing), "--output-dir", str(out), "--summary-json", str(summary)])
    require(result.returncode == 0, result.stderr)
    payload = read_json(summary)
    assert_no_traceback(result, payload)
    require(payload["status"] == "warning", "missing input should be explicit warning")
    require(payload["qa"]["metrics"]["missing_input_count"] == 1, "missing input should be counted")
    require(payload["results"]["intake"]["file_count"] == 0, "missing input should not invent files")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-6-doc-intake-") as raw:
        tmp = Path(raw)
        checks = [
            check_happy_text_intake,
            check_max_files_warns,
            check_corrupt_pdf_warns_without_traceback,
            check_output_dir_file_fails_cleanly,
            check_missing_path_fails_or_warns_cleanly,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All v1.6 document_intake_workbench regressions passed.")


if __name__ == "__main__":
    main()
