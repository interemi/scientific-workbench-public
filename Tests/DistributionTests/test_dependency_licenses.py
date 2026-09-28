import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from audit_dependency_licenses import audit, inspect_archive, main


class DependencyNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.archive = self.root / "synthetic-1-py3-none-any.whl"

    def tearDown(self):
        self.temporary.cleanup()

    def wheel(self, members):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def test_nested_license_directory_is_indexed_without_extracting(self):
        digest = self.wheel({"pkg.dist-info/licenses/vendor/terms.txt": b"synthetic notice",
                             "pkg/module.py": b"raise RuntimeError('never execute')"})
        report = inspect_archive(self.archive, digest)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["sha256"], hashlib.sha256(b"synthetic notice").hexdigest())
        self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_modified_archive_is_rejected_before_parsing(self):
        digest = self.wheel({"LICENSE": b"synthetic notice"})
        self.archive.write_bytes(b"not even a zip archive")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            inspect_archive(self.archive, digest)

    def test_unsafe_paths_and_oversized_notices_are_rejected(self):
        digest = self.wheel({"../LICENSE": b"synthetic notice"})
        with self.assertRaisesRegex(ValueError, "unsafe member"):
            inspect_archive(self.archive, digest)
        digest = self.wheel({"LICENSE": b"12345"})
        with patch("audit_dependency_licenses.MAX_NOTICE_BYTES", 4), self.assertRaisesRegex(ValueError, "limit"):
            inspect_archive(self.archive, digest)

    def test_source_archive_symlink_cannot_be_treated_as_notice_text(self):
        source = self.root / "synthetic.tar.gz"
        with tarfile.open(source, "w:gz") as archive:
            member = tarfile.TarInfo("LICENSE")
            member.type = tarfile.SYMTYPE
            member.linkname = "/protected/original"
            archive.addfile(member)
        with self.assertRaisesRegex(ValueError, "link or special"):
            inspect_archive(source, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_missing_archive_is_failure_not_legal_clearance(self):
        records = [{"name": "missing", "filename": "missing.whl", "sha256": "0" * 64}]
        with patch("audit_dependency_licenses.inventory_records", return_value=records):
            result = audit([self.root])
        self.assertEqual(result["technical_status"], "FAIL")
        self.assertFalse(result["license_review_complete"])
        self.assertEqual(len(result["errors"]), 1)

    def test_no_notices_is_reported_without_inventing_a_license(self):
        digest = self.wheel({"pkg/module.py": b"# synthetic"})
        records = [{"name": "synthetic", "filename": self.archive.name, "sha256": digest}]
        with patch("audit_dependency_licenses.inventory_records", return_value=records):
            result = audit([self.root])
        self.assertEqual(result["technical_status"], "PASS")
        self.assertFalse(result["license_review_complete"])
        self.assertEqual(result["without_named_notices"], [self.archive.name])

    def test_existing_report_is_preserved(self):
        report = self.root / "original.json"
        report.write_text("original evidence")
        with self.assertRaisesRegex(ValueError, "new evidence file"):
            main(["--archives-dir", str(self.root), "--output", str(report)])
        self.assertEqual(report.read_text(), "original evidence")


if __name__ == "__main__":
    unittest.main()
