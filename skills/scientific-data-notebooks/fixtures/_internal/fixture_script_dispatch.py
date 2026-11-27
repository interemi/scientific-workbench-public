"""Dispatch thin public scripts to executable bodies stored in fixtures."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
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


def runtime_inventory_sha256() -> str | None:
    """Fingerprint interpreter binaries and installed distribution metadata."""
    from importlib.metadata import distributions

    try:
        binaries = {}
        for value in (sys.executable, getattr(sys, "_base_executable", sys.executable)):
            path = Path(value).resolve(strict=True)
            if str(path) in binaries:
                continue
            if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                return None
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    digest.update(block)
            binaries[str(path)] = digest.hexdigest()

        packages = []
        for distribution in distributions():
            name, release = distribution.metadata["Name"], distribution.version
            if not name or not release:
                return None
            metadata = tuple(distribution.read_text(file) or "" for file in ("METADATA", "RECORD", "direct_url.json"))
            packages.append((
                re.sub(r"[-_.]+", "-", name).lower(), release,
                str(distribution.locate_file("").resolve()), hashlib.sha256(
                    json.dumps(metadata, ensure_ascii=True).encode("utf-8")
                ).hexdigest(),
            ))
        inventory = (sys.prefix, sys.base_prefix, sys.version, binaries, sorted(packages))
        return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode("utf-8")).hexdigest()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _record_runtime(tool: str) -> None:
    raw = os.environ.get("SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE")
    if not raw or len(raw) > 16384:
        return
    try:
        request = json.loads(raw)
        if request["tool"] != tool or (tool == "datanalysis_env" and sys.argv[1:2] == ["run-tool"]):
            return
        os.environ.pop("SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE", None)
        path = Path(request["destination"])
        if (not path.is_absolute() or path.parent.resolve(strict=True) != path.parent
                or not re.fullmatch(r"\.swb-runtime-[a-f0-9-]{36}\.json", path.name)):
            return
        names = request["packages"]
        if (not isinstance(names, list) or len(names) > 64
                or not all(isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", name) for name in names)):
            return

        from importlib.metadata import PackageNotFoundError, version
        import platform

        packages = {}
        for name in sorted(set(names)):
            try:
                release = version(name)
            except PackageNotFoundError:
                continue
            if isinstance(release, str) and len(release) <= 48:
                packages[name] = release
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({
                "schemaVersion": 1, "tool": tool, "implementation": sys.implementation.name,
                "version": platform.python_version(), "architecture": platform.machine(), "packages": packages,
                "inventorySHA256": runtime_inventory_sha256(),
            }, stream, sort_keys=True)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError):
        # Evidence is optional and must not interrupt the scientific command.
        return


def main(wrapper_file: str) -> int:
    wrapper, root, scripts_dir, fixture = _paths(wrapper_file)
    if not fixture.exists():
        raise SystemExit(f"Fixture script body is missing: {fixture}")
    _prepare_import_path(root, scripts_dir, fixture)
    _record_runtime(wrapper.stem)
    sys.argv[0] = str(fixture)
    runpy.run_path(str(fixture), run_name="__main__")
    return 0
