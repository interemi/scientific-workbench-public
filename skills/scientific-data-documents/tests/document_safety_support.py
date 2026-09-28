"""Behavioral regressions for document and deliverable copy safety."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(FIXTURES))

import document_intake_workbench
import keynote_export
import office_roundtrip
import semantic_diff
from _internal.run_bundle import ensure_run_bundle, finalize_existing_run_bundle


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def directory_snapshot(path: Path) -> dict[str, str]:
    return {str(item.relative_to(path)): sha256(item) for item in sorted(path.rglob("*")) if item.is_file()}


def strict_json(text: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-standard JSON constant: {value}")

    return json.loads(text, parse_constant=reject_constant)


def run_script(name: str, *arguments: object) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *[str(item) for item in arguments]],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
