"""Regression coverage for public dispatch and run-bundle write preflights."""

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
FIXTURES = ROOT / "fixtures"
ASTRO_ROOT = ROOT.parent / "scientific-data-astro"
sys.path.insert(0, str(FIXTURES))

import datanalysis_env


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_public(
    script: str, *arguments: object, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if environment:
        env.update(environment)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *[str(item) for item in arguments]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


class PublicExecutionSafetyTest(unittest.TestCase):
    def test_datanalysis_resolvers_prefer_public_wrappers(self) -> None:
        resolved_tool = datanalysis_env.resolve_tool_script("catalog_workbench")
        self.assertEqual(resolved_tool, SCRIPTS / "catalog_workbench.py")
        self.assertNotEqual(resolved_tool.parent, FIXTURES)

        mother_fixture = FIXTURES / "catalog_workbench.py"
        self.assertEqual(
            datanalysis_env.resolve_public_script(mother_fixture),
            SCRIPTS / mother_fixture.name,
        )

        astro_fixture = ASTRO_ROOT / "fixtures" / "aperture_photometry.py"
        self.assertEqual(
            datanalysis_env.resolve_public_script(astro_fixture),
            ASTRO_ROOT / "scripts" / astro_fixture.name,
        )

    def test_public_datanalysis_run_script_preserves_colliding_astro_input(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.fits"
            source.write_bytes(b"immutable-not-a-fits-file\n")
            before = sha256(source)
            astro_fixture = ASTRO_ROOT / "fixtures" / "aperture_photometry.py"

            completed = run_public(
                "datanalysis_env.py",
                "run-script",
                astro_fixture,
                source,
                "--summary-json",
                source,
                environment={"DATAANALYSIS_PYTHON": sys.executable},
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["errors"][0]["code"], "unsafe_output_input_collision")
            self.assertEqual(payload["artifacts"], {})
            self.assertEqual(sha256(source), before)

    def test_app_run_bundle_rejects_nonempty_directory_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "existing-run"
            run_dir.mkdir()
            sentinel = run_dir / "sentinel.bin"
            sentinel.write_bytes(b"preserve-this-tree\n")
            before_names = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*"))
            before_digest = sha256(sentinel)

            completed = run_public(
                "app_run_bundle.py",
                "--run-dir",
                run_dir,
                "--",
                sys.executable,
                "-c",
                "print('must not run')",
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["artifacts"], {})
            self.assertEqual(
                sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*")),
                before_names,
            )
            self.assertEqual(sha256(sentinel), before_digest)

    def test_app_run_bundle_accepts_new_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "new-run"
            child_code = (
                "import json; from pathlib import Path; "
                f"Path({str(run_dir / 'summary.json')!r}).write_text(json.dumps("
                "{'tool':'synthetic_child','status':'ok','app_status':'PASS','artifacts':{},"
                "'results':{},'qa':{'status':'ok','findings':[]}}), encoding='utf-8'); "
                "print('child-ok')"
            )

            completed = run_public(
                "app_run_bundle.py",
                "--run-dir",
                run_dir,
                "--",
                sys.executable,
                "-c",
                child_code,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "PASS")
            for relative in (
                "summary.json",
                "manifest.json",
                "stdout.txt",
                "stderr.txt",
                "command.txt",
                "next_steps.md",
            ):
                self.assertTrue((run_dir / relative).is_file(), relative)
            self.assertEqual((run_dir / "stdout.txt").read_text(encoding="utf-8"), "child-ok\n")


if __name__ == "__main__":
    unittest.main()
