"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from maintainer_collision_support import *  # noqa: F403


class MaintainerCollisionSafetyTest(unittest.TestCase):
    def test_mother_wrappers_keep_all_five_preflights_fail_closed(self) -> None:
        if not MOTHER_SCRIPTS.is_dir():
            self.skipTest("mother skill root is not available")
        with tempfile.TemporaryDirectory(prefix="maintainer_mother_wrapper_collision_") as raw:
            tmp = Path(raw)
            input_file = tmp / "input.dat"
            input_file.write_text("immutable input\n", encoding="utf-8")
            input_tree = tmp / "input-tree"
            input_tree.mkdir()
            (input_tree / "sentinel.txt").write_text("immutable tree\n", encoding="utf-8")
            file_before = sha256(input_file)
            tree_before = tree_sha256(input_tree)

            commands = [
                (
                    "external_astro_tools_local_validation.py",
                    ["--apt-preferences", str(input_file), "--output-dir", str(input_file)],
                ),
                (
                    "portable_smoke_test.py",
                    ["--examples-dir", str(input_tree), "--output-dir", str(input_tree / "output")],
                ),
                (
                    "validate_skill_samples.py",
                    [str(input_tree), "--output-dir", str(input_tree / "reports"), "--validation-profile", "quick"],
                ),
                (
                    "sync_public_surface_docs.py",
                    ["--check", "--registry", str(input_file), "--summary-json", str(input_file)],
                ),
                (
                    "skill_surface_audit.py",
                    ["--root", str(input_tree), "--summary-json", str(input_tree / "sentinel.txt")],
                ),
            ]
            for name, arguments in commands:
                with self.subTest(script=name):
                    result = run_script(name, *arguments, scripts=MOTHER_SCRIPTS)
                    assert_controlled_block(self, result)
                    self.assertEqual(sha256(input_file), file_before)
                    self.assertEqual(tree_sha256(input_tree), tree_before)

    def test_external_validation_blocks_backend_output_and_hardlink_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="maintainer_external_collision_") as raw:
            tmp = Path(raw)
            preferences = tmp / "APT.pref"
            preferences.write_text("immutable preferences\n", encoding="utf-8")
            before = sha256(preferences)

            exact = run_script(
                "external_astro_tools_local_validation.py",
                "--tool",
                "apt",
                "--apt-preferences",
                str(preferences),
                "--output-dir",
                str(preferences),
            )
            assert_controlled_block(self, exact)
            self.assertEqual(sha256(preferences), before)

            hardlink_summary = tmp / "summary-hardlink.json"
            os.link(preferences, hardlink_summary)
            output_dir = tmp / "safe-output"
            hardlink = run_script(
                "external_astro_tools_local_validation.py",
                "--tool",
                "apt",
                "--apt-preferences",
                str(preferences),
                "--output-dir",
                str(output_dir),
                "--summary-json",
                str(hardlink_summary),
            )
            assert_controlled_block(self, hardlink)
            self.assertFalse(output_dir.exists())
            self.assertEqual(sha256(preferences), before)
            self.assertEqual(sha256(hardlink_summary), before)

    def test_portable_smoke_blocks_all_artifacts_under_examples(self) -> None:
        with tempfile.TemporaryDirectory(prefix="maintainer_portable_collision_") as raw:
            tmp = Path(raw)
            examples = tmp / "examples"
            examples.mkdir()
            sentinel = examples / "sentinel.txt"
            sentinel.write_text("immutable example\n", encoding="utf-8")
            before = tree_sha256(examples)
            nested_output = examples / "smoke-output"

            result = run_script(
                "portable_smoke_test.py",
                "--examples-dir",
                str(examples),
                "--output-dir",
                str(nested_output),
                "--summary-json",
                str(tmp / "safe-summary.json"),
            )
            payload = assert_controlled_block(self, result)
            self.assertIn("path collision", payload["results"]["error"].lower())
            self.assertFalse(nested_output.exists())
            self.assertEqual(tree_sha256(examples), before)

            manifest_alias = tmp / "manifest-hardlink.json"
            os.link(sentinel, manifest_alias)
            result = run_script(
                "portable_smoke_test.py",
                "--examples-dir",
                str(examples),
                "--output-dir",
                str(tmp / "safe-output"),
                "--manifest-json",
                str(manifest_alias),
            )
            assert_controlled_block(self, result)
            self.assertEqual(tree_sha256(examples), before)
            self.assertEqual(sha256(manifest_alias), sha256(sentinel))


if __name__ == "__main__":
    unittest.main()
