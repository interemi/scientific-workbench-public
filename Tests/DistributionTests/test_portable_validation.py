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
from check_distribution_snapshot import ROOT
from check_core_lock import verify_core_lock
from run_portable_core import main, validate_output, validate_summary
from setup_environment import locked_requirements
import setup_environment


class PortableCoreTests(unittest.TestCase):
    def test_output_preserves_existing_evidence_and_rejects_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "evidence.json"
            original.write_text("keep")
            with self.assertRaises(ValueError):
                validate_output(root)
            with self.assertRaises(ValueError):
                validate_output(root / "new", root)
            link = root / "link"
            link.symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                validate_output(link)
            self.assertEqual(original.read_text(), "keep")

    def test_pass_label_cannot_hide_failure_or_missing_coverage(self):
        valid = {"overall_status": "PASS", "profile": "core", "feature_runs": {"fits": {"returncode": 0}},
                 "public_surface_coverage": {"missing_coverage": [], "tiers_enforced": ["core"]}}
        self.assertEqual(validate_summary(valid), 1)
        for replacement in ({"feature_runs": {}}, {"feature_runs": {"fits": {"returncode": 1}}},
                            {"public_surface_coverage": {}},
                            {"public_surface_coverage": {"missing_coverage": ["fits"], "tiers_enforced": ["core"]}}):
            with self.assertRaises(ValueError):
                validate_summary({**valid, **replacement})

    def test_child_failure_preserves_logs_and_failure_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            with patch("run_portable_core.sys.version_info", (3, 11)), \
                 patch("run_portable_core.verify", return_value=1919), \
                 patch("run_portable_core.subprocess.run", side_effect=subprocess.CalledProcessError(7, "doctor")):
                with self.assertRaises(subprocess.CalledProcessError):
                    main(["--output-dir", str(output)])
            self.assertEqual(json.loads((output / "verification.json").read_text())["status"], "FAIL")
            self.assertTrue((output / "step-1.log").exists())
            self.assertFalse((output / "step-2.log").exists())


class GitHygieneTests(unittest.TestCase):
    def test_ignored_finder_metadata_is_preserved_but_tracked_metadata_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "script").mkdir()
            shutil.copy2(ROOT / "script/check_repo_hygiene.sh", root / "script/check_repo_hygiene.sh")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(".DS_Store\ntmp/\n")
            (root / ".DS_Store").write_bytes(b"synthetic Finder metadata")
            (root / "tmp").mkdir()
            (root / "tmp/local.txt").write_text("preserve")
            command = ["bash", str(root / "script/check_repo_hygiene.sh")]
            self.assertEqual(subprocess.run(command + ["--git-visible"], capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            # This forced add is limited to a disposable synthetic test repository.
            subprocess.run(["git", "-C", str(root), "add", "-f", ".DS_Store"], check=True)
            self.assertNotEqual(subprocess.run(command + ["--git-visible"], capture_output=True).returncode, 0)
            self.assertEqual((root / "tmp/local.txt").read_text(), "preserve")


class SwiftRunnerTests(unittest.TestCase):
    def run_native(self, summary, status):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "script").mkdir()
            (root / "bin").mkdir()
            (root / "Tests/ScientificWorkbenchTests").mkdir(parents=True)
            (root / "Tests/ScientificWorkbenchTests/Example.swift").write_text("@Test func one() {}\n@Test func two() {}\n")
            shutil.copy2(ROOT / "script/run_swift_tests.sh", root / "script/run_swift_tests.sh")
            for name, body in {
                "swift": f'#!/bin/bash\nif [[ "$1" == --version ]]; then echo "Swift fixture"; exit 0; fi\necho "{summary}"\nexit {status}\n',
                "xcode-select": '#!/bin/bash\necho /synthetic/Xcode\n',
                "swiftc": '#!/bin/bash\necho "UNEXPECTED_FALLBACK"; exit 99\n',
            }.items():
                path = root / "bin" / name
                path.write_text(body)
                path.chmod(0o755)
            return subprocess.run(["bash", str(root / "script/run_swift_tests.sh")],
                                  env={**os.environ, "PATH": str(root / "bin") + ":" + os.environ["PATH"]},
                                  text=True, capture_output=True)

    def test_native_success_needs_no_custom_linker(self):
        result = self.run_native("Test run with 2 tests in 1 suite passed", 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(SwiftPM)", result.stdout)
        self.assertNotIn("UNEXPECTED_FALLBACK", result.stdout)

    def test_native_failure_is_not_retried_or_hidden(self):
        result = self.run_native("Test run with 2 tests in 1 suite failed", 7)
        self.assertEqual(result.returncode, 7)
        self.assertNotIn("fallback", result.stdout)

    def test_partial_native_discovery_is_rejected(self):
        result = self.run_native("Test run with 1 test in 1 suite passed", 0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected at least 2", result.stderr)

    def test_native_summary_without_suites_is_recognized(self):
        result = self.run_native("Test run with 2 tests passed", 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(SwiftPM)", result.stdout)


class CoreLockTests(unittest.TestCase):
    def test_locked_install_checks_hashes_and_dependency_consistency(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "datanalysis"
            version_and_platform = ["[3,11,15]", '{"system":"Darwin","machine":"arm64","macos":"15.0"}']
            with patch("setup_environment.shutil.which", return_value=sys.executable), \
                 patch("setup_environment.subprocess.check_output", side_effect=version_and_platform), \
                 patch("setup_environment.subprocess.run") as run:
                # Fail dependency consistency to ensure no doctor or success follows.
                run.side_effect = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0),
                                   subprocess.CalledProcessError(1, "pip check")]
                with self.assertRaises(subprocess.CalledProcessError):
                    setup_environment.main(["--python", "python3.11", "--destination", str(destination),
                                            "--locked", "--install"])
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("--require-hashes", commands[1])
            self.assertIn("--only-binary=:all:", commands[1])
            self.assertEqual(commands[-1][-2:], ["pip", "check"])
            plan = json.loads((destination / "scientific-workbench-setup/installation-plan.json").read_text())
            self.assertTrue(plan["locked"])
            self.assertFalse((destination / "scientific-workbench-setup/env-doctor.json").exists())

    def test_lock_rejects_unvalidated_platforms_and_profiles(self):
        for profile, runtime in [
            ("full", {"system": "Darwin", "machine": "arm64", "macos": "14.0"}),
            ("core", {"system": "Darwin", "machine": "x86_64", "macos": "15.0"}),
            ("core", {"system": "Linux", "machine": "arm64", "macos": ""}),
            ("core", {"system": "Darwin", "machine": "arm64", "macos": "13.0"}),
        ]:
            with self.subTest(profile=profile, runtime=runtime), self.assertRaises(ValueError):
                locked_requirements(profile, runtime)

    def test_changed_wheel_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("distribution/locks/core-macos-arm64-py311.txt",
                             "distribution/core-wheel-inventory.json",
                             "skills/scientific-data-analysis/requirements-core.txt"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            self.assertEqual(verify_core_lock(root), 32)
            lock = root / "distribution/locks/core-macos-arm64-py311.txt"
            text = lock.read_text()
            lock.write_text(text.replace("--hash=sha256:", "--hash=sha256:0", 1))
            with self.assertRaises(ValueError):
                verify_core_lock(root)

    def test_new_core_requirement_cannot_silently_escape_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("distribution/locks/core-macos-arm64-py311.txt",
                             "distribution/core-wheel-inventory.json",
                             "skills/scientific-data-analysis/requirements-core.txt"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            requirements = root / "skills/scientific-data-analysis/requirements-core.txt"
            requirements.write_text(requirements.read_text() + "unexpected-package\n")
            with self.assertRaises(ValueError):
                verify_core_lock(root)


if __name__ == "__main__":
    unittest.main()
