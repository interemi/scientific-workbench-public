"""Load deferred internal helper bodies from fixtures/_internal."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _resolve_paths(current_file: str) -> tuple[Path, Path, Path, Path]:
    current = Path(current_file).resolve()
    root = current.parents[2]
    scripts_dir = root / "scripts"
    fixture = root / "fixtures" / "_internal" / current.name
    return current, root, scripts_dir, fixture


def _prepare_import_path(root: Path, scripts_dir: Path, fixture: Path) -> None:
    for path in (scripts_dir, fixture.parent, root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def _module_name(root: Path, current: Path) -> str:
    root_key = root.name.replace("-", "_")
    return f"_internal._deferred_{root_key}_{current.stem}"


def _load_module(module_name: str, fixture: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, fixture)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load deferred internal helper body: {fixture}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _export_symbols(module: ModuleType, module_globals: dict[str, object]) -> None:
    for name, value in vars(module).items():
        if not (name.startswith("__") and name.endswith("__")):
            module_globals[name] = value


def load_deferred_internal(current_file: str, module_globals: dict[str, object]) -> ModuleType:
    current, root, scripts_dir, fixture = _resolve_paths(current_file)
    if not fixture.exists():
        raise ImportError(f"Deferred internal helper body is missing: {fixture}")
    _prepare_import_path(root, scripts_dir, fixture)
    module = _load_module(_module_name(root, current), fixture)
    _export_symbols(module, module_globals)
    return module
