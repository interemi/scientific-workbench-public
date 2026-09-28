"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_safety_support import *  # noqa: F403
import latex_workbench
from _internal import runtime_common


class DocumentSafetyRegressionTest(unittest.TestCase):
    def test_latex_compile_detects_pdflatex_without_latexmk_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            project = root / "project"
            project.mkdir()
            (project / "main.tex").write_text(
                "\\documentclass{article}\\begin{document}x\\end{document}",
                encoding="utf-8",
            )
            before = directory_snapshot(project)
            output = root / "output"
            workdir = root / "work"
            workdir.mkdir()
            args = latex_workbench.build_parser().parse_args(
                ["compile", str(project), "--output-dir", str(output)]
            )
            self.assertIsNone(args.latexmk_path)
            commands = []

            def find_engine(candidates):
                if candidates == ["latexmk"]:
                    return None
                self.assertEqual(candidates, ["pdflatex", "/Library/TeX/texbin/pdflatex"])
                return "pdflatex"

            def compile_copy(command, cwd=None):
                commands.append((command, Path(cwd)))
                (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4\nsynthetic test\n")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.object(latex_workbench.tempfile, "mkdtemp", return_value=str(workdir)),
                patch.object(runtime_common, "find_executable", side_effect=find_engine),
                patch.object(runtime_common, "run_command", side_effect=compile_copy),
                redirect_stdout(io.StringIO()),
            ):
                args.func(args)

            self.assertTrue((output / "main.pdf").is_file())
            self.assertEqual(directory_snapshot(project), before)
            self.assertEqual(len(commands), 2)
            self.assertTrue(all(command[0] == "pdflatex" for command, _ in commands))
            self.assertTrue(all(cwd == workdir / "project" for _, cwd in commands))

    def test_latex_review_outputs_are_external_and_sources_remain_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            project = root / "project"
            project.mkdir()
            (project / "main.tex").write_text(
                "\\documentclass{article}\n\\begin{document}\n\\input{section}\n\\end{document}\n",
                encoding="utf-8",
            )
            (project / "section.tex").write_text("Result text.\n", encoding="utf-8")
            before = directory_snapshot(project)
            control = root / "control"
            report = control / "review.md"
            summary = control / "summary.json"
            manifest = control / "manifest.json"

            completed = run_script(
                "latex_workbench.py",
                "review",
                project,
                "--report-md",
                report,
                "--summary-json",
                summary,
                "--manifest-json",
                manifest,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(directory_snapshot(project), before)
            self.assertTrue(report.is_file())
            strict_json(summary.read_text(encoding="utf-8"))
            strict_json(manifest.read_text(encoding="utf-8"))

    def test_latex_review_output_source_collisions_are_stdout_only(self) -> None:
        for flag in ("--report-md", "--summary-json", "--manifest-json"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                project = root / "project"
                project.mkdir()
                (project / "main.tex").write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\input{section}\n\\end{document}\n",
                    encoding="utf-8",
                )
                source = project / "section.tex"
                source.write_text("Source section.\n", encoding="utf-8")
                before = directory_snapshot(project)

                completed = run_script("latex_workbench.py", "review", project, flag, source)

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(directory_snapshot(project), before)
                self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_latex_review_failure_cannot_write_summary_over_source_without_main(self) -> None:
        for flag in ("--report-md", "--summary-json", "--manifest-json"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as raw:
                project = Path(raw) / "project"
                project.mkdir()
                source = project / "section.tex"
                source.write_text("Source without a document class.\n", encoding="utf-8")
                before = directory_snapshot(project)

                completed = run_script(
                    "latex_workbench.py",
                    "review",
                    project,
                    flag,
                    source,
                )

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(directory_snapshot(project), before)
                self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_latex_compile_rejects_output_tree_inside_source_project(self) -> None:
        for output_mode in ("equal", "inside"):
            with self.subTest(output_mode=output_mode), tempfile.TemporaryDirectory() as raw:
                project = Path(raw) / "project"
                project.mkdir()
                (project / "main.tex").write_text(
                    "\\documentclass{article}\\begin{document}x\\end{document}",
                    encoding="utf-8",
                )
                before = directory_snapshot(project)
                output = project if output_mode == "equal" else project / "build"

                completed = run_script("latex_workbench.py", "compile", project, "--output-dir", output)

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(directory_snapshot(project), before)
                if output_mode == "inside":
                    self.assertFalse(output.exists())
                self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_latex_compile_manifest_cannot_overlap_project_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            project = root / "project"
            project.mkdir()
            (project / "main.tex").write_text(
                "\\documentclass{article}\\begin{document}x\\end{document}",
                encoding="utf-8",
            )
            bibliography = project / "references.bib"
            bibliography.write_text("@misc{x, title={X}}\n", encoding="utf-8")
            before = directory_snapshot(project)
            output = root / "output"

            completed = run_script(
                "latex_workbench.py",
                "compile",
                project,
                "--output-dir",
                output,
                "--manifest-json",
                bibliography,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertEqual(directory_snapshot(project), before)
            self.assertFalse(output.exists())
            self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_latex_scaffold_auxiliary_collision_blocks_before_target_exists(self) -> None:
        for flag in ("--summary-json", "--manifest-json"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as raw:
                target = Path(raw) / "new-project"
                colliding = target / "main.tex"

                completed = run_script("latex_workbench.py", "scaffold", target, flag, colliding)

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(completed.stderr, "")
                self.assertFalse(target.exists())
                self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_latex_scaffold_supports_external_summary_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "new-project"
            summary = root / "control" / "summary.json"
            manifest = root / "control" / "manifest.json"

            completed = run_script(
                "latex_workbench.py",
                "scaffold",
                target,
                "--summary-json",
                summary,
                "--manifest-json",
                manifest,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertTrue((target / "main.tex").is_file())
            strict_json(summary.read_text(encoding="utf-8"))
            strict_json(manifest.read_text(encoding="utf-8"))

    def test_latex_compile_collision_is_controlled_and_preserves_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            project = root / "project"
            output = root / "output"
            project.mkdir()
            output.mkdir()
            (project / "main.tex").write_text(
                "\\documentclass{article}\\begin{document}x\\end{document}",
                encoding="utf-8",
            )
            pdf = output / "main.pdf"
            pdf.write_bytes(b"existing-pdf")
            before = sha256(pdf)
            completed = run_script("latex_workbench.py", "compile", project, "--output-dir", output)
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(sha256(pdf), before)
            self.assertIn("BLOCKED_CONTROLADO", completed.stdout)


if __name__ == "__main__":
    unittest.main()
