#!/usr/bin/env python3
"""Inspect and execute copied Jupyter notebooks without touching originals."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import shutil
import sys
import time
import traceback
import uuid
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime, find_executable

PATH_CALL_PATTERN = re.compile(r"""Path\(\s*(['"])(.+?)\1\s*\)""")
STRING_LITERAL_PATTERN = re.compile(
    r"""(?P<quote>['"])(?P<path>[^'"\n]+\.(?:fits|fit|fz|csv|tsv|txt|json|jsonl|pdf|png|jpg|jpeg|npy|npz|h5|hdf5))(?P=quote)""",
    re.IGNORECASE,
)
PLACEHOLDER_BASENAME_PATTERN = re.compile(r"^(?:imagen\d*|image\d*|example\d*|sample\d*|test\d*)(?:\.[^.]+)?$", re.IGNORECASE)
URL_LITERAL_PATTERN = re.compile(r"""https?://[^\s'"]+""", re.IGNORECASE)
INPUT_CALL_TEXT_PATTERN = re.compile(r"\b(?:builtins\.)?input\s*\(")
NETWORK_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "astroquery"}
OPTIONAL_BACKEND_RULES = [
    {
        "module": "pdf2image",
        "required_binaries": [("pdftoppm",), ("pdftocairo",)],
        "message": "pdf2image usually needs Poppler tools such as pdftoppm or pdftocairo on PATH.",
    }
]


def lazy_imports():
    configure_runtime("notebook_workbench")
    import nbformat
    from nbconvert.preprocessors import CellExecutionError, ExecutePreprocessor

    return nbformat, CellExecutionError, ExecutePreprocessor


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect", help="Inspect notebook structure and metadata.", allow_abbrev=False
    )
    inspect.add_argument("path")
    inspect.add_argument("--summary-json")
    inspect.add_argument("--manifest-json")

    preflight = subparsers.add_parser(
        "preflight-execution",
        help="Inspect notebook execution risks before running a copied notebook.",
        allow_abbrev=False,
    )
    preflight.add_argument("path")
    preflight.add_argument("--summary-json")
    preflight.add_argument("--manifest-json")

    execute = subparsers.add_parser(
        "execute-copy",
        help="Copy a notebook, optionally patch it, and execute the copy.",
        allow_abbrev=False,
    )
    execute.add_argument("path")
    execute.add_argument("--output-dir", required=True)
    execute.add_argument("--kernel-name", default="python3")
    execute.add_argument("--timeout-sec", type=int, default=900)
    execute.add_argument(
        "--trust-notebook-code",
        action="store_true",
        help=(
            "Explicitly confirm that the copied notebook's arbitrary code has been reviewed and trusted. "
            "Execution is blocked without this flag."
        ),
    )
    execute.add_argument(
        "--stage-extra",
        action="append",
        default=[],
        help="File or directory to copy into the notebook workspace before execution. Repeat as needed.",
    )
    execute.add_argument(
        "--append-code",
        action="append",
        default=[],
        help="Code cell text to append before execution. Repeat as needed.",
    )
    execute.add_argument(
        "--append-code-file",
        action="append",
        default=[],
        help="Path to a text file whose contents will be appended as a code cell. Repeat as needed.",
    )
    execute.add_argument(
        "--append-markdown",
        action="append",
        default=[],
        help="Markdown cell text to append before execution. Repeat as needed.",
    )
    execute.add_argument(
        "--cell-range",
        help="Optional 1-based inclusive range like `1:10`, `5:`, or `:12` to execute only a subset of cells.",
    )
    execute.add_argument(
        "--run-from-source-dir",
        action="store_true",
        help="Legacy unsafe mode; controlled execution now blocks instead of using the original source directory.",
    )
    execute.add_argument(
        "--cwd",
        help="Use an existing directory inside OUTPUT_DIR/_workspace as cwd; external directories are blocked.",
    )
    execute.add_argument(
        "--replace-text",
        action="append",
        nargs=2,
        metavar=("FIND", "REPLACE"),
        default=[],
        help="Literal text replacement to apply to notebook cell sources before execution. Repeat as needed.",
    )
    execute.add_argument(
        "--input-value",
        action="append",
        default=[],
        help=(
            "Value to feed sequentially to input() during copied execution. "
            "A temporary provider cell is executed but removed before the copied notebook is saved."
        ),
    )
    execute.add_argument("--summary-json")
    execute.add_argument("--manifest-json")

    return parser.parse_args()


def emit_collision_only(args, collisions: list[dict[str, str]]) -> int:
    message = "Refusing notebook workbench outputs that overlap protected notebook inputs."
    payload = standard_tool_payload(
        "notebook_workbench",
        status="blocked",
        notes=[message, "No notebook copy, summary, manifest, or workspace artifact was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "command": args.command,
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def emit_untrusted_execution_block(args) -> int:
    message = (
        "Notebook code execution is arbitrary code and cannot be proven non-destructive by path planning. "
        "Review the notebook and rerun with --trust-notebook-code only when you explicitly trust it."
    )
    payload = standard_tool_payload(
        "notebook_workbench",
        status="blocked",
        notes=[message, "Inspection and preflight-execution remain available without code execution."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "untrusted_notebook_code",
            "command": args.command,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": 1},
        },
        legacy={"blocked_reason": message},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True, allow_nan=False))
    return 2


def preflight_output_safety(args) -> int | None:
    inputs: list[tuple[str, str | Path | None]] = [("path", args.path)]
    outputs: list[tuple[str, str | Path | None]] = [
        ("--summary-json", getattr(args, "summary_json", None)),
        ("--manifest-json", getattr(args, "manifest_json", None)),
    ]
    if args.command == "execute-copy":
        inputs.extend((f"--stage-extra[{index}]", value) for index, value in enumerate(args.stage_extra, start=1))
        inputs.extend(
            (f"--append-code-file[{index}]", value)
            for index, value in enumerate(args.append_code_file, start=1)
        )
        output_dir = Path(args.output_dir).expanduser()
        workspace_dir = output_dir / "_workspace"
        outputs.extend(
            [
                ("--output-dir", output_dir),
                ("derived:executed_copy", output_dir / notebook_output_name(Path(args.path))),
                ("derived:workspace", workspace_dir),
            ]
        )
        outputs.extend(
            (f"derived:staged-extra[{index}]", workspace_dir / Path(value).name)
            for index, value in enumerate(args.stage_extra, start=1)
        )
    collisions = find_output_input_collisions(inputs, outputs)
    return emit_collision_only(args, collisions) if collisions else None


def execute_summary_path(args) -> Path | None:
    summary_json = getattr(args, "summary_json", None)
    return Path(summary_json) if summary_json else None


def emit_execute_blocked(args, message: str, *, preflight: dict | None = None, error_type: str | None = None) -> int:
    summary_path = execute_summary_path(args)
    payload = standard_tool_payload(
        "notebook_workbench",
        status="blocked",
        notes=[
            "The original notebook was not modified; execution only proceeds on a copied notebook when preconditions are safe enough.",
            "Run preflight-execution first when a notebook has unresolved paths, interactive input, missing imports, or platform-specific assumptions.",
        ],
        artifacts={
            "summary_json": public_path(summary_path) if summary_path else None,
            "manifest_json": getattr(args, "manifest_json", None),
            "output_dir": getattr(args, "output_dir", None),
        },
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "source_notebook": getattr(args, "path", None),
            "output_dir": getattr(args, "output_dir", None),
            "preflight": preflight,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": 1},
        },
        legacy={"blocked_reason": message},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if summary_path:
        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered, encoding="utf-8")
        except OSError:
            pass
    return 2


def emit_readonly_blocked(args, command: str, message: str, *, status: str = "blocked", error_type: str | None = None) -> int:
    summary_path = Path(args.summary_json) if getattr(args, "summary_json", None) else None
    payload = standard_tool_payload(
        "notebook_workbench",
        status=status,
        notes=[f"{command} did not complete; the source notebook was not modified."],
        artifacts={"summary_json": args.summary_json, "manifest_json": getattr(args, "manifest_json", None)},
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "source_notebook": getattr(args, "path", None),
            "command": command,
        },
        qa={
            "status": status,
            "findings": [message],
            "metrics": {"blocking_count": 1 if status == "blocked" else 0},
        },
        legacy={"blocked_reason": message, "command": command},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    outputs = []
    if summary_path:
        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered, encoding="utf-8")
            outputs.append(summary_path)
        except Exception as exc:
            print(f"Could not write summary JSON: {clean_known_stderr(str(exc)) or exc}", file=sys.stderr)
    if getattr(args, "manifest_json", None):
        try:
            write_manifest(
                args.manifest_json,
                inputs=[Path(args.path)],
                outputs=outputs,
                parameters={"command": command},
                command=f"notebook_workbench.py {command}",
                notes=payload["notes"],
            )
        except Exception as exc:
            print(f"Could not write manifest JSON: {clean_known_stderr(str(exc)) or exc}", file=sys.stderr)
    return 2


def notebook_output_name(path: Path) -> str:
    name = path.name
    return name[:-4] if name.lower().endswith(".ipynb.txt") else name


def load_notebook_like(path: Path):
    nbformat, _, _ = lazy_imports()
    raw_text = path.read_text(errors="replace")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict) or "cells" not in payload:
        raise SystemExit(f"{path.name} does not contain notebook JSON.")
    nb = nbformat.from_dict(payload)
    for cell in nb.cells:
        source = cell.get("source", "")
        if isinstance(source, list):
            cell["source"] = "".join(source)
        cell.setdefault("id", uuid.uuid4().hex[:8])
    return nb


def code_cell_sources(nb) -> list[str]:
    return [str(cell.get("source", "")) for cell in nb.cells if cell.get("cell_type") == "code"]


def inspect_notebook(path: Path) -> dict:
    nb = load_notebook_like(path)
    cells = nb.cells
    kernelspec = (nb.metadata.get("kernelspec") or {})
    language_info = (nb.metadata.get("language_info") or {})
    return sanitize_payload(
        {
            "path": str(path.resolve()),
            "name": path.name,
            "cell_count": len(cells),
            "code_cells": sum(1 for cell in cells if cell.get("cell_type") == "code"),
            "markdown_cells": sum(1 for cell in cells if cell.get("cell_type") == "markdown"),
            "raw_cells": sum(1 for cell in cells if cell.get("cell_type") == "raw"),
            "kernelspec": kernelspec,
            "language_info": language_info,
            "cell_preview": [
                {
                    "index": index + 1,
                    "cell_type": cell.get("cell_type"),
                    "source_preview": str(cell.get("source", "")).strip().splitlines()[:2],
                }
                for index, cell in enumerate(cells[:8])
            ],
        }
    )


def normalize_code_for_ast(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%") or stripped.startswith("!") or stripped.startswith("?"):
            continue
        kept.append(line)
    return "\n".join(kept)


def import_names_from_text(text: str) -> set[str]:
    cleaned = normalize_code_for_ast(text)
    if not cleaned.strip():
        return set()
    try:
        tree = ast.parse(cleaned)
    except SyntaxError:
        names = set()
        for line in cleaned.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                tail = stripped[len("import ") :]
                for chunk in tail.split(","):
                    head = chunk.strip().split(" as ", 1)[0].strip()
                    if head:
                        names.add(head.split(".", 1)[0])
            elif stripped.startswith("from "):
                module = stripped[len("from ") :].split(" import ", 1)[0].strip()
                if module and not module.startswith("."):
                    names.add(module.split(".", 1)[0])
        return names
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.module.startswith("."):
            names.add(node.module.split(".", 1)[0])
    return names


def detect_input_calls_from_text(text: str, cell_index: int) -> list[dict]:
    cleaned = normalize_code_for_ast(text)
    findings = []
    if not cleaned.strip():
        return findings
    try:
        tree = ast.parse(cleaned)
    except SyntaxError:
        if INPUT_CALL_TEXT_PATTERN.search(cleaned):
            findings.append({"cell_index": cell_index, "line": None, "prompt": None})
        return findings
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
        findings.append({"cell_index": cell_index, "line": getattr(node, "lineno", None), "prompt": prompt})
    return findings


def detect_interactive_inputs(nb) -> list[dict]:
    findings = []
    for index, cell in enumerate(nb.cells, start=1):
        if cell.get("cell_type") != "code":
            continue
        findings.extend(detect_input_calls_from_text(str(cell.get("source", "")), index))
    return findings


def local_module_exists(module_name: str, notebook_dir: Path) -> bool:
    candidate_file = notebook_dir / f"{module_name}.py"
    candidate_pkg = notebook_dir / module_name / "__init__.py"
    return candidate_file.exists() or candidate_pkg.exists()


def module_available(module_name: str, notebook_dir: Path) -> bool:
    if module_name == "__future__":
        return True
    if importlib.util.find_spec(module_name) is not None:
        return True
    return local_module_exists(module_name, notebook_dir)


def add_path_ref(refs: dict[tuple[str, str], dict], raw_path: str, matched_as: str, notebook_dir: Path) -> None:
    if not raw_path or "://" in raw_path or raw_path.startswith("data:"):
        return
    candidate = Path(raw_path).expanduser()
    is_absolute = candidate.is_absolute()
    resolved = (candidate if is_absolute else notebook_dir / candidate).resolve(strict=False)
    key = ("absolute" if is_absolute else "relative", raw_path)
    entry = refs.setdefault(
        key,
        {
            "raw": raw_path,
            "matched_as": matched_as,
            "resolved": str(resolved),
            "exists": resolved.exists(),
            "basename": candidate.name,
        },
    )
    if entry["matched_as"] != matched_as:
        entry["matched_as"] = f"{entry['matched_as']}+{matched_as}"
    entry["exists"] = entry["exists"] or resolved.exists()


def detect_path_refs(texts: list[str], notebook_dir: Path) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    refs: dict[tuple[str, str], dict] = {}
    for text in texts:
        for match in PATH_CALL_PATTERN.finditer(text):
            add_path_ref(refs, match.group(2), "Path(...)", notebook_dir)
        for match in STRING_LITERAL_PATTERN.finditer(text):
            add_path_ref(refs, match.group("path"), "string_literal", notebook_dir)
    relative_refs = [item for (kind, _), item in refs.items() if kind == "relative"]
    absolute_refs = [item for (kind, _), item in refs.items() if kind == "absolute"]
    missing_relative_refs = [item for item in relative_refs if not item["exists"]]
    placeholder_like_refs = [
        item for item in relative_refs + absolute_refs if PLACEHOLDER_BASENAME_PATTERN.match(item["basename"])
    ]
    return (
        sorted(relative_refs, key=lambda item: item["raw"]),
        sorted(absolute_refs, key=lambda item: item["raw"]),
        sorted(missing_relative_refs, key=lambda item: item["raw"]),
        sorted(placeholder_like_refs, key=lambda item: item["raw"]),
    )


def build_preflight_assessment(
    relative_path_refs: list[dict],
    absolute_path_refs: list[dict],
    missing_relative_refs: list[dict],
    placeholder_like_refs: list[dict],
    missing_imports: list[str],
    missing_binaries: list[str],
    optional_backend_missing: list[str],
    network_required: bool,
    remote_services_detected: list[str],
    interactive_input_calls: list[dict],
    recommended_execution_mode: str,
) -> dict:
    blocking_findings = []
    warning_findings = []
    if missing_imports:
        blocking_findings.append(
            "Missing imports detected: " + ", ".join(missing_imports)
        )
    if recommended_execution_mode == "custom_cwd_needed":
        blocking_findings.append(
            "Notebook references relative paths that do not resolve from the notebook directory. A custom cwd is likely needed."
        )
    elif missing_relative_refs:
        warning_findings.append(
            "Some relative references still do not resolve from the notebook directory."
        )
    if missing_binaries:
        warning_findings.append(
            "Optional execution backends look incomplete: " + ", ".join(missing_binaries)
        )
    if optional_backend_missing:
        warning_findings.extend(optional_backend_missing)
    if absolute_path_refs:
        warning_findings.append(
            "Notebook references absolute local paths; execution may depend on a specific machine layout."
        )
    if placeholder_like_refs:
        warning_findings.append(
            "Notebook contains placeholder-like data references (for example imagen1.fits or sample.csv)."
        )
    if network_required:
        warning_findings.append(
            "Notebook appears to depend on network access or remote services during execution."
        )
    if remote_services_detected:
        warning_findings.append(
            "Remote services detected: " + ", ".join(remote_services_detected[:6])
        )
    if interactive_input_calls:
        warning_findings.append(
            "Notebook calls input(); execute only a copy, feed documented values with --input-value or an equivalent temporary provider, and remove that provider before saving the deliverable."
        )
    if blocking_findings:
        status = "blocked"
    elif warning_findings:
        status = "warning"
    else:
        status = "ok"
    if recommended_execution_mode == "source_dir_copy":
        recommendation = "Keep copied execution in its run-owned workspace and stage only the required files with --stage-extra."
    elif recommended_execution_mode == "custom_cwd_needed":
        recommendation = "Use execute-copy --cwd PATH once you know the project directory that contains the missing relative data."
    else:
        recommendation = "Default execute-copy workspace mode should be fine."
    return {
        "status": status,
        "recommendation": recommendation,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
    }


def detect_remote_services(texts: list[str], imports_detected: list[str]) -> tuple[bool, list[str]]:
    services = []
    for text in texts:
        services.extend(URL_LITERAL_PATTERN.findall(text))
    if "astroquery" in imports_detected:
        services.append("astronomy archive services via astroquery")
    network_required = bool(services or set(imports_detected).intersection(NETWORK_IMPORTS))
    deduped = []
    seen = set()
    for item in services:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return network_required, deduped


def detect_optional_backends(imports_detected: list[str]) -> tuple[list[str], list[str]]:
    missing_binaries = []
    optional_backend_missing = []
    for rule in OPTIONAL_BACKEND_RULES:
        if rule["module"] not in imports_detected:
            continue
        available = any(find_executable(list(binary_group)) for binary_group in rule["required_binaries"])
        if not available:
            binaries = ["|".join(group) for group in rule["required_binaries"]]
            missing_binaries.extend(binaries)
            optional_backend_missing.append(rule["message"])
    return sorted(set(missing_binaries)), optional_backend_missing


def preflight_notebook_execution(path: Path) -> dict:
    notebook_path = path.resolve()
    inspection = inspect_notebook(notebook_path)
    nb = load_notebook_like(notebook_path)
    texts = code_cell_sources(nb)
    notebook_dir = notebook_path.parent
    imports_detected = sorted({name for text in texts for name in import_names_from_text(text)})
    missing_imports = [name for name in imports_detected if not module_available(name, notebook_dir)]
    relative_path_refs, absolute_path_refs, missing_relative_refs, placeholder_like_refs = detect_path_refs(texts, notebook_dir)
    missing_binaries, optional_backend_missing = detect_optional_backends(imports_detected)
    network_required, remote_services_detected = detect_remote_services(texts, imports_detected)
    interactive_input_calls = detect_interactive_inputs(nb)

    if any(item["exists"] for item in relative_path_refs):
        recommended_execution_mode = "source_dir_copy"
    elif relative_path_refs:
        recommended_execution_mode = "custom_cwd_needed"
    else:
        recommended_execution_mode = "workspace_copy"

    assessment = build_preflight_assessment(
        relative_path_refs=relative_path_refs,
        absolute_path_refs=absolute_path_refs,
        missing_relative_refs=missing_relative_refs,
        placeholder_like_refs=placeholder_like_refs,
        missing_imports=missing_imports,
        missing_binaries=missing_binaries,
        optional_backend_missing=optional_backend_missing,
        network_required=network_required,
        remote_services_detected=remote_services_detected,
        interactive_input_calls=interactive_input_calls,
        recommended_execution_mode=recommended_execution_mode,
    )
    return sanitize_payload(
        {
            "path": str(notebook_path),
            "inspection": inspection,
            "execution_signals": {
                "relative_path_refs": relative_path_refs,
                "absolute_path_refs": absolute_path_refs,
                "missing_relative_refs": missing_relative_refs,
                "placeholder_like_refs": placeholder_like_refs,
                "imports_detected": imports_detected,
                "missing_imports": missing_imports,
                "missing_binaries": missing_binaries,
                "remote_services_detected": remote_services_detected,
                "network_required": network_required,
                "optional_backend_missing": optional_backend_missing,
                "interactive_input_calls": interactive_input_calls,
            },
            "recommended_execution_mode": recommended_execution_mode,
            "assessment": assessment,
        }
    )


def path_is_within(candidate: str | Path, root: str | Path) -> bool:
    """Return whether candidate resolves below root, including root itself."""
    candidate_path = Path(candidate).expanduser().resolve(strict=False)
    root_path = Path(root).expanduser().resolve(strict=False)
    try:
        candidate_path.relative_to(root_path)
    except ValueError:
        return False
    return True


def absolute_refs_outside_run(absolute_path_refs: list[dict], output_dir: str | Path) -> list[dict]:
    """Select literal absolute notebook paths that escape the run-owned output tree."""
    unsafe = []
    for item in absolute_path_refs or []:
        resolved = item.get("resolved") if isinstance(item, dict) else None
        if resolved and not path_is_within(resolved, output_dir):
            unsafe.append(item)
    return unsafe


def unsafe_absolute_ref_message(refs: list[dict]) -> str:
    rendered = [public_path(item.get("resolved") or item.get("raw")) for item in refs[:6]]
    suffix = "" if len(refs) <= 6 else f" (+{len(refs) - 6} more)"
    return (
        "Refusing copied execution because literal absolute paths escape the run-owned workspace: "
        + ", ".join(rendered)
        + suffix
        + ". Stage required inputs with --stage-extra and write outputs below OUTPUT_DIR/_workspace."
    )


def parse_cell_range(spec: str | None, total_cells: int) -> tuple[int, int]:
    if not spec:
        return (1, total_cells)
    if ":" not in spec:
        raise SystemExit("--cell-range must look like START:END, START:, or :END.")
    start_raw, end_raw = spec.split(":", 1)
    start = int(start_raw) if start_raw.strip() else 1
    end = int(end_raw) if end_raw.strip() else total_cells
    if start < 1 or end < 1 or start > end or end > total_cells:
        raise SystemExit(f"Invalid --cell-range {spec!r} for notebook with {total_cells} cells.")
    return (start, end)


def stage_extra_inputs(paths: list[str], workspace_dir: Path) -> list[str]:
    staged = []
    workspace_dir.mkdir(parents=True, exist_ok=True)
    used_names = {item.name for item in workspace_dir.iterdir()}
    for raw in paths:
        source = Path(raw).expanduser().resolve()
        if not source.exists():
            continue
        candidate_name = source.name or "extra"
        counter = 1
        while candidate_name in used_names:
            counter += 1
            candidate_name = f"{source.stem}_{counter}{source.suffix}" if source.suffix else f"{source.name}_{counter}"
        used_names.add(candidate_name)
        target = workspace_dir / candidate_name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        staged.append(str(target))
    return staged


def apply_text_replacements(nb, replacements: list[tuple[str, str]]) -> list[dict]:
    applied = []
    for find, replace in replacements:
        replacement_count = 0
        for cell in nb.cells:
            source = str(cell.get("source", ""))
            count = source.count(find)
            if count:
                cell["source"] = source.replace(find, replace)
                replacement_count += count
        applied.append({"find": find, "replace": replace, "replacement_count": replacement_count})
    return applied


def append_cells(nb, append_markdown: list[str], append_code: list[str], append_code_files: list[str]):
    nbformat, _, _ = lazy_imports()
    for text in append_markdown:
        nb.cells.append(nbformat.v4.new_markdown_cell(text))
    for text in append_code:
        nb.cells.append(nbformat.v4.new_code_cell(text))
    for raw in append_code_files:
        source = Path(raw).expanduser()
        code = source.read_text(encoding="utf-8")
        nb.cells.append(nbformat.v4.new_code_cell(code))


def install_temporary_input_provider(nb, input_values: list[str]) -> tuple[int, str | None]:
    if not input_values:
        return 0, None
    nbformat, _, _ = lazy_imports()
    environment_key = f"CODEX_NOTEBOOK_INPUT_VALUES_{uuid.uuid4().hex}"
    os.environ[environment_key] = json.dumps(list(input_values), ensure_ascii=True)
    provider_source = f"""
import builtins as _codex_builtins
import json as _codex_json
import os as _codex_os
_codex_input_values = iter(_codex_json.loads(_codex_os.environ.pop({environment_key!r})))
_codex_original_input = _codex_builtins.input
_codex_previous_global_input = globals().get('input', None)
_codex_had_global_input = 'input' in globals()

def _codex_input_provider(prompt=''):
    try:
        value = next(_codex_input_values)
    except StopIteration as exc:
        raise RuntimeError('No --input-value left for notebook input() call.') from exc
    print(f"{{prompt}}[value supplied]")
    return value

_codex_builtins.input = _codex_input_provider
globals()['input'] = _codex_input_provider
try:
    get_ipython().user_ns['input'] = _codex_input_provider
except Exception:
    pass
""".lstrip()
    cleanup_source = """
import builtins as _codex_builtins
if '_codex_original_input' in globals():
    _codex_builtins.input = _codex_original_input
if '_codex_had_global_input' in globals():
    if _codex_had_global_input:
        globals()['input'] = _codex_previous_global_input
    else:
        globals().pop('input', None)
try:
    if '_codex_had_global_input' in globals() and _codex_had_global_input:
        get_ipython().user_ns['input'] = _codex_previous_global_input
    else:
        get_ipython().user_ns.pop('input', None)
except Exception:
    pass
""".lstrip()
    provider = nbformat.v4.new_code_cell(provider_source)
    provider.metadata["codex_ephemeral"] = "input_provider"
    cleanup = nbformat.v4.new_code_cell(cleanup_source)
    cleanup.metadata["codex_ephemeral"] = "input_provider_cleanup"
    nb.cells.insert(0, provider)
    nb.cells.append(cleanup)
    return 2, environment_key


def remove_ephemeral_codex_cells(nb) -> int:
    before = len(nb.cells)
    nb.cells = [cell for cell in nb.cells if not (cell.get("metadata") or {}).get("codex_ephemeral")]
    return before - len(nb.cells)


def classify_error(error: dict | None, preflight: dict, execution_mode: str) -> dict:
    if not error:
        return {"status": "ok", "recommendation": "Notebook execution completed successfully."}
    blob = " ".join(str(error.get(key) or "") for key in ("type", "message", "traceback")).lower()
    if "permissionerror" in blob and ("find_available_port" in blob or "tmp_sock.bind" in blob or "operation not permitted" in blob):
        return {
            "status": "sandbox_blocked",
            "recommendation": "Kernel startup was blocked by the current sandbox. The copied notebook is still useful, but execution needs a less restricted context.",
        }
    signals = preflight.get("execution_signals") or {}
    missing_imports = signals.get("missing_imports") or []
    relative_refs = signals.get("relative_path_refs") or []
    missing_relative_refs = signals.get("missing_relative_refs") or []
    if "modulenotfounderror" in blob or "no module named" in blob:
        if missing_imports:
            return {
                "status": "execution_failed",
                "recommendation": "Notebook imports modules missing from the current environment: " + ", ".join(missing_imports),
            }
    if "filenotfounderror" in blob:
        if execution_mode == "workspace_copy" and relative_refs:
            return {
                "status": "execution_failed",
                "recommendation": "This looks like a relative-path notebook. Stage the required data with --stage-extra so copied execution remains inside the run-owned workspace.",
            }
        if missing_relative_refs and preflight.get("recommended_execution_mode") == "custom_cwd_needed":
            return {
                "status": "execution_failed",
                "recommendation": "Notebook likely needs a project-level cwd. Retry with --cwd PATH once the correct data root is known.",
            }
    return {
        "status": "execution_failed",
        "recommendation": "Inspect the copied notebook error payload and the preflight findings before retrying.",
    }


def public_execution_error(error: dict | None, assessment: dict) -> dict | None:
    if not error:
        return None
    public_error = {
        "type": error.get("type"),
        "message": error.get("message"),
        "assessment_status": assessment.get("status"),
        "recommendation": assessment.get("recommendation"),
    }
    if assessment.get("status") == "sandbox_blocked":
        public_error["controlled_reason"] = "kernel_start_blocked_by_current_sandbox"
    if error.get("traceback"):
        public_error["traceback_redacted"] = True
    return sanitize_payload(public_error)


def build_execution_notes(result: dict) -> list[str]:
    notes = [
        "The original notebook was not modified; execution always happens on a copied notebook.",
        "Use --cell-range when only part of a teaching notebook should be executed in this run.",
    ]
    mode = result.get("execution_mode")
    if mode == "source_dir_copy":
        notes.append("Execution used the original notebook directory as cwd because the notebook appears to depend on local relative paths.")
    elif mode == "custom_cwd_copy":
        notes.append("Execution used an explicit custom cwd because the notebook appears to depend on project-relative paths.")
    signals = (result.get("preflight") or {}).get("execution_signals") or {}
    missing_imports = signals.get("missing_imports") or []
    if missing_imports:
        notes.append("Preflight detected missing imports before execution: " + ", ".join(missing_imports))
    if result.get("error") and "filenotfounderror" in json.dumps(result["error"]).lower() and signals.get("relative_path_refs"):
        notes.append("The failure looks consistent with notebook-local relative paths or missing local data files.")
    missing_binaries = signals.get("missing_binaries") or []
    if missing_binaries:
        notes.append("Preflight detected optional binary dependencies that may be missing: " + ", ".join(missing_binaries))
    if signals.get("network_required"):
        notes.append("Preflight detected likely network or remote-service usage inside the notebook.")
    if signals.get("interactive_input_calls") and not result.get("input_values_used"):
        notes.append("Preflight detected input() calls; copied execution may need documented --input-value entries.")
    if result.get("input_values_used"):
        notes.append("Temporary input() provider values were used during copied execution and provider cells were removed before saving the notebook copy.")
    if result.get("qa", {}).get("status") == "warning":
        notes.extend(result.get("qa", {}).get("findings") or [])
    return notes


def build_notebook_execution_qa(result: dict, working_nb) -> dict:
    code_cells = [cell for cell in working_nb.cells if cell.get("cell_type") == "code"]
    cells_with_outputs = sum(1 for cell in code_cells if cell.get("outputs"))
    output_error_cells = 0
    for cell in code_cells:
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                output_error_cells += 1
                break
    findings = []
    if result.get("error"):
        if result.get("assessment", {}).get("status") == "sandbox_blocked":
            status = "warning"
            findings.append("Notebook execution was blocked by the current sandbox rather than by notebook logic.")
        else:
            status = "fail"
            findings.append("Notebook execution ended with an error.")
    elif not code_cells:
        status = "warning"
        findings.append("Notebook copy contained no executable code cells in the selected range.")
    elif code_cells and cells_with_outputs == 0:
        status = "warning"
        findings.append("Notebook executed without visible cell outputs; review whether this is expected for this notebook.")
    else:
        status = "ok"
    return {
        "status": status,
        "findings": findings,
        "metrics": {
            "code_cell_count": len(code_cells),
            "cells_with_outputs": cells_with_outputs,
            "cells_with_error_outputs": output_error_cells,
            "executed_cell_count": result.get("executed_cell_count"),
        },
    }


def resolve_execution_context(
    notebook_path: Path,
    output_dir: Path,
    stage_extra: list[str],
    run_from_source_dir: bool,
    cwd: str | None,
) -> tuple[str, Path, Path]:
    if run_from_source_dir and cwd:
        raise SystemExit("--cwd and --run-from-source-dir are mutually exclusive.")
    if (run_from_source_dir or cwd) and stage_extra:
        raise SystemExit("--stage-extra is only supported in the default workspace_copy mode.")
    workspace_dir = (output_dir / "_workspace").resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    if run_from_source_dir:
        raise SystemExit(
            "--run-from-source-dir is blocked because it can modify the original source tree; "
            "use the default run-owned workspace and repeat --stage-extra for required inputs."
        )
    if cwd:
        effective_cwd = Path(cwd).expanduser().resolve()
        if not effective_cwd.exists():
            raise SystemExit(f"--cwd does not exist: {effective_cwd}")
        if not effective_cwd.is_dir():
            raise SystemExit(f"--cwd must point to a directory: {effective_cwd}")
        try:
            effective_cwd.relative_to(workspace_dir)
        except ValueError:
            raise SystemExit(
                "--cwd is outside the run-owned workspace and was blocked to protect original/external files; "
                "use a directory below OUTPUT_DIR/_workspace or use --stage-extra."
            ) from None
        return ("workspace_subdir", effective_cwd, workspace_dir)
    return ("workspace_copy", workspace_dir, workspace_dir)


def execute_notebook_copy(
    notebook_path: Path,
    output_dir: Path,
    kernel_name: str = "python3",
    timeout_sec: int = 900,
    stage_extra: list[str] | None = None,
    append_markdown: list[str] | None = None,
    append_code: list[str] | None = None,
    append_code_files: list[str] | None = None,
    cell_range: str | None = None,
    run_from_source_dir: bool = False,
    cwd: str | None = None,
    replace_text: list[tuple[str, str]] | None = None,
    input_values: list[str] | None = None,
) -> dict:
    nbformat, CellExecutionError, ExecutePreprocessor = lazy_imports()
    notebook_path = notebook_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir = output_dir / "_workspace"
    executed_copy = output_dir / notebook_output_name(notebook_path)
    stage_extra = stage_extra or []
    execution_mode, effective_cwd, workspace_dir_for_result = resolve_execution_context(
        notebook_path=notebook_path,
        output_dir=output_dir,
        stage_extra=stage_extra,
        run_from_source_dir=run_from_source_dir,
        cwd=cwd,
    )

    original_nb = load_notebook_like(notebook_path)
    total_cells = len(original_nb.cells)
    start, end = parse_cell_range(cell_range, total_cells)
    selected_cells = original_nb.cells[start - 1 : end]
    working_nb = nbformat.v4.new_notebook(
        metadata=original_nb.metadata,
        cells=[nbformat.from_dict(cell) for cell in selected_cells],
    )
    applied_replacements = apply_text_replacements(working_nb, replace_text or [])
    append_cells(
        working_nb,
        append_markdown=append_markdown or [],
        append_code=append_code or [],
        append_code_files=append_code_files or [],
    )
    _relative_refs, effective_absolute_refs, _missing_refs, _placeholder_refs = detect_path_refs(
        code_cell_sources(working_nb),
        notebook_path.parent,
    )
    unsafe_effective_refs = absolute_refs_outside_run(effective_absolute_refs, output_dir)
    if unsafe_effective_refs:
        raise SystemExit(unsafe_absolute_ref_message(unsafe_effective_refs))
    staged_extra = stage_extra_inputs(stage_extra, workspace_dir) if execution_mode == "workspace_copy" else []
    preflight = preflight_notebook_execution(notebook_path)
    input_values = input_values or []
    ephemeral_input_cells, input_environment_key = install_temporary_input_provider(working_nb, input_values)
    started = time.time()
    success = False
    error = None
    try:
        executor = ExecutePreprocessor(timeout=timeout_sec, kernel_name=kernel_name)
        executor.preprocess(working_nb, {"metadata": {"path": str(effective_cwd)}})
        success = True
    except CellExecutionError as exc:
        error = {
            "type": exc.__class__.__name__,
            "message": clean_known_stderr(str(exc)),
            "traceback": clean_known_stderr(traceback.format_exc()),
        }
    except Exception as exc:  # pragma: no cover - defensive
        error = {
            "type": exc.__class__.__name__,
            "message": clean_known_stderr(str(exc)),
            "traceback": clean_known_stderr(traceback.format_exc()),
        }
    finally:
        if input_environment_key:
            os.environ.pop(input_environment_key, None)

    removed_ephemeral_cells = remove_ephemeral_codex_cells(working_nb)
    nbformat.write(working_nb, str(executed_copy))
    assessment = classify_error(error, preflight=preflight, execution_mode=execution_mode)
    public_error = public_execution_error(error, assessment)
    result = {
        "source_notebook": str(notebook_path),
        "executed_copy": str(executed_copy),
        "workspace_dir": str(workspace_dir_for_result),
        "effective_cwd": str(effective_cwd),
        "execution_mode": execution_mode,
        "kernel_name": kernel_name,
        "timeout_sec": timeout_sec,
        "selected_cell_range": {"start": start, "end": end},
        "original_cell_count": total_cells,
        "executed_cell_count": len(working_nb.cells),
        "staged_extra_paths": staged_extra,
        "applied_replacements": applied_replacements,
        "input_values_used": [
            {"index": index + 1, "supplied": True}
            for index, _value in enumerate(input_values)
        ],
        "ephemeral_input_provider_cells_executed": ephemeral_input_cells,
        "ephemeral_input_provider_cells_removed_before_save": removed_ephemeral_cells,
        "preflight": preflight,
        "success": success,
        "error": public_error,
        "assessment": assessment,
        "duration_sec": round(time.time() - started, 2),
    }
    result["qa"] = build_notebook_execution_qa(result, working_nb)
    return sanitize_payload(result)


def cmd_inspect(args):
    try:
        summary = inspect_notebook(Path(args.path))
    except Exception as exc:
        message = clean_known_stderr(str(exc)) or f"{exc.__class__.__name__}: {exc}"
        return emit_readonly_blocked(args, "inspect", message, error_type=exc.__class__.__name__)
    payload = standard_tool_payload(
        "notebook_workbench",
        status="ok",
        notes=["Inspection is read-only and does not execute or modify the notebook."],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results={"inspection": summary},
        legacy=summary,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    outputs = []
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
        outputs.append(summary_path)
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[Path(args.path)],
            outputs=outputs,
            parameters={},
            command="notebook_workbench.py inspect",
            notes=[
                "Inspection is read-only and never modifies the source notebook.",
            ],
            extra={"cell_count": summary.get("cell_count"), "code_cells": summary.get("code_cells")},
        )
    return 0


def cmd_preflight_execution(args):
    try:
        summary = preflight_notebook_execution(Path(args.path))
    except Exception as exc:
        message = clean_known_stderr(str(exc)) or f"{exc.__class__.__name__}: {exc}"
        return emit_readonly_blocked(args, "preflight-execution", message, error_type=exc.__class__.__name__)
    payload = standard_tool_payload(
        "notebook_workbench",
        status=summary.get("assessment", {}).get("status"),
        notes=[
            "Preflight is read-only and checks execution risks before creating a copied notebook run.",
        ],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results={"preflight": summary},
        legacy=summary,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    outputs = []
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
        outputs.append(summary_path)
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[Path(args.path)],
            outputs=outputs,
            parameters={},
            command="notebook_workbench.py preflight-execution",
            notes=[
                "Preflight is read-only and checks notebook execution risks before creating a copied run.",
            ],
            extra={
                "recommended_execution_mode": summary.get("recommended_execution_mode"),
                "assessment": summary.get("assessment"),
            },
        )
    return 0


def cmd_execute_copy(args):
    try:
        preflight = preflight_notebook_execution(Path(args.path))
        output_dir = Path(args.output_dir).expanduser().resolve(strict=False)
        absolute_path_refs = (preflight.get("execution_signals") or {}).get("absolute_path_refs") or []
        unsafe_absolute_refs = absolute_refs_outside_run(absolute_path_refs, output_dir)
        if unsafe_absolute_refs:
            raise SystemExit(
                emit_execute_blocked(
                    args,
                    unsafe_absolute_ref_message(unsafe_absolute_refs),
                    preflight=preflight,
                )
            )
        interactive_input_calls = (preflight.get("execution_signals") or {}).get("interactive_input_calls") or []
        if interactive_input_calls and not args.input_value:
            raise SystemExit(
                emit_execute_blocked(
                    args,
                    "Notebook calls input(); rerun execute-copy with one documented --input-value per input() call.",
                    preflight=preflight,
                )
            )
        result = execute_notebook_copy(
            Path(args.path),
            Path(args.output_dir),
            kernel_name=args.kernel_name,
            timeout_sec=args.timeout_sec,
            stage_extra=args.stage_extra,
            append_markdown=args.append_markdown,
            append_code=args.append_code,
            append_code_files=args.append_code_file,
            cell_range=args.cell_range,
            run_from_source_dir=args.run_from_source_dir,
            cwd=args.cwd,
            replace_text=[tuple(item) for item in args.replace_text],
            input_values=args.input_value,
        )
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        message = clean_known_stderr(str(exc.code)) or "Notebook copied execution was blocked."
        raise SystemExit(emit_execute_blocked(args, message, error_type="SystemExit")) from None
    except Exception as exc:
        message = clean_known_stderr(str(exc)) or f"{exc.__class__.__name__}: {exc}"
        raise SystemExit(emit_execute_blocked(args, message, error_type=exc.__class__.__name__)) from None
    notes = build_execution_notes(result)
    if result["success"]:
        status = "warning" if result.get("qa", {}).get("status") == "warning" else "ok"
    else:
        status = "blocked" if result["assessment"]["status"] == "sandbox_blocked" else "fail"
    payload = standard_tool_payload(
        "notebook_workbench",
        status=status,
        notes=notes,
        artifacts={
            "executed_copy": result["executed_copy"],
            "workspace_dir": result["workspace_dir"],
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
        },
        results={"run": result},
        qa=result.get("qa"),
        legacy={
            "environment": environment_summary(),
            "run": result,
        },
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    outputs = [Path(result["executed_copy"])]
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
        outputs.append(summary_path)
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[Path(args.path)],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "cell_range": args.cell_range,
                "stage_extra": args.stage_extra,
                "run_from_source_dir": args.run_from_source_dir,
                "cwd": args.cwd,
                "append_markdown_count": len(args.append_markdown),
                "append_code_count": len(args.append_code) + len(args.append_code_file),
                "replace_text_count": len(args.replace_text),
                "input_value_count": len(args.input_value),
            },
            command="notebook_workbench.py execute-copy",
            notes=payload["notes"],
            extra={"success": result["success"], "error": result["error"], "execution_mode": result["execution_mode"]},
        )
    ok = result["success"] or result["assessment"]["status"] == "sandbox_blocked"
    raise SystemExit(0 if ok else 1)


def main():
    args = parse_args()
    collision_status = preflight_output_safety(args)
    if collision_status is not None:
        raise SystemExit(collision_status)
    if args.command == "inspect":
        raise SystemExit(cmd_inspect(args))
    elif args.command == "preflight-execution":
        raise SystemExit(cmd_preflight_execution(args))
    else:
        if not args.trust_notebook_code:
            raise SystemExit(emit_untrusted_execution_block(args))
        cmd_execute_copy(args)


if __name__ == "__main__":
    main()
