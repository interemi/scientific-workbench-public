"""Dispatch thin public scripts to executable bodies stored in fixtures."""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType


def _paths(wrapper_file: str) -> tuple[Path, Path, Path, Path]:
    wrapper = Path(wrapper_file).resolve()
    root = wrapper.parents[1]
    scripts_dir = root / "scripts"
    fixture = root / "fixtures" / wrapper.name
    return wrapper, root, scripts_dir, fixture


def _prepare_import_path(root: Path, scripts_dir: Path, fixture: Path) -> None:
    for path in [scripts_dir, fixture.parent, root]:
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def load_fixture_module(wrapper_file: str) -> ModuleType | None:
    wrapper, root, scripts_dir, fixture = _paths(wrapper_file)
    if not fixture.exists():
        return None
    _prepare_import_path(root, scripts_dir, fixture)
    module_name = f"_fixture_payload_{wrapper.stem}"
    spec = importlib.util.spec_from_file_location(module_name, fixture)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load fixture script body: {fixture}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(wrapper_file: str) -> int:
    _wrapper, root, scripts_dir, fixture = _paths(wrapper_file)
    if not fixture.exists():
        raise SystemExit(f"Fixture script body is missing: {fixture}")
    _prepare_import_path(root, scripts_dir, fixture)
    sys.argv[0] = str(fixture)
    runpy.run_path(str(fixture), run_name="__main__")
    return 0
