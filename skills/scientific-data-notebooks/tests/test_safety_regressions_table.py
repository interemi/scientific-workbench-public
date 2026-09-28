"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_safety_support import *  # noqa: F403


class TableSafetyRegressionTest(TableSafetyAssertions, unittest.TestCase):
    def test_profile_refuses_input_output_collision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            table = Path(raw) / "raw.csv"
            table.write_text("x,y\n1,2\n", encoding="utf-8")
            before = sha256(table)
            completed = run_script("profile_table.py", table, "--summary-json", table)
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(sha256(table), before)
            self.assertIn("Refusing to overwrite", completed.stdout + completed.stderr)

    def test_dask_profile_counts_and_sanitizes_infinity(self) -> None:
        try:
            import dask.dataframe as dd
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - optional backend
            self.skipTest(str(exc))
        frame = dd.from_pandas(pd.DataFrame({"value": [1.0, float("inf"), float("nan")]}), npartitions=1)
        summary = profile_table.summarize_dask(frame, head=3, max_columns=5)
        column = summary["column_summaries"][0]
        self.assertEqual(column["infinite_count"], 1)
        self.assertEqual(column["stats"]["min"], 1.0)
        self.assertEqual(column["stats"]["max"], 1.0)
        json.dumps(summary, allow_nan=False)

    def test_cross_domain_output_inside_input_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            input_dir = Path(raw) / "input"
            input_dir.mkdir()
            (input_dir / "table.csv").write_text("x\n1\n", encoding="utf-8")
            output_dir = input_dir / "generated"
            completed = run_script("cross_domain_data_workbench.py", input_dir, "--output-dir", output_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertFalse(output_dir.exists())
            self.assertIn("BLOCKED_CONTROLADO", completed.stdout)

    def test_cross_domain_run_dir_inside_input_is_blocked_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "table.csv").write_text("x\n1\n", encoding="utf-8")
            before = hash_tree(input_dir)
            run_dir = input_dir / "run"
            output_dir = root / "derived"
            completed = run_script(
                "cross_domain_data_workbench.py",
                input_dir,
                "--output-dir",
                output_dir,
                "--run-dir",
                run_dir,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(hash_tree(input_dir), before)
            self.assertFalse(run_dir.exists())
            self.assertFalse(output_dir.exists())
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertIn("--run-dir", payload["blocked_reason"])

    def test_cross_domain_summary_cannot_replace_input_file(self) -> None:
        self.assert_cross_domain_metadata_output_cannot_replace_input("--summary-json")

    def test_cross_domain_manifest_cannot_replace_input_file(self) -> None:
        self.assert_cross_domain_metadata_output_cannot_replace_input("--manifest-json")

    def test_cross_domain_rejects_reusing_owned_run_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "table.csv").write_text("x\n1\n2\n", encoding="utf-8")
            run_dir = root / "run"
            first = run_script("cross_domain_data_workbench.py", input_dir, "--run-dir", run_dir)
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            user_note = run_dir / "user-note.txt"
            user_note.write_text("preserve", encoding="utf-8")
            before = hash_tree(run_dir)

            second = run_script("cross_domain_data_workbench.py", input_dir, "--run-dir", run_dir)

            self.assertEqual(second.returncode, 2, second.stderr or second.stdout)
            self.assertEqual(hash_tree(run_dir), before)
            self.assertEqual(user_note.read_text(encoding="utf-8"), "preserve")
            payload = json.loads(second.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertIn("already contains owned artifacts", payload["blocked_reason"])


if __name__ == "__main__":
    unittest.main()
