from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "skills/scientific-data-analysis/scripts/datanalysis_env.py"
EVIDENCE_KEY = "SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE"


class RuntimeEvidenceTests(unittest.TestCase):
    def test_selected_tool_reports_runtime_and_preserves_a_completed_observation(self):
        cases = [
            ("companion_route_check", ["--task", "Inspect synthetic data."]),
            # The dispatcher and the selected command share a stem in this case.
            ("datanalysis_env", ["status"]),
        ]
        for tool, arguments in cases:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                destination = root / ".swb-runtime-ffffffff-ffff-4fff-8fff-ffffffffffff.json"
                environment = {
                    **os.environ,
                    "DATAANALYSIS_PYTHON": sys.executable,
                    EVIDENCE_KEY: json.dumps({
                        "destination": str(destination),
                        "tool": tool,
                        "packages": ["pip", "swb-nonexistent-regression-package"],
                    }),
                }
                command = [sys.executable, "-B", str(WRAPPER), "run-tool", tool, *arguments]
                result = subprocess.run(
                    command, cwd=root, env=environment, capture_output=True, text=True, timeout=30, check=True,
                )
                self.assertIn(json.loads(result.stdout)["status"], {"ok", "warning"})
                retained = destination.read_bytes()
                observation = json.loads(retained)
                self.assertEqual(observation["schemaVersion"], 1)
                self.assertEqual(observation["tool"], tool)
                self.assertEqual(observation["implementation"], sys.implementation.name)
                self.assertEqual(observation["version"], platform.python_version())
                self.assertEqual(observation["architecture"], platform.machine())
                try:
                    expected = {"pip": version("pip")}
                except PackageNotFoundError:
                    expected = {}
                self.assertEqual(observation["packages"], expected)
                self.assertNotIn(str(root).encode(), retained)
                self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

                subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=30, check=True)
                self.assertEqual(destination.read_bytes(), retained)
