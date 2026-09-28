"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from maintainer_collision_support import *  # noqa: F403


class MaintainerCollisionSafetyTest(unittest.TestCase):
    def test_helper_resolves_symlink_alias_without_writing(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            sys.path.insert(0, str(ROOT / "fixtures"))
            from maintainer_path_safety import PathSafetyError, ensure_safe_paths, operand

            with tempfile.TemporaryDirectory(prefix="maintainer_helper_symlink_") as raw:
                tmp = Path(raw)
                source = tmp / "input.txt"
                source.write_text("immutable\n", encoding="utf-8")
                alias = tmp / "output-link.txt"
                alias.symlink_to(source)
                before = sha256(source)
                with self.assertRaises(PathSafetyError):
                    ensure_safe_paths(
                        inputs=[operand("input", source)],
                        outputs=[operand("output", alias)],
                    )
                self.assertEqual(sha256(source), before)
        finally:
            if sys.path and sys.path[0] == str(ROOT / "fixtures"):
                sys.path.pop(0)
            if sys.path and sys.path[0] == str(SCRIPTS):
                sys.path.pop(0)

    def test_helper_blocks_tree_hardlinks_and_exact_output_aliases(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            sys.path.insert(0, str(ROOT / "fixtures"))
            from maintainer_path_safety import PathSafetyError, ensure_safe_paths, operand

            with tempfile.TemporaryDirectory(prefix="maintainer_helper_tree_hardlink_") as raw:
                tmp = Path(raw)
                protected_tree = tmp / "protected"
                output_tree = tmp / "derived"
                protected_tree.mkdir()
                output_tree.mkdir()
                protected = protected_tree / "raw.dat"
                protected.write_text("immutable\n", encoding="utf-8")
                os.link(protected, output_tree / "summary.json")
                before = sha256(protected)

                with self.assertRaises(PathSafetyError):
                    ensure_safe_paths(
                        inputs=[operand("input tree", protected_tree, tree=True)],
                        outputs=[operand("output tree", output_tree, tree=True)],
                    )
                self.assertEqual(sha256(protected), before)

                shared = tmp / "shared-output.json"
                with self.assertRaises(PathSafetyError):
                    ensure_safe_paths(
                        inputs=[],
                        outputs=[operand("summary", shared), operand("manifest", shared)],
                    )

                normal_root = tmp / "normal-output"
                ensure_safe_paths(
                    inputs=[operand("input", protected)],
                    outputs=[
                        operand("output directory", normal_root, tree=True),
                        operand("summary", normal_root / "summary.json"),
                    ],
                )
        finally:
            if sys.path and sys.path[0] == str(ROOT / "fixtures"):
                sys.path.pop(0)
            if sys.path and sys.path[0] == str(SCRIPTS):
                sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
