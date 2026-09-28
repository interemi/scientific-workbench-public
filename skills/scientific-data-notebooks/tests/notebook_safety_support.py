"""Behavioral regressions for copy safety and scientific-data integrity."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(FIXTURES))

import cross_domain_data_workbench
import notebook_workbench
import profile_table
import timeseries_forecasting_workbench
from _internal.run_bundle import ensure_run_bundle, finalize_existing_run_bundle


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hash_tree(path: Path) -> dict[str, str]:
    return {str(item.relative_to(path)): sha256(item) for item in sorted(path.rglob("*")) if item.is_file()}


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


class TableSafetyAssertions:
    def assert_cross_domain_metadata_output_cannot_replace_input(self, option: str) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            table = root / "input.csv"
            table.write_text("x\n1\n", encoding="utf-8")
            before = sha256(table)
            output_dir = root / "derived"

            completed = run_script(
                "cross_domain_data_workbench.py",
                table,
                "--output-dir",
                output_dir,
                option,
                table,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(sha256(table), before)
            self.assertFalse(output_dir.exists())
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertIn(option, payload["blocked_reason"])
            self.assertFalse(payload["original_modified"])
