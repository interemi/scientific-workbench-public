"""Mother-root collision regressions for native general capabilities."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_script(name: str, *arguments: object) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *[str(item) for item in arguments]],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def make_alias(root: Path, source: Path, kind: str) -> Path:
    if kind == "exact":
        return source
    alias = root / f"{kind}-{source.name}"
    if kind == "symlink":
        alias.symlink_to(source)
    else:
        os.link(source, alias)
    return alias


class GeneralOutputCollisionMatrixTest(unittest.TestCase):
    def assert_blocked_unchanged(self, completed: subprocess.CompletedProcess[str], source: Path, digest: str) -> dict:
        self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
        self.assertEqual(payload["results"]["error_type"], "output_input_collision")
        self.assertEqual(payload["artifacts"], {})
        self.assertEqual(sha256(source), digest)
        return payload

    def test_catalog_crossmatch_cannot_replace_either_input(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            left = root / "left.csv"
            right = root / "right.csv"
            left.write_text("ra,dec\n1,2\n", encoding="utf-8")
            right.write_text("ra,dec\n1,2\n", encoding="utf-8")
            before = {left: sha256(left), right: sha256(right)}
            for output in (left, right):
                with self.subTest(output=output.name):
                    completed = run_script(
                        "catalog_workbench.py",
                        "crossmatch-sky",
                        left,
                        right,
                        output,
                        "--left-ra",
                        "ra",
                        "--left-dec",
                        "dec",
                        "--right-ra",
                        "ra",
                        "--right-dec",
                        "dec",
                    )
                    self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                    self.assertEqual(completed.stderr, "")
                    self.assertEqual(json.loads(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")
                    self.assertEqual({path: sha256(path) for path in before}, before)

    def test_catalog_output_alias_variants_are_blocked(self) -> None:
        for kind in ("exact", "symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source = root / "source.csv"
                source.write_text("x\n1\n", encoding="utf-8")
                before = sha256(source)
                output = make_alias(root, source, kind)
                completed = run_script(
                    "catalog_workbench.py",
                    "filter",
                    source,
                    output,
                    "--expression",
                    "x > 0",
                )
                self.assert_blocked_unchanged(completed, source, before)

    def test_companion_file_hint_alias_variants_are_read_only(self) -> None:
        for kind in ("exact", "symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source = root / "source.csv"
                source.write_text("x\n1\n", encoding="utf-8")
                before = sha256(source)
                summary = make_alias(root, source, kind)
                completed = run_script(
                    "companion_route_check.py",
                    "--file",
                    source,
                    "--summary-json",
                    summary,
                )
                self.assert_blocked_unchanged(completed, source, before)

    def test_router_outputs_cannot_enter_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_dir = root / "source"
            source_dir.mkdir()
            source = source_dir / "table.csv"
            source.write_text("x\n1\n", encoding="utf-8")
            before = sha256(source)
            completed = run_script(
                "scientific_workflow_router.py",
                "inspect",
                source_dir,
                "--summary-json",
                source_dir / "summary.json",
            )
            self.assert_blocked_unchanged(completed, source, before)
            self.assertFalse((source_dir / "summary.json").exists())

    def test_distinct_companion_and_catalog_error_outputs_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.csv"
            right = root / "right.csv"
            source.write_text("ra,dec\n1,2\n", encoding="utf-8")
            right.write_text("ra,dec\n1,2\n", encoding="utf-8")
            before = sha256(source)
            companion_summary = root / "companion.json"
            companion = run_script(
                "companion_route_check.py",
                "--file",
                source,
                "--summary-json",
                companion_summary,
            )
            self.assertEqual(companion.returncode, 0, companion.stderr or companion.stdout)
            self.assertEqual(sha256(source), before)
            self.assertIn(json.loads(companion_summary.read_text(encoding="utf-8"))["app_status"], {"PASS", "WARNING"})

            error_summary = root / "catalog-error.json"
            blocked = run_script(
                "catalog_workbench.py",
                "crossmatch-sky",
                source,
                right,
                root / "out.csv",
                "--left-ra",
                "ra",
                "--left-dec",
                "dec",
                "--right-ra",
                "ra",
                "--right-dec",
                "dec",
                "--radius-arcsec",
                "nan",
                "--summary-json",
                error_summary,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr or blocked.stdout)
            self.assertEqual(sha256(source), before)
            self.assertEqual(json.loads(error_summary.read_text(encoding="utf-8"))["app_status"], "BLOCKED_CONTROLADO")


if __name__ == "__main__":
    unittest.main()
