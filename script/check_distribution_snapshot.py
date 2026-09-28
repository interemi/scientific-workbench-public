#!/usr/bin/env python3
"""Verify the reviewed scientific backend snapshot without modifying it."""

import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOTS = {
    "scientific-data-analysis", "scientific-data-astro",
    "scientific-data-documents", "scientific-data-notebooks",
    "scientific-data-maintainer",
}
TRANSIENT = {"__pycache__", ".pytest_cache", ".venv", "tmp"}


def verify(root=ROOT):
    family = root / "skills"
    if family.is_symlink() or not family.is_dir():
        raise ValueError("skills must be a local directory")
    manifest = json.loads((root / "distribution/skill-manifest.json").read_text())
    if manifest.get("schema_version") != 1 or set(manifest.get("roots", [])) != ROOTS:
        raise ValueError("unsupported snapshot schema or skill roots")
    expected = manifest["files"]
    actual = set()
    for current, dirs, files in os.walk(family, followlinks=False):
        dirs[:] = [name for name in dirs if name not in TRANSIENT]
        for name in files + [name for name in dirs if (Path(current) / name).is_symlink()]:
            path = Path(current) / name
            if path.suffix in {".pyc", ".pyo"}:
                continue
            actual.add(path.relative_to(family).as_posix())
    if actual != set(expected):
        raise ValueError(f"snapshot paths differ: missing={sorted(set(expected)-actual)}, "
                         f"unexpected={sorted(actual-set(expected))}")
    for relative, record in expected.items():
        parts = Path(relative).parts
        if not parts or parts[0] not in ROOTS or ".." in parts or Path(relative).is_absolute():
            raise ValueError(f"invalid snapshot path: {relative}")
        path = family / relative
        if not path.resolve(strict=True).is_relative_to(family.resolve()):
            raise ValueError(f"path escapes the family: {relative}")
        if record["kind"] == "symlink":
            if (not path.is_symlink() or os.readlink(path) != record["target"]
                    or os.path.isabs(record["target"])):
                raise ValueError(f"symlink changed: {relative}")
        elif record["kind"] == "file":
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"file type changed: {relative}")
            if (path.stat().st_size != record["size"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
                    or bool(path.stat().st_mode & 0o111) != record["executable"]):
                raise ValueError(f"file content or executable mode changed: {relative}")
        else:
            raise ValueError(f"unknown entry type: {relative}")
    return len(expected)


if __name__ == "__main__":
    try:
        print(f"Scientific Workbench distribution snapshot verified: {verify()} entries.")
    except (OSError, ValueError, KeyError) as error:
        print(f"Distribution snapshot check failed: {error}", file=sys.stderr)
        sys.exit(1)
