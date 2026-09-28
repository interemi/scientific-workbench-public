#!/usr/bin/env python3
"""Inspect mixed document bundles for handoff, intake, and operational review workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from _internal.path_safety import canonical_path, output_overlaps_input
from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.run_bundle import add_run_bundle_argument, apply_run_bundle_defaults, finalize_existing_run_bundle
from _internal.runtime_common import clean_known_stderr, configure_runtime


DOCUMENT_EXTS = {
    ".pdf",
    ".docx",
    ".docm",
    ".doc",
    ".pptx",
    ".pptm",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".xlsb",
    ".txt",
    ".md",
    ".rtf",
    ".pages",
    ".numbers",
    ".key",
    ".odt",
    ".ods",
    ".odp",
    ".epub",
    ".html",
    ".htm",
    ".tex",
}

PRESENTATION_EXTS = {".pptx", ".pptm", ".key", ".odp"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Documents or directories containing mixed document sets.")
    parser.add_argument("--deep-pdf", action="store_true", help="Run PDF recovery/OCR alongside semantic inspection for PDF files.")
    parser.add_argument("--max-files", type=int, default=24, help="Maximum number of documents to inspect.")
    parser.add_argument("--output-dir", help="Directory for intake artifacts and reports.")
    parser.add_argument("--summary-json", help="Optional summary JSON.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    add_run_bundle_argument(parser)
    args = parser.parse_args()
    if not args.output_dir and not args.run_dir:
        parser.error("--output-dir is required unless --run-dir is supplied.")
    return args


def discover_documents(inputs: list[str], limit: int) -> tuple[list[Path], dict]:
    if limit < 1:
        raise ValueError("--max-files must be at least 1.")
    found = []
    seen = set()
    scan = {
        "input_count": len(inputs),
        "max_files": limit,
        "limit_reached": False,
        "missing_inputs": [],
        "unsupported_file_inputs": [],
    }
    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            scan["missing_inputs"].append(public_path(path))
            continue
        if path.is_file():
            resolved = str(path.resolve())
            if path.suffix.lower() not in DOCUMENT_EXTS:
                scan["unsupported_file_inputs"].append(public_path(path))
            elif resolved not in seen:
                if len(found) >= limit:
                    scan["limit_reached"] = True
                    break
                found.append(path.resolve())
                seen.add(resolved)
            continue
        if not path.is_dir():
            continue
        for item in sorted(path.rglob("*")):
            if not item.is_file():
                continue
            if item.suffix.lower() not in DOCUMENT_EXTS:
                continue
            resolved = str(item.resolve())
            if resolved in seen:
                continue
            if len(found) >= limit:
                scan["limit_reached"] = True
                break
            found.append(item.resolve())
            seen.add(resolved)
        if scan["limit_reached"]:
            break
    scan["found_count"] = len(found)
    return found, scan


def output_path_inside_input(output_path: str | Path, inputs: list[str]) -> Path | None:
    for raw in inputs:
        if output_overlaps_input(output_path, raw):
            return canonical_path(raw)
    return None


def output_directory_inside_input(output_dir: str | Path, inputs: list[str]) -> Path | None:
    return output_path_inside_input(output_dir, inputs)


def summarize_child_error(stdout: str, stderr: str) -> tuple[str, str, bool]:
    raw = (stderr or stdout or "").strip()
    if not raw:
        return "", "", False
    had_traceback = "Traceback (most recent call last)" in raw
    if not had_traceback:
        return stdout[-4000:], clean_known_stderr(stderr[-4000:]), False
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    primary = ""
    for line in lines:
        if line.startswith("Traceback") or line.startswith("File ") or line.startswith("~"):
            continue
        primary = line
        break
    final = lines[-1] if lines else "child command failed"
    if primary and primary != final:
        summary = f"{primary}\n{final}\n[child traceback omitted by document_intake_workbench]"
    else:
        summary = f"{final}\n[child traceback omitted by document_intake_workbench]"
    return "", clean_known_stderr(summary[-4000:]), True


def run_json_command(cmd: list[str]) -> tuple[dict | None, dict]:
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    payload = None
    for item in reversed(cmd):
        if item.endswith(".json") and Path(item).exists():
            try:
                payload = json.loads(Path(item).read_text(encoding="utf-8"))
            except Exception:
                payload = None
            break
    stdout, stderr, traceback_omitted = summarize_child_error(completed.stdout[-4000:], completed.stderr[-4000:])
    if completed.returncode == 0:
        stdout = completed.stdout[-4000:]
        stderr = clean_known_stderr(completed.stderr[-4000:])
    return payload, {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "traceback_omitted": traceback_omitted,
    }


def run_script_with_optional_datanalysis(script: Path, script_args: list[str]) -> tuple[dict | None, dict]:
    primary_cmd = [sys.executable, str(script), *script_args]
    payload, runtime = run_json_command(primary_cmd)
    datanalysis_wrapper = script.parent / "datanalysis_env.py"
    if runtime["returncode"] == 0 or not datanalysis_wrapper.exists():
        return payload, runtime
    fallback_cmd = [sys.executable, str(datanalysis_wrapper), "run-script", str(script), *script_args]
    fallback_payload, fallback_runtime = run_json_command(fallback_cmd)
    if fallback_runtime["returncode"] == 0:
        fallback_runtime["fallback_from"] = runtime
        return fallback_payload, fallback_runtime
    return payload, runtime


def summarize_runtime_failures(runtimes: list[dict]) -> list[dict]:
    failures = []
    for runtime in runtimes:
        if runtime.get("returncode") == 0:
            continue
        failures.append(
            {
                "command": runtime.get("command", [])[:3],
                "returncode": runtime.get("returncode"),
                "error": (runtime.get("stderr") or runtime.get("stdout") or "child command failed")[:600],
            }
        )
    return failures


def summarize_item(path: Path, semantic_payload: dict | None, presentation_payload: dict | None, pdf_payload: dict | None, runtimes: list[dict]) -> dict:
    payload = semantic_payload or {}
    presentation = presentation_payload or {}
    pdf = pdf_payload or {}
    inspection = presentation.get("inspection", {})
    runtime_failures = summarize_runtime_failures(runtimes)
    excerpt = payload.get("text_excerpt") or pdf.get("ocr_text_excerpt") or pdf.get("native_text_excerpt") or ""
    method = payload.get("method") or inspection.get("note") or "mixed"
    if runtime_failures and not payload and not presentation and not pdf:
        method = "inspection_failed"
    return {
        "path": public_path(path),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "method": method,
        "pages": payload.get("pages"),
        "slide_count": payload.get("slide_count") or inspection.get("slide_count"),
        "sheet_count": payload.get("sheet_count"),
        "figure_count": pdf.get("figure_count"),
        "ocr_used": bool(pdf),
        "excerpt_length": len(excerpt),
        "excerpt_preview": excerpt[:240],
        "runtime_failure_count": len(runtime_failures),
        "runtime_failures": runtime_failures,
        "runtime": runtimes,
    }


def write_inventory_csv(path: Path, rows: list[dict]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "suffix", "method", "pages", "slide_count", "sheet_count", "figure_count", "ocr_used", "excerpt_length", "path"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def write_report(path: Path, summary: dict) -> None:
    lines = [
        "# Document Intake Workbench",
        "",
        f"- Files inspected: `{summary['file_count']}`",
        f"- Extensions seen: `{', '.join(summary['extensions_seen'])}`",
        f"- Deep PDF recovery used: `{summary['deep_pdf']}`",
        "",
        "## Inventory",
        "",
    ]
    for item in summary["files"]:
        lines.append(
            f"- `{item['name']}` [{item['suffix']}] -> method `{item['method']}`, pages `{item['pages']}`, slides `{item['slide_count']}`, sheets `{item['sheet_count']}`, OCR `{item['ocr_used']}`"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This workflow is intended for mixed office/admin/education/project-document bundles where the first task is to understand what is there without editing originals.",
            "- Presentation files are inspected with the copied-deck presentation toolchain when possible, while other documents go through semantic extraction and optional PDF recovery.",
        ]
    )
    findings = summary.get("qa", {}).get("findings") or []
    if findings:
        lines.extend(["", "## Findings", ""])
        for finding in findings:
            if isinstance(finding, dict):
                title = finding.get("title") or finding.get("detail") or "finding"
                lines.append(f"- `{finding.get('severity', 'warning')}`: {title}")
            else:
                lines.append(f"- {finding}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_payload_safely(payload: dict, summary_json: str | None = None) -> None:
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    if summary_json:
        target = Path(summary_json)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.is_dir():
                raise RuntimeError(f"--summary-json points to a directory, not a file: {public_path(target)}")
            target.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Could not write --summary-json to {public_path(target)}: {exc}") from None
    print(rendered, end="")


def build_failure_payload(args, exc: Exception) -> dict:
    return standard_tool_payload(
        "document_intake_workbench",
        status="fail",
        notes=[
            "The mixed-document intake failed before it could complete cleanly.",
            "No input documents were edited.",
        ],
        artifacts={
            "output_dir": getattr(args, "output_dir", None),
            "summary_json": getattr(args, "summary_json", None),
            "manifest_json": getattr(args, "manifest_json", None),
        },
        results={
            "inputs": getattr(args, "inputs", []),
            "max_files": getattr(args, "max_files", None),
            "deep_pdf": bool(getattr(args, "deep_pdf", False)),
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
        qa={
            "status": "fail",
            "findings": [{"severity": "high", "title": "Document intake failed", "detail": str(exc)}],
            "metrics": {"file_count": 0},
        },
        include_environment=True,
    )


def emit_controlled_block(args, message: str, *, error_type: str | None = None) -> int:
    artifacts = (
        {}
        if error_type == "output_input_collision"
        else {
            "output_dir": getattr(args, "output_dir", None),
            "summary_json": getattr(args, "summary_json", None),
            "manifest_json": getattr(args, "manifest_json", None),
        }
    )
    payload = standard_tool_payload(
        "document_intake_workbench",
        status="blocked",
        notes=[message, "No input documents were edited."],
        artifacts=artifacts,
        results={
            "inputs": getattr(args, "inputs", []),
            "blocked_reason": message,
            "error_type": error_type,
        },
        qa={"status": "blocked", "findings": [message], "metrics": {"file_count": 0, "blocking_count": 1}},
        legacy={"blocked_reason": message, "file_count": 0},
    )
    try:
        emit_payload_safely(payload, getattr(args, "summary_json", None))
    except Exception:
        print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", end="")
    manifest_json = getattr(args, "manifest_json", None)
    if manifest_json:
        outputs = []
        summary_json = getattr(args, "summary_json", None)
        if summary_json and Path(summary_json).is_file():
            outputs.append(Path(summary_json))
        try:
            write_manifest(
                manifest_json,
                inputs=[Path(item) for item in getattr(args, "inputs", [])],
                outputs=outputs,
                parameters={
                    "deep_pdf": bool(getattr(args, "deep_pdf", False)),
                    "max_files": getattr(args, "max_files", None),
                    "status": "blocked",
                },
                command="document_intake_workbench.py",
                notes=payload["notes"],
                extra={"summary": payload},
            )
        except Exception:
            pass
    layout = getattr(args, "_run_bundle_layout", None)
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=2)
    return 2


def run_intake(args) -> None:
    configure_runtime("document_intake_workbench")
    script_dir = Path(__file__).resolve().parent
    semantics_script = script_dir / "document_semantics.py"
    presentation_script = script_dir / "presentation_workbench.py"
    pdf_script = script_dir / "pdf_recover_extract.py"

    document_paths, discovery = discover_documents(args.inputs, args.max_files)

    output_dir = Path(args.output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise RuntimeError(f"--output-dir exists and is not a directory: {public_path(output_dir)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    semantics_dir = output_dir / "semantics"
    pdf_dir = output_dir / "pdf_recovery"
    semantics_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    files = []
    outputs = []
    for index, path in enumerate(document_paths, start=1):
        runtimes = []
        semantic_json = semantics_dir / f"{index:02d}_{path.stem}.json"
        semantic_out_dir = semantics_dir / f"{index:02d}_{path.stem}_assets"
        semantic_payload, runtime = run_script_with_optional_datanalysis(
            semantics_script,
            [
                str(path),
                "--output-json",
                str(semantic_json),
                "--output-dir",
                str(semantic_out_dir),
            ],
        )
        runtimes.append(runtime)
        if semantic_json.exists():
            outputs.append(semantic_json)

        presentation_payload = None
        if path.suffix.lower() in PRESENTATION_EXTS:
            presentation_json = semantics_dir / f"{index:02d}_{path.stem}_presentation.json"
            presentation_payload, runtime = run_script_with_optional_datanalysis(
                presentation_script,
                [
                    "inspect",
                    str(path),
                    "--summary-json",
                    str(presentation_json),
                ],
            )
            runtimes.append(runtime)
            if presentation_json.exists():
                outputs.append(presentation_json)

        pdf_payload = None
        if args.deep_pdf and path.suffix.lower() == ".pdf":
            pdf_json = pdf_dir / f"{index:02d}_{path.stem}.json"
            pdf_artifact_dir = pdf_dir / f"{index:02d}_{path.stem}"
            pdf_payload, runtime = run_script_with_optional_datanalysis(
                pdf_script,
                [
                    str(path),
                    "--output-dir",
                    str(pdf_artifact_dir),
                    "--summary-json",
                    str(pdf_json),
                ],
            )
            runtimes.append(runtime)
            if pdf_json.exists():
                outputs.append(pdf_json)

        files.append(summarize_item(path, semantic_payload, presentation_payload, pdf_payload, runtimes))

    extensions = Counter(item["suffix"] for item in files)
    failed_items = [item for item in files if item.get("runtime_failure_count")]
    findings = []
    if not files:
        findings.append(
            {
                "severity": "medium",
                "title": "No supported documents found",
                "detail": "No document with a supported extension was found in the provided inputs.",
            }
        )
    if discovery.get("missing_inputs"):
        findings.append(
            {
                "severity": "medium",
                "title": "Some input paths were missing",
                "detail": "; ".join(discovery["missing_inputs"][:5]),
            }
        )
    if discovery.get("unsupported_file_inputs"):
        findings.append(
            {
                "severity": "low",
                "title": "Some explicit file inputs were unsupported",
                "detail": "; ".join(discovery["unsupported_file_inputs"][:5]),
            }
        )
    if discovery.get("limit_reached"):
        findings.append(
            {
                "severity": "medium",
                "title": "File limit reached",
                "detail": f"Only the first {args.max_files} supported documents were inspected. Increase --max-files for full intake.",
            }
        )
    if failed_items:
        findings.append(
            {
                "severity": "high",
                "title": "One or more document inspections failed",
                "detail": ", ".join(item["name"] for item in failed_items[:8]),
            }
        )
    status = "ok" if not findings else "warning"
    legacy_summary = {
        "tool": "document_intake_workbench",
        "environment": environment_summary(),
        "file_count": len(files),
        "extensions_seen": sorted(extensions),
        "extension_counts": dict(extensions),
        "deep_pdf": bool(args.deep_pdf),
        "discovery": discovery,
        "files": files,
        "notes": [
            "This workflow is useful for project folders, meeting packs, admin archives, teaching materials, proposals, and mixed office/PDF bundles outside strict science-only work.",
            "It stays copy-safe and read-only on the originals while producing semantic summaries and optional PDF recovery artifacts.",
        ],
    }
    inventory_csv = output_dir / "inventory.csv"
    report_md = output_dir / "report.md"
    qa = {
        "status": status,
        "findings": findings,
        "metrics": {
            "file_count": len(files),
            "presentation_count": sum(1 for item in files if item.get("slide_count")),
            "sheet_like_count": sum(1 for item in files if item.get("sheet_count")),
            "runtime_failure_count": sum(item.get("runtime_failure_count", 0) for item in files),
            "failed_item_count": len(failed_items),
            "limit_reached": bool(discovery.get("limit_reached")),
            "missing_input_count": len(discovery.get("missing_inputs", [])),
            "unsupported_file_input_count": len(discovery.get("unsupported_file_inputs", [])),
        },
    }
    summary = standard_tool_payload(
        "document_intake_workbench",
        status=status,
        notes=legacy_summary["notes"],
        artifacts={
            "inventory_csv": inventory_csv,
            "report_md": report_md,
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
        },
        results={"intake": legacy_summary},
        qa=qa,
        legacy=legacy_summary,
    )
    write_inventory_csv(inventory_csv, files)
    write_report(report_md, summary)
    outputs.extend([inventory_csv, report_md])

    emit_payload_safely(summary, args.summary_json)
    if args.summary_json:
        outputs.append(Path(args.summary_json))

    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=document_paths,
            outputs=outputs,
            parameters={"deep_pdf": args.deep_pdf, "max_files": args.max_files},
            command="document_intake_workbench.py",
            notes=summary["notes"],
            extra={"summary": summary},
        )
    layout = getattr(args, "_run_bundle_layout", None)
    if layout is not None:
        finalize_existing_run_bundle(layout, summary, returncode=0)


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    effective_output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else (run_dir / "artifacts" if run_dir else None)
    )
    requested_outputs: list[tuple[str, Path | str | None]] = [
        ("--output-dir", args.output_dir),
        ("--run-dir", run_dir),
        ("--summary-json", args.summary_json or (run_dir / "summary.json" if run_dir else None)),
        ("--manifest-json", args.manifest_json or (run_dir / "manifest.json" if run_dir else None)),
    ]
    if effective_output_dir is not None:
        requested_outputs.extend(
            [
                ("derived:inventory.csv", effective_output_dir / "inventory.csv"),
                ("derived:report.md", effective_output_dir / "report.md"),
            ]
        )
    if run_dir is not None:
        requested_outputs.extend(
            (f"derived:{name}", run_dir / name)
            for name in ("stdout.txt", "stderr.txt", "command.txt", "next_steps.md")
        )
    overlaps: list[tuple[str, Path]] = []
    for option, value in requested_outputs:
        if value:
            protected_input = output_path_inside_input(value, args.inputs)
            if protected_input is not None:
                overlaps.append((option, protected_input))
    if overlaps:
        option, overlapping_input = overlaps[0]
        args.summary_json = None
        args.manifest_json = None
        args.run_dir = None
        return emit_controlled_block(
            args,
            f"Refusing {option} because it overlaps input {public_path(overlapping_input)}; choose a separate derived-output location.",
            error_type="output_input_collision",
        )
    apply_run_bundle_defaults(args, output_attr="output_dir")
    if len(args.inputs) == 1 and not Path(args.inputs[0]).expanduser().exists():
        return emit_controlled_block(args, f"Input path does not exist: {public_path(Path(args.inputs[0]))}")
    try:
        run_intake(args)
        return 0
    except Exception as exc:
        payload = build_failure_payload(args, exc)
        try:
            emit_payload_safely(payload, getattr(args, "summary_json", None))
        except Exception:
            print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", end="")
        layout = getattr(args, "_run_bundle_layout", None)
        if layout is not None:
            finalize_existing_run_bundle(layout, payload, returncode=2)
        return 2


if __name__ == "__main__":
    sys.exit(main())
