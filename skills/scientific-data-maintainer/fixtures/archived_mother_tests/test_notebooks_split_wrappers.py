"""v2.3 notebook/cross-domain child split checks for mother wrappers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NOTEBOOK_CHILD = ROOT.parent / "scientific-data-notebooks"
NOTEBOOK_SCRIPTS = [
    "profile_table.py",
    "duckdb_workbench.py",
    "cross_domain_data_workbench.py",
    "bootstrap_analysis_notebook.py",
    "notebook_workbench.py",
    "coursework_notebook_fidelity_check.py",
    "notebook_branch_compare.py",
    "timeseries_forecasting_workbench.py",
    "inspect_data_container.py",
    "physical_qa.py",
    "analyze_series.py",
    "pipeline_scaffold.py",
]


def python_executable() -> str:
    datanalysis = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
    return str(datanalysis) if datanalysis.exists() else sys.executable


class NotebooksSplitWrappersTest(unittest.TestCase):
    def run_command(self, command: list[str], tmp: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=160,
        )

    def test_child_has_full_bodies_and_mother_has_wrappers(self) -> None:
        self.assertTrue((NOTEBOOK_CHILD / "SKILL.md").exists())
        self.assertTrue((NOTEBOOK_CHILD / "scripts" / "datanalysis_env.py").exists())
        for name in NOTEBOOK_SCRIPTS:
            mother = SCRIPTS / name
            child = NOTEBOOK_CHILD / "scripts" / name
            self.assertIn("child_skill_dispatch", mother.read_text(encoding="utf-8"), name)
            self.assertTrue(child.exists(), name)
            self.assertNotIn("child_skill_dispatch", child.read_text(encoding="utf-8"), name)

    def test_notebook_family_workflows_execute_through_mother_wrappers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_notebooks_split_") as tmp_raw:
            tmp = Path(tmp_raw)
            csv_path = tmp / "operations.csv"
            csv_path.write_text(
                "date,value,group\n2026-01-01,10,A\n2026-01-02,,B\n2026-01-03,inf,A\n",
                encoding="utf-8",
            )
            original_csv = csv_path.read_bytes()
            ts_path = tmp / "timeseries.csv"
            ts_path.write_text(
                "\n".join(
                    ["date,value"]
                    + [f"2026-01-{day:02d},{10 + day}" for day in range(1, 14)]
                )
                + "\n",
                encoding="utf-8",
            )

            notebook = tmp / "legacy.ipynb"
            notebook.write_text(
                json.dumps({"nbformat": 4, "nbformat_minor": 5, "cells": [], "metadata": {}}),
                encoding="utf-8",
            )

            archive = tmp / "package.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("table.csv", "id,value\n1,2\n")
                handle.writestr("notes.txt", "anonymous package")

            branch_root = tmp / "branches"
            (branch_root / "team_A").mkdir(parents=True)
            (branch_root / "team_B").mkdir(parents=True)
            notebook_text = notebook.read_text(encoding="utf-8")
            (branch_root / "team_A" / "analysis.ipynb").write_text(notebook_text, encoding="utf-8")
            (branch_root / "team_B" / "analysis.ipynb").write_text(notebook_text, encoding="utf-8")

            commands = [
                ([
                    python_executable(),
                    str(SCRIPTS / "profile_table.py"),
                    str(csv_path),
                    "--summary-json",
                    str(tmp / "profile_table.json"),
                ], tmp / "profile_table.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "cross_domain_data_workbench.py"),
                    str(csv_path),
                    "--output-dir",
                    str(tmp / "cross_domain"),
                    "--summary-json",
                    str(tmp / "cross_domain.json"),
                ], tmp / "cross_domain.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "coursework_notebook_fidelity_check.py"),
                    str(notebook),
                    "--summary-json",
                    str(tmp / "fidelity.json"),
                ], tmp / "fidelity.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "inspect_data_container.py"),
                    str(archive),
                    "--summary-json",
                    str(tmp / "container.json"),
                ], tmp / "container.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "timeseries_forecasting_workbench.py"),
                    "--output-dir",
                    str(tmp / "forecast"),
                    "--data-path",
                    str(ts_path),
                    "--date-column",
                    "date",
                    "--value-column",
                    "value",
                    "--test-horizon",
                    "2",
                    "--summary-json",
                    str(tmp / "forecast.json"),
                    "--overwrite",
                ], tmp / "forecast.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "physical_qa.py"),
                    str(csv_path),
                    "--summary-json",
                    str(tmp / "physical_qa.json"),
                ], tmp / "physical_qa.json", False),
                ([
                    python_executable(),
                    str(SCRIPTS / "duckdb_workbench.py"),
                    str(csv_path),
                    "--summary-json",
                    str(tmp / "duckdb.json"),
                    "--output",
                    str(tmp / "duckdb_out.csv"),
                ], tmp / "duckdb.json", True),
                ([
                    python_executable(),
                    str(SCRIPTS / "notebook_branch_compare.py"),
                    str(branch_root),
                    "--output-dir",
                    str(tmp / "branches_out"),
                    "--summary-json",
                    str(tmp / "branches.json"),
                ], tmp / "branches.json", False),
            ]
            for command, summary_path, allow_blocked in commands:
                completed = self.run_command(command, tmp)
                self.assertTrue(summary_path.exists(), f"missing summary for {' '.join(command)}")
                payload = json.loads(summary_path.read_text(encoding="utf-8"))
                if completed.returncode != 0:
                    self.assertTrue(allow_blocked, completed.stdout + completed.stderr)
                    self.assertEqual(payload.get("app_status"), "BLOCKED_CONTROLADO")
                    self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                else:
                    self.assertIn(payload.get("app_status"), {"PASS", "WARNING", "ok", "warning"})
                self.assertFalse(payload.get("original_modified", False))
            self.assertEqual(csv_path.read_bytes(), original_csv)


if __name__ == "__main__":
    unittest.main()
