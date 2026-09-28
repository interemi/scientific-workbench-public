#!/usr/bin/env python3
"""v1.6 regression checks for notebook_branch_compare.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "notebook_branch_compare.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def run_tool(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def read_json(path: Path) -> dict:
    if not path.exists():
        fail(f"summary_json was not written: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_envelope(path: Path, status: str) -> dict:
    payload = read_json(path)
    if payload.get("tool") != "notebook_branch_compare":
        fail(f"unexpected tool id: {payload.get('tool')}")
    if payload.get("status") != status:
        fail(f"expected status {status}, got {payload.get('status')}")
    qa = payload.get("qa")
    if not isinstance(qa, dict) or qa.get("status") != status:
        fail(f"expected qa.status {status}, got {qa}")
    return payload


def no_traceback(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if "Traceback (most recent call last)" in proc.stdout or "Traceback (most recent call last)" in proc.stderr:
        fail(f"{label} emitted a raw traceback")


def write_product(path: Path, text: str = "fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_notebook(path: Path, title: str) -> Path:
    notebook = {
        "cells": [{"cell_type": "markdown", "metadata": {}, "source": title}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    return path


def create_complete_tree(root: Path) -> Path:
    for branch in ["A", "C"]:
        write_notebook(root / branch / "target_R_2025.ipynb", f"# {branch}")
        write_product(root / branch / "target_R_2025.png")
        write_product(root / branch / "target_R_2025.csv", "x,y\n1,2\n")
    return root


def create_warning_tree(root: Path) -> Path:
    write_notebook(root / "A" / "target_R_2025.ipynb", "# A")
    write_product(root / "A" / "target_R_2025.png")
    write_product(root / "A" / "target_R_2025_copy.png")
    write_notebook(root / "C" / "target_R_2025.ipynb", "# C")
    write_product(root / "EDU" / "other_B_2025.png")
    return root


def check_complete_tree_ok(tmp: Path) -> None:
    root = create_complete_tree(tmp / "complete")
    output = tmp / "complete_out"
    summary = output / "summary.json"
    proc = run_tool([str(root), "--output-dir", str(output), "--summary-json", str(summary)])
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["product_count"] != 6:
        fail("complete tree product count should be six")
    for name in ["branch_product_inventory.csv", "branch_summary.csv", "equivalent_products.csv", "candidate_figures.md"]:
        if not (output / name).exists():
            fail(f"expected output artifact missing: {name}")


def check_warning_tree_detects_gaps(tmp: Path) -> None:
    root = create_warning_tree(tmp / "warning")
    output = tmp / "warning_out"
    summary = output / "summary.json"
    proc = run_tool([str(root), "--output-dir", str(output), "--summary-json", str(summary)])
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "warning")
    metrics = payload["qa"]["metrics"]
    if metrics["missing_group_count"] < 1:
        fail("warning tree should detect missing groups")
    if metrics["duplicate_group_count"] < 1:
        fail("warning tree should detect duplicate branch products")


def check_empty_tree_warning(tmp: Path) -> None:
    root = tmp / "empty"
    root.mkdir(parents=True)
    summary = tmp / "empty_summary.json"
    proc = run_tool([str(root), "--summary-json", str(summary)])
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "warning")
    if payload["results"]["product_count"] != 0:
        fail("empty tree product count should be zero")
    findings = " ".join(payload["qa"]["findings"])
    if "No notebook/FITS/PNG/HTML coursework products" not in findings:
        fail("empty tree should include explicit no-products finding")


def check_missing_root_blocked(tmp: Path) -> None:
    summary = tmp / "missing" / "summary.json"
    proc = run_tool([str(tmp / "missing_root"), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("missing root should return non-zero")
    no_traceback(proc, "missing root")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] != "SystemExit":
        fail("missing root should preserve SystemExit-style validation")


def check_output_dir_file_blocked(tmp: Path) -> None:
    root = create_complete_tree(tmp / "output_conflict_root")
    output_file = tmp / "output_is_file"
    output_file.write_text("not a directory\n", encoding="utf-8")
    summary = tmp / "output_conflict" / "summary.json"
    proc = run_tool([str(root), "--output-dir", str(output_file), "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("output-dir file should return non-zero")
    no_traceback(proc, "output-dir file")
    payload = require_envelope(summary, "blocked")
    if payload["results"]["error_type"] != "FileExistsError":
        fail("output-dir file should report FileExistsError")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_notebook_branch_compare_v16_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_complete_tree_ok(tmp)
        print("PASS check_complete_tree_ok")
        check_warning_tree_detects_gaps(tmp)
        print("PASS check_warning_tree_detects_gaps")
        check_empty_tree_warning(tmp)
        print("PASS check_empty_tree_warning")
        check_missing_root_blocked(tmp)
        print("PASS check_missing_root_blocked")
        check_output_dir_file_blocked(tmp)
        print("PASS check_output_dir_file_blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
