"""Canonical path-overlap checks for non-destructive public CLI preflights."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


MAX_DIRECTORY_SCAN_ENTRIES = 100_000


class PathSafetyError(RuntimeError):
    """Raised before execution when requested outputs could modify protected data."""


@dataclass(frozen=True)
class PathOperand:
    label: str
    path: Path | None
    tree: bool = False


def operand(label: str, value: str | Path | None, *, tree: bool = False) -> PathOperand:
    """Describe one optional input or output path for strict maintainer preflights."""
    if value is None or str(value).strip() == "":
        return PathOperand(label=label, path=None, tree=tree)
    return PathOperand(label=label, path=Path(value).expanduser(), tree=tree)


def canonical_path(path: str | Path) -> Path:
    """Resolve existing symlinks and normalize a possibly not-yet-created path."""
    expanded = Path(path).expanduser()
    try:
        return expanded.resolve(strict=False)
    except (OSError, RuntimeError):
        return Path(os.path.abspath(str(expanded)))


def path_is_within(path: str | Path, directory: str | Path) -> bool:
    candidate = canonical_path(path)
    root = canonical_path(directory)
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def paths_alias(left: str | Path, right: str | Path) -> bool:
    """Return True for lexical, normalized, hard-link, or symlink aliases."""
    left_path = Path(left).expanduser()
    right_path = Path(right).expanduser()
    try:
        if left_path.exists() and right_path.exists() and left_path.samefile(right_path):
            return True
    except OSError:
        pass
    return canonical_path(left_path) == canonical_path(right_path)


def hardlink_aliases_directory_member(
    output: str | Path,
    directory: str | Path,
    *,
    max_entries: int = MAX_DIRECTORY_SCAN_ENTRIES,
) -> bool:
    """Detect an output hard-linked to a protected tree member.

    The scan runs only for an existing multiply-linked output. If the bounded
    scan cannot prove safety, it returns True and therefore fails closed.
    """
    output_path = Path(output).expanduser()
    directory_path = Path(directory).expanduser()
    try:
        output_stat = output_path.stat()
        if output_stat.st_nlink <= 1 or not directory_path.is_dir():
            return False
    except OSError:
        return False

    output_identity = (output_stat.st_dev, output_stat.st_ino)
    scanned = 0
    walk_errors: list[OSError] = []
    try:
        for current, directories, files in os.walk(
            directory_path,
            followlinks=False,
            onerror=walk_errors.append,
        ):
            for name in [*directories, *files]:
                scanned += 1
                if scanned > max_entries:
                    return True
                candidate = Path(current) / name
                try:
                    candidate_stat = candidate.stat()
                except OSError:
                    continue
                if (candidate_stat.st_dev, candidate_stat.st_ino) == output_identity:
                    return True
    except OSError:
        return True
    return bool(walk_errors)


def _tree_link_identities(
    directory: str | Path,
    *,
    max_entries: int = MAX_DIRECTORY_SCAN_ENTRIES,
) -> tuple[set[tuple[int, int]], bool]:
    """Return multiply-linked file identities and whether a bounded scan truncated."""
    identities: set[tuple[int, int]] = set()
    scanned = 0
    walk_errors: list[OSError] = []
    try:
        for current, directories, files in os.walk(
            Path(directory).expanduser(),
            followlinks=False,
            onerror=walk_errors.append,
        ):
            for name in [*directories, *files]:
                scanned += 1
                if scanned > max_entries:
                    return identities, True
                candidate = Path(current) / name
                try:
                    candidate_stat = candidate.stat()
                except OSError:
                    continue
                if candidate_stat.st_nlink > 1 and candidate.is_file():
                    identities.add((candidate_stat.st_dev, candidate_stat.st_ino))
    except OSError:
        return identities, True
    return identities, bool(walk_errors)


def output_tree_aliases_input(
    output_tree: str | Path,
    protected_input: str | Path,
    *,
    max_entries: int = MAX_DIRECTORY_SCAN_ENTRIES,
) -> bool:
    """Detect hard-linked members shared by an output tree and protected input."""
    output_path = Path(output_tree).expanduser()
    input_path = Path(protected_input).expanduser()
    try:
        if not output_path.is_dir():
            return False
    except OSError:
        return False

    output_identities, output_truncated = _tree_link_identities(
        output_path,
        max_entries=max_entries,
    )
    if output_truncated:
        return True
    if not output_identities:
        return False

    try:
        input_is_directory = input_path.is_dir()
    except OSError:
        input_is_directory = False
    if not input_is_directory:
        try:
            input_stat = input_path.stat()
        except OSError:
            return False
        return (input_stat.st_dev, input_stat.st_ino) in output_identities

    input_identities, input_truncated = _tree_link_identities(
        input_path,
        max_entries=max_entries,
    )
    return input_truncated or bool(output_identities & input_identities)


def output_overlaps_input(output: str | Path, protected_input: str | Path) -> bool:
    """Protect an input itself and, for directory/package inputs, its full tree."""
    if paths_alias(output, protected_input):
        return True
    input_path = Path(protected_input).expanduser()
    try:
        is_directory_input = input_path.is_dir()
    except OSError:
        is_directory_input = False
    if is_directory_input and (
        path_is_within(output, input_path)
        or hardlink_aliases_directory_member(output, input_path)
    ):
        return True
    return output_tree_aliases_input(output, input_path)


def find_output_input_collisions(
    inputs: Iterable[tuple[str, str | Path | None]],
    outputs: Iterable[tuple[str, str | Path | None]],
) -> list[dict[str, str]]:
    """Describe every requested output that aliases or enters a protected input."""
    protected = [(label, path) for label, path in inputs if path is not None]
    requested = [(label, path) for label, path in outputs if path is not None]
    collisions: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for flag, output in requested:
        for input_label, input_path in protected:
            if not output_overlaps_input(output, input_path):
                continue
            key = (flag, input_label, str(canonical_path(output)))
            if key in seen:
                continue
            seen.add(key)
            collisions.append(
                {
                    "flag": flag,
                    "input": input_label,
                    "input_path": str(canonical_path(input_path)),
                    "output_path": str(canonical_path(output)),
                }
            )
    for index, (left_label, left_path) in enumerate(requested):
        for right_label, right_path in requested[index + 1 :]:
            if not paths_alias(left_path, right_path):
                continue
            key = (left_label, right_label, str(canonical_path(left_path)))
            if key in seen:
                continue
            seen.add(key)
            collisions.append(
                {
                    "flag": left_label,
                    "input": right_label,
                    "input_path": str(canonical_path(right_path)),
                    "output_path": str(canonical_path(left_path)),
                    "collision_kind": "output_output_alias",
                }
            )
    return collisions


def _operand_is_tree(item: PathOperand) -> bool:
    if item.tree:
        return True
    if item.path is None:
        return False
    try:
        return item.path.is_dir()
    except OSError:
        return False


def ensure_safe_paths(
    *,
    inputs: Sequence[PathOperand],
    outputs: Sequence[PathOperand],
) -> None:
    """Fail closed if any requested output aliases or overlaps protected operands."""
    protected = [item for item in inputs if item.path is not None]
    requested = [item for item in outputs if item.path is not None]
    collisions: list[str] = []

    for output in requested:
        assert output.path is not None
        output_is_tree = _operand_is_tree(output)
        for source in protected:
            assert source.path is not None
            source_is_tree = _operand_is_tree(source)
            overlaps = paths_alias(output.path, source.path)
            if source_is_tree and not overlaps:
                overlaps = path_is_within(output.path, source.path)
                if not overlaps:
                    overlaps = hardlink_aliases_directory_member(output.path, source.path)
            if output_is_tree and not overlaps:
                overlaps = path_is_within(source.path, output.path)
                if not overlaps:
                    overlaps = output_tree_aliases_input(output.path, source.path)
            if overlaps:
                collisions.append(
                    f"{output.label} ({canonical_path(output.path)}) conflicts with "
                    f"{source.label} ({canonical_path(source.path)})"
                )

    for index, left in enumerate(requested):
        assert left.path is not None
        for right in requested[index + 1 :]:
            assert right.path is not None
            overlaps = paths_alias(left.path, right.path)
            if overlaps:
                collisions.append(
                    f"{left.label} ({canonical_path(left.path)}) conflicts with "
                    f"{right.label} ({canonical_path(right.path)})"
                )

    if collisions:
        detail = "; ".join(dict.fromkeys(collisions))
        raise PathSafetyError(f"Unsafe path collision blocked before execution: {detail}")
