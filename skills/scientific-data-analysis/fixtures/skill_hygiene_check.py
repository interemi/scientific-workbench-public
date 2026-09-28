#!/usr/bin/env python3
"""Audit and optionally clean generated maintenance residue in the skill tree."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path


ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
GENERATED_FILE_NAMES = {".DS_Store"}
GENERATED_SUFFIXES = {".pyc", ".pyo"}
ROOT_LATEX_ARTIFACT_SUFFIXES = {
    ".aux",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".synctex.gz",
    ".toc",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Skill root to inspect. Defaults to this skill directory.")
    parser.add_argument("--clean", action="store_true", help="Remove generated residue. Default is dry-run.")
    parser.add_argument("--summary-json", help="Optional JSON payload path.")
    return parser.parse_args()


def path_size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file() or item.is_symlink():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def collect_targets(root: Path) -> list[dict]:
    targets: dict[Path, dict] = {}

    tmp_dir = root / "tmp"
    if tmp_dir.exists() and any(tmp_dir.iterdir()):
        targets[tmp_dir] = {"kind": "directory", "reason": "generated_validation_tmp"}

    for path in root.rglob("*"):
        if path == tmp_dir or tmp_dir in path.parents:
            continue
        if any(parent.name in GENERATED_DIR_NAMES for parent in path.parents if parent != root):
            continue
        if path.is_dir() and path.name in GENERATED_DIR_NAMES:
            targets[path] = {"kind": "directory", "reason": path.name}
            continue
        if path.is_file():
            if path.name in GENERATED_FILE_NAMES:
                targets[path] = {"kind": "file", "reason": path.name}
            elif path.suffix in GENERATED_SUFFIXES:
                targets[path] = {"kind": "file", "reason": path.suffix}

    for path in root.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if any(name.endswith(suffix) for suffix in ROOT_LATEX_ARTIFACT_SUFFIXES):
            targets[path] = {"kind": "file", "reason": "root_latex_artifact"}

    rows = []
    for path, meta in sorted(targets.items(), key=lambda item: str(item[0])):
        rows.append(
            {
                "path": public_path(path),
                "kind": meta["kind"],
                "reason": meta["reason"],
                "size_bytes": path_size(path),
            }
        )
    return rows


def clean_targets(root: Path, rows: list[dict]) -> list[dict]:
    removed = []
    for row in rows:
        path = Path(row["path"]).expanduser()
        if not path.is_absolute():
            path = root / row["path"]
        if not is_relative_to(path, root):
            continue
        if not path.exists():
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
            removed.append(row)
        else:
            path.unlink()
            removed.append(row)
    (root / "tmp").mkdir(exist_ok=True)
    return removed


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not (root / "SKILL.md").exists():
        raise SystemExit(f"Not a scientific-data-analysis skill root: {root}")

    targets = collect_targets(root)
    total_bytes = sum(int(item["size_bytes"]) for item in targets)
    removed = clean_targets(root, targets) if args.clean else []
    status = "warning" if targets and not args.clean else "ok"
    action = "cleaned" if args.clean else "dry_run"
    findings = []
    if targets and not args.clean:
        findings.append(
            {
                "severity": "low",
                "title": "Generated residue present",
                "detail": "Run with --clean to remove tmp, __pycache__, .pyc, .pytest_cache, .DS_Store, and root LaTeX build residue.",
            }
        )
    payload = build_tool_payload(
        "skill_hygiene_check",
        status=status,
        notes=[
            "Maintainer hygiene check for generated local residue only.",
            "It does not remove source files, examples, references, registry entries, or installed dependencies.",
        ],
        artifacts={"summary_json": args.summary_json},
        results={
            "root": public_path(root),
            "action": action,
            "candidate_count": len(targets),
            "removed_count": len(removed),
            "reclaimable_bytes": total_bytes,
            "candidates": targets,
        },
        qa={
            "status": "warning" if findings else "ok",
            "findings": findings,
            "metrics": {
                "candidate_count": len(targets),
                "removed_count": len(removed),
                "reclaimable_bytes": total_bytes,
            },
        },
    )
    emit_payload(payload, args.summary_json)


if __name__ == "__main__":
    main()
