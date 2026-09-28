"""Fast layout checks for the staged scientific-data-notebooks child skill."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


class NotebooksChildLayoutTest(unittest.TestCase):
    def test_notebook_scripts_exist_as_full_bodies(self) -> None:
        for name in NOTEBOOK_SCRIPTS:
            script = ROOT / "scripts" / name
            self.assertTrue(script.exists(), name)
            self.assertNotIn("child_skill_dispatch", script.read_text(encoding="utf-8"), name)

    def test_notebook_references_and_helpers_exist(self) -> None:
        for rel in [
            "scripts/datanalysis_env.py",
            "scripts/_internal/public_contract.py",
            "scripts/_internal/tabular_io.py",
            "references/cross-domain-workflows.md",
            "references/general-timeseries.md",
        ]:
            self.assertTrue((ROOT / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
