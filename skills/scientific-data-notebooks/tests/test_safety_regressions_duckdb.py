"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_safety_support import *  # noqa: F403


class TableSafetyRegressionTest(TableSafetyAssertions, unittest.TestCase):
    def test_duckdb_all_output_flags_cannot_replace_any_input(self) -> None:
        for option in ("--output", "--summary-json", "--manifest-json"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                first = root / "first.csv"
                second = root / "second.csv"
                first.write_text("id,value\n1,10\n", encoding="utf-8")
                second.write_text("id,value\n2,20\n", encoding="utf-8")
                output_alias = root / f"{option.removeprefix('--')}.json"
                output_alias.symlink_to(second)
                before = {first.name: sha256(first), second.name: sha256(second)}

                completed = run_script(
                    "duckdb_workbench.py",
                    first,
                    second,
                    option,
                    output_alias,
                )

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(
                    {first.name: sha256(first), second.name: sha256(second)},
                    before,
                )
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                self.assertNotIn("Saved", completed.stdout)
                self.assertTrue(output_alias.is_symlink())
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                self.assertIn(option, payload["blocked_reason"])
                self.assertEqual(payload["artifacts"], {})

    def test_duckdb_does_not_ignore_malformed_rows(self) -> None:
        try:
            import duckdb
            import duckdb_workbench
        except ImportError as exc:  # pragma: no cover - optional backend
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as raw:
            table = Path(raw) / "malformed.csv"
            table.write_text('a,b\n1,2\n3,"unterminated\n4,5\n', encoding="utf-8")
            connection = duckdb.connect(database=":memory:")
            try:
                with self.assertRaises(Exception):
                    duckdb_workbench.register_source(connection, table, "source0")
            finally:
                connection.close()

    def test_duckdb_json_output_has_typed_artifact(self) -> None:
        try:
            import duckdb  # noqa: F401
            import pandas  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional backend
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            table = root / "table.csv"
            table.write_text("id,value\n1,3\n2,4\n", encoding="utf-8")
            output = root / "query.json"
            summary = root / "summary.json"
            completed = run_script(
                "duckdb_workbench.py",
                table,
                "--sql",
                "SELECT * FROM source0 ORDER BY id",
                "--output",
                output,
                "--summary-json",
                summary,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            json.loads(output.read_text(encoding="utf-8"))
            payload = json.loads(summary.read_text(encoding="utf-8"))
            output_artifacts = [
                item for item in payload["typed_artifacts"] if Path(item["path"]).resolve() == output.resolve()
            ]
            self.assertEqual(len(output_artifacts), 1)
            self.assertEqual(output_artifacts[0]["artifact_type"], "metadata_json")
            self.assertNotIn("unknown", payload["app_hints"]["preview_artifact_types"])

    def test_failure_bundle_always_has_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            layout = ensure_run_bundle(Path(raw) / "run")
            payload = {"app_status": "BLOCKED_CONTROLADO", "artifacts": {}, "qa": {"status": "blocked"}}
            finalize_existing_run_bundle(layout, payload, returncode=2)
            self.assertTrue(layout.manifest_json.is_file())
            json.loads(layout.manifest_json.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
