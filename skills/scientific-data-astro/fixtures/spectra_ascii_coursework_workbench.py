#!/usr/bin/env python3
"""Golden path for coursework with 1D ASCII spectra, an optional notebook, and a report bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from latex_workbench import build_review_markdown, render_scaffold, review_project
from notebook_workbench import execute_notebook_copy, inspect_notebook, preflight_notebook_execution
from _internal.ocr_utils import render_pdf_pages
from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload_best_effort
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, compile_latex_project, suppress_fd_output


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spectra", nargs="+", help="ASCII spectra to analyze.")
    parser.add_argument("--output-dir", required=True, help="Directory for the coursework bundle.")
    parser.add_argument("--notebook", help="Optional existing notebook to copy and optionally execute.")
    parser.add_argument("--execute-notebook", action="store_true", help="Execute the copied notebook when --notebook is provided.")
    parser.add_argument("--kernel-name", default="python3")
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--report-title", default="ASCII Spectra Coursework Report")
    parser.add_argument("--report-author", default="Student Name")
    parser.add_argument("--skip-report-project", action="store_true", help="Do not scaffold a LaTeX report project.")
    parser.add_argument("--compile-report", action="store_true", help="Attempt to compile the generated LaTeX report project.")
    parser.add_argument("--stage-extra", action="append", default=[], help="Extra file or directory to stage into the notebook workspace.")
    parser.add_argument(
        "--line-window",
        nargs=3,
        action="append",
        metavar=("LABEL", "XMIN", "XMAX"),
        default=[],
        help="Optional line window to characterize in every spectrum.",
    )
    parser.add_argument("--summary-json")
    parser.add_argument("--manifest-json")
    return parser.parse_args()


def run_ascii_workbench(spectra: list[str], output_dir: Path, line_windows: list[list[str]]) -> dict:
    from ascii_spectrum_workbench import parse_ascii_spectrum, profile_spectrum, write_inventory_csv, write_overlay_plot, write_report

    spectrum_dir = output_dir / "spectra_analysis"
    spectrum_dir.mkdir(parents=True, exist_ok=True)
    profiles = [profile_spectrum(Path(item), line_windows) for item in spectra]
    inventory_csv = spectrum_dir / "spectrum_inventory.csv"
    overlay_raw = spectrum_dir / "overlay_raw.png"
    overlay_norm = spectrum_dir / "overlay_normalized.png"
    report_md = spectrum_dir / "report.md"
    write_inventory_csv(inventory_csv, profiles)
    write_overlay_plot(overlay_raw, profiles, normalized=False)
    write_overlay_plot(overlay_norm, profiles, normalized=True)
    write_report(
        report_md,
        profiles,
        outputs={"inventory": inventory_csv, "overlay_raw": overlay_raw, "overlay_norm": overlay_norm},
    )
    return {
        "profiles": profiles,
        "inventory_csv": str(inventory_csv),
        "overlay_raw": str(overlay_raw),
        "overlay_normalized": str(overlay_norm),
        "report_md": str(report_md),
    }


def resolve_summary_path(args, output_dir: Path | None = None) -> Path | None:
    if getattr(args, "summary_json", None):
        return Path(args.summary_json).expanduser()
    if output_dir is not None:
        return output_dir / "summary.json"
    return None


def emit_blocked(args, message: str, error_type: str | None = None) -> int:
    output_dir = Path(args.output_dir).expanduser() if getattr(args, "output_dir", None) else None
    summary_path = resolve_summary_path(args, output_dir)
    payload = build_blocked_payload(
        "spectra_ascii_coursework_workbench",
        message,
        notes=[
            "The coursework spectra bundle was not completed.",
            "The workflow leaves original spectra and notebooks untouched; rerun after fixing the blocked input or destination.",
        ],
        artifacts={"summary_json": summary_path, "output_dir": output_dir},
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "spectra": list(getattr(args, "spectra", []) or []),
            "notebook": getattr(args, "notebook", None),
            "output_dir": str(output_dir) if output_dir else None,
        },
        legacy={"blocked_reason": message},
        inputs=[*list(getattr(args, "spectra", []) or []), getattr(args, "notebook", None)],
    )
    emit_payload_best_effort(payload, summary_path)
    return 2


def quality_findings(spectrum_bundle: dict) -> list[str]:
    findings = []
    for profile in spectrum_bundle.get("profiles", []):
        name = profile.get("name") or Path(profile.get("path", "spectrum")).name
        for flag in profile.get("quality_flags", []):
            if "heuristic feature proxies" in flag:
                continue
            findings.append(f"{name}: {flag}")
    return findings


def preflight_embedded_notebook_execution(notebook_path: Path) -> dict:
    preflight = preflight_notebook_execution(notebook_path)
    input_calls = (preflight.get("execution_signals") or {}).get("interactive_input_calls") or []
    if input_calls:
        raise SystemExit(
            "Notebook calls input(); this coursework bundle command cannot provide documented input values. "
            "Run notebook_workbench.py execute-copy with --input-value first, or remove the interactive prompt from the copied notebook."
        )
    return preflight


def build_notebook_appendix(summary: dict) -> str:
    lines = [
        "## Coursework bundle notes",
        "",
        "This copied notebook is part of a coursework bundle generated by `spectra_ascii_coursework_workbench.py`.",
        "",
        "Generated analysis outputs:",
        f"- Inventory: `{public_path(summary['spectrum_bundle']['inventory_csv'])}`",
        f"- Raw overlay: `{public_path(summary['spectrum_bundle']['overlay_raw'])}`",
        f"- Normalized overlay: `{public_path(summary['spectrum_bundle']['overlay_normalized'])}`",
        f"- Spectrum report: `{public_path(summary['spectrum_bundle']['report_md'])}`",
    ]
    return "\n".join(lines)


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(text))


def copy_output(source: str, target_dir: Path, target_name: str | None = None) -> Path:
    src = Path(source).expanduser()
    target = target_dir / (target_name or src.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return target


def build_inventory_table_tex(path: Path, profiles: list[dict]) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Spectrum & Samples & $\lambda_{\min}$ & $\lambda_{\max}$ & Outlier frac. & Flags \\",
        r"\midrule",
    ]
    for item in profiles:
        lines.append(
            "{} & {} & {:.2f} & {:.2f} & {:.4f} & {} \\\\".format(
                latex_escape(Path(item["path"]).stem),
                item["samples"],
                item["wavelength_min"],
                item["wavelength_max"],
                item["outlier_fraction"],
                len(item["quality_flags"]),
            )
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\caption{Compact QA summary for the reduced ASCII spectra in this coursework bundle.}",
            r"\label{tab:inventory}",
            r"\end{table*}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_introduction_section(payload: dict) -> str:
    count = len(payload["spectrum_bundle"]["profiles"])
    return "\n".join(
        [
            "This report scaffold was generated from a non-destructive coursework bundle built around reduced ASCII spectra and an optional notebook.",
            "",
            f"The current bundle contains {count} reduced spectra, quick QA overlays, a machine-readable inventory table, and an optional copied notebook workflow.",
            "Replace this introduction with the scientific motivation and the course-specific question before submission.",
        ]
    )


def build_data_method_section(payload: dict) -> str:
    profiles = payload["spectrum_bundle"]["profiles"]
    monotonic_failures = sum(1 for item in profiles if not item["monotonic_increasing"])
    outlier_flagged = sum(1 for item in profiles if item["outlier_fraction"] >= 0.02)
    notebook_lines = []
    if payload["notebook"]:
        notebook_lines.extend(
            [
                f"An existing notebook was supplied: \\texttt{{{latex_escape(Path(payload['notebook']).name)}}}.",
                "The skill always works on a copied notebook rather than touching the original.",
            ]
        )
        if payload["notebook_execution"]:
            notebook_lines.append(
                "A copied notebook execution attempt was also generated as part of this bundle."
            )
    return "\n".join(
        [
            "The workflow used the reduced ASCII spectra as provided and treated them first as QA and comparison products rather than as automatic classifications.",
            "",
            f"Across the bundle, {monotonic_failures} spectra failed strict monotonicity checks and {outlier_flagged} spectra triggered a spike-like outlier warning.",
            "Requested line windows were summarized only as heuristic feature proxies inside predefined wavelength ranges.",
            "These window summaries should not be treated as secure astrophysical identifications without manual inspection and course context.",
            "",
            *notebook_lines,
            "",
            "Table~\\ref{tab:inventory} gives a compact machine-readable overview of the spectra used here.",
            "\\input{tables/inventory_preview}",
        ]
    )


def build_results_section(payload: dict) -> str:
    profiles = payload["spectrum_bundle"]["profiles"]
    lines = [
        "Figures~\\ref{fig:overlay-raw} and~\\ref{fig:overlay-norm} collect the main comparison assets generated automatically for the coursework bundle.",
        "",
        r"\begin{figure*}[t]",
        r"\centering",
        r"\includegraphics[width=0.9\textwidth]{figures/overlay_raw.png}",
        r"\caption{Raw overlay of the reduced ASCII spectra.}",
        r"\label{fig:overlay-raw}",
        r"\end{figure*}",
        "",
        r"\begin{figure*}[t]",
        r"\centering",
        r"\includegraphics[width=0.9\textwidth]{figures/overlay_normalized.png}",
        r"\caption{Normalized overlay using the 95th percentile as a practical scaling proxy.}",
        r"\label{fig:overlay-norm}",
        r"\end{figure*}",
        "",
        "The following per-spectrum notes are deliberately cautious and should be refined manually in the final submitted report:",
        "",
    ]
    for item in profiles:
        flags = item["quality_flags"] or ["none"]
        lines.append(
            "\\paragraph{{{}}} The spectrum covers {:.2f} to {:.2f} with {} samples. QA flags: {}.".format(
                latex_escape(Path(item["path"]).stem),
                item["wavelength_min"],
                item["wavelength_max"],
                item["samples"],
                latex_escape("; ".join(flags)),
            )
        )
        covered_windows = [window for window in item["line_windows"] if window.get("covered")]
        if covered_windows:
            window_bits = []
            for window in covered_windows:
                sigma = window.get("feature_strength_sigma")
                sigma_text = "{:.2f}".format(sigma) if sigma is not None else "n/a"
                window_bits.append(
                    "{}: tentative {} proxy near {:.2f} (support={}, strength~{} sigma)".format(
                        window["label"],
                        window["line_character"],
                        window["feature_center"],
                        window["support_level"],
                        sigma_text,
                    )
                )
            lines.append("Requested windows: {}.".format(latex_escape("; ".join(window_bits))))
        lines.append("")
    return "\n".join(lines)


def build_discussion_section(payload: dict) -> str:
    notebook_status = None
    if payload["notebook_execution"]:
        notebook_status = payload["notebook_execution"]["assessment"]["status"]
    notebook_note = (
        f" The notebook-copy workflow ended with status `{latex_escape(str(notebook_status))}`."
        if notebook_status
        else ""
    )
    return "\n".join(
        [
            "This scaffold intentionally stops short of a fully automatic scientific conclusion.",
            "Its role is to reduce manual glue between reduced spectra, notebook work, and the final memory while keeping the interpretation physically cautious.",
            "In particular, the line-window outputs are feature proxies only, not automatic classifications or line identifications." + notebook_note,
            "",
            "Before submission, replace this section with the domain-specific interpretation actually justified by the course data, the notebook results, and any lecturer or supervisor guidance.",
        ]
    )


def build_conclusion_section(payload: dict) -> str:
    lines = [
        "The generated bundle already contains the key reproducible assets needed to finish the coursework report:",
        "",
        r"\begin{itemize}",
        r"\item a machine-readable spectrum inventory,",
        r"\item raw and normalized comparison plots,",
        r"\item an optional copied notebook workflow, and",
        r"\item this editable academic-report project.",
        r"\end{itemize}",
        "",
        "The remaining work should mainly be scientific interpretation, figure/text polishing, and any course-specific bibliography or discussion updates.",
    ]
    return "\n".join(lines)


def build_appendix_section(payload: dict) -> str:
    notes = [
        "The full machine-readable inventory is copied into \\texttt{tables/spectrum_inventory.csv}.",
        "The upstream coursework bundle summary is available in \\texttt{coursework_bundle_report.md}.",
    ]
    if payload["notebook_execution"]:
        notes.append("A copied notebook execution artifact is included in the bundle and can be cited or inspected manually if needed.")
    return "\n".join(
        [
            "This appendix is a placeholder for wide tables, notebook snapshots, or extra QA diagnostics that do not fit comfortably in the two-column body.",
            "",
            r"\begin{itemize}",
            *[rf"\item {latex_escape(item)}" for item in notes],
            r"\end{itemize}",
        ]
    )


def build_report_project(output_dir: Path, payload: dict, title: str, author: str, compile_report: bool) -> dict:
    project_dir = output_dir / "report_project"
    figures_dir = project_dir / "figures"
    tables_dir = project_dir / "tables"
    sections_dir = project_dir / "sections"
    for directory in (project_dir, figures_dir, tables_dir, sections_dir):
        directory.mkdir(parents=True, exist_ok=True)

    scaffold = render_scaffold("academic-report", title, author)
    main_tex = scaffold["main.tex"]
    main_tex = main_tex.replace(
        "State the context, motivation, and research question.",
        r"\input{sections/introduction}",
    )
    main_tex = main_tex.replace(
        "Describe the inputs, selection choices, assumptions, and reproducible workflow. Distinguish exploratory decisions from validated ones.",
        r"\input{sections/data_method}",
    )
    main_tex = main_tex.replace(
        "Present the main quantitative outputs. Prefer generated figures and tables over manual copy-paste.",
        r"\input{sections/results}",
    )
    main_tex = main_tex.replace(
        "Explain what is supported strongly, what is only suggestive, and which limitations matter most.",
        r"\input{sections/discussion}",
    )
    main_tex = main_tex.replace(
        "Summarize the main result and the next logical step.",
        r"\input{sections/conclusion}",
    )
    main_tex = main_tex.replace(
        "Use the appendix for wide tables, supplementary diagnostics, or generated listings.",
        r"\input{sections/appendix}",
    )

    main_tex_path = project_dir / "main.tex"
    references_path = project_dir / "references.bib"
    main_tex_path.write_text(main_tex, encoding="utf-8")
    references_path.write_text(scaffold["references.bib"], encoding="utf-8")

    overlay_raw = copy_output(payload["spectrum_bundle"]["overlay_raw"], figures_dir, "overlay_raw.png")
    overlay_norm = copy_output(payload["spectrum_bundle"]["overlay_normalized"], figures_dir, "overlay_normalized.png")
    inventory_csv = copy_output(payload["spectrum_bundle"]["inventory_csv"], tables_dir, "spectrum_inventory.csv")
    inventory_preview = tables_dir / "inventory_preview.tex"
    build_inventory_table_tex(inventory_preview, payload["spectrum_bundle"]["profiles"])

    (sections_dir / "introduction.tex").write_text(build_introduction_section(payload) + "\n", encoding="utf-8")
    (sections_dir / "data_method.tex").write_text(build_data_method_section(payload) + "\n", encoding="utf-8")
    (sections_dir / "results.tex").write_text(build_results_section(payload) + "\n", encoding="utf-8")
    (sections_dir / "discussion.tex").write_text(build_discussion_section(payload) + "\n", encoding="utf-8")
    (sections_dir / "conclusion.tex").write_text(build_conclusion_section(payload) + "\n", encoding="utf-8")
    (sections_dir / "appendix.tex").write_text(build_appendix_section(payload) + "\n", encoding="utf-8")

    review_json_path = project_dir / "review_summary.json"
    review_md_path = project_dir / "review_report.md"
    review_payload = review_project(main_tex_path)
    review_json_path.write_text(json.dumps(review_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    review_md_path.write_text(build_review_markdown(review_payload), encoding="utf-8")

    compile_payload = None
    pdf_path = None
    pdf_preview_pages = []
    if compile_report:
        compile_result = compile_latex_project(main_tex_path, passes=2)
        compile_payload = sanitize_payload(
            {
                "attempted": compile_result["attempted"],
                "success": compile_result["success"],
                "engine": compile_result["engine"],
                "pdf_path": compile_result["pdf_path"],
                "stderr": clean_known_stderr(compile_result.get("stderr") or ""),
            }
        )
        if compile_result["success"]:
            pdf_path = Path(compile_result["pdf_path"])
            preview_dir = project_dir / "pdf_preview"
            pdf_preview_pages = [str(path) for path in render_pdf_pages(pdf_path, preview_dir, max_pages=2, zoom=1.8)]

    return sanitize_payload(
        {
            "project_dir": str(project_dir),
            "main_tex": str(main_tex_path),
            "references_bib": str(references_path),
            "figures": [str(overlay_raw), str(overlay_norm)],
            "inventory_csv": str(inventory_csv),
            "inventory_preview_tex": str(inventory_preview),
            "review_md": str(review_md_path),
            "review_json": str(review_json_path),
            "compile_result": compile_payload,
            "compiled_pdf": str(pdf_path) if pdf_path else None,
            "compiled_pdf_preview_pages": pdf_preview_pages,
        }
    )


def write_bundle_report(path: Path, payload: dict):
    lines = [
        "# Spectra ASCII Coursework Bundle",
        "",
        f"- Spectra count: `{len(payload['spectrum_bundle']['profiles'])}`",
        f"- Notebook provided: `{payload['notebook'] is not None}`",
        f"- Notebook executed: `{payload['notebook_execution'].get('success') if payload['notebook_execution'] else None}`",
        "",
        "## Bundle contents",
        "",
        f"- Spectrum inventory: `{public_path(payload['spectrum_bundle']['inventory_csv'])}`",
        f"- Raw overlay: `{public_path(payload['spectrum_bundle']['overlay_raw'])}`",
        f"- Normalized overlay: `{public_path(payload['spectrum_bundle']['overlay_normalized'])}`",
        f"- Spectrum report: `{public_path(payload['spectrum_bundle']['report_md'])}`",
    ]
    if payload["notebook"]:
        lines.extend(
            [
                f"- Notebook source: `{public_path(payload['notebook'])}`",
                f"- Notebook inspection summary: `{payload['notebook_inspection']['cell_count']}` cells",
            ]
        )
    if payload["notebook_execution"]:
        lines.extend(
            [
                f"- Executed notebook copy: `{public_path(payload['notebook_execution']['executed_copy'])}`",
                f"- Notebook workspace: `{public_path(payload['notebook_execution']['workspace_dir'])}`",
            ]
        )
    if payload.get("report_project"):
        lines.extend(
            [
                f"- Report project: `{public_path(payload['report_project']['project_dir'])}`",
                f"- Report main.tex: `{public_path(payload['report_project']['main_tex'])}`",
                f"- Report review: `{public_path(payload['report_project']['review_md'])}`",
            ]
        )
        if payload["report_project"].get("compiled_pdf"):
            lines.append(f"- Compiled report PDF: `{public_path(payload['report_project']['compiled_pdf'])}`")
        if payload["report_project"].get("compiled_pdf_preview_pages"):
            lines.append(
                f"- Compiled PDF preview pages: `{len(payload['report_project']['compiled_pdf_preview_pages'])}` rendered page(s)"
            )
    lines.extend(["", "## Notes", ""])
    lines.extend([f"- {item}" for item in payload["notes"]])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_workflow(args) -> int:
    output_dir = Path(args.output_dir).expanduser()
    if output_dir.exists() and not output_dir.is_dir():
        raise SystemExit(f"--output-dir must point to a directory, not an existing file: {output_dir}")
    if args.execute_notebook and args.timeout_sec < 5:
        raise SystemExit(
            "--timeout-sec is too low for notebook execution in this integrated coursework bundle; "
            "use at least 5 seconds or run notebook_workbench.py preflight/execute-copy separately."
        )
    notebook_path = Path(args.notebook).expanduser() if args.notebook else None
    if notebook_path and args.execute_notebook:
        preflight_embedded_notebook_execution(notebook_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    spectrum_bundle = run_ascii_workbench(args.spectra, output_dir, args.line_window)
    notebook_info = None
    notebook_execution = None
    if notebook_path:
        notebook_info = inspect_notebook(notebook_path)
        if args.execute_notebook:
            notebook_dir = output_dir / "notebook"
            with suppress_fd_output(True):
                notebook_execution = execute_notebook_copy(
                    notebook_path,
                    notebook_dir,
                    kernel_name=args.kernel_name,
                    timeout_sec=args.timeout_sec,
                    stage_extra=args.stage_extra,
                    append_markdown=[build_notebook_appendix({"spectrum_bundle": spectrum_bundle})],
                )

    report_project = None
    bundle_report = output_dir / "coursework_bundle_report.md"
    legacy_payload = sanitize_payload(
        {
            "tool": "spectra_ascii_coursework_workbench",
            "spectra": [str(Path(item).resolve()) for item in args.spectra],
            "notebook": str(Path(args.notebook).resolve()) if args.notebook else None,
            "spectrum_bundle": spectrum_bundle,
            "notebook_inspection": notebook_info,
            "notebook_execution": notebook_execution,
            "report_project": None,
            "notes": [
                "This is a golden path for coursework based on simple reduced ASCII spectra, an optional notebook, and a final write-up bundle.",
                "Requested line-window summaries are heuristic feature proxies; they are useful for QA and write-up prep, not as automatic scientific conclusions.",
            ],
        }
    )
    if not args.skip_report_project:
        report_project = build_report_project(
            output_dir,
            legacy_payload,
            title=args.report_title,
            author=args.report_author,
            compile_report=args.compile_report,
        )
        legacy_payload["report_project"] = report_project
        legacy_payload["notes"].append("A ready-to-edit academic LaTeX report project was scaffolded inside the coursework bundle.")
        if args.compile_report:
            legacy_payload["notes"].append(
                "Report compilation was attempted on the copied scaffold; inspect the compile result in the report project summary."
            )
    write_bundle_report(bundle_report, legacy_payload)
    legacy_payload["bundle_report_md"] = str(bundle_report)
    findings = quality_findings(spectrum_bundle)
    notebook_failed = bool(notebook_execution and not notebook_execution.get("success"))
    if notebook_failed:
        assessment = notebook_execution.get("assessment", {})
        if assessment.get("status") == "sandbox_blocked":
            findings.append("Notebook execution was blocked by the current runtime sandbox; the copied notebook needs a less restricted execution context.")
            payload_status = "warning"
            qa_status = "warning"
        else:
            findings.append("Notebook execution did not complete successfully; inspect the copied notebook execution assessment before treating the bundle as complete.")
            payload_status = "fail"
            qa_status = "fail"
    elif findings:
        payload_status = "warning"
        qa_status = "warning"
    else:
        payload_status = "ok"
        qa_status = "ok"
    payload = build_tool_payload(
        "spectra_ascii_coursework_workbench",
        status=payload_status,
        notes=legacy_payload["notes"],
        artifacts={"summary_json": args.summary_json or output_dir / "summary.json", "bundle_report_md": bundle_report},
        results=legacy_payload,
        qa={
            "status": qa_status,
            "findings": findings,
            "metrics": {
                "spectrum_count": len(args.spectra),
                "notebook_attached": bool(args.notebook),
                "report_project_created": not args.skip_report_project,
                "quality_finding_count": len(findings),
            },
        },
        legacy=legacy_payload,
    )

    summary_path = resolve_summary_path(args, output_dir)
    emit_payload_best_effort(payload, summary_path)
    outputs = [
        Path(spectrum_bundle["inventory_csv"]),
        Path(spectrum_bundle["overlay_raw"]),
        Path(spectrum_bundle["overlay_normalized"]),
        Path(spectrum_bundle["report_md"]),
        bundle_report,
        summary_path,
    ]
    if notebook_execution:
        outputs.append(Path(notebook_execution["executed_copy"]))
    if report_project:
        outputs.extend(
            [
                Path(report_project["main_tex"]),
                Path(report_project["review_md"]),
                Path(report_project["review_json"]),
                Path(report_project["inventory_csv"]),
                Path(report_project["inventory_preview_tex"]),
            ]
        )
        if report_project.get("compiled_pdf"):
            outputs.append(Path(report_project["compiled_pdf"]))
        for preview in report_project.get("compiled_pdf_preview_pages", []):
            outputs.append(Path(preview))
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[Path(item) for item in args.spectra] + ([Path(args.notebook)] if args.notebook else []),
            outputs=outputs,
            parameters={
                "execute_notebook": args.execute_notebook,
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "line_window": args.line_window,
                "skip_report_project": args.skip_report_project,
                "compile_report": args.compile_report,
                "report_title": args.report_title,
                "report_author": args.report_author,
            },
            command="spectra_ascii_coursework_workbench.py",
            notes=legacy_payload["notes"],
        )
    return 1 if payload_status == "fail" else 0


def main():
    args = parse_args()
    try:
        raise SystemExit(run_workflow(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        message = clean_known_stderr(str(exc.code)) or "Spectra coursework bundle was blocked."
        raise SystemExit(emit_blocked(args, message, error_type="SystemExit")) from None
    except Exception as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        raise SystemExit(emit_blocked(args, message, error_type=exc.__class__.__name__)) from None


if __name__ == "__main__":
    main()
