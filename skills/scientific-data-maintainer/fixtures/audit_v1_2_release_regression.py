#!/usr/bin/env python3
"""Focused v1.2 release gate for the matured coursework/document handoff routes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "scientific-data-analysis"
SCRIPTS = ROOT / "scripts"

REGRESSION_SCRIPTS = [
    "audit_coursework_notebook_fidelity_regression.py",
    "audit_document_reporting_regression.py",
    "audit_practice4_visual_handoff_regression.py",
]


def run_cmd(args: list[str], *, tmp: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def check_version_docs() -> dict:
    documents = ROOT.parent / "scientific-data-documents"
    archive = documents / ".cache" / "archived_references"
    expected = {
        archive / "README.txt": ["coursework-notebook-fidelity.md", "coursework-figure-equivalents.md"],
        archive / "RELEASE-v1.txt": ["v1.2 closes the recent coursework and document-handoff maturation"],
        ROOT / "SKILL.md": ["coursework-notebook-fidelity.md", "scripts/presentation_workbench.py"],
        documents / "SKILL.md": ["name: scientific-data-documents", "owning root"],
    }
    results = {}
    for path, terms in expected.items():
        text = path.read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        if missing:
            raise AssertionError(f"{path.name} is missing v1.2 release terms: {missing}")
        results[str(path.relative_to(ROOT.parent))] = {"checked_terms": terms}
    return results


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_v1_2_release_") as raw_tmp:
        tmp = Path(raw_tmp)
        runs = {}
        for script in REGRESSION_SCRIPTS:
            completed = run_cmd([sys.executable, str(SCRIPTS / script)], tmp=tmp)
            runs[script] = {"stdout": completed.stdout.strip().splitlines()[-1:]}
            print(f"PASS {script}")
        docs = check_version_docs()
    print(json.dumps({"status": "ok", "regressions": list(runs), "docs": docs}, indent=2, ensure_ascii=True))
    print("All v1.2 release regressions passed.")


if __name__ == "__main__":
    main()
