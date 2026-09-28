import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from check_core_lock import ROOT
from check_full_lock import FULL_BUILD_LOCK, FULL_RUNTIME_LOCK, verify_full_lock
import setup_environment


class FullLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in [FULL_BUILD_LOCK, FULL_RUNTIME_LOCK, Path("distribution/full-package-inventory.json"),
                         Path("skills/scientific-data-analysis/requirements-core.txt"),
                         Path("skills/scientific-data-analysis/requirements-full.txt")]:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        self.inventory = self.root / "distribution/full-package-inventory.json"

    def tearDown(self):
        self.temporary.cleanup()

    def test_full_lock_checks_runtime_and_build_dependencies(self):
        self.assertEqual(verify_full_lock(self.root), {"runtime_packages": 200, "build_packages": 3})
        path = self.root / FULL_BUILD_LOCK
        path.write_text(path.read_text().replace("--hash=sha256:", "--hash=sha256:0", 1))
        with self.assertRaises(ValueError):
            verify_full_lock(self.root)

    def test_extra_source_build_is_rejected_even_with_unchanged_pins(self):
        inventory = json.loads(self.inventory.read_text())
        record = next(r for r in inventory["runtime_packages"] if r["name"] != "pims")
        record.update(kind="sdist", filename="unexpected.tar.gz", url="https://files.pythonhosted.org/unexpected.tar.gz")
        self.inventory.write_text(json.dumps(inventory))
        with self.assertRaisesRegex(ValueError, "only the reviewed PIMS"):
            verify_full_lock(self.root)

    def test_changed_build_policy_is_rejected(self):
        inventory = json.loads(self.inventory.read_text())
        inventory["source_build_policy"]["build_isolation"] = True
        self.inventory.write_text(json.dumps(inventory))
        with self.assertRaisesRegex(ValueError, "source build policy"):
            verify_full_lock(self.root)

    def test_new_direct_dependency_cannot_escape_full_lock(self):
        path = self.root / "skills/scientific-data-analysis/requirements-full.txt"
        path.write_text(path.read_text() + "\nunreviewed-package\n")
        with self.assertRaisesRegex(ValueError, "requirements-full.txt changed"):
            verify_full_lock(self.root)

    def test_duplicate_runtime_pin_is_rejected(self):
        path = self.root / FULL_RUNTIME_LOCK
        path.write_text(path.read_text() + path.read_text().splitlines()[1] + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate lock"):
            verify_full_lock(self.root)

    def test_build_failure_stops_before_runtime_and_preserves_plan(self):
        destination = self.root / "new/datanalysis"
        with patch("setup_environment.shutil.which", return_value=sys.executable), \
             patch("setup_environment.subprocess.check_output", side_effect=["[3,11,15]", '{"system":"Darwin","machine":"arm64","macos":"15.0"}']), \
             patch("setup_environment.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0), subprocess.CalledProcessError(8, "build-tools")]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                setup_environment.main(["--python", "python3.11", "--profile", "full", "--locked", "--install", "--destination", str(destination)])
        self.assertEqual(run.call_count, 2)
        plan = json.loads((destination / "scientific-workbench-setup/installation-plan.json").read_text())
        self.assertEqual(len(plan["commands"]), 3)
        build, runtime = plan["commands"][1:]
        self.assertIn("--force-reinstall", build)
        self.assertIn("--require-hashes", build)
        for option in ("--require-hashes", "--only-binary=:all:", "--no-binary=pims", "--no-build-isolation", "--no-cache-dir"):
            self.assertIn(option, runtime)
        self.assertNotIn("--use-pep517", runtime)
        self.assertEqual(len(plan["build_requirements_sha256"]), 64)
        self.assertFalse((destination / "scientific-workbench-setup/env-doctor.json").exists())


if __name__ == "__main__":
    unittest.main()
