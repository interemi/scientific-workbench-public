"""CLI matrix for notebook/table output collision preflights."""

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


class NotebookCollisionAssertions:
    def assert_blocked_unchanged(self, completed: subprocess.CompletedProcess[str], sources: dict[Path, str]) -> dict:
        self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
        self.assertEqual(payload["results"]["error_type"], "output_input_collision")
        self.assertEqual(payload["artifacts"], {})
        for path, digest in sources.items():
            self.assertEqual(sha256(path), digest, path)
        return payload
