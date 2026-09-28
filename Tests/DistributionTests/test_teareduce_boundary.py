import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEALTHCHECK_FIXTURES = ROOT / "skills/scientific-data-astro/fixtures"


class TeareduceBoundaryTests(unittest.TestCase):
    def test_package_discovery_does_not_execute_teareduce(self):
        with tempfile.TemporaryDirectory(prefix="teareduce-discovery-test-") as temporary:
            package = Path(temporary) / "teareduce"
            package.mkdir()
            (package / "__init__.py").write_text(
                'raise RuntimeError("TEAREDUCE must not be imported by discovery")\n',
                encoding="utf-8",
            )
            code = (
                "import json, sys\n"
                "from types import SimpleNamespace\n"
                "from unittest.mock import patch\n"
                f"sys.path.insert(0, {str(HEALTHCHECK_FIXTURES)!r})\n"
                f"sys.path.insert(0, {temporary!r})\n"
                "import teareduce_healthcheck as healthcheck\n"
                "with patch.object(healthcheck.metadata, 'distribution', "
                "return_value=SimpleNamespace(version='0.7.9')), "
                "patch.object(healthcheck.metadata, 'entry_points', return_value=[]):\n"
                "    print(json.dumps(healthcheck.inspect_teareduce_environment()))\n"
            )
            result = subprocess.run(
                [sys.executable, "-B", "-c", code],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["installed"])
            self.assertEqual(report["version"], "0.7.9")
            self.assertFalse(report["import_verified"])
            self.assertEqual(report["interpreter_scope"], "launcher_python_only")
            self.assertIn("not imported", report["inspection_scope"])


if __name__ == "__main__":
    unittest.main()
