#!/usr/bin/env python3
"""Advisory scientific write-up review for coursework reports and drafts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import configure_runtime


INCLUDE_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
SECTION_RE = re.compile(r"\\(?:section|subsection)\*?\{([^}]+)\}")
MARKDOWN_SECTION_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:/Users/|/home/|[A-Za-z]:\\\\)")
COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?")
INLINE_MATH_RE = re.compile(r"\$[^$]*\$")
COMMENT_RE = re.compile(r"(?<!\\)%.*")
SUPPORTED_INPUT_SUFFIXES = {".tex", ".md", ".txt", ""}

STRONG_CLAIM_PATTERNS = [
    r"\bdemuestra(?:n)?\b",
    r"\bprueba(?:n)?\b",
    r"\bconfirma(?:n)?\b",
    r"\bconcluye(?:n)? de forma definitiva\b",
    r"\bsin duda\b",
    r"\bes evidente que\b",
    r"\bprove(?:s|d)?\b",
    r"\bdemonstrat(?:e|es|ed) that\b",
    r"\bconfirms?\b",
]
HEDGE_PATTERNS = [
    r"\bsugiere(?:n)?\b",
    r"\bcompatible con\b",
    r"\bconsistente con\b",
    r"\bpodr(?:ia|ía|ian|ían)\b",
    r"\bparece(?:n)?\b",
    r"\blimitaci(?:on|ón|ones)\b",
    r"\bcautela(?:s)?\b",
    r"\bsuggest(?:s|ive)?\b",
    r"\bconsistent with\b",
    r"\bmay\b",
    r"\bmight\b",
]
UNIT_RE = re.compile(
    r"(\bkm\s*/\s*s\b|\bm\s*/\s*s\b|\\AA\b|Å|angstrom|mA\b|mag\b|pix(?:el)?s?\b|nm\b|"
    r"\bMJD\b|\bJD\b|\bK\b|\bcm\b|\bmm\b|\bHz\b|\berg\b|\bR_\{?\\odot\}?|\bM_\{?\\odot\}?)",
    re.IGNORECASE,
)
UNCERTAINTY_RE = re.compile(
    r"(±|\\pm|\+/-|\berror(?:es)?\b|\bincertidumbre(?:s)?\b|\bdesviaci(?:on|ón)\b|"
    r"\bsigma\b|\bstd\b|\buncertaint(?:y|ies)\b)",
    re.IGNORECASE,
)
LIMITATION_RE = re.compile(
    r"(limitaci(?:on|ón|ones)|cautela(?:s)?|sesgo(?:s)?|supuesto(?:s)?|asunci(?:on|ón|ones)|"
    r"no concluyente|no permite(?:n)?|manual|incertidumbre(?:s)?|limitation(?:s)?|bias(?:es)?|assumption(?:s)?)",
    re.IGNORECASE,
)
LITERATURE_RE = re.compile(
    r"(literatura|bibliograf(?:ia|ía)|referencia(?:s)?|\\cite|doi|arxiv|ads|simbad|"
    r"lopez|lópez|galvez|gálvez|jeffries|published|literature|reference)",
    re.IGNORECASE,
)
COMPARISON_RE = re.compile(
    r"(compar(?:a|aci(?:on|ón))|frente a|respecto a|coherente con|compatible con|"
    r"consistent with|difiere|delta|diferencia|versus|vs\.?|against|compared)",
    re.IGNORECASE,
)
RESULT_TERMS_RE = re.compile(r"(resultado(?:s)?|medida(?:s)?|tabla|figura|rv|v\s*sin\s*i|ew|equivalent width)", re.IGNORECASE)
DISCUSSION_TERMS_RE = re.compile(
    r"(interpretaci(?:on|ón)|discusi(?:on|ón)|implica(?:n)?|sugiere(?:n)?|mecanismo(?:s)?|"
    r"explica(?:n)?|conclusi(?:on|ón)|limita(?:n)?|cautela)",
    re.IGNORECASE,
)
INFRASTRUCTURE_TERMS_RE = re.compile(
    r"(workspace|preflight|output_dir|manifest|artifact(?:s)?|logs?|ruta(?:s)?|path(?:s)?|"
    r"carpeta(?:s)?|directorio(?:s)?|json|yaml|script(?:s)?|pipeline|codex|comando(?:s)?|"
    r"stdout|stderr|traceback|entorno|xquartz|mkiraf|xgterm)",
    re.IGNORECASE,
)
SCIENCE_TERMS_RE = re.compile(
    r"(velocidad radial|rv|v\s*sin\s*i|equivalent width|anchura(?:s)? equivalente(?:s)?|"
    r"li\s*i|ca\s*ii|halpha|h\alpha|irt|ccf|gaussiana|orbita(?:l)?|fase(?:s)?|"
    r"literatura|espectr(?:o|al|os)|linea(?:s)?|astrof(?:i|í)sic|f[íi]sic)",
    re.IGNORECASE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input .tex, .md, or .txt write-up.")
    parser.add_argument("--report-md", help="Optional Markdown report path.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional manifest path.")
    return parser.parse_args()


def _requested_outputs(args) -> list[tuple[str, str | None]]:
    return [
        ("--report-md", args.report_md),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
    ]


def _emit_collision_only(input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing write-up review outputs that overlap source files."
    payload = standard_tool_payload(
        "scientific_writeup_review",
        status="blocked",
        notes=[message, "No report, summary, or manifest was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "input_path": public_path(input_path),
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [{"severity": "high", "title": "Input/output collision", "detail": message}],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def _preflight_output_safety(args, input_path: Path, sources: list[Path] | None = None) -> int | None:
    protected = [("input", input_path)]
    protected.extend((f"source[{index}]", path) for index, path in enumerate(sources or [], start=1))
    collisions = find_output_input_collisions(protected, _requested_outputs(args))
    return _emit_collision_only(input_path, collisions) if collisions else None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_tex_include(root: Path, token: str, project_root: Path | None = None) -> Path:
    raw = token.strip()
    candidates = []
    for base in [root.parent, project_root]:
        if base is None:
            continue
        candidate = (base / raw).expanduser()
        candidates.append(candidate)
        if not candidate.suffix:
            candidates.append(candidate.with_suffix(".tex"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def collect_tex_sources(path: Path, seen: set[Path] | None = None, project_root: Path | None = None) -> tuple[str, list[Path], list[str]]:
    seen = seen or set()
    resolved = path.expanduser().resolve()
    project_root = project_root or resolved.parent
    if resolved in seen:
        return "", [], []
    seen.add(resolved)
    try:
        content = read_text(resolved)
    except Exception as exc:
        return "", [], [f"No se pudo leer {public_path(resolved)}: {exc.__class__.__name__}: {exc}"]

    sources = [resolved]
    warnings: list[str] = []

    def replace_include(match: re.Match) -> str:
        token = match.group(1)
        child = resolve_tex_include(resolved, token, project_root)
        if not child.exists():
            warnings.append(f"Include local no resuelto: {token}")
            return match.group(0)
        child_text, child_sources, child_warnings = collect_tex_sources(child, seen, project_root)
        sources.extend(child_sources)
        warnings.extend(child_warnings)
        return "\n" + child_text + "\n"

    content = INCLUDE_RE.sub(replace_include, content)
    return f"\n%% SOURCE: {public_path(resolved)}\n{content}", sources, warnings


def collect_sources(input_path: Path) -> tuple[str, list[Path], list[str]]:
    suffix = input_path.suffix.lower()
    if suffix not in SUPPORTED_INPUT_SUFFIXES:
        return "", [], [f"Formato no soportado para revision de escritura cientifica: {suffix or '[sin extension]'}"]
    if suffix == ".tex":
        return collect_tex_sources(input_path)
    try:
        return read_text(input_path), [input_path.expanduser().resolve()], []
    except Exception as exc:
        return "", [], [f"No se pudo leer {public_path(input_path)}: {exc.__class__.__name__}: {exc}"]


def latex_to_text(content: str) -> str:
    text = COMMENT_RE.sub("", content)
    text = INLINE_MATH_RE.sub(" ", text)
    text = SECTION_RE.sub(lambda m: f"\nSECTION {m.group(1)}\n", text)
    text = COMMAND_RE.sub(lambda m: f" {m.group(1) or ''} ", text)
    text = re.sub(r"[{}_^~]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\wáéíóúÁÉÍÓÚñÑüÜ]+\b", text))


def sentence_count(text: str) -> int:
    return len([item for item in re.split(r"[.!?]\s+", text) if item.strip()])


def extract_sections(content: str) -> list[dict]:
    matches = list(SECTION_RE.finditer(content))
    if not matches:
        matches = list(MARKDOWN_SECTION_RE.finditer(content))
    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = latex_to_text(content[start:end])
        sections.append(
            {
                "title": match.group(1).strip(),
                "word_count": count_words(body),
                "text_preview": body[:220],
            }
        )
    return sections


def section_matches(sections: list[dict], *patterns: str) -> list[dict]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    return [section for section in sections if any(pattern.search(section["title"]) for pattern in compiled)]


def collect_hits(content: str, patterns: list[str], max_hits: int = 8) -> list[dict]:
    hits = []
    lines = content.splitlines()
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for line_no, line in enumerate(lines, 1):
        clean = line.strip()
        if not clean:
            continue
        if any(pattern.search(clean) for pattern in compiled):
            hits.append({"line": line_no, "snippet": clean[:220]})
            if len(hits) >= max_hits:
                break
    return hits


def finding(severity: str, title: str, detail: str, **extra) -> dict:
    payload = {"severity": severity, "title": title, "detail": detail}
    payload.update({key: value for key, value in extra.items() if value not in (None, [], {})})
    return payload


def review_writeup(input_path: Path) -> dict:
    raw_content, sources, source_warnings = collect_sources(input_path)
    plain = latex_to_text(raw_content)
    words = count_words(plain)
    findings: list[dict] = []
    strengths: list[str] = []

    if source_warnings:
        findings.append(
            finding(
                "medium",
                "Algunas fuentes no se pudieron leer",
                "El revisor continuó con el texto disponible, pero hay includes o archivos no resueltos.",
                examples=source_warnings[:5],
            )
        )
    if words < 15:
        blocked_findings = list(findings)
        if source_warnings:
            blocked_findings.append(
                finding(
                    "high",
                    "Entrada no revisable",
                    "No se pudo obtener texto cientifico revisable desde la entrada indicada.",
                    examples=source_warnings[:5],
                )
            )
        blocked_findings.append(finding("high", "Texto insuficiente", "No hay texto útil suficiente para una revisión científica."))
        return {
            "blocked": True,
            "raw_content": raw_content,
            "plain_text": plain,
            "sources": sources,
            "findings": blocked_findings,
            "strengths": strengths,
            "sections": [],
            "metrics": {"word_count": words, "source_count": len(sources)},
        }

    sections = extract_sections(raw_content)
    methodology = section_matches(
        sections,
        r"m[eé]tod",
        r"method",
        r"proced",
        r"datos",
        r"data",
        r"reducci",
        r"trazabilidad",
        r"entorno",
        r"material",
        r"inventario",
    )
    results = section_matches(
        sections,
        r"result",
        r"velocidad",
        r"radial",
        r"v\s*sin\s*i",
        r"anchura",
        r"equivalent",
        r"fotometr",
        r"astrometr",
        r"espectr",
        r"medid",
    )
    discussion = section_matches(sections, r"discusi", r"discussion")
    conclusions = section_matches(sections, r"conclus")
    limitations = section_matches(sections, r"limit", r"cautel", r"incertid", r"sesgo")

    unit_hits = UNIT_RE.findall(raw_content)
    uncertainty_hits = UNCERTAINTY_RE.findall(raw_content)
    limitation_hits = LIMITATION_RE.findall(raw_content)
    literature_mentions = LITERATURE_RE.findall(raw_content)
    comparison_mentions = COMPARISON_RE.findall(raw_content)
    strong_hits = collect_hits(raw_content, STRONG_CLAIM_PATTERNS)
    hedge_hits = collect_hits(raw_content, HEDGE_PATTERNS)
    absolute_hits = ABSOLUTE_PATH_RE.findall(raw_content)
    infrastructure_hits = collect_hits(raw_content, [INFRASTRUCTURE_TERMS_RE.pattern], max_hits=20)
    science_hits = collect_hits(raw_content, [SCIENCE_TERMS_RE.pattern], max_hits=20)
    infrastructure_signal_count = len(INFRASTRUCTURE_TERMS_RE.findall(raw_content))
    science_signal_count = len(SCIENCE_TERMS_RE.findall(raw_content))

    if sections:
        strengths.append(f"Se detectaron {len(sections)} secciones o subsecciones.")
    if methodology:
        strengths.append("Hay una sección metodológica o de datos/procedimiento.")
    if results:
        strengths.append("Hay una sección de resultados.")
    if discussion or conclusions:
        strengths.append("Hay discusión o conclusiones detectables.")
    if unit_hits:
        strengths.append("El texto contiene unidades físicas o técnicas.")
    if uncertainty_hits:
        strengths.append("El texto menciona errores, incertidumbres o dispersión.")
    if limitation_hits:
        strengths.append("El texto menciona limitaciones, cautelas, sesgos o supuestos.")
    if literature_mentions and comparison_mentions:
        strengths.append("Hay señales de comparación con literatura o referencias externas.")
    if science_hits:
        strengths.append("El cuerpo del texto contiene señales de contenido científico y términos de interpretación física.")

    if not methodology:
        findings.append(finding("medium", "Falta metodología o trazabilidad clara", "No se detectó una sección clara de datos, metodología, procedimiento o reducción."))
    if not results:
        findings.append(finding("medium", "Falta una sección clara de resultados", "El texto no parece separar los resultados principales en una sección identificable."))
    if not discussion and not conclusions:
        findings.append(finding("medium", "Falta discusión o cierre interpretativo", "No se detectó una sección clara de discusión o conclusiones."))
    if discussion and all(section["word_count"] < 100 for section in discussion):
        findings.append(finding("low", "Discusión muy breve", "La discusión existe, pero parece demasiado corta para sostener interpretación y cautelas."))
    if conclusions and all(section["word_count"] < 80 for section in conclusions):
        findings.append(finding("low", "Conclusiones muy breves", "Las conclusiones existen, pero parecen demasiado cortas para cerrar una memoria científica."))
    if not unit_hits:
        findings.append(finding("medium", "No se detectan unidades", "Un report científico normalmente debe hacer visibles unidades en medidas, tablas, figuras o parámetros."))
    if not uncertainty_hits:
        findings.append(finding("medium", "No se detectan incertidumbres", "No aparecen errores, dispersión, sigma, ± o lenguaje equivalente. Revisa si las medidas necesitan incertidumbre o cautela."))
    if not limitation_hits and words > 250:
        findings.append(finding("medium", "Faltan limitaciones o cautelas explícitas", "El texto no menciona claramente limitaciones, supuestos, sesgos o condiciones de validez."))
    if strong_hits and not hedge_hits:
        findings.append(
            finding(
                "medium",
                "Conclusiones posiblemente demasiado fuertes",
                "Hay lenguaje fuerte sin señales claras de cautela. Revisa si los datos sostienen esas afirmaciones.",
                examples=strong_hits,
            )
        )
    elif strong_hits:
        findings.append(
            finding(
                "low",
                "Revisar fuerza de algunas afirmaciones",
                "Hay lenguaje fuerte, aunque también aparecen cautelas. Conviene comprobar que cada afirmación fuerte está respaldada.",
                examples=strong_hits[:5],
            )
        )
    if literature_mentions and not comparison_mentions:
        findings.append(
            finding(
                "medium",
                "Literatura mencionada sin comparación clara",
                "El texto menciona referencias, literatura o fuentes externas, pero no se detecta lenguaje claro de comparación.",
            )
        )
    if absolute_hits:
        findings.append(
            finding(
                "medium",
                "Rutas absolutas detectadas",
                "Hay rutas locales absolutas que pueden afectar portabilidad o privacidad del entregable.",
            )
        )
    workflow_heavy = words > 70 and infrastructure_signal_count >= 12 and infrastructure_signal_count > max(6, int(science_signal_count * 1.2))
    if workflow_heavy:
        findings.append(
            finding(
                "medium",
                "Cuerpo principal demasiado centrado en workflow",
                "Se detecta bastante lenguaje de rutas, logs, scripts o pipeline frente a contenido científico. Conviene mover parte de esa trazabilidad a apéndices y dejar método, resultados y discusión en el cuerpo.",
                examples=infrastructure_hits[:8],
            )
        )

    result_sections = results or section_matches(sections, r"medid", r"anal")
    for section in result_sections:
        if RESULT_TERMS_RE.search(section["text_preview"]) and DISCUSSION_TERMS_RE.search(section["text_preview"]):
            findings.append(
                finding(
                    "low",
                    "Resultados e interpretación mezclados",
                    f"La sección `{section['title']}` mezcla señales de resultado e interpretación. Puede ser correcto, pero conviene separar si el report lo requiere.",
                )
            )
            break

    checklist = {
        "has_methodology_or_data_section": bool(methodology),
        "has_results_section": bool(results),
        "has_discussion_or_conclusion": bool(discussion or conclusions),
        "mentions_units": bool(unit_hits),
        "mentions_uncertainty": bool(uncertainty_hits),
        "mentions_limitations_or_assumptions": bool(limitation_hits),
        "literature_comparison_visible": bool(literature_mentions and comparison_mentions),
        "absolute_paths_detected": bool(absolute_hits),
        "science_body_not_workflow_heavy": not workflow_heavy,
    }
    return {
        "blocked": False,
        "raw_content": raw_content,
        "plain_text": plain,
        "sources": sources,
        "findings": findings,
        "strengths": strengths,
        "sections": sections,
        "metrics": {
            "word_count": words,
            "sentence_count": sentence_count(plain),
            "source_count": len(sources),
            "section_count": len(sections),
            "unit_signal_count": len(unit_hits),
            "uncertainty_signal_count": len(uncertainty_hits),
            "limitation_signal_count": len(limitation_hits),
            "literature_signal_count": len(literature_mentions),
            "infrastructure_signal_count": infrastructure_signal_count,
            "science_signal_count": science_signal_count,
        },
        "checklist": checklist,
    }


def recommendation_for_finding(item: dict) -> str:
    title = item.get("title", "").lower()
    if "metodolog" in title or "trazabilidad" in title:
        return "Añade una sección breve con datos usados, procedimiento, criterios de selección, herramientas y parámetros no triviales."
    if "resultado" in title:
        return "Separa una sección de resultados con cifras, tablas o figuras antes de entrar en interpretación."
    if "discusión" in title or "interpretativo" in title:
        return "Añade discusión: qué significan los resultados, alternativas, limitaciones y comparación con literatura si aplica."
    if "unidades" in title:
        return "Revisa cada magnitud física y añade unidades en texto, tablas, captions y ecuaciones."
    if "incertidumbres" in title:
        return "Incluye errores, dispersión, rango de valores o una cautela explícita si no hay incertidumbre cuantitativa."
    if "limitaciones" in title:
        return "Añade una frase o párrafo de límites: calidad de datos, selección de órdenes, ventanas, calibración, supuestos o dependencias externas."
    if "literatura" in title:
        return "Convierte la referencia externa en comparación explícita: valor propio, valor publicado, diferencia y lectura física cauta."
    if "rutas" in title:
        return "Sustituye rutas locales por rutas relativas, nombres de artefactos o una descripción reproducible del workspace."
    if "workflow" in title:
        return "Mueve logs, rutas internas y detalle de pipeline a apéndices o trazabilidad, y reserva el cuerpo principal para método, medidas, comparación e interpretación física."
    return "Revisa el hallazgo y añade una corrección concreta en el texto antes de entregar."


def build_markdown_report(payload: dict) -> str:
    results = payload["results"]
    qa = payload.get("qa", {})
    lines = [
        "# Scientific Write-up Review",
        "",
        "## Resumen",
        "",
        f"- Estado: `{payload['status']}`",
        f"- Archivo principal: `{results.get('input_path')}`",
        f"- Fuentes leídas: `{results.get('metrics', {}).get('source_count', 0)}`",
        f"- Palabras aproximadas: `{results.get('metrics', {}).get('word_count', 0)}`",
        f"- Hallazgos: `{len(qa.get('findings', []))}`",
        "",
        "## Fortalezas Detectadas",
        "",
    ]
    strengths = results.get("strengths", [])
    if strengths:
        lines.extend(f"- {item}" for item in strengths)
    else:
        lines.append("- No se detectaron fortalezas estructurales claras de forma automática.")
    lines.extend(["", "## Hallazgos", ""])
    findings = qa.get("findings", [])
    if findings:
        for item in findings:
            lines.append(f"- `{item['severity']}` {item['title']}: {item['detail']}")
            for example in item.get("examples", []):
                if isinstance(example, dict):
                    lines.append(f"  - línea {example.get('line')}: `{example.get('snippet')}`")
                else:
                    lines.append(f"  - {example}")
    else:
        lines.append("- No se detectaron riesgos académicos de alto nivel con estas heurísticas.")
    lines.extend(["", "## Checklist Académica", ""])
    checklist = results.get("checklist", {})
    for key, value in checklist.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Recomendaciones Concretas", ""])
    if findings:
        for item in findings:
            lines.append(f"- {recommendation_for_finding(item)}")
    else:
        lines.append("- Mantén el texto como está y haz una lectura humana final centrada en precisión científica y estilo.")
    lines.extend(["", "## Nota", ""])
    for note in payload.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def ensure_output_file_path(path: Path | None, label: str) -> None:
    if not path:
        return
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"{label} apunta a un directorio, no a un archivo: {public_path(path)}")
    if path.parent.exists() and not path.parent.is_dir():
        raise NotADirectoryError(f"El directorio padre de {label} no es un directorio: {public_path(path.parent)}")


def emit_payload(payload: dict, summary_path: Path | None = None) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")


def build_failure_payload(input_path: Path, error: Exception | str, report_path: Path | None, summary_path: Path | None) -> dict:
    detail = str(error)
    if isinstance(error, Exception):
        detail = f"{type(error).__name__}: {error}"
    findings = [finding("high", "Revision no ejecutada", detail)]
    return standard_tool_payload(
        "scientific_writeup_review",
        status="fail",
        notes=[
            "La revision no pudo producir un resultado fiable.",
            "Corrige la entrada o las rutas de salida y vuelve a ejecutar antes de usar este check.",
        ],
        artifacts={"report_md": report_path, "summary_json": summary_path},
        results={
            "input_path": public_path(input_path),
            "sources": [],
            "sections": [],
            "strengths": [],
            "metrics": {"word_count": 0, "source_count": 0},
            "checklist": {},
        },
        qa={
            "status": "fail",
            "findings": findings,
            "metrics": {"finding_count": len(findings), "word_count": 0},
        },
    )


def cmd_review(args):
    configure_runtime("scientific_writeup_review")
    input_path = Path(args.input).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve() if args.report_md else None
    summary_path = Path(args.summary_json).expanduser().resolve() if args.summary_json else None
    collision_status = _preflight_output_safety(args, input_path)
    if collision_status is not None:
        raise SystemExit(collision_status)
    try:
        ensure_output_file_path(report_path, "--report-md")
        ensure_output_file_path(summary_path, "--summary-json")
        ensure_output_file_path(Path(args.manifest_json).expanduser().resolve() if args.manifest_json else None, "--manifest-json")
    except Exception as exc:
        payload = build_failure_payload(input_path, exc, report_path, summary_path)
        safe_summary_path = summary_path
        try:
            ensure_output_file_path(summary_path, "--summary-json")
        except Exception:
            safe_summary_path = None
        emit_payload(payload, safe_summary_path)
        raise SystemExit(2)

    if not input_path.exists():
        review = {
            "blocked": True,
            "sources": [],
            "findings": [finding("high", "Archivo no encontrado", f"No existe: {public_path(input_path)}")],
            "strengths": [],
            "sections": [],
            "metrics": {"word_count": 0, "source_count": 0},
            "checklist": {},
        }
    else:
        review = review_writeup(input_path)

    collision_status = _preflight_output_safety(args, input_path, review.get("sources", []))
    if collision_status is not None:
        raise SystemExit(collision_status)

    status = "blocked" if review.get("blocked") else ("warning" if review["findings"] else "ok")
    notes = [
        "Revision heuristica y advisory: no sustituye lectura experta ni criterio del profesor.",
        "Complementa latex_workbench.py review: aqui se revisa contenido cientifico e interpretacion, no maquetacion.",
    ]
    artifacts = {"report_md": report_path, "summary_json": summary_path}
    results = {
        "input_path": public_path(input_path),
        "sources": [public_path(path) for path in review.get("sources", [])],
        "sections": review.get("sections", []),
        "strengths": review.get("strengths", []),
        "metrics": review.get("metrics", {}),
        "checklist": review.get("checklist", {}),
    }
    qa = {
        "status": status,
        "findings": review["findings"],
        "metrics": {
            "finding_count": len(review["findings"]),
            "word_count": review.get("metrics", {}).get("word_count", 0),
        },
    }
    payload = standard_tool_payload(
        "scientific_writeup_review",
        status=status,
        notes=notes,
        artifacts=artifacts,
        results=results,
        qa=qa,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_markdown_report(payload), encoding="utf-8")
    emit_payload(payload, summary_path)
    if args.manifest_json:
        outputs = [path for path in [report_path, summary_path] if path]
        write_manifest(
            args.manifest_json,
            inputs=review.get("sources", [input_path]),
            outputs=outputs,
            parameters={"tool": "scientific_writeup_review"},
            command=" ".join(sys.argv),
            notes=notes,
            extra={"status": status, "finding_count": len(review["findings"])},
        )
    if status == "blocked":
        raise SystemExit(2)


def main():
    args = parse_args()
    cmd_review(args)


if __name__ == "__main__":
    main()
