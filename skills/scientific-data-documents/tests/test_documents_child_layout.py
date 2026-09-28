"""Fast layout checks for the staged scientific-data-documents child skill."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_SCRIPTS = [
    "document_intake_workbench.py",
    "document_semantics.py",
    "pdf_recover_extract.py",
    "office_roundtrip.py",
    "iwork_workbench.py",
    "iwork_roundtrip.py",
    "presentation_workbench.py",
    "quicklook_bridge.py",
    "keynote_export.py",
    "latex_workbench.py",
    "scientific_writeup_review.py",
    "deliverable_factory.py",
    "semantic_diff.py",
]


class DocumentsChildLayoutTest(unittest.TestCase):
    def test_document_scripts_exist_as_full_bodies(self) -> None:
        for name in DOCUMENT_SCRIPTS:
            script = ROOT / "scripts" / name
            self.assertTrue(script.exists(), name)
            self.assertNotIn("child_skill_dispatch", script.read_text(encoding="utf-8"), name)

    def test_document_references_and_helpers_exist(self) -> None:
        for rel in [
            "scripts/datanalysis_env.py",
            "scripts/_internal/public_contract.py",
            "references/formats-and-handoffs.md",
            "references/latex-overleaf.md",
            "references/scientific-presentation-handoff.md",
        ]:
            self.assertTrue((ROOT / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
