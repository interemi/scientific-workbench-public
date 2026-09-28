import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from audit_publication_history import ROOT, audit, fingerprint, scan_text


class PublicationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="publication-audit-test-")
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        self.temporary.cleanup()

    def commit(self, message):
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Audit Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", message], check=True)

    def test_new_test_files_are_scanned_without_exemptions(self):
        token = "ghp_" + "A" * 36
        (self.root / "Tests").mkdir()
        (self.root / "Tests/new_test.py").write_text(f'token = "{token}"\n')
        result = audit(self.root)
        self.assertIsNone(result["head"])
        self.assertEqual(len(result["potential_secrets"]), 1)
        self.assertEqual(result["potential_secrets"][0]["path"], "Tests/new_test.py")
        self.assertNotIn(token, json.dumps(result))

    def test_unquoted_provider_assignment_is_not_missed(self):
        line = "OPENAI_API_KEY=" + "F" * 24
        pending, _, _ = scan_text(line.encode(), {"script/example.sh"}, "synthetic", set())
        self.assertTrue(any(f["rule"] == "unquoted_provider_assignment" for f in pending))
        self.assertNotIn("F" * 24, json.dumps(pending))

    def test_exact_fixture_exception_cannot_hide_a_changed_key(self):
        line = 'token = "' + "ghp_" + "A" * 36 + '"'
        fixtures = {("Tests/fixture.py", "github_token", fingerprint(line))}
        pending, reviewed, _ = scan_text(line.encode(), {"Tests/fixture.py"}, "synthetic", fixtures)
        self.assertEqual(len(pending), 0)
        self.assertEqual(len(reviewed), 1)
        changed = line.replace("A" * 36, "B" * 36)
        pending, reviewed, _ = scan_text(changed.encode(), {"Tests/fixture.py"}, "synthetic", fixtures)
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(reviewed), 0)
        pending, _, _ = scan_text(line.encode(), {"another.py"}, "synthetic", fixtures)
        self.assertEqual(len(pending), 1)

    def test_removed_secret_remains_visible_in_history(self):
        token = "ghp_" + "C" * 36
        file = self.root / "config.txt"
        file.write_text(token)
        self.commit("Add synthetic audit input")
        file.unlink()
        self.commit("Remove synthetic audit input")
        self.assertEqual(audit(self.root)["potential_secrets"], [])
        result = audit(self.root, history=True)
        self.assertEqual(len(result["commits"]), 2)
        self.assertTrue(any(f["path"] == "config.txt" for f in result["potential_secrets"]))
        self.assertNotIn(token, json.dumps(result))

    def test_commit_messages_are_also_scanned(self):
        (self.root / "source.txt").write_text("synthetic")
        self.commit("Synthetic token " + "ghp_" + "D" * 36)
        result = audit(self.root, history=True)
        self.assertTrue(any(f["path"] == "(commit metadata)" for f in result["potential_secrets"]))

    def test_ignored_files_are_not_read_and_large_candidates_are_reported(self):
        (self.root / ".gitignore").write_text("private-local/\n")
        private = self.root / "private-local"
        private.mkdir()
        (private / "config").write_text("ghp_" + "E" * 36)
        (self.root / "large.txt").write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        result = audit(self.root)
        self.assertEqual(result["potential_secrets"], [])
        self.assertEqual(len(result["oversized_objects"]), 1)

    def test_shallow_history_cannot_claim_complete_review(self):
        (self.root / "source.txt").write_text("synthetic")
        self.commit("Synthetic baseline")
        clone = self.root / "shallow-clone"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.root.as_uri(), str(clone)], check=True)
        with self.assertRaisesRegex(ValueError, "shallow history"):
            audit(clone, history=True)

    def test_forced_tracked_credential_file_is_blocked(self):
        scripts = self.root / "script"
        scripts.mkdir()
        for name in ("check_git_publication_readiness.sh", "check_repo_hygiene.sh", "audit_publication_history.py"):
            shutil.copy2(ROOT / "script" / name, scripts / name)
        (self.root / ".gitignore").write_text(".env\n")
        (self.root / ".env").write_text("synthetic local configuration")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", ".env"], check=True)
        result = subprocess.run(["bash", str(scripts / "check_git_publication_readiness.sh")],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential/signing files", result.stderr)
        self.assertEqual((self.root / ".env").read_text(), "synthetic local configuration")

    def test_dependency_or_model_payload_is_blocked(self):
        scripts = self.root / "script"
        scripts.mkdir()
        for name in ("check_git_publication_readiness.sh", "check_repo_hygiene.sh", "audit_publication_history.py"):
            shutil.copy2(ROOT / "script" / name, scripts / name)
        model = self.root / "synthetic-model.onnx"
        model.write_bytes(b"synthetic model fixture")
        result = subprocess.run(["bash", str(scripts / "check_git_publication_readiness.sh")],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundled dependency, model, environment, or app payloads", result.stderr)
        self.assertEqual(model.read_bytes(), b"synthetic model fixture")


if __name__ == "__main__":
    unittest.main()
