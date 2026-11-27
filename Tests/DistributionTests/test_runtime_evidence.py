from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import shlex
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
                    "PYTHONPATH": str(WRAPPER.parent),
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
                self.assertRegex(observation["inventorySHA256"], r"^[0-9a-f]{64}$")
                probe = subprocess.run(
                    [sys.executable, "-B", str(WRAPPER), "python", "-B", "-c",
                     "from _internal.fixture_script_dispatch import runtime_inventory_sha256; "
                     "print(runtime_inventory_sha256())"],
                    cwd=root, env={key: value for key, value in environment.items() if key != EVIDENCE_KEY},
                    capture_output=True, text=True, timeout=30, check=True,
                )
                self.assertEqual(observation["inventorySHA256"], probe.stdout.strip())
                self.assertNotIn(str(root).encode(), retained)
                self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

                subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=30, check=True)
                self.assertEqual(destination.read_bytes(), retained)

    def test_stilts_manifest_hashes_final_summary_alongside_products(self):
        stilts = ROOT / "skills/scientific-data-astro/scripts/stilts_workbench.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "input.csv"
            source.write_bytes(b"id,ra,dec\n1,10,20\n")
            original = source.read_bytes()
            backend = root / "fake_stilts.py"
            backend.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "output = next(arg[4:] for arg in sys.argv[1:] if arg.startswith('out='))\n"
                "Path(output).write_bytes(Path('input.csv').read_bytes())\n",
                encoding="utf-8",
            )
            command = [
                sys.executable, "-B", str(stilts), "convert", "input.csv", "output.csv",
                "--stilts-command", shlex.join([sys.executable, str(backend)]),
                "--summary-json", "summary.json", "--log-dir", "logs", "--manifest-json",
            ]
            result = subprocess.run([*command, "manifest.json"], cwd=root, capture_output=True, timeout=30, check=True)
            summary = (root / "summary.json").read_bytes()
            self.assertEqual(result.stdout, summary)
            self.assertEqual(json.loads(summary)["app_status"], "PASS")
            manifest = json.loads((root / "manifest.json").read_bytes())
            output_paths = [
                root / path for path in (
                    "output.csv", "summary.json", "logs/stilts_command.sh", "logs/stilts_stdout.txt", "logs/stilts_stderr.txt",
                )
            ]
            for record, path in zip(manifest["inputs"] + manifest["outputs"], [source, *output_paths], strict=True):
                self.assertTrue(record["exists"])
                self.assertEqual(record["sha256"], sha256(path.read_bytes()).hexdigest())
                self.assertEqual(record["size_bytes"], path.stat().st_size)
            alias = subprocess.run([*command, "./summary.json"], cwd=root, capture_output=True, timeout=30)
            self.assertEqual(alias.returncode, 2)
            self.assertEqual(json.loads(alias.stdout)["results"]["path_collisions"][0]["collision_kind"],
                             "output_output_alias")
            self.assertEqual((root / "summary.json").read_bytes(), summary)
            self.assertEqual(source.read_bytes(), original)
