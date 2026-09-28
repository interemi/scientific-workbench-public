"""Dispatch a historical mother-script path to a staged child skill script."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

from .provenance_utils import standard_tool_payload


def _candidate_child_roots(wrapper_file: str, child_skill_name: str) -> list[Path]:
    wrapper = Path(wrapper_file).resolve()
    skill_root = wrapper.parents[1]
    return [
        skill_root.parent / child_skill_name,
        Path.home() / ".codex" / "skills" / child_skill_name,
    ]


def _failure_payload(wrapper_file: str, child_skill_name: str, message: str) -> str:
    payload = standard_tool_payload(
        Path(wrapper_file).stem,
        status="fail",
        notes=[message],
        results={"required_child_skill": child_skill_name},
        qa={"status": "fail", "findings": [message]},
    )
    return json.dumps(payload, indent=2, allow_nan=False)


def child_script_for(wrapper_file: str, child_skill_name: str) -> Path | None:
    script_name = Path(wrapper_file).name
    for child_root in _candidate_child_roots(wrapper_file, child_skill_name):
        child_script = child_root / "scripts" / script_name
        if child_script.exists():
            return child_script
    return None


def load_child_module(wrapper_file: str, child_skill_name: str):
    child_script = child_script_for(wrapper_file, child_skill_name)
    if child_script is None:
        return None
    module_name = f"_child_{child_skill_name.replace('-', '_')}_{Path(wrapper_file).stem}"
    spec = importlib.util.spec_from_file_location(module_name, child_script)
    if spec is None or spec.loader is None:
        return None
    child_scripts_dir = str(child_script.parent)
    if child_scripts_dir not in sys.path:
        sys.path.insert(0, child_scripts_dir)
    child_internal_dir = str(child_script.parent / "_internal")
    internal_package = sys.modules.get("_internal")
    if internal_package is not None and hasattr(internal_package, "__path__"):
        internal_paths = list(internal_package.__path__)
        if child_internal_dir not in internal_paths:
            internal_package.__path__ = [*internal_paths, child_internal_dir]
            importlib.invalidate_caches()
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main(wrapper_file: str, child_skill_name: str) -> int:
    script_name = Path(wrapper_file).name
    child_script = child_script_for(wrapper_file, child_skill_name)
    if child_script is not None:
        completed = subprocess.run([sys.executable, str(child_script), *sys.argv[1:]], check=False)
        return int(completed.returncode)

    message = f"Required child skill dependency {child_skill_name} is not installed next to the mother skill or in ~/.codex/skills."
    print(_failure_payload(wrapper_file, child_skill_name, message))
    return 2
