#!/usr/bin/env python3
"""Helpers for v1.8 app-ready run bundles."""

from __future__ import annotations

import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .provenance_utils import (
    public_path,
    sanitize_payload,
    typed_artifacts_from_legacy,
    write_manifest,
)


REQUIRED_DIRS = ("artifacts", "previews", "reports", "tables", "logs")
REQUIRED_FILES = ("manifest.json", "summary.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md")


@dataclass(frozen=True)
class RunBundleLayout:
    run_dir: Path
    manifest_json: Path
    summary_json: Path
    stdout_txt: Path
    stderr_txt: Path
    command_txt: Path
    next_steps_md: Path
    artifacts_dir: Path
    previews_dir: Path
    reports_dir: Path
    tables_dir: Path
    logs_dir: Path


def ensure_run_bundle(run_dir: str | Path) -> RunBundleLayout:
    root = Path(run_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    layout = RunBundleLayout(
        run_dir=root,
        manifest_json=root / "manifest.json",
        summary_json=root / "summary.json",
        stdout_txt=root / "stdout.txt",
        stderr_txt=root / "stderr.txt",
        command_txt=root / "command.txt",
        next_steps_md=root / "next_steps.md",
        artifacts_dir=root / "artifacts",
        previews_dir=root / "previews",
        reports_dir=root / "reports",
        tables_dir=root / "tables",
        logs_dir=root / "logs",
    )
    for directory in (layout.artifacts_dir, layout.previews_dir, layout.reports_dir, layout.tables_dir, layout.logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for placeholder in (layout.stdout_txt, layout.stderr_txt):
        if not placeholder.exists():
            placeholder.write_text("", encoding="utf-8")
    return layout


def add_run_bundle_argument(parser) -> None:
    parser.add_argument(
        "--run-dir",
        help=(
            "Optional v1.8 app-ready run bundle directory. When supplied, missing "
            "--summary-json/--manifest-json paths default to run/summary.json and run/manifest.json."
        ),
    )


def shell_join(argv: Iterable[object]) -> str:
    return " ".join(shlex.quote(str(item)) for item in argv)


def write_command_txt(layout: RunBundleLayout, argv: Iterable[object] | None = None, cwd: str | Path | None = None) -> None:
    argv = list(argv or sys.argv)
    cwd = Path(cwd or Path.cwd())
    lines = [
        f"cwd: {public_path(cwd)}",
        f"argv: {shell_join(argv)}",
        "",
    ]
    layout.command_txt.write_text("\n".join(lines), encoding="utf-8")


def run_bundle_artifacts(layout: RunBundleLayout) -> dict:
    return {
        "run_bundle": layout.run_dir,
        "summary_json": layout.summary_json,
        "manifest_json": layout.manifest_json,
        "stdout_txt": layout.stdout_txt,
        "stderr_txt": layout.stderr_txt,
        "command_txt": layout.command_txt,
        "next_steps_md": layout.next_steps_md,
    }


def augment_artifacts_with_run_bundle(artifacts: dict | None, layout: RunBundleLayout | None) -> dict:
    merged = dict(artifacts or {})
    if layout is not None:
        merged.update(run_bundle_artifacts(layout))
    return merged


def apply_run_bundle_defaults(
    args,
    *,
    output_attr: str | None = None,
    output_subdir: str = "artifacts",
) -> RunBundleLayout | None:
    raw_run_dir = getattr(args, "run_dir", None)
    if not raw_run_dir:
        return None
    layout = ensure_run_bundle(raw_run_dir)
    if hasattr(args, "summary_json") and not getattr(args, "summary_json", None):
        args.summary_json = str(layout.summary_json)
    if hasattr(args, "manifest_json") and not getattr(args, "manifest_json", None):
        args.manifest_json = str(layout.manifest_json)
    if output_attr and hasattr(args, output_attr) and not getattr(args, output_attr, None):
        destination = getattr(layout, f"{output_subdir}_dir", layout.artifacts_dir)
        setattr(args, output_attr, str(destination))
    try:
        setattr(args, "_run_bundle_layout", layout)
    except Exception:
        pass
    write_command_txt(layout)
    return layout


def _read_payload(summary_path: Path) -> dict | None:
    if not summary_path.exists():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _app_status(payload: dict) -> str:
    if payload.get("app_status"):
        return str(payload["app_status"])
    legacy = str(payload.get("status", "")).lower()
    return {
        "ok": "PASS",
        "pass": "PASS",
        "success": "PASS",
        "warning": "WARNING",
        "blocked": "BLOCKED_CONTROLADO",
        "fail": "FAIL",
        "failed": "FAIL",
        "error": "FAIL",
    }.get(legacy, "WARNING")


def _next_action_lines(payload: dict) -> list[str]:
    app_status = _app_status(payload)
    lines = [
        "# Next Steps",
        "",
        f"- Status: `{app_status}`",
        f"- Tool: `{payload.get('tool', 'unknown')}`",
        "",
    ]
    warnings = payload.get("warnings") or []
    errors = payload.get("errors") or []
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings[:12])
        lines.append("")
    if errors:
        lines.extend(["## Errors Or Blocks", ""])
        for item in errors[:12]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('message', item)}")
            else:
                lines.append(f"- {item}")
        lines.append("")
    actions = payload.get("next_actions") or []
    if actions:
        lines.extend(["## Suggested Actions", ""])
        for action in actions:
            if isinstance(action, dict):
                label = action.get("label") or action.get("kind") or "Review result"
                priority = action.get("priority")
                suffix = f" (`{priority}`)" if priority else ""
                lines.append(f"- {label}{suffix}")
            else:
                lines.append(f"- {action}")
    else:
        lines.extend(["## Suggested Actions", "", "- Review `summary.json` and generated artifacts."])
    lines.append("")
    return lines


def write_next_steps_md(layout: RunBundleLayout, payload: dict) -> None:
    layout.next_steps_md.write_text("\n".join(_next_action_lines(payload)), encoding="utf-8")


def update_payload_for_run_bundle(payload: dict, layout: RunBundleLayout, *, returncode: int | None = None) -> dict:
    enriched = dict(payload or {})
    artifact_map = enriched.get("artifacts") if isinstance(enriched.get("artifacts"), dict) else {}
    artifact_map = augment_artifacts_with_run_bundle(artifact_map, layout)
    typed_artifacts = typed_artifacts_from_legacy(artifact_map)
    enriched["artifacts"] = sanitize_payload(artifact_map)
    enriched["typed_artifacts"] = typed_artifacts
    enriched["outputs"] = typed_artifacts
    enriched.setdefault("contract_version", "1.8")
    enriched.setdefault("original_modified", False)
    enriched["run_bundle"] = sanitize_payload(
        {
            "path": public_path(layout.run_dir),
            "returncode": returncode,
            "required_files": list(REQUIRED_FILES),
            "required_dirs": list(REQUIRED_DIRS),
        }
    )
    return sanitize_payload(enriched)


def finalize_existing_run_bundle(layout: RunBundleLayout, payload: dict, *, returncode: int | None = None) -> dict:
    enriched = update_payload_for_run_bundle(payload, layout, returncode=returncode)
    write_next_steps_md(layout, enriched)
    layout.summary_json.write_text(json.dumps(enriched, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    child_manifest = _read_payload(layout.manifest_json)
    write_run_manifest(
        layout,
        payload=enriched,
        command=list(sys.argv),
        returncode=returncode,
        child_manifest=child_manifest,
    )
    return enriched


def write_run_manifest(
    layout: RunBundleLayout,
    *,
    payload: dict | None = None,
    command: list[str] | None = None,
    returncode: int | None = None,
    child_manifest: dict | None = None,
) -> dict:
    outputs = [
        layout.summary_json,
        layout.manifest_json,
        layout.stdout_txt,
        layout.stderr_txt,
        layout.command_txt,
        layout.next_steps_md,
    ]
    for item in (payload or {}).get("typed_artifacts", []) or []:
        raw_path = item.get("path") if isinstance(item, dict) else None
        if raw_path and not str(raw_path).startswith("~"):
            outputs.append(Path(raw_path))
    return write_manifest(
        layout.manifest_json,
        inputs=[],
        outputs=outputs,
        parameters={
            "contract": "v1.8 run bundle",
            "returncode": returncode,
            "required_files": list(REQUIRED_FILES),
            "required_dirs": list(REQUIRED_DIRS),
        },
        command=shell_join(command or []),
        notes=[
            "This manifest describes the app-ready run bundle, not only the child tool outputs.",
            "Child tool provenance is preserved under extra.child_manifest when available.",
        ],
        extra={"child_manifest": child_manifest, "summary_app_status": (payload or {}).get("app_status")},
    )


def load_child_manifest(layout: RunBundleLayout) -> dict | None:
    return _read_payload(layout.manifest_json)


def load_summary(layout: RunBundleLayout) -> dict | None:
    return _read_payload(layout.summary_json)
