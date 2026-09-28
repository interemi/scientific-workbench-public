"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from maintainer_collision_support import *  # noqa: F403


class MaintainerCollisionSafetyTest(unittest.TestCase):
    def test_validate_samples_blocks_reports_under_root_and_hardlink_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="maintainer_samples_collision_") as raw:
            tmp = Path(raw)
            sample_root = tmp / "samples"
            sample_root.mkdir()
            sentinel = sample_root / "sample.csv"
            sentinel.write_text("x,y\n1,2\n", encoding="utf-8")
            before = tree_sha256(sample_root)

            nested = run_script(
                "validate_skill_samples.py",
                str(sample_root),
                "--validation-profile",
                "quick",
                "--output-dir",
                str(sample_root / "reports"),
            )
            assert_controlled_block(self, nested)
            self.assertEqual(tree_sha256(sample_root), before)

            summary_alias = tmp / "summary-hardlink.json"
            os.link(sentinel, summary_alias)
            hardlink = run_script(
                "validate_skill_samples.py",
                str(sample_root),
                "--validation-profile",
                "quick",
                "--output-dir",
                str(tmp / "safe-reports"),
                "--summary-json",
                str(summary_alias),
            )
            assert_controlled_block(self, hardlink)
            self.assertFalse((tmp / "safe-reports").exists())
            self.assertEqual(tree_sha256(sample_root), before)
            self.assertEqual(sha256(summary_alias), sha256(sentinel))

    def test_sync_docs_check_never_overwrites_registry_summary_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="maintainer_sync_collision_") as raw:
            tmp = Path(raw)
            registry = tmp / "registry.yaml"
            registry.write_text("immutable registry bytes\n", encoding="utf-8")
            before = sha256(registry)

            exact = run_script(
                "sync_public_surface_docs.py",
                "--check",
                "--registry",
                str(registry),
                "--summary-json",
                str(registry),
            )
            assert_controlled_block(self, exact)
            self.assertEqual(sha256(registry), before)

            alias = tmp / "registry-summary-hardlink.json"
            os.link(registry, alias)
            hardlink = run_script(
                "sync_public_surface_docs.py",
                "--check",
                "--registry",
                str(registry),
                "--summary-json",
                str(alias),
            )
            assert_controlled_block(self, hardlink)
            self.assertEqual(sha256(registry), before)
            self.assertEqual(sha256(alias), before)

    def test_surface_audit_blocks_summary_inside_root_and_hardlink_descendant(self) -> None:
        with tempfile.TemporaryDirectory(prefix="maintainer_surface_collision_") as raw:
            tmp = Path(raw)
            skill_root = tmp / "skill"
            skill_root.mkdir()
            (skill_root / "SKILL.md").write_text("# Immutable skill\n", encoding="utf-8")
            sentinel = skill_root / "sentinel.json"
            sentinel.write_text('{"immutable": true}\n', encoding="utf-8")
            before = tree_sha256(skill_root)

            nested = run_script(
                "skill_surface_audit.py",
                "--root",
                str(skill_root),
                "--skip-hygiene",
                "--summary-json",
                str(sentinel),
            )
            assert_controlled_block(self, nested)
            self.assertEqual(tree_sha256(skill_root), before)

            alias = tmp / "surface-summary-hardlink.json"
            os.link(sentinel, alias)
            hardlink = run_script(
                "skill_surface_audit.py",
                "--root",
                str(skill_root),
                "--skip-hygiene",
                "--summary-json",
                str(alias),
            )
            assert_controlled_block(self, hardlink)
            self.assertEqual(tree_sha256(skill_root), before)
            self.assertEqual(sha256(alias), sha256(sentinel))


if __name__ == "__main__":
    unittest.main()
