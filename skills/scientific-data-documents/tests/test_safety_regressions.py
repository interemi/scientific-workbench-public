"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_safety_support import *  # noqa: F403


class DocumentSafetyRegressionTest(unittest.TestCase):
    def test_office_mutations_refuse_same_input_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "original"
            with self.assertRaises(ValueError):
                office_roundtrip.docx_replace_text(target, target, "a", "b")
            with self.assertRaises(ValueError):
                office_roundtrip.pptx_replace_text(target, target, "a", "b")
            with self.assertRaises(ValueError):
                office_roundtrip.xlsx_set_cell(target, target, "Sheet", "A1", "1")

    def test_document_output_inside_input_is_blocked_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            input_dir = Path(raw) / "input"
            input_dir.mkdir()
            (input_dir / "note.txt").write_text("source text", encoding="utf-8")
            output_dir = input_dir / "generated"
            completed = run_script("document_intake_workbench.py", input_dir, "--output-dir", output_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertFalse(output_dir.exists())
            self.assertIn("BLOCKED_CONTROLADO", completed.stdout)

    def test_document_collision_is_stdout_only_even_with_external_control_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "note.txt").write_text("source text", encoding="utf-8")
            before = directory_snapshot(input_dir)
            output_dir = input_dir / "generated"
            summary_json = root / "control" / "summary.json"
            manifest_json = root / "control" / "manifest.json"
            run_dir = root / "run"

            completed = run_script(
                "document_intake_workbench.py",
                input_dir,
                "--output-dir",
                output_dir,
                "--summary-json",
                summary_json,
                "--manifest-json",
                manifest_json,
                "--run-dir",
                run_dir,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(directory_snapshot(input_dir), before)
            self.assertFalse(output_dir.exists())
            stdout_payload = strict_json(completed.stdout)
            self.assertEqual(stdout_payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertFalse(summary_json.exists())
            self.assertFalse(manifest_json.exists())
            self.assertFalse(run_dir.exists())

    def test_single_missing_input_is_controlled_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            completed = run_script(
                "document_intake_workbench.py",
                root / "missing.docx",
                "--output-dir",
                root / "derived",
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertIn("BLOCKED_CONTROLADO", completed.stdout)

    def test_semantic_table_comparison_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            baseline = root / "baseline.csv"
            candidate = root / "candidate.csv"
            baseline.write_text("id,value\n" + "".join(f"{i},same\n" for i in range(30)), encoding="utf-8")
            candidate.write_text(
                "id,value\n" + "".join(f"{i},{'changed' if i == 25 else 'same'}\n" for i in range(30)),
                encoding="utf-8",
            )
            summary = semantic_diff.compare_tables(baseline, candidate)
            self.assertTrue(summary["comparison_complete"])
            self.assertEqual(summary["inspected_rows"], 30)
            self.assertEqual(summary["cell_change_count"], 1)
            self.assertEqual(summary["cell_changes"][0]["row"], 25)

    def test_semantic_diff_writes_and_declares_strict_output_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            baseline = root / "baseline.csv"
            candidate = root / "candidate.csv"
            baseline.write_text("id,value\n1,old\n", encoding="utf-8")
            candidate.write_text("id,value\n1,new\n", encoding="utf-8")
            diff_json = root / "diff.json"
            summary_json = root / "summary.json"
            report_md = root / "diff.md"
            manifest_json = root / "manifest.json"

            completed = run_script(
                "semantic_diff.py",
                baseline,
                candidate,
                "--output-json",
                diff_json,
                "--summary-json",
                summary_json,
                "--output-md",
                report_md,
                "--manifest-json",
                manifest_json,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            diff_payload = strict_json(diff_json.read_text(encoding="utf-8"))
            summary_payload = strict_json(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(diff_payload, summary_payload)
            self.assertEqual(diff_payload["results"]["cell_change_count"], 1)
            self.assertTrue(diff_payload["artifacts"]["diff_json"])
            diff_artifacts = [item for item in diff_payload["typed_artifacts"] if item["label"] == "diff json"]
            self.assertEqual(len(diff_artifacts), 1)
            self.assertEqual(diff_artifacts[0]["artifact_type"], "app_preview")
            self.assertTrue(report_md.is_file())
            strict_json(manifest_json.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
