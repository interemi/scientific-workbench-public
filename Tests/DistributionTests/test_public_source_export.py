from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from export_public_source import ExportError, export_repository
from check_distribution_snapshot import ROOTS, verify


class PublicSourceExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="public-source-export-test-")
        self.base = Path(self.temporary.name)
        self.repository = self.base / "private"
        self.repository.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        (self.repository / "README.md").write_text("# Synthetic project\n", encoding="utf-8")
        scripts = self.repository / "script"
        scripts.mkdir()
        executable = scripts / "run.sh"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        (self.repository / "README-link.md").symlink_to("README.md")
        subprocess.run(["git", "-C", str(self.repository), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.repository),
                "-c", "user.name=Export Fixture",
                "-c", "user.email=fixture.invalid",
                "commit", "-qm", "Synthetic export baseline",
            ],
            check=True,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def commit_fixture(self, message):
        subprocess.run(["git", "-C", str(self.repository), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(self.repository), "-c", "user.name=Export Fixture",
             "-c", "user.email=fixture.invalid", "commit", "-qm", message],
            check=True,
        )

    def prepare_documentation_fixture(self):
        family = self.repository / "skills"
        for root in ROOTS:
            (family / root).mkdir(parents=True)
        parent = family / "scientific-data-analysis"
        original = parent / "README.txt"
        original.write_text("Guia historica: conserva los datos originales.\n")
        (parent / "guide.txt").symlink_to("README.txt")
        code = parent / "run.py"
        code.write_text("print('synthetic unchanged runtime')\n")
        files = {}
        for path in (original, code):
            files[path.relative_to(family).as_posix()] = {
                "kind": "file", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size, "executable": False,
            }
        files["scientific-data-analysis/guide.txt"] = {"kind": "symlink", "target": "README.txt"}
        distribution = self.repository / "distribution"
        distribution.mkdir()
        (distribution / "skill-manifest.json").write_text(json.dumps({
            "schema_version": 1, "roots": sorted(ROOTS), "files": files,
        }))
        docs = self.repository / "docs"
        docs.mkdir()
        edition = docs / "guide.en.txt"
        edition.write_text("Historical guide: preserve original data.\n")
        mapping = {"schema_version": 1, "replacements": [{
            "path": original.relative_to(self.repository).as_posix(),
            "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "edition": "docs/guide.en.txt",
            "edition_sha256": hashlib.sha256(edition.read_bytes()).hexdigest(),
            "reason": "English edition of a preserved historical guide.",
        }]}
        mapping_path = distribution / "public-documentation-map.json"
        mapping_path.write_text(json.dumps(mapping))
        self.commit_fixture("Add synthetic historical guide and English edition")
        return original, edition, mapping_path

    def test_english_export_preserves_private_sources_and_verifiable_backend(self):
        original, edition, _ = self.prepare_documentation_fixture()
        private_bytes = original.read_bytes()
        manifest_bytes = (self.repository / "distribution/skill-manifest.json").read_bytes()
        selected_commit = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True,
        ).strip()
        original_edition = edition.read_bytes()
        edition.write_text("A later unreviewed edition.\n")
        self.commit_fixture("Change current edition after the selected commit")
        output = self.base / "public"
        report = export_repository(self.repository, output, source_ref=selected_commit)
        public_guide = output / original.relative_to(self.repository)
        self.assertEqual(public_guide.read_bytes(), original_edition)
        self.assertEqual((public_guide.parent / "guide.txt").read_bytes(), original_edition)
        self.assertEqual(original.read_bytes(), private_bytes)
        self.assertEqual((self.repository / "distribution/skill-manifest.json").read_bytes(), manifest_bytes)
        self.assertEqual((public_guide.parent / "run.py").read_bytes(),
                         (original.parent / "run.py").read_bytes())
        self.assertEqual(verify(output), 3)
        self.assertEqual(report["schema_version"], 2)
        derived = json.loads((output / "distribution/skill-manifest.json").read_text())
        self.assertEqual(derived["publication_documentation"]["source_manifest_sha256"],
                         hashlib.sha256(manifest_bytes).hexdigest())
        for record in report["files"]:
            path = output / record["path"]
            if not path.is_symlink():
                self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_stale_edition_hash_stops_before_creating_export(self):
        original, edition, _ = self.prepare_documentation_fixture()
        private_bytes = original.read_bytes()
        edition.write_text("Changed translation without a renewed review.\n")
        self.commit_fixture("Change synthetic edition without mapping update")
        with self.assertRaisesRegex(ExportError, "English edition hash differs"):
            export_repository(self.repository, self.base / "public")
        self.assertFalse((self.base / "public").exists())
        self.assertEqual(original.read_bytes(), private_bytes)

    def test_changed_private_original_cannot_silently_use_an_old_translation(self):
        original, _, _ = self.prepare_documentation_fixture()
        original.write_text("New original evidence requiring translation review.\n")
        self.commit_fixture("Change synthetic original after translation")
        with self.assertRaisesRegex(ExportError, "original documentation hash differs"):
            export_repository(self.repository, self.base / "public")
        self.assertFalse((self.base / "public").exists())

    def test_exclusion_policy_is_read_from_selected_commit(self):
        policy = self.repository / "exclusions.txt"
        policy.write_text("script/\n")
        self.commit_fixture("Record reviewed synthetic exclusion policy")
        selected = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True,
        ).strip()
        policy.write_text("README.md\nREADME-link.md\n")
        self.commit_fixture("Change policy after selected commit")
        report = export_repository(
            self.repository, self.base / "public", source_ref=selected, exclusions_file=policy,
        )
        self.assertEqual(report["excluded_paths"], ["script/run.sh"])
        self.assertTrue((self.base / "public/README.md").is_file())
        self.assertEqual(report["exclusion_policy"]["sha256"],
                         hashlib.sha256(b"script/\n").hexdigest())

    def test_documentation_mapping_cannot_replace_runtime_code(self):
        _, _, mapping_path = self.prepare_documentation_fixture()
        mapping = json.loads(mapping_path.read_text())
        mapping["replacements"][0]["path"] = "skills/scientific-data-analysis/run.py"
        mapping["replacements"][0]["edition"] = "docs/run.py"
        mapping_path.write_text(json.dumps(mapping))
        self.commit_fixture("Try mapping runtime code as documentation")
        with self.assertRaisesRegex(ExportError, "must map skill documentation"):
            export_repository(self.repository, self.base / "public")
        self.assertFalse((self.base / "public").exists())

    def prepare_private_historical_fixture(self):
        original, _, _ = self.prepare_documentation_fixture()
        family = self.repository / "skills"
        fixture = family / "scientific-data-analysis/fixtures/historical_check.py"
        fixture.parent.mkdir()
        fixture.write_text('from pathlib import Path\nAPP = Path("/Users/private-person/app")\n')
        original_code = fixture.read_bytes()
        edition_code = original_code.replace(
            b'Path("/Users/private-person/app")', b'Path(__file__).resolve().parents[3]'
        )
        manifest_path = self.repository / "distribution/skill-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["scientific-data-analysis/fixtures/historical_check.py"] = {
            "kind": "file", "sha256": hashlib.sha256(original_code).hexdigest(),
            "size": len(original_code), "executable": False,
        }
        manifest_path.write_text(json.dumps(manifest))
        private_map = self.repository / "distribution/private-code-path-map.json"
        private_map.write_text(json.dumps({"schema_version": 1, "replacements": [{
            "path": "skills/scientific-data-analysis/fixtures/historical_check.py",
            "source_sha256": hashlib.sha256(original_code).hexdigest(),
            "edition_sha256": hashlib.sha256(edition_code).hexdigest(),
            "reason": "Remove a private location from a historical fixture.",
            "changes": [{"from": 'Path("/Users/private-person/app")',
                         "to": "Path(__file__).resolve().parents[3]", "count": 1}],
        }]}))
        exclusions = self.repository / "distribution/public-source-exclusions.txt"
        exclusions.write_text("distribution/private-code-path-map.json\n")
        self.commit_fixture("Review private fixture path replacement")
        return original, fixture, original_code, edition_code, private_map, exclusions

    def test_private_historical_fixture_paths_are_exported_portably_with_provenance(self):
        original, fixture, original_code, edition_code, private_map, exclusions = (
            self.prepare_private_historical_fixture()
        )
        output = self.base / "public"
        report = export_repository(self.repository, output, exclusions_file=exclusions)
        self.assertEqual(fixture.read_bytes(), original_code)
        self.assertEqual(original.read_text(), "Guia historica: conserva los datos originales.\n")
        self.assertEqual((output / fixture.relative_to(self.repository)).read_bytes(), edition_code)
        self.assertFalse((output / private_map.relative_to(self.repository)).exists())
        self.assertEqual(verify(output), 4)
        self.assertEqual(report["excluded_paths"], ["distribution/private-code-path-map.json"])
        exported = json.loads((output / "SOURCE_PROVENANCE.json").read_text())
        self.assertEqual(exported["private_code_path_map_sha256"],
                         hashlib.sha256(private_map.read_bytes()).hexdigest())
        self.assertNotIn("/Users/private-person", (output / "SOURCE_PROVENANCE.json").read_text())

    def test_changed_historical_fixture_rejects_stale_path_mapping(self):
        _, fixture, _, _, _, exclusions = self.prepare_private_historical_fixture()
        fixture.write_text(fixture.read_text() + "# changed\n")
        self.commit_fixture("Change private historical fixture after review")
        with self.assertRaisesRegex(ExportError, "private code source hash differs"):
            export_repository(self.repository, self.base / "second-public", exclusions_file=exclusions)
        self.assertFalse((self.base / "second-public").exists())

    def test_private_path_policy_cannot_be_exported(self):
        self.prepare_private_historical_fixture()
        with self.assertRaisesRegex(ExportError, "policy must be a regular, excluded file"):
            export_repository(self.repository, self.base / "public")
        self.assertFalse((self.base / "public").exists())

    def test_exact_commit_is_exported_without_history(self):
        output = self.base / "public"
        report = export_repository(self.repository, output)
        self.assertTrue((output / "README-link.md").is_symlink())
        self.assertEqual((output / "README-link.md").read_text(), "# Synthetic project\n")
        self.assertTrue((output / "script/run.sh").stat().st_mode & 0o111)
        self.assertFalse((output / ".git").exists())
        provenance = json.loads((output / "SOURCE_PROVENANCE.json").read_text())
        self.assertEqual(provenance["source_commit"], report["source_commit"])
        self.assertEqual(provenance["exported_entries"], 3)
        self.assertEqual(provenance["excluded_paths"], [])

    def test_dirty_repository_and_existing_destination_are_preserved(self):
        (self.repository / "uncommitted.txt").write_text("keep me", encoding="utf-8")
        with self.assertRaisesRegex(ExportError, "repository is dirty"):
            export_repository(self.repository, self.base / "public")
        self.assertEqual((self.repository / "uncommitted.txt").read_text(), "keep me")

        (self.repository / "uncommitted.txt").unlink()
        output = self.base / "existing"
        output.mkdir()
        marker = output / "marker.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ExportError, "will not be overwritten"):
            export_repository(self.repository, output)
        self.assertEqual(marker.read_text(), "preserve")

    def test_reviewed_exclusions_are_exact_and_recorded(self):
        exclusions = self.base / "exclusions.txt"
        exclusions.write_text("script/\n", encoding="utf-8")
        output = self.base / "public"
        report = export_repository(
            self.repository,
            output,
            exclusions_file=exclusions,
        )
        self.assertFalse((output / "script").exists())
        self.assertEqual(report["excluded_paths"], ["script/run.sh"])
        self.assertTrue((output / "README.md").is_file())

    def test_symlink_that_escapes_snapshot_is_rejected(self):
        (self.repository / "README-link.md").unlink()
        (self.repository / "unsafe-link").symlink_to("../../private-data")
        subprocess.run(["git", "-C", str(self.repository), "add", "-A"], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.repository),
                "-c", "user.name=Export Fixture",
                "-c", "user.email=fixture.invalid",
                "commit", "-qm", "Add unsafe synthetic link",
            ],
            check=True,
        )
        with self.assertRaisesRegex(ExportError, "symlink would escape"):
            export_repository(self.repository, self.base / "public")
        self.assertFalse((self.base / "public").exists())


if __name__ == "__main__":
    unittest.main()
