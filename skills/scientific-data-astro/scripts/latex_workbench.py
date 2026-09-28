"""Dependency shim for the documents child `latex_workbench.py` module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_dependency():
    module_name = "_astro_dependency_scientific_data_documents_latex_workbench"
    if module_name in sys.modules:
        return sys.modules[module_name]
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "scientific-data-documents" / "scripts" / "latex_workbench.py",
        Path.home() / ".codex" / "skills" / "scientific-data-documents" / "scripts" / "latex_workbench.py",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        scripts_dir = str(candidate.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    raise ModuleNotFoundError("Could not find scientific-data-documents/scripts/latex_workbench.py")


_module = _load_dependency()

for _name, _value in vars(_module).items():
    if not _name.startswith("__"):
        globals()[_name] = _value
