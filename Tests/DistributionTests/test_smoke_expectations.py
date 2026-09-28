import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

FIXTURES = Path(__file__).resolve().parents[2] / "skills/scientific-data-maintainer/fixtures"
sys.path.insert(0, str(FIXTURES))
from portable_smoke_test import require_controlled_rejection, require_unchanged
from _internal.public_contract import build_blocked_payload


class SmokeExpectationTests(unittest.TestCase):
    def blocked_payload(self):
        return build_blocked_payload("notebook_workbench", "expected protection", legacy={"original_modified": False})

    def test_expected_rejection_preserves_observed_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary.json"
            summary.write_text(json.dumps(self.blocked_payload()))
            result = require_controlled_rejection({"returncode": 2}, summary, "expected protection")
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["observed_returncode"], 2)
            self.assertEqual(result["expectation"], "controlled_rejection")

    def test_success_unrelated_failure_or_modified_input_cannot_pass_negative_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary.json"
            for exit_code, changes in [(0, {}), (2, {"blocked_reason": "another failure"}),
                                       (2, {"original_modified": True}), (2, {"original_modified": None})]:
                with self.subTest(exit_code=exit_code, changes=changes):
                    summary.write_text(json.dumps({**self.blocked_payload(), **changes}))
                    result = require_controlled_rejection({"returncode": exit_code}, summary, "expected protection")
                    self.assertNotEqual(result["returncode"], 0)

    def test_missing_malformed_or_incomplete_summary_does_not_hide_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "missing.json"
            self.assertEqual(require_controlled_rejection({"returncode": 2}, summary, "protection")["returncode"], 1)
            for content in ["invalid JSON", "{}"]:
                summary.write_text(content)
                self.assertEqual(require_controlled_rejection({"returncode": 2}, summary, "protection")["returncode"], 1)

    def test_input_hash_mismatch_or_missing_file_fails_even_after_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "synthetic.txt"
            original.write_bytes(b"original")
            before = {original: hashlib.sha256(original.read_bytes()).hexdigest()}
            self.assertTrue(require_unchanged({"returncode": 0}, before)["original_hashes_verified"])
            original.write_bytes(b"changed")
            changed = require_unchanged({"returncode": 0}, before)
            self.assertEqual(changed["returncode"], 1)
            self.assertFalse(changed["original_hashes_verified"])
            missing = {Path(temporary) / "missing.txt": before[original]}
            self.assertEqual(require_unchanged({"returncode": 0}, missing)["returncode"], 1)
            self.assertEqual(require_unchanged({"returncode": 7}, before)["returncode"], 7)


if __name__ == "__main__":
    unittest.main()
