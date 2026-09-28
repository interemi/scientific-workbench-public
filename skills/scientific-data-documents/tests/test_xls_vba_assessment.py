"""Legacy XLS inspection must not silently claim that VBA is absent."""

from __future__ import annotations

import builtins
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import document_semantics  # noqa: E402


class LegacyXlsAssessmentTests(unittest.TestCase):
    def test_xls_stream_inspection_reports_vba_unknown_without_oletools(self) -> None:
        class FakeOleFile:
            closed = False

            def listdir(self):
                return [["Workbook"], ["VBA", "Module1"]]

            def get_metadata(self):
                return SimpleNamespace(
                    title="Synthetic workbook", author="Test", last_saved_by=None,
                    create_time=None,
                )

            def close(self):
                self.closed = True

        fake_ole = FakeOleFile()
        fake_module = ModuleType("olefile")
        fake_module.OleFileIO = lambda _path: fake_ole
        real_import = builtins.__import__
        imported_oletools = []

        def guarded_import(name, *args, **kwargs):
            if name.startswith("oletools"):
                imported_oletools.append(name)
                raise AssertionError("oletools must not be imported for XLS inspection")
            return real_import(name, *args, **kwargs)

        with patch.dict(sys.modules, {"olefile": fake_module}), \
                patch.object(document_semantics, "shutil_which", return_value=None), \
                patch("builtins.__import__", side_effect=guarded_import):
            summary = document_semantics.extract_xls(Path("synthetic.xls"), 200)

        self.assertEqual(summary["method"], "olefile")
        self.assertEqual(summary["streams"], ["Workbook", "VBA/Module1"])
        self.assertEqual(summary["vba_assessment"], "not_assessed")
        self.assertNotIn("has_vba", summary)
        self.assertEqual(imported_oletools, [])
        self.assertTrue(fake_ole.closed)


if __name__ == "__main__":
    unittest.main()
