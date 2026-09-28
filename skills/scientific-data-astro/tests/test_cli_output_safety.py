"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from astro_cli_output_safety_support import *  # noqa: F403


class AstroCliOutputSafetyRegressionTest(AstroCliCollisionAssertions, unittest.TestCase):
    def test_path_helper_detects_symlink_hardlink_and_tree_member_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protected = root / "protected.dat"
            protected.write_text("immutable\n", encoding="utf-8")
            symlink = root / "symlink.dat"
            symlink.symlink_to(protected)
            hardlink = root / "hardlink.dat"
            os.link(protected, hardlink)
            tree = root / "tree"
            tree.mkdir()
            member = tree / "member.dat"
            member.write_text("tree member\n", encoding="utf-8")
            external_hardlink = root / "external-member-alias.dat"
            os.link(member, external_hardlink)

            self.assertTrue(paths_alias(protected, symlink))
            self.assertTrue(paths_alias(protected, hardlink))
            self.assertTrue(output_overlaps_input(external_hardlink, tree))

    def test_disjoint_representative_outputs_remain_allowed_for_every_planner(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "raw"
            outputs = root / "derived"
            tree = inputs / "tree"
            project = inputs / "project"
            for directory in (inputs, outputs, tree, project):
                directory.mkdir(parents=True, exist_ok=True)
            first = inputs / "first.dat"
            second = inputs / "second.dat"
            preferences = inputs / "APT.pref"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            preferences.write_text("preferences\n", encoding="utf-8")

            safe_cases = resolve_cli_case_map(
                load_cli_case_data()["safe_cases"],
                {
                    "first": first,
                    "second": second,
                    "tree": tree,
                    "project": project,
                    "preferences": preferences,
                    "outputs": outputs,
                },
            )

            self.assertEqual(set(safe_cases), set(PLANNERS))
            for script, args in safe_cases.items():
                with self.subTest(script=script):
                    self.assertEqual(find_plan_collisions(PLANNERS[script](args)), [])

            same_alias = str(outputs / "same-summary.json")
            self.assertEqual(
                find_plan_collisions(
                    PLANNERS["photometric_solution.py"](
                        [str(first), "--summary-json", same_alias, "--output-json", same_alias]
                    )
                ),
                [],
            )
            self.assertEqual(
                find_plan_collisions(
                    PLANNERS["photometry_noise_budget.py"](["--summary-json", same_alias, "--output-json", same_alias])
                ),
                [],
            )
            self.assertTrue(
                find_plan_collisions(
                    PLANNERS["photometry_noise_budget.py"](
                        [
                            "--summary-json",
                            str(outputs / "noise-summary.json"),
                            "--output-json",
                            str(outputs / "noise-output.json"),
                        ]
                    )
                )
            )

    def test_destructive_workflow_lifecycle_conflicts_block_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            occupied_output = root / "occupied"
            occupied_output.mkdir()
            sentinel = occupied_output / "keep.txt"
            sentinel.write_text("immutable\n", encoding="utf-8")
            before = tree_snapshot(root)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "astrometry_local_smoke_test.py"),
                    "--output-dir",
                    str(occupied_output),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["artifacts"], {})
            self.assertEqual(tree_snapshot(root), before)

            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            notebook = {
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            (first_dir / "same.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
            (second_dir / "same.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
            runner_output = root / "runner-output"
            before = tree_snapshot(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "teareduce_notebook_runner.py"),
                    str(first_dir / "same.ipynb"),
                    str(second_dir / "same.ipynb"),
                    "--output-dir",
                    str(runner_output),
                    "--trust-notebook-code",
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["artifacts"], {})
            collision_kinds = {item["collision_kind"] for item in payload["results"]["path_collisions"]}
            self.assertIn("duplicate_notebook_output_workspace", collision_kinds)
            self.assertEqual(tree_snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
