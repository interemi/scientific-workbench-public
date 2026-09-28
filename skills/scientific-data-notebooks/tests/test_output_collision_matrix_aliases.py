"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_collision_support import *  # noqa: F403


class NotebookOutputCollisionMatrixTest(NotebookCollisionAssertions, unittest.TestCase):
    def test_output_directory_hardlink_member_cannot_alias_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            notebook = root / "source.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            run = root / "run"
            run.mkdir()
            executed = run / notebook.name
            os.link(notebook, executed)
            before = sha256(notebook)
            completed = run_script(
                "notebook_workbench.py",
                "execute-copy",
                notebook,
                "--output-dir",
                run,
            )
            self.assert_blocked_unchanged(completed, {notebook: before})

    def test_bootstrap_distinct_outputs_preserve_success_and_error_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "data.csv"
            data.write_text("x\n1\n", encoding="utf-8")
            before = sha256(data)
            notebook = root / "run" / "analysis.ipynb"
            summary = root / "run" / "summary.json"
            manifest = root / "run" / "manifest.json"
            completed = run_script(
                "bootstrap_analysis_notebook.py",
                notebook,
                "--data-path",
                data,
                "--summary-json",
                summary,
                "--manifest-json",
                manifest,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(sha256(data), before)
            self.assertTrue(notebook.is_file())
            self.assertIn(json.loads(summary.read_text(encoding="utf-8"))["app_status"], {"PASS", "WARNING"})
            json.loads(manifest.read_text(encoding="utf-8"))

            bad_summary = root / "bad-summary.json"
            blocked = run_script(
                "bootstrap_analysis_notebook.py",
                root / "not-a-notebook.txt",
                "--data-path",
                data,
                "--summary-json",
                bad_summary,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertEqual(sha256(data), before)
            self.assertIn(
                json.loads(bad_summary.read_text(encoding="utf-8"))["app_status"], {"BLOCKED_CONTROLADO", "FAIL"}
            )


if __name__ == "__main__":
    unittest.main()
