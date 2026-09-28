"""CLI regressions for earliest astro output/input collision blocking."""

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
for entry in (str(SCRIPTS), str(ROOT / "fixtures")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from _internal.astro_cli_output_safety import PLANNERS, find_plan_collisions
from _internal.path_safety import output_overlaps_input, paths_alias


def tree_snapshot(root: Path) -> dict[str, tuple[str, str]]:
    snapshot: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snapshot[relative] = ("directory", "")
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[relative] = ("file", digest)
        else:
            snapshot[relative] = ("other", "")
    return snapshot


class AstroCliCollisionAssertions:
    def assert_controlled_collision(
        self,
        temp_root: Path,
        script: str,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> None:
        before = tree_snapshot(temp_root)
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=ROOT,
            env={**os.environ, **(extra_env or {}), "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        required_contract_fields = {
            "tool",
            "status",
            "contract_version",
            "app_status",
            "command",
            "inputs",
            "outputs",
            "warnings",
            "errors",
            "qa",
            "provenance",
            "app_hints",
            "next_actions",
            "original_modified",
        }
        self.assertFalse(required_contract_fields - set(payload))
        self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["error"]["kind"], "output_conflict")
        self.assertGreaterEqual(payload["qa"]["metrics"]["collision_count"], 1)
        self.assertEqual(payload["artifacts"], {})
        self.assertEqual(payload["typed_artifacts"], [])
        self.assertEqual(tree_snapshot(temp_root), before)


ASTRO_CLI_CASE_DATA = Path(__file__).with_name("astro_cli_output_safety_cases.json")


def load_cli_case_data() -> dict[str, object]:
    return json.loads(ASTRO_CLI_CASE_DATA.read_text(encoding="utf-8"))


def resolve_cli_case_argument(argument: str, paths: dict[str, object]) -> str:
    if not argument.startswith("$"):
        return argument
    root_name, *parts = argument[1:].split("/")
    return str(Path(paths[root_name]).joinpath(*parts))


def resolve_cli_case_map(specs: dict[str, list[str]], paths: dict[str, object]) -> dict[str, list[str]]:
    return {
        script: [resolve_cli_case_argument(argument, paths) for argument in arguments]
        for script, arguments in specs.items()
    }


def resolve_cli_collision_cases(
    specs: list[list[object]], paths: dict[str, object]
) -> list[tuple[str, str, list[str]]]:
    return [
        (label, script, [resolve_cli_case_argument(argument, paths) for argument in arguments])
        for label, script, arguments in specs
    ]
