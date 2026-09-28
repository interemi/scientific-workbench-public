"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from notebook_collision_support import *  # noqa: F403


class NotebookOutputCollisionMatrixTest(NotebookCollisionAssertions, unittest.TestCase):
    def test_exact_collision_matrix_blocks_before_read_or_import(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            notebook = root / "source.ipynb"
            table = root / "source.csv"
            archive = root / "source.zip"
            notebook.write_text("{}", encoding="utf-8")
            table.write_text("x,y\n1,2\n", encoding="utf-8")
            archive.write_bytes(b"not-a-zip")
            branch_root = root / "branches"
            branch_root.mkdir()
            branch_product = branch_root / "product.txt"
            branch_product.write_text("source", encoding="utf-8")

            cases = (
                (
                    "bootstrap_analysis_notebook.py",
                    (notebook, "--data-path", notebook, "--overwrite"),
                    (notebook,),
                ),
                (
                    "notebook_workbench.py",
                    ("execute-copy", notebook, "--output-dir", root),
                    (notebook,),
                ),
                (
                    "coursework_notebook_fidelity_check.py",
                    (notebook, "--summary-json", notebook),
                    (notebook,),
                ),
                (
                    "notebook_branch_compare.py",
                    (branch_root, "--summary-json", branch_root / "summary.json"),
                    (branch_product,),
                ),
                (
                    "inspect_data_container.py",
                    (archive, "--summary-json", archive),
                    (archive,),
                ),
                (
                    "physical_qa.py",
                    (table, "--summary-json", table),
                    (table,),
                ),
                (
                    "analyze_series.py",
                    (table, "--plot", table),
                    (table,),
                ),
                (
                    "profile_table.py",
                    (table, "--manifest-json", table),
                    (table,),
                ),
                (
                    "cross_domain_data_workbench.py",
                    (table, "--output-dir", root / "cross-out", "--summary-json", table),
                    (table,),
                ),
            )
            for script, arguments, protected in cases:
                with self.subTest(script=script):
                    before = {path: sha256(path) for path in protected}
                    self.assert_blocked_unchanged(run_script(script, *arguments), before)

    def test_notebook_summary_alias_variants_are_blocked(self) -> None:
        for kind in ("exact", "symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                notebook = root / "source.ipynb"
                notebook.write_text("{}", encoding="utf-8")
                before = sha256(notebook)
                alias = make_alias(root, notebook, kind)
                completed = run_script(
                    "notebook_workbench.py",
                    "inspect",
                    notebook,
                    "--summary-json",
                    alias,
                )
                self.assert_blocked_unchanged(completed, {notebook: before})


if __name__ == "__main__":
    unittest.main()
