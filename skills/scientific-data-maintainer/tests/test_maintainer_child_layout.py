"""Fast layout checks for the staged scientific-data-maintainer child skill."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MaintainerChildLayoutTest(unittest.TestCase):
    def test_core_maintainer_scripts_exist_as_full_bodies(self) -> None:
        for name in [
            "portable_smoke_test.py",
            "sync_public_surface_docs.py",
            "skill_surface_audit.py",
            "validate_skill_samples.py",
            "capability_probe_matrix.py",
        ]:
            script = ROOT / "scripts" / name
            self.assertTrue(script.exists(), name)
            self.assertNotIn("archived_regression_runner", script.read_text(encoding="utf-8"), name)

    def test_registry_and_internal_helpers_exist(self) -> None:
        self.assertTrue((ROOT / "public_surface_registry.yaml").exists())
        self.assertTrue((ROOT / "scripts" / "_internal" / "public_contract.py").exists())

    def test_direct_probe_entrypoint_loads_from_maintainer_root(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["SCIENTIFIC_DATA_ANALYSIS_DATANALYSIS_REEXEC"] = "capability_probe_matrix"
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "capability_probe_matrix.py"), "--help"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--output-dir", completed.stdout)


if __name__ == "__main__":
    unittest.main()
