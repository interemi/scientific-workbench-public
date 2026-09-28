"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_safety_support import *  # noqa: F403


class TableSafetyRegressionTest(TableSafetyAssertions, unittest.TestCase):
    def test_timeseries_excludes_infinity_and_preserves_warning_logic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data = Path(raw) / "series.csv"
            rows = ["date,value"]
            for index in range(12):
                value = "inf" if index == 5 else str(index + 1)
                rows.append(f"2025-{index + 1:02d}-01,{value}")
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                data_path=str(data),
                runtime_profile="local",
                date_column="date",
                value_column="value",
                test_horizon=2,
            )
            profile, warnings_found = timeseries_forecasting_workbench.validate_data_path(args)
            self.assertEqual(profile["infinite_value_count"], 1)
            self.assertEqual(profile["valid_row_count"], 11)
            self.assertTrue(any("infinite_values=1" in item for item in warnings_found))
            self.assertNotIn("filterwarnings('ignore')", timeseries_forecasting_workbench.build_setup_cell("local"))
            load_cell = timeseries_forecasting_workbench.build_load_cell()
            self.assertIn("errors='coerce'", load_cell)
            self.assertIn("np.isfinite", load_cell)
            for label, source in {
                "setup": timeseries_forecasting_workbench.build_setup_cell("local"),
                "helpers": timeseries_forecasting_workbench.build_helper_cell(),
                "load": load_cell,
                "final": timeseries_forecasting_workbench.build_final_forecast_cell(),
                "export": timeseries_forecasting_workbench.build_export_cell(),
            }.items():
                compile(source, f"<generated-{label}>", "exec")

    def test_timeseries_created_paths_cannot_replace_data_file(self) -> None:
        cases = (
            ("--output-dir", lambda root, data: ["--output-dir", data]),
            (
                "--summary-json",
                lambda root, data: ["--output-dir", root / "run", "--summary-json", data],
            ),
            (
                "--manifest-json",
                lambda root, data: ["--output-dir", root / "run", "--manifest-json", data],
            ),
            (
                "generated notebook",
                lambda root, data: [
                    "--output-dir",
                    root / "run",
                    "--notebook-name",
                    "../series.csv",
                ],
            ),
        )
        for label, build_arguments in cases:
            with self.subTest(output=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                data = root / "series.csv"
                data.write_text("date,value\n2025-01-01,1\n", encoding="utf-8")
                before = sha256(data)

                completed = run_script(
                    "timeseries_forecasting_workbench.py",
                    "--data-path",
                    data,
                    *build_arguments(root, data),
                )

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(sha256(data), before)
                self.assertFalse((root / "run").exists())
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                self.assertEqual(payload["results"]["error_type"], "output_input_collision")
                self.assertIn("--data-path", payload["blocked_reason"])
                self.assertEqual(payload["artifacts"], {})

    def test_timeseries_rejects_every_output_kind_inside_directory_data_path(self) -> None:
        cases = (
            (
                "--output-dir",
                lambda root, source: ["--output-dir", source / "generated"],
            ),
            (
                "--summary-json",
                lambda root, source: [
                    "--output-dir",
                    root / "run",
                    "--summary-json",
                    source / "summary.json",
                ],
            ),
            (
                "--manifest-json",
                lambda root, source: [
                    "--output-dir",
                    root / "run",
                    "--manifest-json",
                    source / "manifest.json",
                ],
            ),
            (
                "generated notebook",
                lambda root, source: [
                    "--output-dir",
                    root / "run",
                    "--notebook-name",
                    source / "generated.ipynb",
                ],
            ),
        )
        for label, build_arguments in cases:
            with self.subTest(output=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source = root / "source"
                source.mkdir()
                (source / "series.csv").write_text("date,value\n2025-01-01,1\n", encoding="utf-8")
                before = hash_tree(source)

                completed = run_script(
                    "timeseries_forecasting_workbench.py",
                    "--data-path",
                    source,
                    *build_arguments(root, source),
                )

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(hash_tree(source), before)
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                self.assertIn("inside directory --data-path", payload["blocked_reason"])

    def test_timeseries_distinct_outputs_preserve_success_and_error_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "series.csv"
            rows = ["date,value"] + [f"2024-{index + 1:02d}-01,{index + 1}" for index in range(12)]
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")
            before = sha256(data)
            output_dir = root / "successful-run"
            summary = root / "summary.json"
            manifest = root / "manifest.json"

            completed = run_script(
                "timeseries_forecasting_workbench.py",
                "--data-path",
                data,
                "--output-dir",
                output_dir,
                "--summary-json",
                summary,
                "--manifest-json",
                manifest,
                "--test-horizon",
                2,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(sha256(data), before)
            self.assertTrue((output_dir / "timeseries_forecasting_notebook.ipynb").is_file())
            self.assertEqual(json.loads(summary.read_text(encoding="utf-8"))["app_status"], "PASS")
            json.loads(manifest.read_text(encoding="utf-8"))

            error_summary = root / "error-summary.json"
            blocked = run_script(
                "timeseries_forecasting_workbench.py",
                "--data-path",
                data,
                "--output-dir",
                root / "blocked-run",
                "--summary-json",
                error_summary,
                "--test-horizon",
                0,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertEqual(sha256(data), before)
            self.assertFalse((root / "blocked-run").exists())
            self.assertEqual(
                json.loads(error_summary.read_text(encoding="utf-8"))["app_status"],
                "BLOCKED_CONTROLADO",
            )


if __name__ == "__main__":
    unittest.main()
