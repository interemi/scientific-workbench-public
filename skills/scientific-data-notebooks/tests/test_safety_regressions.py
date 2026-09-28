"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_safety_support import *  # noqa: F403


class NotebookSafetyRegressionTest(unittest.TestCase):
    def test_container_fallback_aliases_are_unambiguous_and_output_safe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("data.txt", "immutable\n")
            before = sha256(source)

            same_output = root / "same-summary.json"
            allowed = run_script(
                "inspect_data_container.py",
                source,
                "--summary-json",
                same_output,
                "--output-json",
                same_output,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr or allowed.stdout)
            self.assertEqual(sha256(source), before)
            self.assertEqual(json.loads(same_output.read_text(encoding="utf-8"))["tool"], "inspect_data_container")

            ambiguous_summary = root / "summary.json"
            ambiguous_output = root / "legacy-output.json"
            blocked = run_script(
                "inspect_data_container.py",
                source,
                "--summary-json",
                ambiguous_summary,
                "--output-json",
                ambiguous_output,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertEqual(sha256(source), before)
            self.assertFalse(ambiguous_summary.exists())
            self.assertFalse(ambiguous_output.exists())
            payload = json.loads(blocked.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(
                payload["results"]["collisions"][0]["collision_kind"],
                "ambiguous_fallback_aliases",
            )

            shared_output = root / "shared-output.json"
            blocked = run_script(
                "inspect_data_container.py",
                source,
                "--summary-json",
                shared_output,
                "--manifest-json",
                shared_output,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertFalse(shared_output.exists())
            self.assertEqual(sha256(source), before)
            payload = json.loads(blocked.stdout)
            self.assertTrue(
                any(item.get("collision_kind") == "output_output_alias" for item in payload["results"]["collisions"])
            )

    def test_external_and_source_cwd_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            output = root / "output"
            external = root / "external"
            source.mkdir()
            external.mkdir()
            notebook = source / "analysis.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            with self.assertRaises(SystemExit):
                notebook_workbench.resolve_execution_context(notebook, output, [], True, None)
            with self.assertRaises(SystemExit):
                notebook_workbench.resolve_execution_context(notebook, output, [], False, str(external))

            safe_subdir = output / "_workspace" / "subdir"
            safe_subdir.mkdir(parents=True)
            mode, effective_cwd, _workspace = notebook_workbench.resolve_execution_context(
                notebook, output, [], False, str(safe_subdir)
            )
            self.assertEqual(mode, "workspace_subdir")
            self.assertEqual(effective_cwd, safe_subdir.resolve())

    def test_input_value_is_not_persisted_or_printed(self) -> None:
        try:
            import nbformat
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(str(exc))
        secret = "TOP_SECRET_NOTEBOOK_VALUE_56"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.ipynb"
            output = root / "run"
            summary = root / "summary.json"
            notebook = nbformat.v4.new_notebook(
                cells=[nbformat.v4.new_code_cell("answer = input('Password: '); print(len(answer))")]
            )
            nbformat.write(notebook, source)
            completed = run_script(
                "notebook_workbench.py",
                "execute-copy",
                source,
                "--output-dir",
                output,
                "--trust-notebook-code",
                "--input-value",
                secret,
                "--summary-json",
                summary,
                "--timeout-sec",
                60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            inspected = completed.stdout + completed.stderr + summary.read_text(encoding="utf-8")
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    inspected += artifact.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(secret, inspected)
            self.assertIn("[value supplied]", inspected)


if __name__ == "__main__":
    unittest.main()
