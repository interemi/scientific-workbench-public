"""Dynamic no-mutation regressions for maintainer input/output preflights."""

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
MOTHER_SCRIPTS = ROOT.parent / "scientific-data-analysis" / "scripts"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_symlink():
            digest.update(b"SYMLINK")
            digest.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(path.read_bytes())
        elif path.is_dir():
            digest.update(b"DIRECTORY")
    return digest.hexdigest()


def run_script(name: str, *args: str, scripts: Path = SCRIPTS) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(scripts / name), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def stdout_payload(result: subprocess.CompletedProcess[str]) -> dict:
    if "Traceback" in (result.stdout + result.stderr):
        raise AssertionError(f"unexpected traceback\nstdout={result.stdout}\nstderr={result.stderr}")
    payload = json.loads(result.stdout)
    if payload.get("status") == "blocked" and payload.get("artifacts") != {}:
        raise AssertionError(f"blocked preflight declared non-materialized artifacts: {payload.get('artifacts')}")
    return payload


def assert_controlled_block(test: unittest.TestCase, result: subprocess.CompletedProcess[str]) -> dict:
    test.assertEqual(result.returncode, 2, result.stderr)
    payload = stdout_payload(result)
    test.assertEqual(payload["status"], "blocked")
    test.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
    return payload
