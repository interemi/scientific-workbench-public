"""Stable import bridge for the maintainer-local path-safety implementation.

Mother compatibility wrappers execute maintainer fixture bodies while the
mother ``_internal`` package is already imported.  A unique top-level module
name avoids accidentally resolving a different root's internal helper.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_MODULE_NAME = "_scientific_data_maintainer_path_safety"
_IMPLEMENTATION = Path(__file__).resolve().parent / "_internal" / "path_safety.py"
_SPEC = importlib.util.spec_from_file_location(_MODULE_NAME, _IMPLEMENTATION)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load maintainer path-safety helper: {_IMPLEMENTATION}")
_MODULE = sys.modules.get(_MODULE_NAME)
if _MODULE is None:
    _MODULE = importlib.util.module_from_spec(_SPEC)
    sys.modules[_MODULE_NAME] = _MODULE
    _SPEC.loader.exec_module(_MODULE)

for _name, _value in vars(_MODULE).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
