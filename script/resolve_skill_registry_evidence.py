#!/usr/bin/env python3
"""Resolve and fingerprint the installed Scientific Workbench registry chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


MAX_REGISTRY_DEPTH = 16
CANONICAL_PATTERN = re.compile(r"^canonical_registry\s*:\s*(.*?)\s*$")


class RegistryEvidenceError(RuntimeError):
    """Raised when the registry chain cannot provide trustworthy evidence."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise RegistryEvidenceError(
            f"registry path escapes the installed skills root: {path}"
        ) from exc


def decode_yaml_scalar(raw_value: str, source: Path) -> str:
    value = raw_value.strip()
    if not value:
        raise RegistryEvidenceError(f"empty canonical_registry in {source}")

    if value[0] in {'"', "'"}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise RegistryEvidenceError(
                f"malformed quoted canonical_registry in {source}"
            )
        if quote == '"':
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RegistryEvidenceError(
                    f"malformed quoted canonical_registry in {source}: {exc}"
                ) from exc
            if not isinstance(decoded, str):
                raise RegistryEvidenceError(
                    f"canonical_registry must be a string in {source}"
                )
            return decoded
        return value[1:-1].replace("''", "'")

    value = value.split(" #", 1)[0].strip()
    if not value:
        raise RegistryEvidenceError(f"empty canonical_registry in {source}")
    return value


def canonical_target(path: Path) -> str | None:
    matches: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RegistryEvidenceError(f"cannot read registry {path}: {exc}") from exc

    for line in lines:
        if line[:1].isspace() or line.lstrip().startswith("#"):
            continue
        match = CANONICAL_PATTERN.fullmatch(line)
        if match:
            matches.append(decode_yaml_scalar(match.group(1), path))

    if len(matches) > 1:
        raise RegistryEvidenceError(
            f"multiple top-level canonical_registry values in {path}"
        )
    return matches[0] if matches else None


def resolve_registry_evidence(skills_root: Path, mother_registry: Path) -> dict:
    try:
        resolved_root = skills_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise RegistryEvidenceError(
            f"installed skills root is unavailable: {skills_root}"
        ) from exc
    if not resolved_root.is_dir():
        raise RegistryEvidenceError(
            f"installed skills root is not a directory: {resolved_root}"
        )

    try:
        current = mother_registry.expanduser().resolve(strict=True)
    except OSError as exc:
        raise RegistryEvidenceError(
            f"mother-skill registry is unavailable: {mother_registry}"
        ) from exc

    chain: list[dict[str, str]] = []
    seen: set[Path] = set()
    for _ in range(MAX_REGISTRY_DEPTH):
        relative = relative_to_root(current, resolved_root)
        if current in seen:
            raise RegistryEvidenceError(
                f"canonical_registry cycle detected at {relative}"
            )
        seen.add(current)
        if not current.is_file():
            raise RegistryEvidenceError(f"registry is not a regular file: {current}")

        chain.append({"relative_path": relative, "sha256": sha256(current)})
        target = canonical_target(current)
        if target is None:
            break

        try:
            current = (current.parent / target).resolve(strict=True)
        except OSError as exc:
            raise RegistryEvidenceError(
                f"canonical registry target is unavailable from {relative}: {target}"
            ) from exc
        relative_to_root(current, resolved_root)
    else:
        raise RegistryEvidenceError(
            f"canonical_registry exceeds maximum depth {MAX_REGISTRY_DEPTH}"
        )

    first = chain[0]
    canonical = chain[-1]
    return {
        "skill_registry_chain": chain,
        "skill_registry_relative_path": canonical["relative_path"],
        "skill_registry_sha256": canonical["sha256"],
        "skill_registry_stub_sha256": first["sha256"],
    }


def default_skills_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve and fingerprint the canonical scientific skill registry."
    )
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--mother-registry", type=Path)
    args = parser.parse_args()

    skills_root = args.skills_root or default_skills_root()
    mother_registry = args.mother_registry or (
        skills_root / "scientific-data-analysis" / "public_surface_registry.yaml"
    )
    try:
        evidence = resolve_registry_evidence(skills_root, mother_registry)
    except RegistryEvidenceError as exc:
        parser.exit(1, f"registry evidence failed: {exc}\n")

    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
