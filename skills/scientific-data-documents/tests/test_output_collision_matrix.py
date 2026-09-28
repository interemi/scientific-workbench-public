"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_collision_support import *  # noqa: F403


class DocumentOutputCollisionMatrixTest(DocumentCollisionAssertions, unittest.TestCase):
    def test_primary_matrix_exact_collisions_precede_success_and_error_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            deck = root / "deck.pptx"
            iwork = root / "draft.pages"
            writeup = root / "draft.tex"
            pdf = root / "scan.pdf"
            baseline = root / "baseline.csv"
            candidate = root / "candidate.csv"
            for path, data in (
                (deck, b"not-a-deck"),
                (iwork, b"not-an-iwork-zip"),
                (writeup, b"Result text."),
                (pdf, b"not-a-pdf"),
                (baseline, b"id,value\n1,old\n"),
                (candidate, b"id,value\n1,new\n"),
            ):
                path.write_bytes(data)
            cases = (
                ("presentation_workbench.py", ("inspect", deck, "--summary-json", deck), (deck,)),
                ("iwork_workbench.py", (iwork, "--output-dir", root / "iwork-out", "--output-json", iwork), (iwork,)),
                (
                    "quicklook_bridge.py",
                    (iwork, "--output", root / "preview.png", "--preflight-only", "--summary-json", iwork),
                    (iwork,),
                ),
                ("scientific_writeup_review.py", (writeup, "--summary-json", writeup), (writeup,)),
                ("document_semantics.py", (iwork, "--output-json", iwork), (iwork,)),
                ("pdf_recover_extract.py", (pdf, "--output-dir", root / "pdf-out", "--summary-json", pdf), (pdf,)),
                ("iwork_roundtrip.py", ("convert", iwork, iwork), (iwork,)),
                ("office_roundtrip.py", ("docx-export-text", deck, deck), (deck,)),
                ("semantic_diff.py", (baseline, candidate, "--output-json", baseline), (baseline, candidate)),
            )
            for script, arguments, protected in cases:
                with self.subTest(script=script):
                    sources = {path: sha256(path) for path in protected}
                    self.assert_blocked_unchanged(run_script(script, *arguments), sources)

    def test_summary_alias_variants_are_blocked_before_quicklook_preflight(self) -> None:
        for kind in ("exact", "symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source = root / "source.pages"
                source.write_bytes(b"source-package")
                before = sha256(source)
                alias = make_alias(root, source, kind)
                completed = run_script(
                    "quicklook_bridge.py",
                    source,
                    "--output",
                    root / "preview.png",
                    "--preflight-only",
                    "--summary-json",
                    alias,
                )
                self.assert_blocked_unchanged(completed, {source: before})
                if kind != "exact":
                    self.assertTrue(alias.exists() or alias.is_symlink())


if __name__ == "__main__":
    unittest.main()
