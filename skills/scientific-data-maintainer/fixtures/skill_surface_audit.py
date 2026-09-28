#!/usr/bin/env python3
"""Audit registry, routing docs, and maintainer hygiene for this skill."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

# The hygiene collector remains a mother-owned compatibility helper. Resolve
# it from the sibling skill instead of relying on a machine-specific path.
MOTHER_FIXTURES = Path(__file__).resolve().parents[2] / "scientific-data-analysis" / "fixtures"
if str(MOTHER_FIXTURES) not in sys.path:
    sys.path.insert(0, str(MOTHER_FIXTURES))

from _internal.public_contract import build_tool_payload
from _internal.provenance_utils import public_path
from maintainer_path_safety import PathSafetyError, ensure_safe_paths, operand
from skill_hygiene_check import collect_targets


VISIBLE_BLOCK_ORDER = [
    "core / routing",
    "astronomy observational",
    "documents + reporting",
    "notebooks + cross-domain",
]

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

REQUIRED_REGISTRY_FIELDS = {
    "id",
    "label",
    "script",
    "visible_block",
    "kind",
    "support_level",
    "platform",
    "requires_datanalysis",
    "preflight_mode",
    "smoke_tier",
    "short_description",
}
ALLOWED_KINDS = {"golden_path", "supporting_tool", "maintainer_only"}
ALLOWED_SUPPORT_LEVELS = {"stable", "narrow", "optional", "platform_bound"}
ALLOWED_PLATFORMS = {"portable", "macos", "datanalysis"}
ALLOWED_PREFLIGHT_MODES = {"none", "explicit", "inline"}
ALLOWED_SMOKE_TIERS = {"none", "core", "full"}
SCRIPT_REF_RE = re.compile(r"scripts/[A-Za-z0-9_./-]+\.py")


def default_audit_root() -> Path:
    family = Path(__file__).resolve().parents[2]
    mother = family / "scientific-data-analysis"
    return mother if mother.is_dir() else Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(default_audit_root()), help="Mother skill root to audit.")
    parser.add_argument(
        "--skip-hygiene",
        action="store_true",
        help="Skip generated-residue checks. Useful when called from smoke tests that intentionally write tmp outputs.",
    )
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    return parser.parse_args()


def replace_between_markers(text: str, start_marker: str, end_marker: str, content: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        return text
    start_content = start + len(start_marker)
    return text[:start_content] + "\n" + content.rstrip() + "\n" + text[end:]


def marker_problem(text: str, start_marker: str, end_marker: str) -> str | None:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 and end == -1:
        return "missing_markers"
    if start == -1:
        return "missing_start_marker"
    if end == -1:
        return "missing_end_marker"
    if end <= start:
        return "misordered_markers"
    return None


def find_doc_script_refs(root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    doc_paths = [root / "SKILL.md", root / "README.txt", root / "RELEASE-v1.txt"]
    doc_paths.extend(sorted((root / "references").glob("*.md")))
    for path in doc_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in SCRIPT_REF_RE.finditer(text):
            refs.setdefault(match.group(0), []).append(public_path(path))
    return refs


def snapshot_drift(root: Path, entries: list[dict]) -> list[dict]:
    from _internal.public_surface_registry import render_registry_snapshot

    drift = []
    for target in TARGETS:
        path = root / target["path"]
        if not path.exists():
            drift.append({"target": public_path(path), "reason": "missing_snapshot_target"})
            continue
        current = path.read_text(encoding="utf-8")
        marker_issue = marker_problem(current, target["start"], target["end"])
        if marker_issue:
            drift.append({"target": public_path(path), "reason": marker_issue})
            continue
        rendered = render_registry_snapshot(entries, fmt=target["format"])
        updated = replace_between_markers(current, target["start"], target["end"], rendered)
        if current != updated:
            drift.append({"target": public_path(path), "reason": "registry_snapshot_drift"})
    return drift


def audit_registry(root: Path, entries: list[dict]) -> tuple[list[dict], dict]:
    findings = []
    ids = Counter(str(entry.get("id", "")) for entry in entries)
    labels = Counter(str(entry.get("label", "")) for entry in entries)
    scripts = Counter(str(entry.get("script", "")) for entry in entries)

    for entry in entries:
        entry_id = entry.get("id", "<missing id>")
        missing = sorted(REQUIRED_REGISTRY_FIELDS - set(entry))
        if missing:
            findings.append({"severity": "high", "title": "Registry entry missing fields", "entry": entry_id, "detail": missing})
        checks = [
            ("visible_block", VISIBLE_BLOCK_ORDER),
            ("kind", ALLOWED_KINDS),
            ("support_level", ALLOWED_SUPPORT_LEVELS),
            ("platform", ALLOWED_PLATFORMS),
            ("preflight_mode", ALLOWED_PREFLIGHT_MODES),
            ("smoke_tier", ALLOWED_SMOKE_TIERS),
        ]
        for field, allowed in checks:
            value = entry.get(field)
            if value not in allowed:
                findings.append(
                    {
                        "severity": "high",
                        "title": "Registry entry has unsupported value",
                        "entry": entry_id,
                        "field": field,
                        "value": value,
                    }
                )
        script = entry.get("script")
        if script and not (root / script).exists():
            findings.append({"severity": "high", "title": "Registry script is missing", "entry": entry_id, "script": script})

    for label, counter, field in (("id", ids, "id"), ("label", labels, "label")):
        duplicates = sorted(item for item, count in counter.items() if item and count > 1)
        if duplicates:
            findings.append({"severity": "high", "title": f"Duplicate registry {label}", "field": field, "detail": duplicates})

    stats = {
        "entry_count": len(entries),
        "unique_script_count": len(scripts),
        "by_block": dict(Counter(entry.get("visible_block") for entry in entries)),
        "by_kind": dict(Counter(entry.get("kind") for entry in entries)),
        "by_smoke_tier": dict(Counter(entry.get("smoke_tier") for entry in entries)),
    }
    return findings, stats


def emit_payload_safely(payload: dict, summary_json: str | None = None) -> None:
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
    print(rendered, end="")


def build_failure_payload(args: argparse.Namespace, root: Path, exc: Exception, *, blocked: bool = False) -> dict:
    return build_tool_payload(
        "skill_surface_audit",
        status="blocked" if blocked else "fail",
        notes=[
            "Maintainer audit for routing, registry, generated snapshots, doc script references, and generated residue.",
            (
                "The audit was blocked before writing because its summary could overlap the audited root."
                if blocked
                else "The audit failed before it could complete cleanly."
            ),
        ],
        artifacts={} if blocked else {"summary_json": args.summary_json},
        results={
            "root": public_path(root),
            "snapshot_drift": [],
            "missing_doc_script_refs": [],
            "unregistered_script_count": 0,
            "unregistered_scripts": [],
            "doc_refs_not_in_registry_count": 0,
            "doc_refs_not_in_registry": [],
            "hygiene_candidate_count": 0,
            "hygiene_candidates": [],
            "skip_hygiene": bool(getattr(args, "skip_hygiene", False)),
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
        qa={
            "status": "blocked" if blocked else "fail",
            "findings": [
                {
                    "severity": "high",
                    "title": "skill_surface_audit blocked" if blocked else "skill_surface_audit failed",
                    "detail": str(exc),
                }
            ],
            "metrics": {
                "high_count": 1,
                "low_count": 0,
                "registry_entry_count": 0,
                "missing_doc_script_ref_count": 0,
                "snapshot_drift_count": 0,
                "hygiene_candidate_count": 0,
            },
        },
    )


def run_audit(args: argparse.Namespace) -> tuple[dict, int]:
    from _internal.public_surface_registry import load_public_surface_registry

    requested_root = Path(args.root).expanduser()
    ensure_safe_paths(
        inputs=[operand("--root", requested_root, tree=True)],
        outputs=[operand("--summary-json", args.summary_json)],
    )
    root = requested_root.resolve()
    if not root.exists() or not (root / "SKILL.md").exists():
        raise RuntimeError(f"Not a scientific-data-analysis skill root: {root}")

    entries = load_public_surface_registry(root / "public_surface_registry.yaml")
    registry_findings, registry_stats = audit_registry(root, entries)
    drift_findings = snapshot_drift(root, entries)

    refs = find_doc_script_refs(root)
    missing_doc_refs = sorted(ref for ref in refs if not (root / ref).exists())
    registry_scripts = {entry.get("script") for entry in entries}
    public_scripts = {f"scripts/{path.name}" for path in (root / "scripts").glob("*.py")}
    unregistered_scripts = sorted(public_scripts - registry_scripts - {"scripts/sync_public_surface_docs.py"})
    doc_refs_not_registry = sorted(set(refs) - registry_scripts)
    hygiene_targets = [] if args.skip_hygiene else collect_targets(root)

    findings = list(registry_findings)
    findings.extend({"severity": "high", **item} for item in drift_findings)
    for ref in missing_doc_refs:
        findings.append({"severity": "high", "title": "Documentation references a missing script", "script": ref, "sources": refs[ref]})
    if hygiene_targets:
        findings.append(
            {
                "severity": "low",
                "title": "Generated residue present",
                "detail": "Run scripts/skill_hygiene_check.py --clean before release or sync.",
                "count": len(hygiene_targets),
            }
        )

    high_count = sum(1 for item in findings if item.get("severity") == "high")
    low_count = sum(1 for item in findings if item.get("severity") == "low")
    status = "fail" if high_count else ("warning" if low_count else "ok")

    payload = build_tool_payload(
        "skill_surface_audit",
        status=status,
        notes=[
            "Maintainer audit for routing, registry, generated snapshots, doc script references, and generated residue.",
            "Unregistered scripts are reported as inventory, not as failures; many are intentionally deep, legacy, optional, or regression-only.",
        ],
        artifacts={"summary_json": args.summary_json},
        results={
            "root": public_path(root),
            "registry": registry_stats,
            "snapshot_drift": drift_findings,
            "missing_doc_script_refs": missing_doc_refs,
            "unregistered_script_count": len(unregistered_scripts),
            "unregistered_scripts": unregistered_scripts,
            "doc_refs_not_in_registry_count": len(doc_refs_not_registry),
            "doc_refs_not_in_registry": doc_refs_not_registry,
            "hygiene_candidate_count": len(hygiene_targets),
            "hygiene_candidates": hygiene_targets,
            "skip_hygiene": bool(args.skip_hygiene),
        },
        qa={
            "status": "ok" if status == "ok" else status,
            "findings": findings,
            "metrics": {
                "high_count": high_count,
                "low_count": low_count,
                "registry_entry_count": len(entries),
                "missing_doc_script_ref_count": len(missing_doc_refs),
                "snapshot_drift_count": len(drift_findings),
                "hygiene_candidate_count": len(hygiene_targets),
            },
        },
    )
    return payload, 1 if high_count else 0


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser()
    try:
        payload, exit_code = run_audit(args)
        emit_payload_safely(payload, args.summary_json)
    except Exception as exc:
        blocked = isinstance(exc, PathSafetyError)
        payload = build_failure_payload(args, root, exc, blocked=blocked)
        summary_target = None if blocked else args.summary_json
        try:
            emit_payload_safely(payload, summary_target)
        except Exception as emit_exc:
            payload["notes"].append(str(emit_exc))
            payload["results"]["summary_json_error"] = str(emit_exc)
            emit_payload_safely(payload, None)
        raise SystemExit(2 if blocked else 1) from None
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
