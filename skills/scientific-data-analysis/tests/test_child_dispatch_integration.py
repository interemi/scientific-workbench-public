"""Regression coverage for historical mother wrappers delegated to child roots."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ChildDispatchIntegrationTest(unittest.TestCase):
    def test_mother_env_doctor_imports_astro_wrapper_with_mother_internal_loaded(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "env_doctor.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["tool"], "env_doctor")
        self.assertIn("external_astronomy_tools", payload["results"])
        self.assertNotIn("ModuleNotFoundError", completed.stdout)


if __name__ == "__main__":
    unittest.main()
