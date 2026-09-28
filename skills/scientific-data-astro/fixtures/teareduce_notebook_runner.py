#!/usr/bin/env python3
"""Execute real TEAREDUCE notebooks in copies without touching originals."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import traceback
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime

ensure_datanalysis_runtime("teareduce_notebook_runner")

import nbformat
from nbconvert.preprocessors import CellExecutionError, ExecutePreprocessor

from _internal.path_safety import canonical_path, find_output_input_collisions, path_is_within
from _internal.public_contract import build_blocked_payload
from _internal.provenance_utils import environment_summary, write_manifest
from _internal.runtime_common import clean_known_stderr
from teareduce_healthcheck import bootstrap_runtime_dirs, inspect_teareduce_environment, notebook_candidates, scan_notebook


PATH_LITERAL_PATTERN = re.compile(r"Path\((['\"])(.+?)\1\)")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Notebook paths or directories containing TEAREDUCE notebooks.")
    parser.add_argument("--output-dir", required=True, help="Directory for executed notebook copies and reports.")
    parser.add_argument("--kernel-name", default="python3", help="Kernel name to use during execution.")
    parser.add_argument("--timeout-sec", type=int, default=900, help="Per-cell execution timeout in seconds.")
    parser.add_argument(
        "--trust-notebook-code",
        action="store_true",
        help="Explicitly confirm that every selected notebook's arbitrary code has been reviewed and trusted.",
    )
    parser.add_argument("--max-notebooks", type=int, default=4, help="Maximum real .ipynb notebooks to execute.")
    parser.add_argument(
        "--stage-extra",
        action="append",
        default=[],
        help="Extra file or directory to copy into each notebook workspace before execution. Repeat as needed.",
    )
    parser.add_argument("--summary-json", help="Optional JSON report path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def notebook_source_text(path: Path) -> str:
    data = json.loads(path.read_text(errors="replace"))
    blobs = []
    for cell in data.get("cells", []):
        source = cell.get("source", [])
        if isinstance(source, list):
            blobs.append("".join(source))
        elif source:
            blobs.append(str(source))
    return "\n".join(blobs)


def load_notebook_like(path: Path):
    raw_text = path.read_text(errors="replace")
    data = json.loads(raw_text)
    if not isinstance(data, dict) or "cells" not in data:
        raise ValueError(f"{path.name} does not contain notebook JSON.")
    nb = nbformat.from_dict(data)
    for cell in nb.cells:
        source = cell.get("source", "")
        if isinstance(source, list):
            cell["source"] = "".join(source)
    return nb


def output_notebook_name(path: Path) -> str:
    if path.name.lower().endswith(".ipynb.txt"):
        return path.name[:-4]
    return path.name


def stage_inputs(path_checks: list[dict], workspace_dir: Path) -> dict[str, str]:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    used_names = set()
    for entry in path_checks:
        source = Path(entry["path"])
        if not source.exists():
            continue
        base_name = source.name or "root"
        candidate_name = base_name
        counter = 1
        while candidate_name in used_names:
            counter += 1
            candidate_name = f"{base_name}_{counter}"
        used_names.add(candidate_name)
        target = workspace_dir / candidate_name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        mapping[str(source)] = str(target)
    return mapping


def stage_extra_inputs(paths: list[str], workspace_dir: Path) -> list[str]:
    staged = []
    used_names = {item.name for item in workspace_dir.iterdir()} if workspace_dir.exists() else set()
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


def rewrite_notebook_paths(nb, path_map: dict[str, str]) -> None:
    if not path_map:
        return
    for cell in nb.cells:
        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else str(source)
        for original, replacement in path_map.items():
            text = text.replace(original, replacement)
        cell["source"] = text


def absolute_path_checks(text: str) -> list[dict]:
    seen = set()
    checks = []
    for match in PATH_LITERAL_PATTERN.finditer(text):
        raw = match.group(2)
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            continue
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        checks.append({"path_literal": raw, "path": resolved, "exists": candidate.exists()})
    return checks


def discovered_notebook_inputs(
    notebook_paths: list[Path],
    extra_paths: list[str] | None = None,
) -> list[tuple[str, Path]]:
    """Collect explicit and existing absolute paths referenced by notebooks."""
    discovered: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(label: str, value: Path) -> None:
        try:
            resolved = value.expanduser().resolve(strict=False)
        except (OSError, RuntimeError):
            resolved = value.expanduser()
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            discovered.append((label, resolved))

    for index, notebook_path in enumerate(notebook_paths, start=1):
        notebook = Path(notebook_path).expanduser()
        add(f"notebook[{index}]", notebook)
        try:
            checks = absolute_path_checks(notebook_source_text(notebook))
        except (OSError, ValueError, json.JSONDecodeError):
            checks = []
        for check_index, entry in enumerate(checks, start=1):
            candidate = Path(entry["path"]).expanduser()
            if entry.get("exists") or candidate.exists():
                add(f"notebook[{index}] absolute input[{check_index}]", candidate)

    for index, raw_path in enumerate(extra_paths or [], start=1):
        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            add(f"staged input[{index}]", candidate)
    return discovered


def require_trusted_notebook_code(tool: str, trusted: bool) -> None:
    if trusted:
        return
    message = (
        "Notebook execution is arbitrary code and is blocked by default. Review every selected notebook "
        "and rerun with --trust-notebook-code only when that code is explicitly trusted."
    )
    payload = build_blocked_payload(
        tool,
        message,
        artifacts={},
        results={"error_type": "untrusted_notebook_code"},
    )
    print(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False))
    raise SystemExit(2)


def block_notebook_output_collisions(
    tool: str,
    *,
    notebook_paths: list[Path],
    extra_paths: list[str] | None,
    outputs: list[tuple[str, str | Path | None]],
    output_dirs: list[tuple[str, str | Path | None]],
) -> None:
    """Block explicit outputs that could replace implicit notebook inputs."""
    inputs = discovered_notebook_inputs(notebook_paths, extra_paths)
    requested = [(label, value) for label, value in [*outputs, *output_dirs] if value is not None]
    collisions = find_output_input_collisions(inputs, requested)
    seen = {
        (item.get("flag"), item.get("input"), item.get("output_path"))
        for item in collisions
    }
    for output_label, output_dir in output_dirs:
        if output_dir is None:
            continue
        for input_label, input_path in inputs:
            if not path_is_within(input_path, output_dir):
                continue
            key = (output_label, input_label, str(canonical_path(output_dir)))
            if key in seen:
                continue
            seen.add(key)
            collisions.append(
                {
                    "flag": output_label,
                    "input": input_label,
                    "input_path": str(canonical_path(input_path)),
                    "output_path": str(canonical_path(output_dir)),
                    "collision_kind": "output_tree_contains_notebook_input",
                }
            )
    if not collisions:
        return
    message = "Notebook-derived inputs overlap requested outputs; no execution or write was allowed."
    payload = build_blocked_payload(
        tool,
        message,
        artifacts={},
        results={"collisions": collisions},
    )
    print(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False))
    raise SystemExit(2)


def classify_execution_result(notebook_path: Path, success: bool, error: dict | None) -> dict:
    if success:
        return {
            "status": "ready",
            "reason": "Notebook executed successfully in a copied workspace.",
            "recommendation": "Safe to use this notebook through the TEAREDUCE copied-execution path.",
            "next_step": "Inspect the copied notebook, summary JSON, and manifest outputs.",
        }
    error_blob = " ".join(
        str((error or {}).get(key) or "")
        for key in ("type", "message", "traceback")
    ).lower()
    message = ((error or {}).get("message") or "").lower()
    notebook_name = notebook_path.name.lower()
    if "permissionerror" in error_blob and ("find_available_port" in error_blob or "tmp_sock.bind" in error_blob):
        return {
            "status": "sandbox_blocked",
            "reason": "Notebook execution needs a Jupyter kernel launch that this sandbox blocked while binding a local port.",
            "recommendation": "Re-run the copied notebook execution with the required desktop or escalated permissions, or use the already-validated TEAREDUCE workflow wrappers in a context that allows Jupyter kernel startup.",
            "next_step": "Treat this as an execution-environment issue, not as a broken notebook or broken TEAREDUCE workflow.",
        }
    if "undefined parameter:" in message:
        return {
            "status": "parameterized_template",
            "reason": "Notebook expects user-supplied parameters before execution.",
            "recommendation": "Use it as a recipe/template, or inject the required parameters before running the copy.",
            "next_step": "Supply the missing parameter values in the copied workspace before retrying.",
        }
    if "filenotfounderror" in message and "filter_not_" in message:
        return {
            "status": "missing_sidecar_files",
            "reason": "Notebook depends on sidecar calibration or throughput text files that were not found.",
            "recommendation": "Stage the referenced sidecar files next to the copied notebook workspace before execution.",
            "next_step": "Use the canonical flat workflow with --fetch-official-sidecars when appropriate.",
        }
    if "filenotfounderror" in message and ("tea_procesado_int" in message or "n1/" in message or "ftdz_" in message):
        if "p3_04" in notebook_name or "rayos_cosmicos" in notebook_name or "cr2images" in notebook_name:
            return {
                "status": "missing_dataset",
                "reason": "Notebook references the classroom spectroscopy tree `TEA_procesado_INT`, which is not available locally.",
                "recommendation": "Use the cookbook fallback notebook `PAQUETE DE COSAS/cr2images.ipynb` through `teareduce_cookbook_cr2images_workflow.py`, or provide the original `TEA_procesado_INT` tree.",
                "next_step": "Route this task through the canonical `cr2images` fallback unless the exact classroom tree is available.",
            }
        if "p3_05" in notebook_name or "longitud" in notebook_name or "wavecal" in notebook_name:
            return {
                "status": "missing_dataset",
                "reason": "Notebook references the classroom spectroscopy tree `TEA_procesado_INT`, which is not available locally.",
                "recommendation": "Use the cookbook fallback notebook `PAQUETE DE COSAS/wavecalib.ipynb` through `teareduce_cookbook_wavecal_workflow.py`, or provide the original `TEA_procesado_INT` tree.",
                "next_step": "Route this task through the canonical `wavecalib` fallback unless the exact classroom tree is available.",
            }
        return {
            "status": "missing_dataset",
            "reason": "Notebook references a processed dataset tree that is not available locally.",
            "recommendation": "Provide the expected TEAREDUCE processed data tree before retrying execution, or use the cookbook fallbacks under `PAQUETE DE COSAS` when they cover the same method.",
            "next_step": "If the missing tree is `TEA_procesado_INT`, check whether a `cr2images` or `wavecalib` fallback applies first.",
        }
    if notebook_path.name.lower().endswith(".ipynb.txt"):
        return {
            "status": "execution_failed_from_misnamed_copy",
            "reason": "The notebook copy was executable despite the suffix mismatch, but the run still failed for another reason.",
            "recommendation": "Treat the file as a notebook, inspect the traceback, and fix the missing inputs or parameters in the copied workspace.",
            "next_step": "Rename the copied output to `.ipynb` if that makes review easier, but keep the source untouched.",
        }
    return {
        "status": "execution_failed",
        "reason": "Notebook execution failed for a notebook-specific reason shown in the traceback.",
        "recommendation": "Inspect the copied notebook output and traceback, then supply the missing inputs or patch the copied execution context.",
        "next_step": "Use the copied workspace as the place to patch inputs, not the original notebook.",
    }


def execute_copy(
    notebook_path: Path,
    output_dir: Path,
    kernel_name: str,
    timeout_sec: int,
    extra_stage_paths: list[str] | None = None,
) -> dict:
    notebook_path = notebook_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / output_notebook_name(notebook_path)
    source_text = notebook_source_text(notebook_path)
    preflight = {
        "notebook": scan_notebook(notebook_path),
        "absolute_paths": absolute_path_checks(source_text),
    }
    nb = load_notebook_like(notebook_path)
    workspace_dir = output_dir / "_workspace"
    staged_path_map = stage_inputs(preflight["absolute_paths"], workspace_dir)
    staged_extras = stage_extra_inputs(extra_stage_paths or [], workspace_dir)
    rewrite_notebook_paths(nb, staged_path_map)
    started = time.time()
    error = None
    success = False
    try:
        executor = ExecutePreprocessor(timeout=timeout_sec, kernel_name=kernel_name)
        executor.preprocess(nb, {"metadata": {"path": str(workspace_dir)}})
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
    nbformat.write(nb, str(destination))
    assessment = classify_execution_result(notebook_path, success=success, error=error)
    return {
        "source_notebook": str(notebook_path),
        "executed_copy": str(destination),
        "kernel_name": kernel_name,
        "timeout_sec": timeout_sec,
        "duration_sec": round(time.time() - started, 2),
        "success": success,
        "error": error,
        "workspace_dir": str(workspace_dir),
        "staged_path_map": staged_path_map,
        "staged_extra_paths": staged_extras,
        "preflight": preflight,
        "assessment": assessment,
    }


def main():
    bootstrap = bootstrap_runtime_dirs()
    args = parse_args()
    require_trusted_notebook_code("teareduce_notebook_runner", args.trust_notebook_code)
    output_root = Path(args.output_dir)

    candidates = [
        path
        for path in notebook_candidates(args.paths, max_notebooks=max(32, args.max_notebooks * 4))
        if path.suffix.lower() == ".ipynb" or path.name.lower().endswith(".ipynb.txt")
    ][: args.max_notebooks]

    run_ids = [path.stem for path in candidates]
    duplicate_run_ids = sorted({item for item in run_ids if run_ids.count(item) > 1})
    output_conflict = output_root.is_symlink() or (
        output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir()))
    )
    if duplicate_run_ids or output_conflict:
        findings = []
        if duplicate_run_ids:
            findings.append(
                "Notebook basenames would share an output workspace: "
                + ", ".join(duplicate_run_ids)
                + ". Select one input at a time or rename only a copied source."
            )
        if output_conflict:
            findings.append(
                "--output-dir must be absent or empty; refusing to overwrite prior notebook runs."
            )
        payload = build_blocked_payload(
            "teareduce_notebook_runner",
            " ".join(findings),
            artifacts={},
            results={
                "duplicate_run_ids": duplicate_run_ids,
                "blocked_output_dir": str(output_root) if output_conflict else None,
            },
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        raise SystemExit(2)

    block_notebook_output_collisions(
        "teareduce_notebook_runner",
        notebook_paths=candidates,
        extra_paths=args.stage_extra,
        outputs=[
            ("--summary-json", args.summary_json),
            ("--manifest-json", args.manifest_json),
        ],
        output_dirs=[("--output-dir", output_root)],
    )

    output_root.mkdir(parents=True, exist_ok=True)

    runs = []
    for notebook_path in candidates:
        run_dir = output_root / notebook_path.stem
        runs.append(
            execute_copy(
                notebook_path,
                run_dir,
                kernel_name=args.kernel_name,
                timeout_sec=args.timeout_sec,
                extra_stage_paths=args.stage_extra,
            )
        )

    payload = {
        "tool": "teareduce_notebook_runner",
        "environment": environment_summary(extra={"runtime_overrides": bootstrap}),
        "teareduce": inspect_teareduce_environment(),
        "requested_paths": args.paths,
        "executed_count": len(runs),
        "runs": runs,
        "notes": [
            "Original notebooks were not modified; each execution wrote a copied notebook to the output directory.",
            "Execution stages writable copies of any discovered absolute input paths under the output directory before running the notebook.",
            "TEAREDUCE package discovery describes only the launcher Python, not the selected notebook kernel; inspect that kernel separately.",
        ],
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
    if args.manifest_json:
        outputs = [Path(run["executed_copy"]) for run in runs if Path(run["executed_copy"]).exists()]
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[Path(item) for item in args.paths if Path(item).exists()],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "max_notebooks": args.max_notebooks,
                "stage_extra": args.stage_extra,
            },
            command="teareduce_notebook_runner.py",
            notes=payload["notes"],
            extra={"runs": runs, "teareduce": payload["teareduce"]},
        )
    raise SystemExit(0 if all(run["success"] for run in runs) else 1)


if __name__ == "__main__":
    main()
