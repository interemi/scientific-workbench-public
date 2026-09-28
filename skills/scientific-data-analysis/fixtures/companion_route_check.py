#!/usr/bin/env python3
"""Recommend installed Codex companion skills/plugins for a scientific-data-analysis task.

This tool is advisory only. It does not invoke plugins, read connector data, or
perform side effects. Its job is to keep companion routing explicit and auditable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import sanitize_payload
from _internal.public_contract import build_tool_payload


EXCLUDED_COMPANIONS = {
    "gmail": {
        "label": "Gmail",
        "reason": "Excluded from the v1.4 companion-routing integration by product decision.",
        "keywords": {"gmail", "email", "mail", "correo", "inbox"},
    },
    "google_drive": {
        "label": "Google Drive / Docs / Sheets / Slides",
        "reason": "Excluded from the v1.4 companion-routing integration by product decision.",
        "keywords": {"google drive", "drive", "google docs", "google sheets", "google slides"},
    },
    "zotero": {
        "label": "Zotero",
        "reason": "Excluded from the v1.4 companion-routing integration by product decision.",
        "keywords": {"zotero", "bibtex library", "biblioteca zotero"},
    },
}


COMPANION_RULES = [
    {
        "id": "pdf_visual_review",
        "companion": "pdf",
        "companion_type": "skill",
        "formats": {".pdf"},
        "keywords": {"pdf", "render", "layout", "visual", "pagina", "page", "revisar paginas"},
        "confidence": "high",
        "reason": "Use for layout-sensitive PDF reading, rendering, page screenshots, and visual QA.",
        "handoff": "scientific-data-analysis decides what needs scientific review; pdf renders or inspects pages when layout matters.",
        "cautions": ["Do not rely only on extracted text when figures, captions, or slide layout matter."],
    },
    {
        "id": "docx_format_roundtrip",
        "companion": "doc or Documents",
        "companion_type": "skill/plugin",
        "formats": {".docx", ".doc", ".docm", ".odt", ".rtf"},
        "keywords": {"docx", "word", "documento", "formato", "estilos", "render docx", "redline"},
        "confidence": "high",
        "reason": "Use for DOCX editing, format-sensitive readback, rendering, and marked fragment review.",
        "handoff": "scientific-data-analysis keeps scientific/reporting criteria; doc/Documents handles faithful document editing and visual verification.",
        "cautions": ["Work on copies and verify readback before treating edits as final."],
    },
    {
        "id": "presentation_deck_handoff",
        "companion": "Presentations",
        "companion_type": "plugin",
        "formats": {".pptx", ".ppt", ".pptm"},
        "keywords": {"pptx", "powerpoint", "deck", "slides", "diapositiva", "presentacion", "presentation"},
        "confidence": "high",
        "reason": "Use for creating, editing, rendering, and verifying editable presentation decks.",
        "handoff": "scientific-data-analysis prepares scientific figures, provenance, and narrative constraints; Presentations builds or edits the deck.",
        "cautions": ["Keep scientific figures as images, but titles, captions, arrows, labels, and text editable."],
    },
    {
        "id": "spreadsheet_workbook",
        "companion": "Spreadsheets",
        "companion_type": "plugin",
        "formats": {".xlsx", ".xls", ".xlsm", ".xlsb", ".ods"},
        "keywords": {"excel", "spreadsheet", "xlsx", "formulas", "graficos", "hoja de calculo"},
        "confidence": "high",
        "reason": "Use for workbooks with formulas, formatting, charts, tables, or recalculation needs.",
        "handoff": "scientific-data-analysis profiles and interprets data; Spreadsheets handles workbook-native edits and verification.",
        "cautions": ["For simple CSV profiling, use scientific-data-analysis first; escalate only when workbook semantics matter."],
    },
    {
        "id": "jupyter_notebook_authoring",
        "companion": "jupyter-notebook",
        "companion_type": "skill",
        "formats": {".ipynb"},
        "keywords": {"ipynb", "jupyter", "notebook", "celda", "cells", "kernel"},
        "confidence": "high",
        "reason": "Use for creating or editing notebooks cleanly while preserving notebook structure.",
        "handoff": "scientific-data-analysis defines scientific workflow and QA; jupyter-notebook scaffolds or edits notebook artifacts.",
        "cautions": ["Respect professor-provided notebooks; use copies for execution or structural edits."],
    },
    {
        "id": "browser_html_plotly_qa",
        "companion": "Browser Use / playwright",
        "companion_type": "plugin/skill",
        "formats": {".html", ".htm"},
        "keywords": {"html", "plotly", "localhost", "browser", "js", "javascript", "visor blanco", "cuadro blanco"},
        "confidence": "medium",
        "reason": "Use when HTML, Plotly, dashboards, local web previews, or JS-rendered outputs need visual verification.",
        "handoff": "scientific-data-analysis checks scientific intent; Browser Use or playwright verifies whether the rendered artifact is actually visible.",
        "cautions": ["If JS output remains blank, add a static PNG/Matplotlib fallback instead of only changing renderer settings."],
    },
    {
        "id": "latex_compile_fallback",
        "companion": "latex-tectonic",
        "companion_type": "plugin-if-active",
        "formats": {".tex", ".bib", ".sty"},
        "keywords": {"latex", "tex", "tectonic", "compile", "overleaf"},
        "confidence": "medium",
        "reason": "Use as a compact LaTeX compilation fallback when the bundled plugin is active and system LaTeX is unavailable.",
        "handoff": "scientific-data-analysis reviews/report-scaffolds LaTeX; latex-tectonic can compile in constrained environments.",
        "cautions": ["Prefer the local TeX toolchain when already available and stable."],
    },
    {
        "id": "visual_evidence_capture",
        "companion": "screenshot",
        "companion_type": "skill",
        "formats": set(),
        "keywords": {"screenshot", "captura", "pantalla", "window", "ventana"},
        "confidence": "medium",
        "reason": "Use for OS-level visual evidence when file renderers or app-specific previews are insufficient.",
        "handoff": "scientific-data-analysis decides what evidence is needed; screenshot captures the current visual state.",
        "cautions": ["Avoid using screenshots as substitutes for editable scientific deliverables."],
    },
    {
        "id": "oral_presentation_audio",
        "companion": "transcribe / speech",
        "companion_type": "skill",
        "formats": {".mp3", ".wav", ".m4a", ".mp4", ".mov"},
        "keywords": {"audio", "transcribe", "transcripcion", "voz", "guion oral", "voiceover", "narracion"},
        "confidence": "medium",
        "reason": "Use for oral-script material, transcription, voiceover drafts, or rehearsal assets.",
        "handoff": "scientific-data-analysis keeps scientific claims and slide intent; transcribe/speech handles audio text or narration.",
        "cautions": ["Do not let generated narration replace scientific verification of claims."],
    },
    {
        "id": "non_scientific_image_generation",
        "companion": "imagegen",
        "companion_type": "skill",
        "formats": {".png", ".jpg", ".jpeg", ".webp"},
        "keywords": {"ilustracion", "cover", "portada", "imagen generada", "bitmap", "mockup"},
        "confidence": "low",
        "reason": "Use only for non-data decorative or explanatory bitmap assets.",
        "handoff": "scientific-data-analysis must generate scientific figures from data; imagegen is only for non-scientific visuals.",
        "cautions": ["Never use generated imagery as a substitute for FITS, plots, diagnostics, or data-derived figures."],
    },
    {
        "id": "app_or_dashboard_build",
        "companion": "frontend-skill / build-web-apps",
        "companion_type": "skill/plugin-if-active",
        "formats": {".tsx", ".jsx", ".css"},
        "keywords": {"dashboard", "app", "web", "frontend", "react", "next.js", "interfaz"},
        "confidence": "low",
        "reason": "Use only when the scientific output needs to become an actual app or dashboard.",
        "handoff": "scientific-data-analysis produces validated data products; frontend tools build the interface around them.",
        "cautions": ["Do not turn a normal report or notebook task into an app by default."],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="", help="Short natural-language task description.")
    parser.add_argument("--file", action="append", default=[], help="Input file path or representative filename. Repeatable.")
    parser.add_argument("--format", action="append", default=[], help="Explicit format or extension hint. Repeatable.")
    parser.add_argument("--summary-json", help="Optional JSON summary output path.")
    return parser.parse_args()


def normalize_extension(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return ""
    if value.startswith("."):
        return value
    if "/" not in value and len(value) <= 8:
        return "." + value
    return Path(value).suffix.lower()


def collect_extensions(files: list[str], formats: list[str]) -> set[str]:
    extensions = set()
    for value in files + formats:
        extension = normalize_extension(value)
        if extension:
            extensions.add(extension)
    return extensions


def keyword_hits(text: str, keywords: set[str]) -> list[str]:
    lowered = text.lower()
    return sorted(keyword for keyword in keywords if keyword in lowered)


def build_recommendations(task: str, files: list[str], formats: list[str]) -> tuple[list[dict], list[dict]]:
    extensions = collect_extensions(files, formats)
    haystack = " ".join([task, *files, *formats]).lower()
    recommendations = []
    excluded_hits = []

    for companion_id, companion in EXCLUDED_COMPANIONS.items():
        hits = keyword_hits(haystack, companion["keywords"])
        if hits:
            excluded_hits.append(
                {
                    "id": companion_id,
                    "label": companion["label"],
                    "reason": companion["reason"],
                    "matched_keywords": hits,
                }
            )

    for rule in COMPANION_RULES:
        ext_hits = sorted(extensions & rule["formats"])
        hits = keyword_hits(haystack, rule["keywords"])
        if not ext_hits and not hits:
            continue
        score = len(ext_hits) * 2 + len(hits)
        recommendations.append(
            {
                "id": rule["id"],
                "companion": rule["companion"],
                "companion_type": rule["companion_type"],
                "confidence": rule["confidence"],
                "score": score,
                "matched_extensions": ext_hits,
                "matched_keywords": hits,
                "reason": rule["reason"],
                "handoff": rule["handoff"],
                "cautions": rule["cautions"],
            }
        )

    recommendations.sort(key=lambda item: (item["score"], item["confidence"] == "high"), reverse=True)
    return recommendations, excluded_hits


def render_payload(payload: dict) -> str:
    return json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"


def output_failure_payload(args: argparse.Namespace, message: str, payload: dict | None = None) -> int:
    results = {
        "task": args.task,
        "files": args.file,
        "formats": args.format,
        "detected_extensions": sorted(collect_extensions(args.file, args.format)),
        "recommendations": [],
        "excluded_by_policy": [],
        "error": message,
    }
    if payload:
        results["computed_status_before_output_failure"] = payload.get("status")
        results["computed_recommendation_count_before_output_failure"] = len(
            payload.get("results", {}).get("recommendations", [])
        )
    failure = build_tool_payload(
        "companion_route_check",
        status="fail",
        notes=[
            "Advisory companion routing only: this tool does not invoke plugins, read connector data, or open input files.",
            "The route check could not finish because the requested summary JSON could not be written.",
        ],
        artifacts={"summary_json": args.summary_json},
        results=results,
        qa={
            "status": "fail",
            "findings": [message],
            "metrics": {
                "recommendation_count": 0,
                "excluded_policy_hit_count": 0,
            },
        },
    )
    print(render_payload(failure), end="")
    return 2


def emit_companion_payload(payload: dict, args: argparse.Namespace) -> int:
    rendered = render_payload(payload)
    if args.summary_json:
        try:
            path = Path(args.summary_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_dir():
                return output_failure_payload(args, f"--summary-json points to a directory, not a file: {path}", payload)
            path.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            return output_failure_payload(args, f"Could not write --summary-json: {exc}", payload)
    print(rendered, end="")
    return 0


def emit_collision_only(args: argparse.Namespace, collisions: list[dict[str, str]]) -> int:
    message = "Refusing a companion-route summary that overlaps a supplied file hint."
    payload = build_tool_payload(
        "companion_route_check",
        status="blocked",
        notes=[
            message,
            "File hints remain read-only; no summary was written and no hinted file was modified.",
        ],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "files": args.file,
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(render_payload(payload), end="")
    return 2


def main() -> int:
    args = parse_args()
    collisions = find_output_input_collisions(
        [(f"--file[{index}]", value) for index, value in enumerate(args.file, start=1)],
        [("--summary-json", args.summary_json)],
    )
    if collisions:
        return emit_collision_only(args, collisions)
    recommendations, excluded_hits = build_recommendations(args.task, args.file, args.format)
    status = "ok" if recommendations else "warning"
    notes = [
        "Advisory companion routing only: this tool does not invoke plugins, read connector data, or open input files.",
        "Email, Google Drive, and Zotero routing are intentionally excluded from the v1.4 integration.",
        "Use scientific-data-analysis as the scientific/product owner; companion skills handle format-specific execution only when justified.",
    ]
    payload = build_tool_payload(
        "companion_route_check",
        status=status,
        notes=notes,
        artifacts={"summary_json": args.summary_json},
        results={
            "task": args.task,
            "files": args.file,
            "formats": args.format,
            "detected_extensions": sorted(collect_extensions(args.file, args.format)),
            "recommendations": recommendations,
            "excluded_by_policy": excluded_hits,
            "policy": {
                "automatic_decision": True,
                "automatic_plugin_invocation": False,
                "excluded_companions": [item["label"] for item in EXCLUDED_COMPANIONS.values()],
                "file_inputs_are_hints_only": True,
            },
        },
        qa={
            "status": "ok" if recommendations else "warning",
            "findings": [] if recommendations else ["No companion recommendation matched the supplied task or file hints."],
            "metrics": {
                "recommendation_count": len(recommendations),
                "excluded_policy_hit_count": len(excluded_hits),
            },
        },
    )
    return emit_companion_payload(payload, args)


if __name__ == "__main__":
    sys.exit(main())
