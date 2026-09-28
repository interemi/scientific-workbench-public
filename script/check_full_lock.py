#!/usr/bin/env python3
"""Check the full runtime/source and build-tool locks against their reviewed inventory."""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from check_core_lock import ROOT, normalized, read_pinned_lock

FULL_RUNTIME_LOCK = Path("distribution/locks/full-macos-arm64-py311.txt")
FULL_BUILD_LOCK = Path("distribution/locks/full-build-py311.txt")


def verify_full_lock(root=ROOT):
    inventory = json.loads((root / "distribution/full-package-inventory.json").read_text())
    if inventory.get("platform") != {"system": "Darwin", "architecture": "arm64", "python": "3.11", "minimum_macos": "15.0"}:
        raise ValueError("full lock platform changed; review installer compatibility explicitly")
    if inventory.get("source_build_policy") != {"allowed_source_packages": ["pims"], "build_isolation": False, "cache": False}:
        raise ValueError("full source build policy changed; review the installer explicitly")
    groups = {}
    for key, relative in [("runtime_packages", FULL_RUNTIME_LOCK), ("build_packages", FULL_BUILD_LOCK)]:
        expected = {}
        sources = set()
        for record in inventory[key]:
            name = normalized(record["name"])
            if name in expected:
                raise ValueError(f"duplicate inventory package: {name}")
            expected[name] = (record["version"], record["sha256"])
            parsed = urlparse(record["url"])
            if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org" or Path(parsed.path).name != record["filename"]:
                raise ValueError(f"unreviewed distribution source: {name}")
            if record["kind"] == "sdist" and record["filename"].endswith(".tar.gz"):
                sources.add(name)
            elif record["kind"] != "wheel" or not record["filename"].endswith(".whl"):
                raise ValueError(f"unexpected distribution format: {name}")
        if sources != ({"pims"} if key == "runtime_packages" else set()):
            raise ValueError("only the reviewed PIMS source distribution may be built")
        if not expected or read_pinned_lock(root / relative) != expected:
            raise ValueError(f"{key} lock differs from the reviewed inventory")
        groups[key] = expected
    if set(groups["build_packages"]) != {"pip", "setuptools", "wheel"} or set(groups["runtime_packages"]) & set(groups["build_packages"]):
        raise ValueError("PIMS build tools must be exactly pip, setuptools and wheel, separate from runtime")
    for name in ("requirements-core.txt", "requirements-full.txt"):
        path = root / "skills/scientific-data-analysis" / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != inventory["requirements_sha256"][name]:
            raise ValueError(f"{name} changed; explicitly re-resolve and review the full lock")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or (name == "requirements-full.txt" and line == "-r requirements-core.txt"):
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", line) or normalized(line) not in groups["runtime_packages"]:
                raise ValueError(f"full requirement is missing or changed format: {line}")
    return {key: len(value) for key, value in groups.items()}


if __name__ == "__main__":
    try:
        counts = verify_full_lock()
        print(f"Full lock verified: {counts['runtime_packages']} runtime packages and {counts['build_packages']} build tools.")
    except (OSError, KeyError, ValueError) as error:
        raise SystemExit(f"Full lock check failed: {error}")
