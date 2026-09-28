#!/usr/bin/env python3
"""Registry helpers for the public surface of scientific-data-analysis."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - used on minimal Python installs.
    yaml = None


VISIBLE_BLOCK_ORDER = [
    "core / routing",
    "astronomy observational",
    "documents + reporting",
    "notebooks + cross-domain",
]

DEFAULT_MAX_REGISTRY_DEPTH = 8


def registry_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return Path(__file__).resolve().parents[2] / "public_surface_registry.yaml"


def _coerce_scalar(value: str):
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        return [item.strip() for item in value[1:-1].split(",") if item.strip()]
    return value


def _load_registry_without_yaml(path: Path) -> dict[str, list[dict]]:
    top_level: dict[str, object] = {}
    entries: list[dict] = []
    current: dict | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped == "entries:":
            continue
        if stripped.startswith("- "):
            if current:
                entries.append(current)
            current = {}
            stripped = stripped[2:].strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if current is None:
            top_level[key.strip()] = _coerce_scalar(value)
            continue
        current[key.strip()] = _coerce_scalar(value)
    if current:
        entries.append(current)
    top_level["entries"] = entries
    return top_level


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _family_root_for(source: Path) -> Path:
    for candidate in source.parents:
        if (candidate / "scientific-data-analysis").is_dir() and (candidate / "scientific-data-maintainer").is_dir():
            return candidate.resolve()
    return source.parent.resolve()


def load_public_surface_registry(
    path: str | Path | None = None,
    *,
    max_depth: int = DEFAULT_MAX_REGISTRY_DEPTH,
    family_root: str | Path | None = None,
    _visited: set[Path] | None = None,
    _depth: int = 0,
) -> list[dict]:
    """Load a registry stub chain without escaping or cycling outside its family.

    ``family_root`` is inferred for the installed/editable five-skill layout and
    may be supplied explicitly by isolated tests. Canonical targets outside that
    boundary are rejected before they are read.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    requested = registry_path(path).expanduser().absolute()
    boundary = Path(family_root).expanduser().resolve() if family_root else _family_root_for(requested)
    source = requested.resolve()
    if not _is_within(source, boundary):
        raise ValueError(f"registry path escapes skill family: {source}")
    if _depth > max_depth:
        raise ValueError(f"canonical registry chain exceeds max depth {max_depth}: {source}")
    visited = set() if _visited is None else _visited
    if source in visited:
        chain = " -> ".join(str(item) for item in [*visited, source])
        raise ValueError(f"canonical registry cycle detected: {chain}")
    if not source.is_file():
        raise FileNotFoundError(f"public surface registry is missing: {source}")
    visited.add(source)

    payload = yaml.safe_load(source.read_text(encoding="utf-8")) if yaml is not None else _load_registry_without_yaml(source)
    payload = payload or {}
    if isinstance(payload, dict) and payload.get("canonical_registry"):
        canonical = Path(payload["canonical_registry"])
        if not canonical.is_absolute():
            canonical = requested.parent / canonical
        canonical = canonical.resolve()
        if not _is_within(canonical, boundary):
            raise ValueError(f"canonical registry target escapes skill family: {canonical}")
        return load_public_surface_registry(
            canonical,
            max_depth=max_depth,
            family_root=boundary,
            _visited=visited,
            _depth=_depth + 1,
        )
    entries = payload.get("entries", payload)
    if not isinstance(entries, list):
        raise ValueError("public_surface_registry.yaml must contain a top-level 'entries' list.")
    normalized = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("every public surface registry entry must be a mapping")
        item = dict(entry)
        capability_id = str(item.get("id", "")).strip()
        if not capability_id:
            raise ValueError("every public surface registry entry must have a non-empty id")
        if capability_id in seen_ids:
            raise ValueError(f"duplicate public surface registry id: {capability_id}")
        seen_ids.add(capability_id)
        item["id"] = capability_id
        item.setdefault("visible_block", "core / routing")
        item.setdefault("kind", "supporting_tool")
        item.setdefault("support_level", "stable")
        item.setdefault("platform", "portable")
        item.setdefault("requires_datanalysis", False)
        item.setdefault("preflight_mode", "none")
        item.setdefault("smoke_tier", "none")
        item.setdefault("label", item.get("id", "unknown"))
        item.setdefault("short_description", "")
        normalized.append(item)
    return normalized


def grouped_entries(entries: list[dict], include_maintainer: bool = False) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        if not include_maintainer and entry.get("kind") == "maintainer_only":
            continue
        groups[entry["visible_block"]].append(entry)
    for block in groups:
        groups[block] = sorted(groups[block], key=lambda item: (item.get("kind") != "golden_path", item["label"]))
    return groups


def coverage_matrix(entries: list[dict]) -> dict[str, list[dict]]:
    matrix: dict[str, list[dict]] = {"core": [], "full": [], "none": []}
    for entry in entries:
        tier = entry.get("smoke_tier", "none")
        if tier not in matrix:
            matrix[tier] = []
        matrix[tier].append(
            {
                "id": entry["id"],
                "label": entry["label"],
                "visible_block": entry["visible_block"],
                "kind": entry["kind"],
                "support_level": entry["support_level"],
                "preflight_mode": entry["preflight_mode"],
            }
        )
    for tier in matrix:
        matrix[tier] = sorted(matrix[tier], key=lambda item: (item["visible_block"], item["label"]))
    return matrix


def render_registry_snapshot(entries: list[dict], fmt: str = "markdown") -> str:
    groups = grouped_entries(entries)
    if fmt == "markdown":
        lines = [
            "_This snapshot is generated from `public_surface_registry.yaml`._",
            "_Compact v2.5 form: labels and routing metadata only; keep full descriptions in the registry._",
            "",
        ]
        for block in VISIBLE_BLOCK_ORDER:
            block_entries = groups.get(block, [])
            if not block_entries:
                continue
            lines.append(f"### {block}")
            for entry in block_entries:
                lines.append(
                    f"- `{entry['label']}` [{entry['kind']}, {entry['support_level']}, smoke `{entry['smoke_tier']}`]"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    if fmt == "text":
        lines = [
            "This snapshot is generated from public_surface_registry.yaml.",
            "Compact text form: see references/public-surface-snapshot.md for descriptions.",
            "",
        ]
        for block in VISIBLE_BLOCK_ORDER:
            block_entries = groups.get(block, [])
            if not block_entries:
                continue
            lines.append(f"{block}:")
            for entry in block_entries:
                lines.append(
                    f"- {entry['label']} [{entry['kind']}, {entry['support_level']}, smoke {entry['smoke_tier']}]"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    if fmt == "release_text":
        lines = [
            "This compact release snapshot is generated from public_surface_registry.yaml.",
            f"Public capability labels: {len(entries)} entries.",
            "",
        ]
        for block in VISIBLE_BLOCK_ORDER:
            block_entries = groups.get(block, [])
            if not block_entries:
                continue
            labels = "; ".join(entry["label"] for entry in block_entries)
            lines.append(f"{block}: {labels}")
        return "\n".join(lines).rstrip() + "\n"
    raise ValueError(f"Unsupported snapshot format: {fmt}")
