#!/usr/bin/env python3
"""Synchronize registry-backed public-surface snapshots across skill docs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _internal.public_contract import build_tool_payload
from _internal.provenance_utils import public_path
from maintainer_path_safety import PathSafetyError, ensure_safe_paths, operand


TARGETS = [
    {
        "path": "references/public-surface-snapshot.md",
        "format": "markdown",
        "start": "<!-- BEGIN GENERATED PUBLIC SURFACE SNAPSHOT -->",
        "end": "<!-- END GENERATED PUBLIC SURFACE SNAPSHOT -->",
    },
    {
        "path": "README.txt",
        "format": "text",
        "start": "BEGIN GENERATED PUBLIC SURFACE SNAPSHOT",
        "end": "END GENERATED PUBLIC SURFACE SNAPSHOT",
    },
    {
        "path": "RELEASE-v1.txt",
        "format": "release_text",
        "start": "BEGIN GENERATED PUBLIC SURFACE SNAPSHOT",
        "end": "END GENERATED PUBLIC SURFACE SNAPSHOT",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="Optional registry YAML path.")
    parser.add_argument("--check", action="store_true", help="Check for drift without writing files.")
    parser.add_argument("--summary-json", help="Optional summary JSON path.")
    return parser.parse_args()


def replace_between_markers(text: str, start_marker: str, end_marker: str, content: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Missing or misordered markers: {start_marker} / {end_marker}")
    start_content = start + len(start_marker)
    return text[:start_content] + "\n" + content.rstrip() + "\n" + text[end:]


def emit_payload_safely(payload: dict, summary_json: str | None = None, *, full_stdout: bool = True) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if summary_json:
        target = Path(summary_json)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(
                f"Could not write summary JSON to {public_path(target)}: {exc.__class__.__name__}: {exc}"
            ) from None
    if full_stdout:
        print(rendered, end="")
    else:
        print(json.dumps(payload["results"], indent=2, ensure_ascii=True))


def build_failure_payload(args: argparse.Namespace, exc: Exception, *, blocked: bool = False) -> dict:
    root = Path(__file__).resolve().parent.parent
    return build_tool_payload(
        "sync_public_surface_docs",
        status="blocked" if blocked else "fail",
        notes=[
            "The public surface snapshot is derived from public_surface_registry.yaml.",
            (
                "The sync/check operation was blocked before writing because an output could overlap an input."
                if blocked
                else "The sync/check operation failed before it could complete cleanly."
            ),
        ],
        artifacts={} if blocked else {"summary_json": args.summary_json},
        results={
            "check_mode": args.check,
            "registry": public_path(args.registry or (root / "public_surface_registry.yaml")),
            "targets": [public_path(root / item["path"]) for item in TARGETS],
            "drifted_targets": [],
            "touched_targets": [],
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
        qa={
            "status": "blocked" if blocked else "fail",
            "findings": [
                {
                    "severity": "high",
                    "title": "sync_public_surface_docs blocked" if blocked else "sync_public_surface_docs failed",
                    "detail": str(exc),
                }
            ],
            "metrics": {"target_count": len(TARGETS), "drift_count": 0},
        },
    )


def ensure_sync_paths(args: argparse.Namespace) -> Path:
    """Validate all registry, snapshot, and summary paths before doc writes."""

    root = Path(__file__).resolve().parent.parent
    registry = Path(args.registry).expanduser() if args.registry else root / "public_surface_registry.yaml"
    targets = [root / target["path"] for target in TARGETS]
    if args.check:
        inputs = [
            operand("--registry", registry, tree=registry.is_dir()),
            *(operand(f"snapshot target {path.name}", path) for path in targets),
        ]
        outputs = [operand("--summary-json", args.summary_json)]
    else:
        inputs = [operand("--registry", registry, tree=registry.is_dir())]
        outputs = [
            *(operand(f"snapshot target {path.name}", path) for path in targets),
            operand("--summary-json", args.summary_json),
        ]
    ensure_safe_paths(inputs=inputs, outputs=outputs)
    return root


def run_sync(args: argparse.Namespace) -> tuple[dict, int]:
    from _internal.public_surface_registry import load_public_surface_registry, render_registry_snapshot

    root = ensure_sync_paths(args)
    entries = load_public_surface_registry(args.registry)
    touched = []
    drift = []
    for target in TARGETS:
        path = root / target["path"]
        current = path.read_text(encoding="utf-8")
        rendered = render_registry_snapshot(entries, fmt=target["format"])
        updated = replace_between_markers(current, target["start"], target["end"], rendered)
        if current != updated:
            drift.append(public_path(path))
            if not args.check:
                path.write_text(updated, encoding="utf-8")
                touched.append(public_path(path))
    status = "fail" if drift and args.check else "ok"
    notes = [
        "The public surface snapshot is derived from public_surface_registry.yaml.",
    ]
    if args.check and drift:
        notes.append("Documentation drift was detected between the registry and one or more derived sections.")
    payload = build_tool_payload(
        "sync_public_surface_docs",
        status=status,
        notes=notes,
        artifacts={"summary_json": args.summary_json},
        results={
            "check_mode": args.check,
            "registry": public_path(args.registry or (root / "public_surface_registry.yaml")),
            "targets": [public_path(root / item["path"]) for item in TARGETS],
            "drifted_targets": drift,
            "touched_targets": touched,
        },
        qa={
            "status": "warning" if drift and args.check else "ok",
            "findings": drift,
            "metrics": {"target_count": len(TARGETS), "drift_count": len(drift)},
        },
    )
    return payload, 1 if drift and args.check else 0


def main():
    args = parse_args()
    try:
        payload, exit_code = run_sync(args)
        emit_payload_safely(payload, args.summary_json, full_stdout=bool(args.summary_json))
    except Exception as exc:
        blocked = isinstance(exc, PathSafetyError)
        payload = build_failure_payload(args, exc, blocked=blocked)
        summary_target = None if blocked else args.summary_json
        try:
            emit_payload_safely(payload, summary_target, full_stdout=True)
        except Exception as emit_exc:
            payload["notes"].append(str(emit_exc))
            payload["results"]["summary_json_error"] = str(emit_exc)
            emit_payload_safely(payload, None, full_stdout=True)
        raise SystemExit(2 if blocked else 1) from None
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
