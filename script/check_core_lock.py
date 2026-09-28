#!/usr/bin/env python3
"""Check that the core lock matches the reviewed wheel inventory and core requirements."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pinned_lock(lock):
    actual = {}
    for line in lock.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.+-]+) --hash=sha256:([a-f0-9]{64})", line)
        if not match:
            raise ValueError("lock entries must pin one package version and one reviewed distribution hash")
        name = normalized(match[1])
        if name in actual:
            raise ValueError(f"duplicate lock package: {name}")
        actual[name] = (match[2], match[3])
    return actual


def verify_core_lock(root=ROOT):
    inventory = json.loads((root / "distribution/core-wheel-inventory.json").read_text())
    expected = {}
    for record in inventory["runtime_packages"]:
        name = normalized(record["name"])
        if name in expected:
            raise ValueError(f"duplicate inventory package: {name}")
        expected[name] = (record["version"], record["sha256"])
    actual = read_pinned_lock(root / "distribution/locks/core-macos-arm64-py311.txt")
    if not actual or actual != expected:
        raise ValueError("core lock differs from the reviewed wheel inventory")
    requirements = root / "skills/scientific-data-analysis/requirements-core.txt"
    for line in requirements.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", line):
            raise ValueError("core requirement format changed; review the lock explicitly")
        if normalized(line) not in actual:
            raise ValueError(f"core requirement is missing from lock: {line}")
    return len(actual)


if __name__ == "__main__":
    try:
        print(f"Core lock verified: {verify_core_lock()} runtime packages.")
    except (OSError, KeyError, ValueError) as error:
        raise SystemExit(f"Core lock check failed: {error}")
