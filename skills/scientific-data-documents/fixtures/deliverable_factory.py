#!/usr/bin/env python3
"""Scaffold common deliverables and package outputs for handoff."""

import argparse
import html
import json
import zipfile
from pathlib import Path

from _internal.path_safety import output_overlaps_input, paths_alias
from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest


KIND_SECTIONS = {
    "report": ["Executive Summary", "Background", "Methods", "Results", "Recommendations", "Appendix"],
    "academic-report": ["Abstract", "Introduction", "Data and Methodology", "Results", "Discussion", "Conclusion", "Appendix"],
    "proposal": ["Need", "Objectives", "Approach", "Timeline", "Risks", "Resources"],
    "minutes": ["Attendees", "Agenda", "Discussion", "Decisions", "Action Items", "Next Meeting"],
    "executive-summary": ["Context", "Key Findings", "Decision Points", "Risks", "Next Steps"],
    "presentation": ["Audience", "Narrative Spine", "Slide Plan", "Figures", "Speaker Notes", "Export Plan"],
    "status-report": ["Scope", "Current Status", "Completed Work", "Blockers", "Risks", "Next Actions"],
    "project-brief": ["Context", "Stakeholders", "Inputs", "Constraints", "Plan", "Deliverables"],
    "qa-summary": ["Context", "Checks Performed", "Findings", "Open Issues", "Recommendations", "Sign-off"],
}
SECTION_TRANSLATIONS = {
    "Executive Summary": "Resumen ejecutivo",
    "Background": "Contexto",
    "Methods": "Metodos",
    "Results": "Resultados",
    "Recommendations": "Recomendaciones",
    "Appendix": "Apendice",
    "Abstract": "Resumen",
    "Introduction": "Introduccion",
    "Data and Methodology": "Datos y metodologia",
    "Discussion": "Discusion",
    "Conclusion": "Conclusion",
    "Need": "Necesidad",
    "Objectives": "Objetivos",
    "Approach": "Enfoque",
    "Timeline": "Cronograma",
    "Risks": "Riesgos",
    "Resources": "Recursos",
    "Attendees": "Asistentes",
    "Agenda": "Agenda",
    "Decisions": "Decisiones",
    "Action Items": "Acciones pendientes",
    "Next Meeting": "Proxima reunion",
    "Context": "Contexto",
    "Key Findings": "Hallazgos clave",
    "Decision Points": "Puntos de decision",
    "Next Steps": "Siguientes pasos",
    "Audience": "Audiencia",
    "Narrative Spine": "Eje narrativo",
    "Slide Plan": "Plan de diapositivas",
    "Figures": "Figuras",
    "Speaker Notes": "Notas de exposicion",
    "Export Plan": "Plan de exportacion",
    "Scope": "Alcance",
    "Current Status": "Estado actual",
    "Completed Work": "Trabajo completado",
    "Blockers": "Bloqueos",
    "Next Actions": "Siguientes acciones",
    "Stakeholders": "Interesados",
    "Inputs": "Entradas",
    "Constraints": "Restricciones",
    "Plan": "Plan",
    "Deliverables": "Entregables",
    "Checks Performed": "Checks realizados",
    "Findings": "Hallazgos",
    "Open Issues": "Cuestiones abiertas",
    "Sign-off": "Cierre",
}


class ControlledBlock(RuntimeError):
    """Expected output-collision refusal exposed as BLOCKED_CONTROLADO."""
FILLER_BY_LANGUAGE = {
    "english": "Fill in this section.",
    "spanish": "Completa esta seccion.",
    "bilingual": "Fill in this section. / Completa esta seccion.",
}
LATEX_TEXT_ESCAPES = {
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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold", help="Create a reusable deliverable template.")
    scaffold.add_argument("output_dir")
    scaffold.add_argument("--kind", choices=sorted(KIND_SECTIONS), default="report")
    scaffold.add_argument("--format", choices=["markdown", "latex", "html"], default="markdown")
    scaffold.add_argument("--title", required=True)
    scaffold.add_argument("--language", choices=["english", "spanish", "bilingual"], default="english")
    scaffold.add_argument("--manifest-json")
    scaffold.add_argument("--summary-json")
    scaffold.add_argument("--overwrite", action="store_true", help="Allow replacing an existing scaffold target file.")

    package = subparsers.add_parser("package", help="Bundle outputs and a short readme into a ZIP archive.")
    package.add_argument("output_zip")
    package.add_argument("inputs", nargs="+")
    package.add_argument("--title", default="Deliverable Package")
    package.add_argument("--manifest-json")
    package.add_argument("--overwrite", action="store_true", help="Allow replacing existing package, README, and index outputs.")

    return parser.parse_args()


def escape_latex_text(value: str) -> str:
    return "".join(LATEX_TEXT_ESCAPES.get(char, char) for char in str(value))


def localized_section(section: str, language: str) -> str:
    translated = SECTION_TRANSLATIONS.get(section, section)
    if language == "spanish":
        return translated
    if language == "bilingual":
        return f"{section} / {translated}" if translated != section else section
    return section


def filler(language: str) -> str:
    return FILLER_BY_LANGUAGE.get(language, FILLER_BY_LANGUAGE["english"])


def ensure_output_file_path(pathlike, label: str) -> None:
    if not pathlike:
        return
    path = Path(pathlike)
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"{label} points to a directory, not a file: {public_path(path)}")
    if path.parent.exists() and not path.parent.is_dir():
        raise NotADirectoryError(f"{label} parent is not a directory: {public_path(path.parent)}")


def same_output_path(left: Path, right: Path) -> bool:
    return paths_alias(left, right)


def output_inside_input_directory(output: Path, inputs: list[Path]) -> Path | None:
    for input_path in inputs:
        if input_path.expanduser().is_dir() and output_overlaps_input(output, input_path):
            return input_path.expanduser().resolve(strict=False)
    return None


def ensure_auxiliary_paths_do_not_overwrite_target(target: Path, *pathlikes) -> None:
    for pathlike in pathlikes:
        if not pathlike:
            continue
        candidate = Path(pathlike)
        if same_output_path(candidate, target):
            raise ValueError(f"Auxiliary output would overwrite the scaffold target: {public_path(candidate)}")


def scaffold_target(output_dir: Path, file_format: str) -> Path:
    if file_format == "markdown":
        return output_dir / "deliverable.md"
    if file_format == "latex":
        return output_dir / "main.tex"
    return output_dir / "deliverable.html"


def build_scaffold_payload(summary: dict, status: str = "ok", findings: list[dict] | None = None, notes: list[str] | None = None) -> dict:
    findings = list(findings or [])
    return standard_tool_payload(
        "deliverable_factory.scaffold",
        status=status,
        notes=notes or ["Deliverable scaffold check completed."],
        artifacts={
            "output_dir": summary.get("output_dir"),
            "target": summary.get("target"),
            "manifest_json": summary.get("manifest_json"),
            "summary_json": summary.get("summary_json"),
        },
        results=summary,
        qa={
            "status": status if status in {"ok", "warning", "blocked", "fail"} else "warning",
            "findings": findings,
            "metrics": {
                "created_file_count": len(summary.get("created_files", [])),
                "collision_count": len(summary.get("collisions", [])),
                "kind": summary.get("kind"),
            },
        },
        legacy=summary,
    )


def emit_json_payload(payload: dict, summary_json=None) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if summary_json:
        path = Path(summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def scaffold_markdown(kind, title, language):
    lines = [f"# {title}", "", f"- Deliverable kind: `{kind}`", f"- Language: `{language}`", ""]
    for section in KIND_SECTIONS[kind]:
        lines.extend([f"## {localized_section(section, language)}", "", f"_{filler(language)}_", ""])
    return "\n".join(lines).strip() + "\n"


def scaffold_latex(kind, title, language):
    safe_title = escape_latex_text(title)
    fill = filler(language)
    if kind == "academic-report":
        section_names = {section: localized_section(section, language) for section in KIND_SECTIONS[kind]}
        abstract_label = "Resumen" if language == "spanish" else ("Abstract / Resumen" if language == "bilingual" else "Abstract")
        return (
            "\\documentclass[a4paper,11pt,twocolumn]{article}\n"
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage[T1]{fontenc}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{lmodern}\n"
            "\\usepackage{microtype}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{booktabs}\n"
            "\\usepackage{longtable}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{siunitx}\n"
            "\\title{" + safe_title + "}\n"
            "\\author{Scientific Data Analysis Skill}\n"
            "\\date{}\n"
            "\\begin{document}\n"
            "\\twocolumn[\n"
            "\\maketitle\n"
            "\\begin{center}\n"
            "\\begin{minipage}{0.93\\textwidth}\n"
            f"\\small\\textbf{{{escape_latex_text(abstract_label)}.}} {fill}\n"
            "\\end{minipage}\n"
            "\\end{center}\n"
            "\\vspace{1em}\n"
            "]\n"
            f"\\section{{{escape_latex_text(section_names['Introduction'])}}}\n{fill}\n"
            f"\\section{{{escape_latex_text(section_names['Data and Methodology'])}}}\n{fill}\n"
            f"\\section{{{escape_latex_text(section_names['Results'])}}}\n{fill}\n"
            f"\\section{{{escape_latex_text(section_names['Discussion'])}}}\n{fill}\n"
            f"\\section{{{escape_latex_text(section_names['Conclusion'])}}}\n{fill}\n"
            "\\appendix\n\\onecolumn\n"
            f"\\section{{{escape_latex_text(section_names['Appendix'])}}}\n{fill}\n"
            "\\end{document}\n"
        )
    sections = "\n".join(
        f"\\section{{{escape_latex_text(localized_section(section, language))}}}\n{fill}\n" for section in KIND_SECTIONS[kind]
    )
    return (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\title{" + safe_title + "}\n"
        "\\author{Scientific Data Analysis Skill}\n"
        "\\date{}\n"
        "\\begin{document}\n\\maketitle\n"
        f"\\noindent Deliverable kind: \\texttt{{{kind}}}\\\\\n"
        f"Language: \\texttt{{{language}}}\n\n"
        + sections
        + "\\end{document}\n"
    )


def scaffold_html(kind, title, language):
    safe_title = html.escape(title, quote=True)
    safe_kind = html.escape(kind, quote=True)
    safe_language = html.escape(language, quote=True)
    safe_fill = html.escape(filler(language), quote=True)
    sections = "".join(
        f"<section><h2>{html.escape(localized_section(section, language), quote=True)}</h2><p>{safe_fill}</p></section>"
        for section in KIND_SECTIONS[kind]
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + safe_title
        + "</title><style>body{font-family:Georgia,serif;margin:2rem;max-width:900px;color:#18344c;}section{margin-bottom:1.5rem;}h1,h2{color:#114a72;}</style></head><body>"
        + f"<h1>{safe_title}</h1><p><strong>Kind:</strong> {safe_kind} | <strong>Language:</strong> {safe_language}</p>"
        + sections
        + "</body></html>\n"
    )


def do_scaffold(args):
    output_dir = Path(args.output_dir)
    target = scaffold_target(output_dir, args.format)
    summary = {
        "output_dir": str(output_dir.resolve(strict=False)),
        "target": str(target.resolve(strict=False)),
        "kind": args.kind,
        "format": args.format,
        "title": args.title,
        "language": args.language,
        "manifest_json": str(Path(args.manifest_json).resolve(strict=False)) if args.manifest_json else None,
        "summary_json": str(Path(args.summary_json).resolve(strict=False)) if args.summary_json else None,
        "created_files": [],
        "collisions": [],
        "overwrote_existing_files": False,
    }
    try:
        if output_dir.exists() and not output_dir.is_dir():
            raise NotADirectoryError(f"Output path exists and is not a directory: {public_path(output_dir)}")
        ensure_output_file_path(args.manifest_json, "--manifest-json")
        ensure_output_file_path(args.summary_json, "--summary-json")
        ensure_auxiliary_paths_do_not_overwrite_target(target, args.manifest_json, args.summary_json)
        target_preexisted = target.exists()
        if target.exists() and not args.overwrite:
            summary["collisions"] = [str(target.resolve())]
            payload = build_scaffold_payload(
                summary,
                status="blocked",
                findings=[
                    {
                        "severity": "high",
                        "title": "Existing deliverable scaffold would be overwritten",
                        "detail": "Refusing to overwrite an existing scaffold target without --overwrite.",
                        "files": summary["collisions"],
                    }
                ],
                notes=["Deliverable scaffold was blocked to avoid overwriting an existing file."],
            )
            emit_json_payload(payload, args.summary_json)
            raise SystemExit(2)
        output_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "markdown":
            target.write_text(scaffold_markdown(args.kind, args.title, args.language), encoding="utf-8")
        elif args.format == "latex":
            target.write_text(scaffold_latex(args.kind, args.title, args.language), encoding="utf-8")
        else:
            target.write_text(scaffold_html(args.kind, args.title, args.language), encoding="utf-8")
        summary["created_files"] = [str(target.resolve())]
        summary["overwrote_existing_files"] = bool(args.overwrite and target_preexisted)
    except SystemExit:
        raise
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
        payload = build_scaffold_payload(
            summary,
            status="fail",
            findings=[
                {
                    "severity": "high",
                    "title": "Deliverable scaffold failed",
                    "detail": summary["error"],
                }
            ],
            notes=["Deliverable scaffold failed before producing a trustworthy output."],
        )
        safe_summary_json = args.summary_json
        if safe_summary_json:
            try:
                ensure_output_file_path(safe_summary_json, "--summary-json")
                if same_output_path(Path(safe_summary_json), target):
                    safe_summary_json = None
            except Exception:
                safe_summary_json = None
        try:
            emit_json_payload(payload, safe_summary_json)
        except Exception:
            emit_json_payload(payload)
        raise SystemExit(2)
    outputs = [target]
    print(f"Saved scaffold: {public_path(target)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[],
            outputs=outputs,
            parameters={"kind": args.kind, "format": args.format, "title": args.title, "language": args.language},
            command="deliverable_factory.py scaffold",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    if args.summary_json:
        findings = []
        notes = ["Deliverable scaffold created."]
        status = "ok"
        if summary.get("overwrote_existing_files"):
            status = "warning"
            notes.append("An existing scaffold target was overwritten because --overwrite was explicitly set.")
            findings.append(
                {
                    "severity": "medium",
                    "title": "Existing scaffold target overwritten",
                    "detail": "The original input was not modified, but an existing output scaffold file was replaced in the chosen output directory.",
                    "files": summary.get("created_files", []),
                }
            )
        payload = build_scaffold_payload(summary, status=status, findings=findings, notes=notes)
        emit_json_payload(payload, args.summary_json)


def do_package(args):
    output_zip = Path(args.output_zip)
    inputs = [Path(item) for item in args.inputs]
    readme = output_zip.with_suffix(".README.md")
    handoff_index = output_zip.with_suffix(".index.json")
    targets = [output_zip, readme, handoff_index]
    manifest_path = Path(args.manifest_json) if args.manifest_json else None
    all_outputs = [*targets, *([manifest_path] if manifest_path else [])]
    for output_path in all_outputs:
        containing_input = output_inside_input_directory(output_path, inputs)
        if containing_input is not None:
            raise ControlledBlock(
                "Refusing to create a package output inside an input directory: "
                f"{public_path(output_path)} is within {public_path(containing_input)}"
            )
    if manifest_path and any(same_output_path(manifest_path, target) for target in targets):
        raise ControlledBlock("--manifest-json must be distinct from the package, README, and index outputs.")
    for input_path in inputs:
        if any(same_output_path(input_path, target) for target in all_outputs):
            raise ControlledBlock(
                f"Refusing to overwrite a package input with a package output: {public_path(input_path)}"
            )
    collisions = [target for target in all_outputs if target.exists()]
    if collisions and not args.overwrite:
        rendered = ", ".join(public_path(target) for target in collisions)
        raise ControlledBlock(f"Refusing to overwrite existing package outputs without --overwrite: {rendered}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {args.title}", "", "## Included files"]
    for item in inputs:
        lines.append(f"- `{public_path(item)}`")
    lines.extend(
        [
            "",
            "## Handoff notes",
            "- Raw inputs should remain untouched; package only derived outputs or copied deliverables.",
            "- When a deck or document also needs PDF output, keep a note of which backend produced it (for example LibreOffice CLI or Keynote fallback).",
        ]
    )
    readme.write_text("\n".join(lines) + "\n")
    handoff_index.write_text(
        json.dumps(
            {
                "title": args.title,
                "included": [public_path(item) for item in inputs],
                "notes": [
                    "This package is intended for handoff and review of derived outputs.",
                    "Keep originals outside the package unless a copied document bundle is explicitly needed.",
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n"
    )
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(readme, arcname=readme.name)
        archive.write(handoff_index, arcname=handoff_index.name)
        for item in inputs:
            item = Path(item)
            if item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        archive.write(child, arcname=str(child.relative_to(item.parent)))
            elif item.is_file():
                archive.write(item, arcname=item.name)
    outputs = [output_zip, readme, handoff_index]
    print(f"Saved package: {public_path(output_zip)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=inputs,
            outputs=outputs,
            parameters={"title": args.title, "overwrite": bool(args.overwrite)},
            command="deliverable_factory.py package",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


def main():
    args = parse_args()
    try:
        if args.command == "scaffold":
            do_scaffold(args)
        else:
            do_package(args)
    except ControlledBlock as exc:
        message = str(exc)
        payload = standard_tool_payload(
            f"deliverable_factory.{args.command}",
            status="blocked",
            notes=[message, "Existing inputs and outputs were not modified."],
            artifacts={"output_zip": getattr(args, "output_zip", None)},
            results={"blocked_reason": message},
            qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": 1}},
            legacy={"blocked_reason": message},
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
