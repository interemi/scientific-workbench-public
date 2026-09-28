#!/usr/bin/env python3
"""Internal helpers to re-run heavy tools inside the dedicated datanalysis environment."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import public_path
try:
    from datanalysis_env import locate_env_real
except ModuleNotFoundError as exc:
    if exc.name != "datanalysis_env":
        raise
    mother_scripts = Path(__file__).resolve().parents[3] / "scientific-data-analysis" / "scripts"
    if not (mother_scripts / "datanalysis_env.py").is_file():
        raise ModuleNotFoundError(
            "The sibling scientific-data-analysis skill is required for maintainer environment discovery."
        ) from exc
    sys.path.append(str(mother_scripts))
    from datanalysis_env import locate_env_real


REEXEC_ENV_VAR = "SCIENTIFIC_DATA_ANALYSIS_DATANALYSIS_REEXEC"


def current_python_matches(selected_python: Path | str | None) -> bool:
    if not selected_python:
        return False
    try:
        return Path(sys.executable).resolve() == Path(selected_python).resolve()
    except Exception:
        return False


def build_rerun_command(script_path: Path, argv: list[str], env_python: Path) -> str:
    parts = [public_path(env_python), public_path(script_path), *[shlex.quote(arg) for arg in argv]]
    return " ".join(parts)


def ensure_datanalysis_runtime(tool_name: str, *, argv: list[str] | None = None, strict: bool = True) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get(REEXEC_ENV_VAR) == tool_name:
        return
    payload = locate_env_real()
    selected = payload.get("selected")
    script_path = Path(sys.argv[0]).resolve()
    if selected and current_python_matches(selected.get("python")):
        return
    if selected:
        env_python = Path(selected["python"]).resolve()
        rerun_cmd = [str(env_python), str(script_path), *argv]
        hint = build_rerun_command(script_path, argv, env_python)
        print(
            f"[scientific-data-analysis] Re-running {tool_name} inside datanalysis: {hint}",
            file=sys.stderr,
        )
        env = dict(os.environ)
        env[REEXEC_ENV_VAR] = tool_name
        completed = subprocess.run(rerun_cmd, env=env)
        raise SystemExit(completed.returncode)
    if strict:
        env_wrapper = script_path.with_name("datanalysis_env.py")
        quoted_args = " ".join(shlex.quote(arg) for arg in argv)
        rerun_hint = f"python {public_path(env_wrapper)} run-tool {tool_name} {quoted_args}".strip()
        raise SystemExit(
            f"{tool_name} should be run inside the datanalysis environment for reliable astronomy/notebook behavior. "
            f"Could not locate that environment automatically. Re-run with: {rerun_hint}"
        )
