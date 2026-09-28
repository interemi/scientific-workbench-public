#!/usr/bin/env python3
"""Read-only fidelity checks for professor-provided coursework notebooks."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload
from _internal.provenance_utils import sanitize_payload


FILENAME_PATTERN = re.compile(
    r"(?<![\w/.-])(?P<name>[\w.-]+\.(?:txt|csv|tsv|dat|fits|fit|fts|png|jpg|jpeg|html|htm|ipynb|py|md|pdf|tex))(?![\w/.-])",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(
    r"(^|\n)\s*(?:#+\s*)?(?:pregunta|question|ejercicio|exercise|apartado|task)\b|[?]",
    re.IGNORECASE,
)
EMPTY_ANSWER_PATTERN = re.compile(
    r"^\s*(?:respuesta|answer|todo|pendiente|completar|rellenar|your answer|write here)\s*:?\s*$",
    re.IGNORECASE,
)
TRACEABILITY_WORD_PATTERN = re.compile(
    r"\b(?:manual|visual|estimated|estimate|estimad\w*|refined|refinad\w*|adopted|adoptad\w*|input|codex)\b",
    re.IGNORECASE,
)
PLOTLY_TEXT_PATTERN = re.compile(r"\b(?:plotly|pio\.renderers|go\.Figure|px\.)\b", re.IGNORECASE)
PLOTLY_HTML_PATTERN = re.compile(r"plotly|Plotly\.newPlot|application/vnd\.plotly", re.IGNORECASE)
INPUT_TEXT_PATTERN = re.compile(r"\b(?:builtins\.)?input\s*\(")
STATIC_VISUAL_MIME_PREFIXES = ("image/",)
STATIC_VISUAL_MIME_TYPES = {"application/pdf"}
STATIC_EXPORT_PATTERN = re.compile(r"\b(?:savefig|write_image|to_image)\s*\(", re.IGNORECASE)
FIGURE_CODE_PATTERN = re.compile(
    r"\b(?:plt\.|ax\.|imshow\s*\(|scatter\s*\(|plot\s*\(|errorbar\s*\(|go\.Figure|px\.|sns\.)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", help="Professor or coursework notebook to inspect without modifying it.")
    parser.add_argument(
        "--assignment-file",
        action="append",
        default=[],
        help="Optional assignment statement, README, or sidecar instructions to scan for auxiliary files. Repeat as needed.",
    )
    parser.add_argument("--report-md", help="Write a short Markdown report.")
    parser.add_argument("--summary-json", help="Write the standard JSON payload.")
    return parser.parse_args()


def emit_collision_only(args: argparse.Namespace, collisions: list[dict[str, str]]) -> int:
    message = "Refusing coursework-fidelity outputs that overlap the notebook or assignment inputs."
    payload = build_blocked_payload(
        "coursework_notebook_fidelity_check",
        message,
        notes=[
            "Read-only guard for professor-provided coursework notebooks.",
            "No report or summary was written and no source input was modified.",
        ],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "collisions": collisions,
        },
        inputs=[args.notebook, *list(args.assignment_file or [])],
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def preflight_output_safety(args: argparse.Namespace) -> int | None:
    inputs = [("notebook", args.notebook)]
    inputs.extend(
        (f"--assignment-file[{index}]", value)
        for index, value in enumerate(args.assignment_file, start=1)
    )
    outputs = [
        ("--report-md", args.report_md),
        ("--summary-json", args.summary_json),
    ]
    collisions = find_output_input_collisions(inputs, outputs)
    return emit_collision_only(args, collisions) if collisions else None


def emit_blocked(args: argparse.Namespace, message: str, error_type: str | None = None) -> int:
    payload = build_blocked_payload(
        "coursework_notebook_fidelity_check",
        message,
        notes=[
            "Read-only guard for professor-provided coursework notebooks.",
            "The checker did not modify the input notebook; fix the blocking input problem and rerun.",
        ],
        artifacts={"summary_json": args.summary_json, "report_md": args.report_md},
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "notebook": args.notebook,
            "assignment_files": args.assignment_file,
        },
        inputs=[args.notebook, *list(args.assignment_file or [])],
    )
    emit_payload(payload, args.summary_json)
    return 2


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(item) for item in source)
    return str(source or "")


def load_notebook(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(payload, dict) or "cells" not in payload:
        raise SystemExit(f"{path} is not notebook JSON.")
    return payload


def normalize_code_for_ast(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%") or stripped.startswith("!") or stripped.startswith("?"):
            continue
        kept.append(line)
    return "\n".join(kept)


def finding(code: str, severity: str, message: str, recommendation: str, cell_index: int | None = None, evidence: dict | None = None) -> dict:
    item = {
        "code": code,
        "severity": severity,
        "message": message,
        "recommendation": recommendation,
    }
    if cell_index is not None:
        item["cell_index"] = cell_index
    if evidence:
        item["evidence"] = evidence
    return item


def detect_input_calls(source: str, cell_index: int) -> list[dict]:
    cleaned = normalize_code_for_ast(source)
    if not cleaned.strip():
        return []
    try:
        tree = ast.parse(cleaned)
    except SyntaxError:
        if INPUT_TEXT_PATTERN.search(cleaned):
            return [{"cell_index": cell_index, "line": None, "prompt": None}]
        return []
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_input = isinstance(func, ast.Name) and func.id == "input"
        is_builtins_input = (
            isinstance(func, ast.Attribute)
            and func.attr == "input"
            and isinstance(func.value, ast.Name)
            and func.value.id == "builtins"
        )
        if not (is_input or is_builtins_input):
            continue
        prompt = None
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            prompt = node.args[0].value
        calls.append({"cell_index": cell_index, "line": getattr(node, "lineno", None), "prompt": prompt})
    return calls


def detect_interactive_inputs(cells: list[dict]) -> tuple[list[dict], list[dict]]:
    calls = []
    findings = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "code":
            continue
        calls.extend(detect_input_calls(source_text(cell), index))
    if calls:
        findings.append(
            finding(
                "interactive_input",
                "warning",
                "The notebook contains input() calls.",
                "Run only a copy, feed values with notebook_workbench.py execute-copy --input-value, and record every value in the answer or traceability table.",
                evidence={"calls": calls},
            )
        )
    return calls, findings


def output_contains_plotly(output: dict) -> bool:
    data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(data, dict):
        return False
    for key, value in data.items():
        if PLOTLY_HTML_PATTERN.search(str(key)):
            return True
        if key == "text/html":
            if isinstance(value, list):
                value = "".join(str(item) for item in value)
            if PLOTLY_HTML_PATTERN.search(str(value)):
                return True
    return False


def output_contains_static_visual(output: dict) -> bool:
    data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(data, dict):
        return False
    for key in data:
        if any(str(key).startswith(prefix) for prefix in STATIC_VISUAL_MIME_PREFIXES):
            return True
        if key in STATIC_VISUAL_MIME_TYPES:
            return True
    return False


def detect_plotly_portability(cells: list[dict]) -> tuple[list[dict], list[dict]]:
    plotly_cells = []
    renderer_cells = []
    output_cells = []
    static_output_cells = []
    static_export_cells = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "code":
            continue
        source = source_text(cell)
        if PLOTLY_TEXT_PATTERN.search(source):
            plotly_cells.append(index)
        if "pio.renderers.default" in source:
            renderer_cells.append(index)
        if any(output_contains_plotly(output) for output in cell.get("outputs", []) or []):
            output_cells.append(index)
        if any(output_contains_static_visual(output) for output in cell.get("outputs", []) or []):
            static_output_cells.append(index)
        if STATIC_EXPORT_PATTERN.search(source):
            static_export_cells.append(index)
    findings = []
    if plotly_cells or output_cells:
        evidence = {
            "plotly_code_cells": plotly_cells,
            "plotly_output_cells": output_cells,
            "renderer_override_cells": renderer_cells,
            "static_visual_output_cells": static_output_cells,
            "static_export_cells": static_export_cells,
        }
        findings.append(
            finding(
                "plotly_portability",
                "warning",
                "Plotly or HTML/JS visual outputs are present; a saved notebook can be valid while a user's viewer still shows a blank box.",
                "Verify the visual output in the target viewer. If it is blank, add a static PNG/Matplotlib fallback or a robust exported image; changing only pio.renderers.default is not enough evidence.",
                evidence=evidence,
            )
        )
        if not static_output_cells and not static_export_cells:
            findings.append(
                finding(
                    "plotly_static_fallback_missing",
                    "warning",
                    "Plotly/HTML visuals were detected without an obvious static image output or export fallback.",
                    "Add or verify a Matplotlib/PNG/SVG fallback near the interactive cell before treating the notebook as portable.",
                    evidence=evidence,
                )
            )
    return plotly_cells + output_cells, findings


def excerpt(text: str, limit: int = 140) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "..."


def build_question_answer_map(cells: list[dict]) -> tuple[list[dict], list[dict]]:
    question_answer_map = []
    incomplete = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "markdown":
            continue
        text = source_text(cell).strip()
        if not QUESTION_PATTERN.search(text):
            continue

        answer_cell = None
        answer_status = "missing"
        answer_excerpt = ""
        for lookahead in range(index + 1, min(len(cells), index + 5) + 1):
            candidate = cells[lookahead - 1]
            if candidate.get("cell_type") != "markdown":
                continue
            candidate_text = source_text(candidate).strip()
            if QUESTION_PATTERN.search(candidate_text):
                break
            answer_cell = lookahead
            answer_excerpt = excerpt(candidate_text)
            if not candidate_text or EMPTY_ANSWER_PATTERN.match(candidate_text):
                answer_status = "empty"
            else:
                answer_status = "present"
            break

        entry = {
            "question_cell": index,
            "question_excerpt": excerpt(text),
            "answer_cell": answer_cell,
            "answer_status": answer_status,
            "answer_excerpt": answer_excerpt,
        }
        question_answer_map.append(entry)
        if answer_status != "present":
            incomplete.append(entry)

    findings = []
    if incomplete:
        findings.append(
            finding(
                "answer_map_incomplete",
                "warning",
                "One or more question-like cells do not have a nearby non-empty answer cell.",
                "Before delivery, map every question to a final answer cell and verify that the answer includes the relevant numerical result, interpretation, and limitation.",
                evidence={"incomplete": incomplete, "question_answer_map": question_answer_map},
            )
        )
    return question_answer_map, findings


def detect_answer_placeholders(cells: list[dict]) -> list[dict]:
    findings = []
    question_cells = []
    empty_answer_cells = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "markdown":
            continue
        text = source_text(cell).strip()
        if QUESTION_PATTERN.search(text):
            question_cells.append(index)
            for lookahead in range(index + 1, min(len(cells), index + 3) + 1):
                next_cell = cells[lookahead - 1]
                if next_cell.get("cell_type") != "markdown":
                    continue
                next_text = source_text(next_cell).strip()
                if not next_text or EMPTY_ANSWER_PATTERN.match(next_text):
                    empty_answer_cells.append(lookahead)
                break
        elif EMPTY_ANSWER_PATTERN.match(text):
            empty_answer_cells.append(index)
    if question_cells and empty_answer_cells:
        findings.append(
            finding(
                "empty_answer_cell",
                "warning",
                "Question-like markdown cells have nearby empty answer placeholders.",
                "Map every notebook question to its answer cell and verify that no answer placeholder remains empty in the final notebook.",
                evidence={"question_cells": question_cells, "empty_answer_cells": sorted(set(empty_answer_cells))},
            )
        )
    return findings


def detect_traceability_need(cells: list[dict], input_calls: list[dict]) -> tuple[dict, list[dict]]:
    all_text = "\n".join(source_text(cell) for cell in cells)
    traceability_signal = bool(input_calls or TRACEABILITY_WORD_PATTERN.search(all_text))
    markdown_text = "\n".join(source_text(cell) for cell in cells if cell.get("cell_type") == "markdown").lower()
    has_traceability = (
        ("traceability" in markdown_text or "trazabilidad" in markdown_text)
        and ("manual" in markdown_text or "visual" in markdown_text or "refinad" in markdown_text or "refined" in markdown_text)
    )
    result = {
        "traceability_required": traceability_signal,
        "traceability_table_detected": has_traceability,
    }
    findings = []
    if traceability_signal and not has_traceability:
        findings.append(
            finding(
                "traceability_missing",
                "warning",
                "The notebook appears to mix manual/visual/refined/Codex-mediated values but no explicit traceability table was detected.",
                "Add a compact table with: quantity, visual/manual value, notebook-refined value, Codex-added calculation, source cell/input value, and final adopted value.",
                evidence=result,
            )
        )
    return result, findings


def collect_named_files(text: str, base_dir: Path, origin: str) -> list[dict]:
    refs = []
    for match in FILENAME_PATTERN.finditer(text):
        name = match.group("name")
        if name.lower().startswith(("http", "www.")):
            continue
        path = (base_dir / name).resolve(strict=False)
        refs.append(
            {
                "name": name,
                "origin": origin,
                "resolved": str(path),
                "exists": path.exists(),
            }
        )
    return refs


def detect_auxiliary_references(cells: list[dict], notebook_dir: Path, assignment_files: list[Path]) -> tuple[list[dict], list[dict]]:
    refs = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") not in {"markdown", "code"}:
            continue
        refs.extend(collect_named_files(source_text(cell), notebook_dir, f"notebook_cell_{index}"))
    for path in assignment_files:
        if not path.exists():
            refs.append({"name": path.name, "origin": "assignment_file_argument", "resolved": str(path), "exists": False})
            continue
        refs.extend(collect_named_files(path.read_text(encoding="utf-8", errors="replace"), path.parent, f"assignment_file:{path.name}"))
    deduped = []
    seen = set()
    for ref in refs:
        key = (ref["name"], ref["origin"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    findings = []
    if deduped:
        findings.append(
            finding(
                "auxiliary_file_reference",
                "warning",
                "Notebook or assignment text references auxiliary files.",
                "Decide explicitly for each file whether it must be staged, executed, inserted conceptually, or cited; do not assume the main notebook already absorbed it.",
                evidence={"references": deduped},
            )
        )
    return deduped, findings


def detect_axis_variable_mismatch(cells: list[dict]) -> list[dict]:
    findings = []
    marker_pattern = re.compile(r"\b(?:axvline|vlines|add_vline)\s*\(\s*(?P<var>[A-Za-z_]\w*)")
    ro_axis_pattern = re.compile(r"(?:xlabel|set_xlabel|xaxis_title)\s*[=(]\s*['\"][^'\"]*\bRo\b", re.IGNORECASE)
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "code":
            continue
        source = source_text(cell)
        marker_vars = marker_pattern.findall(source)
        if ro_axis_pattern.search(source) and "p_sat" in marker_vars:
            findings.append(
                finding(
                    "axis_variable_mismatch",
                    "warning",
                    "A plotting cell labels the x axis as Ro but draws a saturation marker with p_sat.",
                    "Check copied plotting blocks: variables used for axes and reference lines should match the displayed axis, for example Ro_sat for a Ro axis.",
                    cell_index=index,
                    evidence={"marker_variables": marker_vars},
                )
            )
    return findings


def detect_visual_output_consistency(cells: list[dict]) -> list[dict]:
    risky_cells = []
    for index, cell in enumerate(cells, start=1):
        if cell.get("cell_type") != "code":
            continue
        source = source_text(cell)
        if not FIGURE_CODE_PATTERN.search(source):
            continue
        outputs = cell.get("outputs", []) or []
        has_visual_output = any(output_contains_plotly(output) or output_contains_static_visual(output) for output in outputs)
        has_static_export = bool(STATIC_EXPORT_PATTERN.search(source))
        if not has_visual_output and not has_static_export:
            risky_cells.append({"cell_index": index, "source_excerpt": excerpt(source)})
    if not risky_cells:
        return []
    return [
        finding(
            "figure_output_missing",
            "warning",
            "Figure-generating code cells were found without saved visual outputs or an obvious static export.",
            "If those cells affect the deliverable, re-execute them and save the resulting output before handing over the notebook.",
            evidence={"cells": risky_cells},
        )
    ]


def build_cleanup_policy() -> list[str]:
    return [
        "Keep the professor notebook as the canonical source unless the user asks for a rewritten solution.",
        "Create trial copies with clear names such as *_working.ipynb or *_executed_copy.ipynb.",
        "Keep the final deliverable distinct from HTML previews, scratch folders, and diagnostic exports.",
        "Before closing, list scratch artifacts and either ask the user or move them to Trash/archive according to the workspace policy.",
    ]


def render_markdown_report(results: dict) -> str:
    lines = [
        "# Coursework Notebook Fidelity Check",
        "",
        f"- Notebook: `{results['notebook']['path']}`",
        f"- Cells: {results['notebook']['cell_count']} total, {results['notebook']['code_cells']} code, {results['notebook']['markdown_cells']} markdown",
        f"- Findings: {len(results['findings'])}",
        "",
        "## Findings",
    ]
    if not results["findings"]:
        lines.append("- No fidelity warnings detected by the lightweight checker.")
    else:
        for item in results["findings"]:
            cell = f" cell {item['cell_index']}:" if "cell_index" in item else ""
            lines.append(f"- `{item['severity']}` `{item['code']}`{cell} {item['message']}")
            lines.append(f"  Recommendation: {item['recommendation']}")
    lines.extend(["", "## Question / Answer Map"])
    question_map = results["signals"].get("question_answer_map") or []
    if not question_map:
        lines.append("- No question-like markdown cells detected.")
    else:
        lines.append("| Question cell | Answer cell | Status | Question excerpt |")
        lines.append("| --- | --- | --- | --- |")
        for item in question_map:
            answer_cell = item["answer_cell"] if item["answer_cell"] is not None else "-"
            lines.append(
                f"| {item['question_cell']} | {answer_cell} | {item['answer_status']} | {item['question_excerpt']} |"
            )
    lines.extend(["", "## Final Delivery Checklist"])
    for item in results["final_delivery_checklist"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def inspect_coursework_notebook(notebook_path: Path, assignment_files: list[Path]) -> dict:
    notebook_path = notebook_path.resolve()
    notebook = load_notebook(notebook_path)
    cells = notebook.get("cells") or []
    findings = []

    input_calls, new_findings = detect_interactive_inputs(cells)
    findings.extend(new_findings)
    _, new_findings = detect_plotly_portability(cells)
    findings.extend(new_findings)
    question_answer_map, new_findings = build_question_answer_map(cells)
    findings.extend(new_findings)
    findings.extend(detect_answer_placeholders(cells))
    traceability, new_findings = detect_traceability_need(cells, input_calls)
    findings.extend(new_findings)
    auxiliary_refs, new_findings = detect_auxiliary_references(cells, notebook_path.parent, assignment_files)
    findings.extend(new_findings)
    findings.extend(detect_axis_variable_mismatch(cells))
    findings.extend(detect_visual_output_consistency(cells))

    return {
        "notebook": {
            "path": str(notebook_path),
            "cell_count": len(cells),
            "code_cells": sum(1 for cell in cells if cell.get("cell_type") == "code"),
            "markdown_cells": sum(1 for cell in cells if cell.get("cell_type") == "markdown"),
        },
        "signals": {
            "input_calls": input_calls,
            "auxiliary_references": auxiliary_refs,
            "traceability": traceability,
            "question_answer_map": question_answer_map,
        },
        "findings": findings,
        "final_delivery_checklist": [
            "Original professor notebook preserved or copied before execution.",
            "Auxiliary files from the assignment checked as staged, executed, inserted, or cited.",
            "Manual estimates, notebook-refined values, and Codex-added calculations separated in a traceability note.",
            "Plotly/HTML visuals verified in the target viewer or backed by static PNG/Matplotlib outputs.",
            "Every question maps to a non-empty answer cell in the final notebook.",
            "After any figure-code edit, the affected cells were re-executed and saved outputs match the code.",
            "Scratch copies, HTML previews, and temporary result folders were listed for cleanup or archive.",
        ],
    }


def main() -> None:
    args = parse_args()
    collision_status = preflight_output_safety(args)
    if collision_status is not None:
        raise SystemExit(collision_status)
    try:
        notebook_path = Path(args.notebook).expanduser()
        assignment_files = [Path(item).expanduser().resolve(strict=False) for item in args.assignment_file]
        results = inspect_coursework_notebook(notebook_path, assignment_files)
        report_path = Path(args.report_md).expanduser() if args.report_md else None
        artifacts = {"summary_json": args.summary_json}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_markdown_report(results), encoding="utf-8")
            artifacts["report_md"] = str(report_path)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        raise SystemExit(emit_blocked(args, str(exc.code), error_type="SystemExit")) from None
    except Exception as exc:
        raise SystemExit(emit_blocked(args, f"{exc.__class__.__name__}: {exc}", error_type=exc.__class__.__name__)) from None
    status = "warning" if results["findings"] else "ok"
    qa = {
        "status": "warning" if results["findings"] else "ok",
        "findings": [item["message"] for item in results["findings"]],
        "metrics": {
            "finding_count": len(results["findings"]),
            "input_call_count": len(results["signals"]["input_calls"]),
            "auxiliary_reference_count": len(results["signals"]["auxiliary_references"]),
            "question_answer_map_count": len(results["signals"]["question_answer_map"]),
            "incomplete_answer_count": sum(
                1 for item in results["signals"]["question_answer_map"] if item.get("answer_status") != "present"
            ),
        },
    }
    payload = build_tool_payload(
        "coursework_notebook_fidelity_check",
        status=status,
        notes=[
            "Read-only guard for professor-provided coursework notebooks.",
            "This check complements notebook_workbench.py; it does not execute or modify the notebook.",
        ],
        artifacts=artifacts,
        results=results,
        qa=qa,
        legacy=results,
    )
    emit_payload(payload, args.summary_json)


if __name__ == "__main__":
    main()
