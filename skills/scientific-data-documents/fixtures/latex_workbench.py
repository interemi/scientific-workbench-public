#!/usr/bin/env python3
"""Inspect, scaffold, review, and compile Overleaf-friendly LaTeX projects."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from _internal.path_safety import output_overlaps_input, paths_alias
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.runtime_common import compile_latex_project, configure_runtime

DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[(?P<options>[^\]]*)\])?\{(?P<class>[^}]+)\}")
PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}")
INCLUDE_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
BIB_RE = re.compile(r"\\(?:bibliography|addbibresource)\{([^}]+)\}")
GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
CITE_RE = re.compile(r"\\cite\w*(?:\[[^\]]*\])?\{([^}]+)\}")
TABULAR_RE = re.compile(r"\\begin\{tabular\}\{([^}]*)\}")
LONGTABLE_RE = re.compile(r"\\begin\{longtable\}\{([^}]*)\}")
ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:/Users/|/home/|[A-Za-z]:\\\\)")
BIB_ENTRY_RE = re.compile(r"@\w+\{([^,\s]+)\s*,")
SECTION_RE = re.compile(r"\\section\{([^}]+)\}")
STRONG_CLAIM_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bprove(?:s|d)?\b",
        r"\bproves that\b",
        r"\bdemonstrat(?:e|es|ed) that\b",
        r"\bmore common\b",
        r"\bdominates?\b",
        r"\bdisproportionately\b",
        r"\bmonotonic(?:ally)?\b",
        r"\bdeclines?\b",
    ]
]


class ControlledBlock(RuntimeError):
    """Expected safety refusal that must be exposed without a traceback."""


def same_output_path(left: str | Path, right: str | Path) -> bool:
    return paths_alias(left, right)


def path_inside_or_equal(path: str | Path, directory: str | Path) -> bool:
    return output_overlaps_input(path, directory)


def project_source_paths(main_tex: Path, requested_path: str | Path | None = None) -> list[Path]:
    candidates = [main_tex]
    if requested_path is not None:
        candidates.append(Path(requested_path))
    project_root = main_tex.parent
    if project_root.is_dir():
        candidates.extend(path for path in project_root.rglob("*") if path.is_file())
    unique = {}
    for path in candidates:
        unique[str(path.expanduser().resolve(strict=False))] = path
    return list(unique.values())


def requested_source_paths(requested_path: str | Path) -> list[Path]:
    source = Path(requested_path)
    candidates = [source]
    if source.is_dir():
        candidates.extend(path for path in source.rglob("*") if path.is_file())
    return candidates


def ensure_outputs_do_not_overlap_sources(
    outputs: list[tuple[str, str | Path | None]],
    sources: list[Path],
) -> None:
    for label, pathlike in outputs:
        if not pathlike:
            continue
        for source in sources:
            if same_output_path(pathlike, source):
                raise ControlledBlock(
                    f"{label} must not overwrite a LaTeX project source: {public_path(source)}"
                )


def ensure_distinct_outputs(outputs: list[tuple[str, str | Path | None]]) -> None:
    present = [(label, pathlike) for label, pathlike in outputs if pathlike]
    for index, (left_label, left_path) in enumerate(present):
        for right_label, right_path in present[index + 1 :]:
            if same_output_path(left_path, right_path):
                raise ControlledBlock(f"{left_label} and {right_label} must use distinct output paths.")


HEDGE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bsuggest(?:ive|s)?\b",
        r"\bconsistent with\b",
        r"\bmay\b",
        r"\bmight\b",
        r"\bcautio(?:n|us|nary)\b",
        r"\bnot conclusive\b",
        r"\btoo small\b",
    ]
]
GRAPHIC_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg"]


SCAFFOLDS = {
    "article": {
        "main.tex": r"""\documentclass[a4paper,11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{natbib}
\bibliographystyle{unsrtnat}

\title{<<TITLE>>}
\author{<<AUTHOR>>}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
Write a concise abstract here.
\end{abstract}

\section{Introduction}
State the motivation, context, and question.

\section{Methods}
Describe the data, processing steps, and assumptions.

\section{Results}
Summarize the main findings and include figures or tables when needed.

\section{Conclusions}
Explain the main takeaways and next steps.

\bibliography{references}
\end{document}
""",
        "references.bib": "@article{example2024,\n  author = {Author, A.},\n  title = {Example reference},\n  journal = {Journal Name},\n  year = {2024}\n}\n",
    },
    "proposal": {
        "main.tex": r"""\documentclass[a4paper,11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\usepackage{hyperref}
\geometry{margin=1in}

\title{<<TITLE>>}
\author{<<AUTHOR>>}
\date{\today}

\begin{document}
\maketitle

\section{Objective}
Summarize the proposed work.

\section{Background}
Explain why the project matters.

\section{Methodology}
Describe the plan, data, and validation strategy.

\section{Timeline}
Outline milestones and deliverables.

\section{Expected Outcomes}
State the expected impact and outputs.

\end{document}
""",
        "references.bib": "",
    },
    "academic-report": {
        "main.tex": r"""\documentclass[a4paper,11pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{amsmath}
\usepackage{siunitx}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{natbib}
\bibliographystyle{unsrtnat}
\geometry{margin=1in}

\title{<<TITLE>>}
\author{<<AUTHOR>>}
\date{\today}

\begin{document}
\twocolumn[
\maketitle
\begin{center}
\begin{minipage}{0.93\textwidth}
\small\textbf{Abstract.} Summarize the question, data, core method, most defensible findings, and the main caveat.
\end{minipage}
\end{center}
\vspace{1em}
]

\section{Introduction}
State the context, motivation, and research question.

\section{Data and Methodology}
Describe the inputs, selection choices, assumptions, and reproducible workflow. Distinguish exploratory decisions from validated ones.

\section{Results}
Present the main quantitative outputs. Prefer generated figures and tables over manual copy-paste.

\section{Discussion}
Explain what is supported strongly, what is only suggestive, and which limitations matter most.

\section{Conclusion}
Summarize the main result and the next logical step.

\appendix
\onecolumn
\section{Appendix Material}
Use the appendix for wide tables, supplementary diagnostics, or generated listings.

\bibliography{references}
\end{document}
""",
        "references.bib": "@article{example2024,\n  author = {Author, A.},\n  title = {Example reference},\n  journal = {Journal Name},\n  year = {2024}\n}\n",
    },
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

SPANISH_SCAFFOLD_REPLACEMENTS = {
    r"\begin{abstract}": r"\begin{abstract}",
    "Write a concise abstract here.": "Escribe aqui un resumen conciso.",
    r"\section{Introduction}": r"\section{Introduccion}",
    "State the motivation, context, and question.": "Presenta la motivacion, el contexto y la pregunta.",
    r"\section{Methods}": r"\section{Metodologia}",
    "Describe the data, processing steps, and assumptions.": "Describe los datos, el procesamiento y los supuestos.",
    r"\section{Results}": r"\section{Resultados}",
    "Summarize the main findings and include figures or tables when needed.": "Resume los resultados principales e incluye figuras o tablas cuando haga falta.",
    r"\section{Conclusions}": r"\section{Conclusiones}",
    "Explain the main takeaways and next steps.": "Explica las conclusiones principales y los pasos siguientes.",
    r"\section{Objective}": r"\section{Objetivo}",
    "Summarize the proposed work.": "Resume el trabajo propuesto.",
    r"\section{Background}": r"\section{Contexto}",
    "Explain why the project matters.": "Explica por que el proyecto es relevante.",
    r"\section{Methodology}": r"\section{Metodologia}",
    "Describe the plan, data, and validation strategy.": "Describe el plan, los datos y la estrategia de validacion.",
    r"\section{Timeline}": r"\section{Cronograma}",
    "Outline milestones and deliverables.": "Resume los hitos y entregables.",
    r"\section{Expected Outcomes}": r"\section{Resultados esperados}",
    "State the expected impact and outputs.": "Indica el impacto y los productos esperados.",
    r"\small\textbf{Abstract.}": r"\small\textbf{Resumen.}",
    "Summarize the question, data, core method, most defensible findings, and the main caveat.": "Resume la pregunta, los datos, el metodo central, los resultados mas defendibles y la cautela principal.",
    r"\section{Data and Methodology}": r"\section{Datos y metodologia}",
    "Describe the inputs, selection choices, assumptions, and reproducible workflow. Distinguish exploratory decisions from validated ones.": "Describe los datos, las decisiones de seleccion, los supuestos y el flujo reproducible. Distingue las decisiones exploratorias de las validadas.",
    "Present the main quantitative outputs. Prefer generated figures and tables over manual copy-paste.": "Presenta los resultados cuantitativos principales. Prioriza figuras y tablas generadas frente a copias manuales.",
    r"\section{Discussion}": r"\section{Discusion}",
    "Explain what is supported strongly, what is only suggestive, and which limitations matter most.": "Explica que esta bien respaldado, que es solo indicativo y que limitaciones importan mas.",
    r"\section{Conclusion}": r"\section{Conclusion}",
    "Summarize the main result and the next logical step.": "Resume el resultado principal y el siguiente paso logico.",
    r"\section{Appendix Material}": r"\section{Material de apendice}",
    "Use the appendix for wide tables, supplementary diagnostics, or generated listings.": "Usa el apendice para tablas anchas, diagnosticos suplementarios o listados generados.",
}

BILINGUAL_SCAFFOLD_REPLACEMENTS = {
    r"\section{Introduction}": r"\section{Introduction / Introduccion}",
    r"\section{Methods}": r"\section{Methods / Metodologia}",
    r"\section{Results}": r"\section{Results / Resultados}",
    r"\section{Conclusions}": r"\section{Conclusions / Conclusiones}",
    r"\section{Objective}": r"\section{Objective / Objetivo}",
    r"\section{Background}": r"\section{Background / Contexto}",
    r"\section{Methodology}": r"\section{Methodology / Metodologia}",
    r"\section{Timeline}": r"\section{Timeline / Cronograma}",
    r"\section{Expected Outcomes}": r"\section{Expected Outcomes / Resultados esperados}",
    r"\section{Data and Methodology}": r"\section{Data and Methodology / Datos y metodologia}",
    r"\section{Discussion}": r"\section{Discussion / Discusion}",
    r"\section{Conclusion}": r"\section{Conclusion / Conclusion}",
    r"\section{Appendix Material}": r"\section{Appendix Material / Material de apendice}",
}


def find_main_tex(path):
    path = Path(path)
    if path.is_file():
        return path
    candidates = []
    for tex in path.rglob("*.tex"):
        try:
            content = tex.read_text(errors="replace")
        except Exception:
            continue
        if "\\documentclass" in content and "\\begin{document}" in content:
            candidates.append(tex)
    if not candidates:
        raise SystemExit("Could not find a main .tex file.")
    candidates.sort(key=lambda p: ("main.tex" not in p.name.lower(), len(str(p))))
    return candidates[0]


def escape_latex_text(value: str) -> str:
    return "".join(LATEX_TEXT_ESCAPES.get(char, char) for char in str(value))


def localize_scaffold(text: str, language: str) -> str:
    replacements = {}
    if language == "spanish":
        replacements = SPANISH_SCAFFOLD_REPLACEMENTS
    elif language == "bilingual":
        replacements = BILINGUAL_SCAFFOLD_REPLACEMENTS
    for source, target in replacements.items():
        text = text.replace(source, target)
    if language == "bilingual":
        text = text.replace(
            "Write a concise abstract here.",
            "Write a concise abstract here. / Escribe aqui un resumen conciso.",
        )
    return text


def render_scaffold(kind: str, title: str, author: str, language: str = "english") -> dict[str, str]:
    rendered = {}
    for name, text in SCAFFOLDS[kind].items():
        text = localize_scaffold(text, language)
        rendered[name] = text.replace("<<TITLE>>", escape_latex_text(title)).replace("<<AUTHOR>>", escape_latex_text(author))
    return rendered


def resolve_include(token: str, root: Path) -> Path | None:
    candidate = (root / token).expanduser()
    if candidate.exists():
        return candidate
    if candidate.suffix:
        return candidate if candidate.exists() else None
    tex_candidate = candidate.with_suffix(".tex")
    if tex_candidate.exists():
        return tex_candidate
    return None


def resolve_project_file(token: str, root: Path, *, extensions: list[str] | None = None) -> Path | None:
    token = token.strip()
    if not token:
        return None
    raw_path = Path(token).expanduser()
    candidate = raw_path if raw_path.is_absolute() else (root / raw_path)
    if candidate.exists():
        return candidate
    if candidate.suffix:
        return None
    for extension in extensions or []:
        extended = candidate.with_suffix(extension)
        if extended.exists():
            return extended
    return None


def count_columns(spec: str) -> int:
    cleaned = re.sub(r"\{[^{}]*\}", "", spec)
    return len(re.findall(r"[lcrpmbXSD]", cleaned))


def inspect_project(main_tex):
    content = main_tex.read_text(errors="replace")
    docclass_match = DOCUMENTCLASS_RE.search(content)
    packages = []
    for match in PACKAGE_RE.findall(content):
        packages.extend([item.strip() for item in match.split(",") if item.strip()])
    citations = []
    for match in CITE_RE.findall(content):
        citations.extend([item.strip() for item in match.split(",") if item.strip()])
    options = (docclass_match.group("options") if docclass_match else "") or ""
    option_tokens = [item.strip() for item in options.split(",") if item.strip()]
    return {
        "main_tex": str(main_tex.resolve()),
        "documentclass": docclass_match.group("class") if docclass_match else None,
        "documentclass_options": option_tokens,
        "twocolumn": "twocolumn" in option_tokens,
        "packages": sorted(set(packages)),
        "includes": INCLUDE_RE.findall(content),
        "bibliography": BIB_RE.findall(content),
        "figures": GRAPHIC_RE.findall(content),
        "citations": sorted(set(citations)),
        "has_document_environment": "\\begin{document}" in content and "\\end{document}" in content,
        "has_begin_document": "\\begin{document}" in content,
        "has_end_document": "\\end{document}" in content,
        "has_abstract": "\\begin{abstract}" in content or "\\textbf{Abstract." in content or "\\textbf{Abstract}" in content,
        "section_count": len(re.findall(r"\\section\{", content)),
        "forced_float_count": len(re.findall(r"\\begin\{figure\}\[H\]|\\begin\{table\}\[H\]", content)),
        "absolute_path_hits": len(ABSOLUTE_PATH_RE.findall(content)),
    }


def resolve_bibliography_files(main_tex: Path, bibliography_tokens: list[str]) -> list[Path]:
    project_root = main_tex.parent
    resolved = []
    seen = set()
    for token in bibliography_tokens:
        for part in [item.strip() for item in token.split(",") if item.strip()]:
            raw = part
            if raw.startswith("{") and raw.endswith("}"):
                raw = raw[1:-1]
            candidate = (project_root / raw).expanduser()
            if candidate.suffix == "":
                candidate = candidate.with_suffix(".bib")
            if candidate.exists():
                key = str(candidate.resolve())
                if key not in seen:
                    seen.add(key)
                    resolved.append(candidate.resolve())
    return resolved


def unresolved_bibliography_tokens(main_tex: Path, bibliography_tokens: list[str]) -> list[str]:
    project_root = main_tex.parent
    missing = []
    for token in bibliography_tokens:
        for part in [item.strip() for item in token.split(",") if item.strip()]:
            raw = part[1:-1] if part.startswith("{") and part.endswith("}") else part
            candidate = (project_root / raw).expanduser()
            if candidate.suffix == "":
                candidate = candidate.with_suffix(".bib")
            if not candidate.exists():
                missing.append(raw)
    return sorted(set(missing))


def extract_bib_keys(paths: list[Path]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        text = path.read_text(errors="replace")
        keys.update(match.strip() for match in BIB_ENTRY_RE.findall(text))
    return keys


def extract_sections(content: str) -> list[dict]:
    matches = list(SECTION_RE.finditer(content))
    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end]
        word_count = len(re.findall(r"\b\w+\b", re.sub(r"\\[A-Za-z]+\{[^}]*\}", " ", body)))
        sections.append({"title": match.group(1), "word_count": word_count})
    return sections


def inspect_table_inputs(main_tex: Path, include_tokens: list[str]) -> list[dict]:
    items = []
    project_root = main_tex.parent
    seen: set[Path] = set()
    for token in include_tokens:
        resolved = resolve_include(token, project_root)
        if not resolved or resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        text = resolved.read_text(errors="replace")
        tabular_specs = TABULAR_RE.findall(text)
        longtable_specs = LONGTABLE_RE.findall(text)
        items.append(
            {
                "path": str(resolved.resolve()),
                "tabular_column_counts": [count_columns(spec) for spec in tabular_specs],
                "longtable_column_counts": [count_columns(spec) for spec in longtable_specs],
                "has_resizebox": "\\resizebox" in text or "\\begin{adjustbox}" in text,
                "has_small_font_hint": any(token in text for token in ["\\small", "\\footnotesize", "\\scriptsize"]),
            }
        )
    return items


def collect_pattern_hits(text: str, patterns: list[re.Pattern[str]]) -> list[dict]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            if pattern.search(line):
                hits.append({"line": lineno, "snippet": line.strip(), "pattern": pattern.pattern})
                break
    return hits


def review_project(main_tex: Path) -> dict:
    summary = inspect_project(main_tex)
    content = main_tex.read_text(errors="replace")
    table_inputs = inspect_table_inputs(main_tex, summary["includes"])
    strong_claim_hits = collect_pattern_hits(content, STRONG_CLAIM_PATTERNS)
    hedge_hits = collect_pattern_hits(content, HEDGE_PATTERNS)
    bibliography_files = resolve_bibliography_files(main_tex, summary["bibliography"])
    missing_bibliography_tokens = unresolved_bibliography_tokens(main_tex, summary["bibliography"])
    bib_keys = extract_bib_keys(bibliography_files)
    cited_keys = set(summary["citations"])
    missing_citation_keys = sorted(cited_keys - bib_keys)
    sections = extract_sections(content)
    project_root = main_tex.parent
    missing_includes = [
        token for token in summary["includes"] if resolve_include(token, project_root) is None
    ]
    missing_figures = [
        token for token in summary["figures"] if resolve_project_file(token, project_root, extensions=GRAPHIC_EXTENSIONS) is None
    ]

    findings = []
    strengths = []

    if not summary["documentclass"]:
        findings.append(
            {
                "severity": "high",
                "title": "Missing documentclass",
                "detail": "The source does not contain a detectable `\\documentclass{...}` declaration, so build behavior and package assumptions are ambiguous.",
            }
        )

    if not summary["has_begin_document"] or not summary["has_end_document"]:
        findings.append(
            {
                "severity": "high",
                "title": "Missing document environment boundary",
                "detail": "The source does not contain both `\\begin{document}` and `\\end{document}`. This is likely an incomplete or corrupt main file.",
            }
        )

    if summary["has_abstract"]:
        strengths.append("The document includes an abstract or abstract-like summary.")
    if summary["citations"]:
        strengths.append(f"The project already cites {len(summary['citations'])} source keys.")
    if summary["twocolumn"]:
        strengths.append("The main manuscript uses a two-column academic layout.")
    if summary["absolute_path_hits"] == 0:
        strengths.append("No absolute local filesystem paths were detected in the LaTeX source.")
    if bibliography_files and not missing_citation_keys:
        strengths.append("Bibliography files were resolved and all cited keys found there.")
    if sections:
        strengths.append(f"The manuscript has {len(sections)} section-level blocks with detectable body text.")

    if not summary["has_abstract"]:
        findings.append(
            {
                "severity": "medium",
                "title": "Missing abstract",
                "detail": "The manuscript does not appear to contain an abstract or abstract-style opening summary.",
            }
        )

    if cited_keys and not bibliography_files:
        findings.append(
            {
                "severity": "high",
                "title": "Citations detected without a resolved bibliography file",
                "detail": "The source cites references, but no `.bib` file referenced from the main manuscript could be resolved.",
            }
        )
    elif missing_citation_keys:
        findings.append(
            {
                "severity": "high",
                "title": "Missing bibliography keys",
                "detail": "Some citation keys used in the manuscript do not appear in the resolved bibliography files.",
                "missing_keys": missing_citation_keys[:20],
            }
        )

    if missing_bibliography_tokens:
        findings.append(
            {
                "severity": "high" if cited_keys else "medium",
                "title": "Bibliography files do not resolve",
                "detail": "One or more bibliography files referenced by the main manuscript could not be found relative to the project root.",
                "missing_files": missing_bibliography_tokens[:20],
            }
        )

    if summary["bibliography"] and not cited_keys:
        findings.append(
            {
                "severity": "low",
                "title": "Bibliography present but no citations detected",
                "detail": "The manuscript references a bibliography, but no `\\cite` keys were detected in the LaTeX source.",
            }
        )

    if missing_includes:
        findings.append(
            {
                "severity": "high",
                "title": "Included TeX files do not resolve",
                "detail": "`\\input` or `\\include` references were found, but some targets could not be resolved relative to the project root.",
                "missing_files": missing_includes[:20],
            }
        )

    if missing_figures:
        findings.append(
            {
                "severity": "medium",
                "title": "Figure files do not resolve",
                "detail": "`\\includegraphics` references were found, but some image files could not be resolved relative to the project root.",
                "missing_files": missing_figures[:20],
            }
        )

    if summary["twocolumn"] and summary["forced_float_count"] >= 3:
        findings.append(
            {
                "severity": "medium",
                "title": "Many forced floats in a two-column layout",
                "detail": f"The source uses {summary['forced_float_count']} [H]-forced figures/tables. In two-column reports this often creates whitespace or awkward page breaks.",
            }
        )

    if summary["twocolumn"] and any(item["longtable_column_counts"] for item in table_inputs):
        appendix_switch_ok = bool(re.search(r"\\appendix[\s\S]{0,400}\\onecolumn|\\onecolumn[\s\S]{0,400}\\appendix", content))
        if not appendix_switch_ok:
            findings.append(
                {
                    "severity": "high",
                    "title": "Longtable used without a clear one-column appendix switch",
                    "detail": "A longtable-like input was detected in a two-column manuscript, but the main source does not clearly switch to one-column mode near the appendix.",
                }
            )

    wide_tables = [
        item
        for item in table_inputs
        if max(item["tabular_column_counts"] + item["longtable_column_counts"] + [0]) >= 6
        and not item["has_resizebox"]
        and not item["has_small_font_hint"]
    ]
    if summary["twocolumn"] and wide_tables:
        findings.append(
            {
                "severity": "medium",
                "title": "Potentially wide tables in two-column mode",
                "detail": "Some included table files look wide for a single column and do not advertise resizing or smaller-font wrappers.",
                "paths": [item["path"] for item in wide_tables],
            }
        )

    if strong_claim_hits:
        severity = "low" if hedge_hits else "medium"
        findings.append(
            {
                "severity": severity,
                "title": "Check the strength of some conclusion wording",
                "detail": "The source contains phrases that can read as stronger claims. This does not mean they are wrong; it is a cue to verify that the evidence level, teaching context, or supervisor guidance matches the wording.",
                "examples": strong_claim_hits[:5],
            }
        )

    if summary["absolute_path_hits"]:
        findings.append(
            {
                "severity": "medium",
                "title": "Absolute path leakage risk",
                "detail": "The LaTeX source appears to contain one or more absolute local filesystem paths, which can hurt portability and privacy when sharing the project.",
            }
        )

    for section in sections:
        title_lower = section["title"].strip().lower()
        if title_lower in {"discussion", "conclusion", "conclusions"} and section["word_count"] < 120:
            findings.append(
                {
                    "severity": "low",
                    "title": f"Very short {section['title']} section",
                    "detail": f"The section `{section['title']}` appears to contain only about {section['word_count']} words. For coursework reports this can be a sign that interpretation or closure is underdeveloped.",
                }
            )

    return sanitize_payload(
        {
            "main_tex": str(main_tex.resolve()),
            "inspection": summary,
            "bibliography_files": [str(path) for path in bibliography_files],
            "missing_bibliography_files": missing_bibliography_tokens,
            "missing_citation_keys": missing_citation_keys,
            "missing_includes": missing_includes,
            "missing_figures": missing_figures,
            "sections": sections,
            "table_inputs": table_inputs,
            "findings": findings,
            "strengths": strengths,
            "notes": [
                "This review is advisory. It should help catch layout or evidence-strength risks, not override domain-specific decisions already accepted by a supervisor or course context.",
                "Use it as a pre-submission check, especially for long LaTeX reports or paper-style coursework.",
            ],
        }
    )


def build_review_markdown(review: dict) -> str:
    lines = ["# Academic Report Review", ""]
    lines.extend(
        [
            f"- Main file: `{review['main_tex']}`",
            f"- Document class: `{review['inspection'].get('documentclass')}`",
            f"- Two-column layout: `{review['inspection'].get('twocolumn')}`",
            f"- Figures detected: `{len(review['inspection'].get('figures', []))}`",
            f"- Citations detected: `{len(review['inspection'].get('citations', []))}`",
            f"- Resolved bibliography files: `{len(review.get('bibliography_files', []))}`",
            "",
        ]
    )

    lines.append("## Strengths")
    if review["strengths"]:
        for item in review["strengths"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No obvious strengths were recorded automatically.")
    lines.append("")

    lines.append("## Findings")
    if review["findings"]:
        for item in review["findings"]:
            lines.append(f"- `{item['severity']}` {item['title']}: {item['detail']}")
            for path in item.get("paths", []):
                lines.append(f"  - path: `{path}`")
            for missing_file in item.get("missing_files", []):
                lines.append(f"  - missing file: `{missing_file}`")
            for key in item.get("missing_keys", []):
                lines.append(f"  - missing cite key: `{key}`")
            for example in item.get("examples", []):
                lines.append(f"  - line {example['line']}: `{example['snippet']}`")
    else:
        lines.append("- No high-signal risks were detected automatically.")
    lines.append("")

    lines.append("## Notes")
    for note in review["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def review_status(review: dict) -> str:
    blocking_titles = {"Missing documentclass", "Missing document environment boundary"}
    titles = {item.get("title") for item in review.get("findings", [])}
    if titles & blocking_titles:
        return "fail"
    return "warning" if review.get("findings") else "ok"


def build_scaffold_payload(summary: dict, *, status="ok", findings=None, artifacts=None, notes=None) -> dict:
    findings = list(findings or [])
    return build_tool_payload(
        tool="latex_workbench.scaffold",
        status=status,
        notes=notes or ["LaTeX scaffold created."],
        artifacts=artifacts or {},
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


def ensure_summary_json_path(summary_json) -> None:
    if not summary_json:
        return
    summary_path = Path(summary_json)
    if summary_path.exists() and summary_path.is_dir():
        raise IsADirectoryError(f"--summary-json points to a directory, not a file: {public_path(summary_path)}")
    if summary_path.parent.exists() and not summary_path.parent.is_dir():
        raise NotADirectoryError(f"--summary-json parent is not a directory: {public_path(summary_path.parent)}")


def emit_or_print_payload(payload: dict, summary_json=None) -> None:
    if summary_json:
        ensure_summary_json_path(summary_json)
        emit_payload(payload, summary_json)
    else:
        print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))


def ensure_output_file_path(pathlike, label: str) -> None:
    if not pathlike:
        return
    path = Path(pathlike)
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"{label} points to a directory, not a file: {public_path(path)}")
    if path.parent.exists() and not path.parent.is_dir():
        raise NotADirectoryError(f"{label} parent is not a directory: {public_path(path.parent)}")


def build_review_payload(review: dict, *, summary_path=None, report_path=None, manifest_path=None) -> dict:
    high_signal = [item for item in review.get("findings", []) if item.get("severity") in {"high", "medium"}]
    status = review_status(review)
    return build_tool_payload(
        tool="latex_workbench.review",
        status=status,
        notes=review["notes"],
        artifacts={
            "summary_json": str(Path(summary_path).resolve()) if summary_path else None,
            "report_md": str(Path(report_path).resolve()) if report_path else None,
            "manifest_json": str(Path(manifest_path).resolve()) if manifest_path else None,
        },
        results=review,
        qa={
            "status": status,
            "findings": high_signal,
            "metrics": {
                "finding_count": len(review.get("findings", [])),
                "high_signal_count": len(high_signal),
                "strength_count": len(review.get("strengths", [])),
            },
        },
        legacy=review,
    )


def emit_review_failure(args, error, *, exit_code=2) -> None:
    attempted_path = getattr(args, "path", None)
    failure = {
        "main_tex": str(Path(attempted_path).resolve(strict=False)) if attempted_path else None,
        "inspection": {},
        "bibliography_files": [],
        "missing_citation_keys": [],
        "sections": [],
        "table_inputs": [],
        "findings": [
            {
                "severity": "high",
                "title": "LaTeX review failed",
                "detail": f"{type(error).__name__}: {error}",
            }
        ],
        "strengths": [],
        "notes": [
            "The review could not produce a trustworthy advisory result.",
            "Fix the input or output paths and rerun before using this as a pre-submission check.",
        ],
    }
    payload = build_tool_payload(
        tool="latex_workbench.review",
        status="fail",
        notes=failure["notes"],
        artifacts={
            "summary_json": str(Path(args.summary_json).resolve()) if getattr(args, "summary_json", None) else None,
            "report_md": str(Path(args.report_md).resolve()) if getattr(args, "report_md", None) else None,
            "manifest_json": str(Path(args.manifest_json).resolve()) if getattr(args, "manifest_json", None) else None,
        },
        results=failure,
        qa={
            "status": "fail",
            "findings": failure["findings"],
            "metrics": {"finding_count": 1, "high_signal_count": 1, "strength_count": 0},
        },
        legacy=failure,
    )
    try:
        emit_or_print_payload(payload, getattr(args, "summary_json", None))
    except Exception as summary_error:
        failure["findings"].append(
            {
                "severity": "high",
                "title": "Could not write summary JSON",
                "detail": f"{type(summary_error).__name__}: {summary_error}",
            }
        )
        payload = build_tool_payload(
            tool="latex_workbench.review",
            status="fail",
            notes=failure["notes"],
            artifacts={
                "summary_json": str(Path(args.summary_json).resolve()) if getattr(args, "summary_json", None) else None,
                "report_md": str(Path(args.report_md).resolve()) if getattr(args, "report_md", None) else None,
                "manifest_json": str(Path(args.manifest_json).resolve()) if getattr(args, "manifest_json", None) else None,
            },
            results=failure,
            qa={
                "status": "fail",
                "findings": failure["findings"],
                "metrics": {"finding_count": len(failure["findings"]), "high_signal_count": len(failure["findings"]), "strength_count": 0},
            },
            legacy=failure,
        )
        print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    raise SystemExit(exit_code)


def validate_scaffold_paths(
    target: Path,
    rendered: dict[str, str],
    summary_json=None,
    manifest_json=None,
) -> list[str]:
    if target.exists() and not target.is_dir():
        raise NotADirectoryError(f"Output path exists and is not a directory: {public_path(target)}")
    ensure_summary_json_path(summary_json)
    ensure_output_file_path(manifest_json, "--manifest-json")
    auxiliary_outputs = [
        ("--summary-json", summary_json),
        ("--manifest-json", manifest_json),
    ]
    ensure_distinct_outputs(auxiliary_outputs)
    generated_targets = [target / name for name in rendered]
    for label, pathlike in auxiliary_outputs:
        if pathlike and any(same_output_path(pathlike, generated) for generated in generated_targets):
            raise ControlledBlock(f"{label} must not overwrite a generated LaTeX scaffold file.")
    if not target.exists():
        return []
    return sorted(name for name in rendered if (target / name).exists())


def cmd_inspect(args):
    main_tex = find_main_tex(args.path)
    summary = inspect_project(main_tex)
    print(f"Main file: {summary['main_tex']}")
    print(f"Document class: {summary['documentclass']}")
    print(f"Two-column: {summary['twocolumn']}")
    print(f"Packages: {', '.join(summary['packages']) or '[none]'}")
    print(f"Included files: {', '.join(summary['includes']) or '[none]'}")
    print(f"Bibliography refs: {', '.join(summary['bibliography']) or '[none]'}")
    print(f"Figures: {', '.join(summary['figures']) or '[none]'}")
    print(f"Citations: {', '.join(summary['citations']) or '[none]'}")
    if args.summary_json:
        payload = build_tool_payload(
            tool="latex_workbench.inspect",
            status="ok",
            notes=["LaTeX project inspection completed."],
            artifacts={"summary_json": str(Path(args.summary_json).resolve())},
            results=summary,
            qa={
                "status": "not_applicable",
                "findings": [],
                "metrics": {
                    "figure_count": len(summary.get("figures", [])),
                    "citation_count": len(summary.get("citations", [])),
                    "section_count": summary.get("section_count", 0),
                },
            },
            legacy=summary,
        )
        emit_payload(payload, args.summary_json)
        print(f"Saved summary: {public_path(args.summary_json)}")


def cmd_scaffold(args):
    target = Path(args.output)
    rendered = render_scaffold(args.kind, args.title, args.author, args.language)
    summary = {
        "output_dir": str(target.resolve(strict=False)),
        "kind": args.kind,
        "title": args.title,
        "author": args.author,
        "language": args.language,
        "created_files": [],
        "collisions": [],
        "overwrote_existing_files": False,
    }
    artifacts = {
        "project_root": str(target.resolve(strict=False)),
        "summary_json": str(Path(args.summary_json).resolve()) if args.summary_json else None,
        "manifest_json": str(Path(args.manifest_json).resolve()) if args.manifest_json else None,
    }
    try:
        collisions = validate_scaffold_paths(target, rendered, args.summary_json, args.manifest_json)
        summary["collisions"] = collisions
        if collisions and not args.overwrite:
            payload = build_scaffold_payload(
                summary,
                status="blocked",
                findings=[
                    {
                        "severity": "high",
                        "title": "Existing scaffold files would be overwritten",
                        "detail": "Refusing to overwrite existing LaTeX scaffold files without --overwrite.",
                        "files": collisions,
                    }
                ],
                artifacts=artifacts,
                notes=["LaTeX scaffold was blocked to avoid overwriting existing project files."],
            )
            emit_or_print_payload(payload, args.summary_json)
            raise SystemExit(2)
        target.mkdir(parents=True, exist_ok=True)
        for name, text in rendered.items():
            path = target / name
            path.write_text(text, encoding="utf-8")
        summary["created_files"] = sorted(rendered)
        summary["overwrote_existing_files"] = bool(collisions and args.overwrite)
    except SystemExit:
        raise
    except ControlledBlock:
        raise
    except Exception as error:
        summary["error"] = str(error)
        payload = build_scaffold_payload(
            summary,
            status="fail",
            findings=[
                {
                    "severity": "high",
                    "title": "LaTeX scaffold failed",
                    "detail": f"{type(error).__name__}: {error}",
                }
            ],
            artifacts=artifacts,
            notes=["LaTeX scaffold failed before producing a trustworthy project."],
        )
        try:
            emit_or_print_payload(payload, args.summary_json)
        except Exception as summary_error:
            summary["summary_json_error"] = str(summary_error)
            payload = build_scaffold_payload(
                summary,
                status="fail",
                findings=[
                    {
                        "severity": "high",
                        "title": "LaTeX scaffold failed",
                        "detail": f"{type(error).__name__}: {error}",
                    },
                    {
                        "severity": "high",
                        "title": "Could not write summary JSON",
                        "detail": f"{type(summary_error).__name__}: {summary_error}",
                    },
                ],
                artifacts=artifacts,
                notes=["LaTeX scaffold failed before producing a trustworthy project."],
            )
            print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
        raise SystemExit(2)
    print(f"Scaffold created at {public_path(target)}")
    if args.summary_json:
        payload = build_scaffold_payload(summary, artifacts=artifacts)
        emit_payload(payload, args.summary_json)
        print(f"Saved summary: {public_path(args.summary_json)}")
    if args.manifest_json:
        outputs = [target / name for name in sorted(rendered)]
        if args.summary_json:
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[],
            outputs=outputs,
            parameters={
                "kind": args.kind,
                "title": args.title,
                "author": args.author,
                "language": args.language,
                "overwrite": bool(args.overwrite),
            },
            command="latex_workbench.py scaffold",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


def preflight_review(args) -> Path:
    outputs = [
        ("--report-md", args.report_md),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
    ]
    for label, pathlike in outputs:
        ensure_output_file_path(pathlike, label)
    ensure_distinct_outputs(outputs)
    ensure_outputs_do_not_overlap_sources(outputs, requested_source_paths(args.path))
    main_tex = find_main_tex(args.path)
    ensure_outputs_do_not_overlap_sources(outputs, project_source_paths(main_tex, args.path))
    return main_tex


def cmd_review(args):
    try:
        main_tex = preflight_review(args)
        review = review_project(main_tex)
    except ControlledBlock:
        raise
    except SystemExit as error:
        emit_review_failure(args, error.code or "Could not find a main .tex file.")
    except Exception as error:
        emit_review_failure(args, error)

    markdown = build_review_markdown(review)
    print(markdown)
    outputs = []
    if args.report_md:
        report_path = Path(args.report_md)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
        outputs.append(report_path)
        print(f"Saved review report: {public_path(report_path)}")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        payload = build_review_payload(
            review,
            summary_path=summary_path,
            report_path=Path(args.report_md) if args.report_md else None,
            manifest_path=Path(args.manifest_json) if args.manifest_json else None,
        )
        emit_payload(payload, summary_path)
        outputs.append(summary_path)
        print(f"Saved review summary: {public_path(summary_path)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[main_tex],
            outputs=outputs,
            parameters={"mode": "review"},
            command="latex_workbench.py review",
            notes=review["notes"],
            extra={"finding_count": len(review["findings"])},
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    if review_status(review) == "fail":
        raise SystemExit(2)


def preflight_compile(args) -> tuple[Path, Path, Path | None]:
    main_tex = find_main_tex(args.path)
    project_root = main_tex.parent
    sources = project_source_paths(main_tex, args.path)
    if args.output_dir and path_inside_or_equal(args.output_dir, project_root):
        raise ControlledBlock("--output-dir must be outside the LaTeX source project.")
    manifest_path = Path(args.manifest_json) if args.manifest_json else None
    if manifest_path:
        ensure_output_file_path(manifest_path, "--manifest-json")
        ensure_outputs_do_not_overlap_sources([("--manifest-json", manifest_path)], sources)
    output_dir = Path(args.output_dir) if args.output_dir else None
    return main_tex, project_root, output_dir


def cmd_compile(args):
    main_tex, project_root, requested_output_dir = preflight_compile(args)
    configure_runtime("latex_workbench")
    output_dir = requested_output_dir or Path(tempfile.mkdtemp(prefix="latex-workbench-output-"))
    expected_pdf = output_dir / f"{main_tex.stem}.pdf"
    if args.manifest_json and same_output_path(args.manifest_json, expected_pdf):
        raise ControlledBlock("--manifest-json must not point to the compiled PDF output.")
    if args.manifest_json and Path(args.manifest_json).exists() and not args.overwrite:
        raise ControlledBlock(
            f"Refusing to overwrite existing manifest without --overwrite: {public_path(args.manifest_json)}"
        )
    if args.output_dir and expected_pdf.exists() and not args.overwrite:
        raise ControlledBlock(
            f"Refusing to overwrite existing compiled PDF without --overwrite: {public_path(expected_pdf)}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(tempfile.mkdtemp(prefix="latex-workbench-"))
    project_copy = workdir / project_root.name
    shutil.copytree(project_root, project_copy)
    copied_main = project_copy / main_tex.name

    compile_result = compile_latex_project(copied_main, passes=args.passes, latexmk_path=args.latexmk_path)
    produced_pdf = copied_main.with_suffix(".pdf")
    outputs = []
    if produced_pdf.exists():
        final_pdf = output_dir / produced_pdf.name
        shutil.copy2(produced_pdf, final_pdf)
        outputs.append(final_pdf)
    else:
        final_pdf = output_dir / f"{copied_main.stem}.pdf"
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[main_tex],
            outputs=outputs,
            parameters={"passes": args.passes, "latexmk_path": args.latexmk_path, "overwrite": bool(args.overwrite)},
            command="latex_workbench.py compile",
            notes=["Compilation happens in a copied working directory to preserve the original project."],
            extra={"compile_result": compile_result, "copied_project_root": public_path(project_copy)},
        )
    if compile_result["passes"]:
        last = compile_result["passes"][-1]
        print((last.get("stdout") or "")[-4000:])
        if last.get("returncode") != 0:
            print((last.get("stderr") or "")[-4000:])
    if not compile_result["success"]:
        raise SystemExit("LaTeX compilation failed; inspect the manifest or compiler output for details.")
    print(f"Compiled PDF: {public_path(final_pdf)}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_inspect = subparsers.add_parser("inspect", help="Inspect a LaTeX file or project directory.")
    p_inspect.add_argument("path")
    p_inspect.add_argument("--summary-json")
    p_inspect.set_defaults(func=cmd_inspect)

    p_scaffold = subparsers.add_parser("scaffold", help="Create a minimal Overleaf-friendly LaTeX project.")
    p_scaffold.add_argument("output")
    p_scaffold.add_argument("--title", default="Scientific Report")
    p_scaffold.add_argument("--author", default="Author Name")
    p_scaffold.add_argument("--language", choices=["english", "spanish", "bilingual"], default="english")
    p_scaffold.add_argument("--kind", default="article", choices=sorted(SCAFFOLDS))
    p_scaffold.add_argument("--summary-json")
    p_scaffold.add_argument("--manifest-json")
    p_scaffold.add_argument("--overwrite", action="store_true", help="Allow replacing scaffold-owned files in the output directory.")
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_review = subparsers.add_parser("review", help="Run an advisory review over a LaTeX report or manuscript.")
    p_review.add_argument("path")
    p_review.add_argument("--report-md")
    p_review.add_argument("--summary-json")
    p_review.add_argument("--manifest-json")
    p_review.set_defaults(func=cmd_review)

    p_compile = subparsers.add_parser("compile", help="Compile a LaTeX project in a copied work directory.")
    p_compile.add_argument("path")
    p_compile.add_argument("--output-dir")
    p_compile.add_argument("--manifest-json")
    p_compile.add_argument("--latexmk-path", help="Optional latexmk executable; by default, detect latexmk and then pdflatex.")
    p_compile.add_argument("--passes", type=int, default=2)
    p_compile.add_argument("--overwrite", action="store_true", help="Allow replacing an existing compiled PDF in --output-dir.")
    p_compile.set_defaults(func=cmd_compile)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ControlledBlock as exc:
        message = str(exc)
        payload = build_tool_payload(
            f"latex_workbench.{args.command}",
            status="blocked",
            notes=[message, "The source LaTeX project and existing outputs were not modified."],
            artifacts={},
            results={"blocked_reason": message},
            qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": 1}},
            legacy={"blocked_reason": message},
        )
        print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
