"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_safety_support import *  # noqa: F403


class NotebookSafetyRegressionTest(unittest.TestCase):
    def test_absolute_path_escape_is_blocked_before_execution(self) -> None:
        try:
            import nbformat
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_dir = root / "source"
            source_dir.mkdir()
            source = source_dir / "unsafe.ipynb"
            escaped = source_dir / "side_effect.txt"
            summary = root / "summary.json"
            notebook = nbformat.v4.new_notebook(
                cells=[
                    nbformat.v4.new_code_cell(
                        f"from pathlib import Path\nPath({str(escaped)!r}).write_text('escaped', encoding='utf-8')"
                    )
                ]
            )
            nbformat.write(notebook, source)
            before = hash_tree(source_dir)

            completed = run_script(
                "notebook_workbench.py",
                "execute-copy",
                source,
                "--output-dir",
                root / "run",
                "--trust-notebook-code",
                "--summary-json",
                summary,
                "--timeout-sec",
                60,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(hash_tree(source_dir), before)
            self.assertFalse(escaped.exists())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertFalse(payload["original_modified"])
            self.assertNotIn('"app_status": "PASS"', completed.stdout)

    def test_appended_code_cannot_bypass_absolute_path_guard(self) -> None:
        try:
            import nbformat
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "safe.ipynb"
            escaped = root / "outside" / "side_effect.txt"
            summary = root / "summary.json"
            nbformat.write(nbformat.v4.new_notebook(cells=[]), source)
            before = sha256(source)
            completed = run_script(
                "notebook_workbench.py",
                "execute-copy",
                source,
                "--output-dir",
                root / "run",
                "--trust-notebook-code",
                "--append-code",
                (
                    "from pathlib import Path\n"
                    f"Path({str(escaped)!r}).parent.mkdir(parents=True, exist_ok=True)\n"
                    f"Path({str(escaped)!r}).write_text('escaped')"
                ),
                "--summary-json",
                summary,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(sha256(source), before)
            self.assertFalse(escaped.exists())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")

    def test_notebook_execution_requires_explicit_code_trust(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.ipynb"
            source.write_text(
                json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
                encoding="utf-8",
            )
            before = sha256(source)
            completed = run_script(
                "notebook_workbench.py",
                "execute-copy",
                source,
                "--output-dir",
                root / "run",
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertEqual(sha256(source), before)
            self.assertFalse((root / "run").exists())
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["results"]["error_type"], "untrusted_notebook_code")
            self.assertEqual(payload["artifacts"], {})


if __name__ == "__main__":
    unittest.main()
