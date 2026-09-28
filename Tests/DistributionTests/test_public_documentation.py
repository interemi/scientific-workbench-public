import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PublicDocumentationTests(unittest.TestCase):
    def test_plain_text_guidance_is_included_in_strict_language_gate(self):
        with tempfile.TemporaryDirectory(prefix="documentation-audit-test-") as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            scripts = root / "script"
            scripts.mkdir()
            audit = scripts / "audit_public_documentation.py"
            shutil.copy2(ROOT / "script" / audit.name, audit)
            spanish = (
                "Antes de ejecutar, revisa los archivos de datos en la carpeta. "
                "No debes modificar los archivos originales. Para usar la guía, "
                "comprueba que los datos se mantienen en una carpeta separada.\n"
            )
            for name in ("README.txt", "RELEASE-v1.txt", "INSTALL"):
                (root / name).write_text(spanish, encoding="utf-8")
            records = root / "docs" / "skill-records"
            records.mkdir(parents=True)
            (records / "legacy-spectroscopy-README.en.txt").write_text(spanish, encoding="utf-8")
            (root / "spectrum.txt").write_text("5000 1.2\n5001 1.3\n")
            (root / "requirements-core.txt").write_text("example-package==1.0\n")
            (root / "LICENSE.txt").write_text("Original third-party license text.\n")
            inventory = subprocess.run(
                [sys.executable, str(audit)], capture_output=True, text=True,
            )
            self.assertEqual(inventory.returncode, 0, inventory.stderr)
            report = json.loads(inventory.stdout)
            self.assertEqual(report["text_documents"], 4)
            self.assertEqual(
                {item["path"] for item in report["spanish_candidates"]},
                {"README.txt", "RELEASE-v1.txt", "INSTALL",
                 "docs/skill-records/legacy-spectroscopy-README.en.txt"},
            )
            strict = subprocess.run(
                [sys.executable, str(audit), "--require-english"],
                capture_output=True, text=True,
            )
            self.assertEqual(strict.returncode, 1, strict.stderr)
            self.assertIn("4 documents are likely Spanish", strict.stderr)
            self.assertEqual(json.loads(strict.stdout)["unreadable_pdf_groups"], 0)


if __name__ == "__main__":
    unittest.main()
