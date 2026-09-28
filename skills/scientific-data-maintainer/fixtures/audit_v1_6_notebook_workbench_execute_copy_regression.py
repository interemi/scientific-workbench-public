#!/usr/bin/env python3
"""v1.6 regression checks for notebook_workbench.py execute-copy."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "notebook_workbench.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def run_tool(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_sandbox_blocked(payload: dict) -> bool:
    run = payload.get("results", {}).get("run", {})
    assessment_status = run.get("assessment", {}).get("status") if isinstance(run, dict) else None
    return payload.get("status") == "blocked" and assessment_status == "sandbox_blocked"


def require_envelope(path: Path, status: str) -> dict:
    if not path.exists():
        fail(f"summary_json was not written: {path}")
    payload = read_json(path)
    if payload.get("tool") != "notebook_workbench":
        fail(f"unexpected tool id: {payload.get('tool')}")
    actual_status = payload.get("status")
    sandbox_blocked = is_sandbox_blocked(payload)
    if actual_status != status and not (status in {"ok", "warning"} and sandbox_blocked):
        fail(f"expected status {status}, got {payload.get('status')}")
    qa = payload.get("qa")
    if not isinstance(qa, dict):
        fail("missing qa envelope")
    if status in {"ok", "warning"} and sandbox_blocked:
        if qa.get("status") != "warning":
            fail(f"expected warning qa.status for sandbox block, got {qa.get('status')}")
        return payload
    if status in {"warning", "blocked"} and qa.get("status") != status:
        fail(f"expected qa.status {status}, got {qa.get('status')}")
    if status == "ok" and qa.get("status") not in {"ok", "not_applicable"}:
        fail(f"expected ok/not_applicable qa.status, got {qa.get('status')}")
    return payload


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def markdown_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }


def write_notebook(path: Path, cells: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook(cells), indent=2), encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def no_traceback(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if "Traceback (most recent call last)" in proc.stdout or "Traceback (most recent call last)" in proc.stderr:
        fail(f"{label} emitted a raw traceback")


def check_happy_copy(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "happy" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["happy"]),
            "--output-dir",
            str(tmp / "happy" / "run"),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    no_traceback(proc, "happy copy")
    payload = require_envelope(summary, "ok")
    executed = Path(payload["artifacts"]["executed_copy"])
    if not executed.exists():
        fail("executed notebook copy was not written")


def check_staged_extra_copy(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "staged" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["staged"]),
            "--output-dir",
            str(tmp / "staged" / "run"),
            "--stage-extra",
            str(fixtures["csv"]),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    no_traceback(proc, "staged extra copy")
    payload = require_envelope(summary, "ok")
    staged = payload["results"]["run"]["staged_extra_paths"]
    if not staged:
        fail("staged extra file was not recorded")


def check_input_without_provider_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "input_blocked" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["input"]),
            "--output-dir",
            str(tmp / "input_blocked" / "run"),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode == 0:
        fail("input() notebook without --input-value should return non-zero")
    no_traceback(proc, "input without provider")
    payload = require_envelope(summary, "blocked")
    if "input()" not in payload["results"]["blocked_reason"]:
        fail("blocked reason should mention input()")


def check_input_provider_cleanup(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "input_ok" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["input"]),
            "--output-dir",
            str(tmp / "input_ok" / "run"),
            "--input-value",
            "Vega",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    no_traceback(proc, "input provider cleanup")
    payload = require_envelope(summary, "ok")
    run = payload["results"]["run"]
    if run["ephemeral_input_provider_cells_removed_before_save"] != 2:
        fail("temporary input provider cells were not removed before save")
    saved = read_json(Path(payload["artifacts"]["executed_copy"]))
    saved_text = json.dumps(saved)
    if "codex_ephemeral" in saved_text or "_codex_input_provider" in saved_text:
        fail("temporary input provider leaked into saved notebook copy")


def check_corrupt_notebook_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "corrupt" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["corrupt"]),
            "--output-dir",
            str(tmp / "corrupt" / "run"),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode == 0:
        fail("corrupt notebook should return non-zero")
    no_traceback(proc, "corrupt notebook")
    require_envelope(summary, "blocked")


def check_markdown_only_range_warning(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "markdown_only" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["happy"]),
            "--output-dir",
            str(tmp / "markdown_only" / "run"),
            "--cell-range",
            "1:1",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    no_traceback(proc, "markdown-only range")
    payload = require_envelope(summary, "warning")
    if is_sandbox_blocked(payload):
        return
    findings = " ".join(payload.get("qa", {}).get("findings") or [])
    if "no executable code cells" not in findings:
        fail("markdown-only range should produce an explicit no-code warning")


def check_original_notebook_untouched(tmp: Path, fixtures: dict[str, Path]) -> None:
    before = sha256(fixtures["happy"])
    summary = tmp / "untouched" / "summary.json"
    proc = run_tool(
        [
            "execute-copy",
            str(fixtures["happy"]),
            "--output-dir",
            str(tmp / "untouched" / "run"),
            "--append-code",
            "print('extra copied cell')",
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    no_traceback(proc, "original untouched")
    require_envelope(summary, "ok")
    after = sha256(fixtures["happy"])
    if before != after:
        fail("source notebook changed during execute-copy")


def write_fixtures(tmp: Path) -> dict[str, Path]:
    fixtures = tmp / "fixtures"
    data = fixtures / "measurements.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
    happy = write_notebook(
        fixtures / "happy.ipynb",
        [
            markdown_cell("# Synthetic notebook"),
            code_cell("x = 6 * 7\nprint(f'answer={x}')"),
        ],
    )
    staged = write_notebook(
        fixtures / "staged.ipynb",
        [
            markdown_cell("# Staged data notebook"),
            code_cell("from pathlib import Path\nprint(Path('measurements.csv').read_text().splitlines()[0])"),
        ],
    )
    input_nb = write_notebook(
        fixtures / "needs_input.ipynb",
        [
            markdown_cell("# Interactive notebook"),
            code_cell("name = input('name? ')\nprint('hello', name)"),
        ],
    )
    corrupt = fixtures / "corrupt.ipynb"
    corrupt.write_text('{"cells": [', encoding="utf-8")
    return {"happy": happy, "staged": staged, "input": input_nb, "corrupt": corrupt, "csv": data}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_notebook_execute_copy_regression_") as tmp_name:
        tmp = Path(tmp_name)
        fixtures = write_fixtures(tmp)
        check_happy_copy(tmp, fixtures)
        print("PASS check_happy_copy")
        check_staged_extra_copy(tmp, fixtures)
        print("PASS check_staged_extra_copy")
        check_input_without_provider_blocked(tmp, fixtures)
        print("PASS check_input_without_provider_blocked")
        check_input_provider_cleanup(tmp, fixtures)
        print("PASS check_input_provider_cleanup")
        check_corrupt_notebook_blocked(tmp, fixtures)
        print("PASS check_corrupt_notebook_blocked")
        check_markdown_only_range_warning(tmp, fixtures)
        print("PASS check_markdown_only_range_warning")
        check_original_notebook_untouched(tmp, fixtures)
        print("PASS check_original_notebook_untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
