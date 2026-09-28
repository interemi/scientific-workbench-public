"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_collision_support import *  # noqa: F403


class DocumentOutputCollisionMatrixTest(DocumentCollisionAssertions, unittest.TestCase):
    def test_document_intake_hardlink_summary_is_stdout_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.md"
            source.write_text("source", encoding="utf-8")
            summary = root / "summary.json"
            os.link(source, summary)
            before = sha256(source)
            completed = run_script(
                "document_intake_workbench.py",
                source,
                "--output-dir",
                root / "out",
                "--summary-json",
                summary,
            )
            self.assert_blocked_unchanged(completed, {source: before})
            self.assertFalse((root / "out").exists())

    def test_helper_detects_external_hardlink_to_directory_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_dir = root / "source"
            source_dir.mkdir()
            member = source_dir / "member.txt"
            member.write_text("preserve", encoding="utf-8")
            external = root / "external.txt"
            os.link(member, external)
            self.assertTrue(output_overlaps_input(external, source_dir))

    def test_distinct_writeup_outputs_preserve_success_and_error_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "draft.md"
            source.write_text(
                "# Methods\n"
                "We describe the data selection, calibration, assumptions, units, and uncertainty "
                "model in a reproducible methodology. "
                "The measurements were inspected before transformation and every selection criterion was recorded.\n\n"
                "# Results\n"
                "The measured value is 1.0 +/- 0.1 km/s and the repeated observations are "
                "consistent within uncertainty. "
                "A comparison with the reference literature suggests agreement, although the "
                "limited sample remains an important caveat.\n\n"
                "# Discussion\n"
                "The result may support the proposed interpretation, but it does not prove it. "
                "Limitations include sample size and calibration systematics.\n",
                encoding="utf-8",
            )
            before = sha256(source)
            summary = root / "control" / "summary.json"
            report = root / "control" / "report.md"
            completed = run_script(
                "scientific_writeup_review.py",
                source,
                "--summary-json",
                summary,
                "--report-md",
                report,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(sha256(source), before)
            self.assertIn(json.loads(summary.read_text(encoding="utf-8"))["app_status"], {"PASS", "WARNING"})
            self.assertTrue(report.is_file())

            missing_summary = root / "missing-summary.json"
            blocked = run_script(
                "scientific_writeup_review.py",
                root / "missing.md",
                "--summary-json",
                missing_summary,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertEqual(
                json.loads(missing_summary.read_text(encoding="utf-8"))["app_status"], "BLOCKED_CONTROLADO"
            )


if __name__ == "__main__":
    unittest.main()
