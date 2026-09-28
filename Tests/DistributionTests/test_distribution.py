import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from check_distribution_snapshot import ROOT, ROOTS, verify
from setup_environment import installation_environment, main, validate_destination


class DistributionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="swb-distribution-")
        self.root = Path(self.temporary.name)
        (self.root / "distribution").mkdir()
        self.relative = "scientific-data-analysis/scripts/example.py"
        self.file = self.root / "skills" / self.relative
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b"print('synthetic')\n")
        self.manifest = {"schema_version": 1, "roots": sorted(ROOTS), "files": {
            self.relative: {"kind": "file", "size": self.file.stat().st_size,
                            "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(),
                            "executable": False}}}
        self.write_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def write_manifest(self):
        (self.root / "distribution/skill-manifest.json").write_text(json.dumps(self.manifest))

    def test_modified_backend_is_rejected(self):
        self.assertEqual(verify(self.root), 1)
        self.file.write_bytes(b"changed after review\n")
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_external_symlink_is_rejected_even_if_declared(self):
        outside = self.root / "outside.txt"
        outside.write_text("protected original")
        link = self.file.parent / "escape"
        link.symlink_to("../../../outside.txt")
        relative = link.relative_to(self.root / "skills").as_posix()
        self.manifest["files"][relative] = {"kind": "symlink", "target": "../../../outside.txt"}
        self.write_manifest()
        with self.assertRaises(ValueError):
            verify(self.root)
        self.assertEqual(outside.read_text(), "protected original")

    def test_unreviewed_file_is_rejected(self):
        (self.file.parent / "extra.py").write_text("unreviewed")
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_existing_environment_is_preserved(self):
        destination = self.root / "existing/datanalysis"
        destination.mkdir(parents=True)
        sentinel = destination / "original.txt"
        sentinel.write_text("keep this environment")
        with self.assertRaises(ValueError):
            validate_destination(destination, self.root / "checkout")
        self.assertEqual(sentinel.read_text(), "keep this environment")

    def test_dangling_destination_symlink_is_rejected(self):
        destination = self.root / "datanalysis"
        destination.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            validate_destination(destination, self.root / "checkout")
        self.assertTrue(destination.is_symlink())
        self.assertFalse((self.root / "missing").exists())

    def test_environment_inside_source_is_rejected_without_writes(self):
        destination = self.root / "env/datanalysis"
        with self.assertRaises(ValueError):
            validate_destination(destination, self.root)
        self.assertFalse(destination.parent.exists())

    def test_host_pip_redirections_cannot_reach_installation(self):
        host = {"PATH": "/usr/bin", "PIP_TARGET": "/protected", "PIP_PREFIX": "/protected",
                "PIP_USER": "1", "PIP_CONFIG_FILE": "/host/pip.conf", "PYTHONPATH": "/host/code"}
        clean = installation_environment(host)
        for key in ("PIP_TARGET", "PIP_PREFIX", "PIP_USER", "PYTHONPATH"):
            self.assertNotIn(key, clean)
        self.assertEqual(clean["PIP_CONFIG_FILE"], os.devnull)
        self.assertEqual(clean["PIP_REQUIRE_VIRTUALENV"], "1")
        self.assertEqual(host["PIP_TARGET"], "/protected")

    def test_missing_core_stops_setup_before_success(self):
        destination = self.root / "new/datanalysis"
        commands = []

        def simulate(command, **kwargs):
            commands.append(command)
            if any(str(arg).endswith("env_doctor.py") for arg in command):
                self.assertIn("--strict-core", command)
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        output = io.StringIO()
        with patch("setup_environment.verify"), patch("setup_environment.shutil.which", return_value=sys.executable), \
             patch("setup_environment.subprocess.check_output", side_effect=["[3,11,15]", "numpy==1.0\n"]), \
             patch("setup_environment.subprocess.run", side_effect=simulate), contextlib.redirect_stdout(output):
            with self.assertRaises(subprocess.CalledProcessError):
                main(["--python", "python3.11", "--destination", str(destination), "--install"])
        self.assertNotIn("Settings >", output.getvalue())
        self.assertTrue(destination.exists())
        self.assertFalse(any(any(str(arg).endswith("datanalysis_env.py") for arg in command) for command in commands))

    def test_hygiene_rejects_manifest_without_backend_directory(self):
        checkout = self.root / "broken-checkout"
        (checkout / "script").mkdir(parents=True)
        (checkout / "distribution").mkdir()
        for name in ("check_repo_hygiene.sh", "check_distribution_snapshot.py"):
            shutil.copy2(ROOT / "script" / name, checkout / "script" / name)
        (checkout / "distribution/skill-manifest.json").write_text(json.dumps(self.manifest))
        result = subprocess.run(["bash", str(checkout / "script/check_repo_hygiene.sh")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot failed verification", result.stderr)


if __name__ == "__main__":
    unittest.main()
