#!/usr/bin/env python3
"""Create a reproducible analysis notebook scaffold for local or Colab-style workflows."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import public_path, sanitize_payload, standard_qa_payload, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload


TEXT = {
    "en": {
        "intro": "Create a reproducible notebook for inspecting, analyzing, and explaining the dataset.",
        "goals_heading": "## Goals",
        "goals_body_general": (
            "- Describe the analytical question.\n"
            "- Inspect the input data before transforming it.\n"
            "- Build the analysis step by step.\n"
            "- Summarize findings, caveats, and next steps."
        ),
        "goals_body_applied": (
            "- Describe the applied question and the intended deliverable.\n"
            "- Inspect and clean the operational dataset.\n"
            "- Build a reproducible workflow with tables, figures, and validation.\n"
            "- End with interpretation and a short conclusion."
        ),
        "goals_body_astronomy": (
            "- Describe the scientific question.\n"
            "- Inspect the raw or reduced inputs.\n"
            "- Build the analysis step by step.\n"
            "- Summarize findings and caveats."
        ),
        "workflow_heading": "## Workflow",
        "workflow_body_general": "Use small cells, inspect outputs often, and keep assumptions, units, and selection cuts explicit.",
        "workflow_body_applied": "Keep data preparation, metrics, and exported deliverables explicit. Prefer one output directory and avoid hidden local path dependencies.",
        "workflow_body_astronomy": "Use small cells, inspect outputs often, and keep units, assumptions, and selection cuts explicit.",
        "runtime_heading": "## Runtime profile",
        "runtime_local": "This notebook is scaffolded for local Python work. Keep outputs in one project folder and avoid overwriting source data.",
        "runtime_colab": "This notebook is scaffolded for Colab-style execution. Avoid hard-coded home paths, stage inputs explicitly, and keep outputs inside one export folder.",
        "outputs_heading": "## Output policy",
        "outputs_body": (
            "- Keep raw inputs untouched.\n"
            "- Save derived tables, figures, and reports under one explicit output directory.\n"
            "- Prefer relative or project-local paths over user-specific absolute paths.\n"
            "- Export figures with stable names if the notebook is part of a deliverable."
        ),
        "results_heading": "## Results",
        "results_body": "Add figures, tables, validation notes, and a short written interpretation here.",
        "conclusion_heading": "## Conclusion",
        "conclusion_body": "Summarize the final answer, limitations, and any follow-up work that remains.",
        "data_intake_heading": "## Data intake",
        "data_intake_body": "Load the source data and inspect the first rows before any transformation.",
        "data_notes_heading": "## Data notes",
        "data_notes_body": "Document variable meanings, units, frequency, caveats, and any assumptions about missing values or identifiers.",
        "methodology_heading": "## Methodology",
        "methodology_body": "Explain the transformation or modeling choices before running them.",
    },
    "es": {
        "intro": "Crea un notebook reproducible para inspeccionar, analizar y explicar el conjunto de datos.",
        "goals_heading": "## Objetivos",
        "goals_body_general": (
            "- Describir la pregunta de analisis.\n"
            "- Inspeccionar los datos antes de transformarlos.\n"
            "- Construir el flujo paso a paso.\n"
            "- Resumir resultados, limitaciones y siguientes pasos."
        ),
        "goals_body_applied": (
            "- Describir la pregunta aplicada y el entregable esperado.\n"
            "- Inspeccionar y limpiar el dataset operativo.\n"
            "- Construir un flujo reproducible con tablas, figuras y validacion.\n"
            "- Cerrar con interpretacion y conclusion breve."
        ),
        "goals_body_astronomy": (
            "- Describir la pregunta cientifica.\n"
            "- Inspeccionar los datos de entrada.\n"
            "- Construir el analisis paso a paso.\n"
            "- Resumir resultados y limitaciones."
        ),
        "workflow_heading": "## Flujo de trabajo",
        "workflow_body_general": "Usa celdas pequenas, inspecciona salidas con frecuencia y deja claros los supuestos, unidades y filtros.",
        "workflow_body_applied": "Deja explicitos la preparacion de datos, las metricas y los entregables exportados. Prefiere una sola carpeta de salida y evita depender de rutas locales ocultas.",
        "workflow_body_astronomy": "Usa celdas pequenas, inspecciona salidas con frecuencia y deja claras las unidades, supuestos y cortes.",
        "runtime_heading": "## Perfil de ejecucion",
        "runtime_local": "Este notebook esta pensado para trabajo local en Python. Mantiene las salidas en una sola carpeta de proyecto y no toca los datos fuente.",
        "runtime_colab": "Este notebook esta pensado para ejecucion estilo Colab. Evita rutas absolutas de usuario, deja los inputs explicitos y guarda las salidas dentro de una sola carpeta de exportacion.",
        "outputs_heading": "## Politica de outputs",
        "outputs_body": (
            "- No tocar datos brutos.\n"
            "- Guardar tablas derivadas, figuras y reportes en una sola carpeta de salida explicita.\n"
            "- Preferir rutas relativas o locales al proyecto en vez de rutas absolutas personales.\n"
            "- Exportar figuras con nombres estables si el notebook forma parte de una entrega."
        ),
        "results_heading": "## Resultados",
        "results_body": "Anade aqui figuras, tablas, notas de validacion e interpretacion breve.",
        "conclusion_heading": "## Conclusiones",
        "conclusion_body": "Resume la respuesta final, las limitaciones y cualquier trabajo pendiente.",
        "data_intake_heading": "## Carga inicial de datos",
        "data_intake_body": "Carga los datos fuente e inspecciona las primeras filas antes de transformarlos.",
        "data_notes_heading": "## Notas sobre los datos",
        "data_notes_body": "Documenta significado de variables, unidades, frecuencia, limitaciones y supuestos sobre valores ausentes o identificadores.",
        "methodology_heading": "## Metodologia",
        "methodology_body": "Explica las transformaciones o decisiones de modelado antes de ejecutarlas.",
    },
    "bilingual": {
        "intro": "Create a reproducible notebook / Crea un notebook reproducible para inspeccionar, analizar y explicar el conjunto de datos.",
        "goals_heading": "## Goals / Objetivos",
        "goals_body_general": (
            "- Describe the analytical question / Describe la pregunta de analisis.\n"
            "- Inspect the inputs before transforming them / Inspecciona los datos antes de transformarlos.\n"
            "- Build the analysis step by step / Construye el flujo paso a paso.\n"
            "- Summarize findings and caveats / Resume resultados y limitaciones."
        ),
        "goals_body_applied": (
            "- Describe the applied question and deliverable / Describe la pregunta aplicada y el entregable.\n"
            "- Inspect and clean the dataset / Inspecciona y limpia el dataset.\n"
            "- Build a reproducible workflow with tables and figures / Construye un flujo reproducible con tablas y figuras.\n"
            "- End with interpretation and conclusion / Cierra con interpretacion y conclusion."
        ),
        "goals_body_astronomy": (
            "- Describe the scientific question / Describe la pregunta cientifica.\n"
            "- Inspect the inputs / Inspecciona los datos de entrada.\n"
            "- Build the analysis step by step / Construye el analisis paso a paso.\n"
            "- Summarize findings and caveats / Resume resultados y limitaciones."
        ),
        "workflow_heading": "## Workflow / Flujo de trabajo",
        "workflow_body_general": "Use small cells and explicit assumptions / Usa celdas pequenas y supuestos explicitos.",
        "workflow_body_applied": "Keep outputs explicit and portable / Mantiene los outputs explicitos y portables.",
        "workflow_body_astronomy": "Use small cells and explicit assumptions / Usa celdas pequenas y supuestos explicitos.",
        "runtime_heading": "## Runtime profile / Perfil de ejecucion",
        "runtime_local": "Prepared for local execution / Preparado para ejecucion local.",
        "runtime_colab": "Prepared for Colab-style execution / Preparado para ejecucion tipo Colab.",
        "outputs_heading": "## Output policy / Politica de outputs",
        "outputs_body": (
            "- Keep raw data untouched / No tocar datos brutos.\n"
            "- Save deliverables under one output folder / Guardar entregables en una sola carpeta de salida.\n"
            "- Prefer portable paths / Preferir rutas portables."
        ),
        "results_heading": "## Results / Resultados",
        "results_body": "Add figures, tables, and interpretation / Anade figuras, tablas e interpretacion.",
        "conclusion_heading": "## Conclusion / Conclusiones",
        "conclusion_body": "Summarize the final answer and caveats / Resume la respuesta final y las limitaciones.",
        "data_intake_heading": "## Data intake / Carga inicial de datos",
        "data_intake_body": "Load and inspect the source data before transformation / Carga e inspecciona los datos fuente antes de transformarlos.",
        "data_notes_heading": "## Data notes / Notas sobre los datos",
        "data_notes_body": "Document variables, units, caveats, and assumptions / Documenta variables, unidades, limitaciones y supuestos.",
        "methodology_heading": "## Methodology / Metodologia",
        "methodology_body": "Explain transformations or modeling choices first / Explica antes las transformaciones o decisiones de modelado.",
    },
}


TOOL_NAME = "bootstrap_analysis_notebook.py"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Output .ipynb path.")
    parser.add_argument("--title", default="Scientific Data Analysis", help="Notebook title.")
    parser.add_argument(
        "--domain",
        choices=["general", "applied", "astronomy"],
        default="general",
        help="Notebook template flavor.",
    )
    parser.add_argument("--language", choices=["en", "es", "bilingual"], default="en")
    parser.add_argument("--runtime-profile", choices=["local", "colab"], default="local")
    parser.add_argument("--data-path", help="Optional data path to include in the loading scaffold.")
    parser.add_argument("--output-dir-name", default="analysis_outputs", help="Default export directory name inside the notebook.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the notebook if it already exists.")
    parser.add_argument("--summary-json", help="Optional standard-envelope JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def _emit_collision_only(args, collisions: list[dict[str, str]]) -> int:
    message = "Refusing notebook scaffold outputs that overlap the source data path."
    payload = build_tool_payload(
        TOOL_NAME,
        status="blocked",
        notes=[message, "No notebook, summary, or manifest was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "collisions": collisions,
        },
        qa=standard_qa_payload(status="blocked", findings=[message], metrics={"blocking_count": len(collisions)}),
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def _preflight_output_safety(args) -> int | None:
    inputs = [("--data-path", args.data_path)] if args.data_path else []
    outputs = [
        ("output", args.output),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
    ]
    collisions = find_output_input_collisions(inputs, outputs)
    return _emit_collision_only(args, collisions) if collisions else None


def md_cell(text: str, *, metadata: dict | None = None) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": metadata or {},
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


def code_cell(text: str, *, collapsed: bool = False) -> dict:
    metadata = {}
    if collapsed:
        metadata = {"jupyter": {"source_hidden": True}, "tags": ["helper"]}
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": [],
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


def import_block(domain: str, runtime_profile: str) -> str:
    base = [
        "from pathlib import Path",
        "",
        "import json",
        "import numpy as np",
        "import pandas as pd",
        "import matplotlib.pyplot as plt",
        "from IPython.display import display",
        "",
        "plt.style.use('seaborn-v0_8-whitegrid')",
    ]
    if domain == "astronomy":
        base.extend(
            [
                "from astropy.io import fits",
                "from astropy.table import Table",
                "from astropy.visualization import ImageNormalize, PercentileInterval",
                "from astropy.wcs import WCS",
            ]
        )
    if domain == "applied":
        base.extend(
            [
                "from scipy import stats",
                "try:",
                "    import statsmodels.api as sm",
                "except Exception:",
                "    sm = None",
            ]
        )
    if runtime_profile == "colab":
        base.extend(
            [
                "",
                "try:",
                "    import google.colab  # type: ignore",
                "    IN_COLAB = True",
                "except Exception:",
                "    IN_COLAB = False",
            ]
        )
    else:
        base.extend(["", "IN_COLAB = False"])
    return "\n".join(base)


def config_block(data_path: str | None, output_dir_name: str) -> str:
    data_literal = repr(data_path) if data_path else "None"
    return "\n".join(
        [
            f"DATA_PATH = {data_literal}",
            f"OUTPUT_DIR = Path('{output_dir_name}')",
            "OUTPUT_DIR.mkdir(parents=True, exist_ok=True)",
            "FIGURE_REGISTRY = []",
            "",
            "if DATA_PATH is None:",
            "    print('Set DATA_PATH before running the notebook.')",
            "else:",
            "    print(f'Using input: {DATA_PATH}')",
            "print(f'Output directory: {OUTPUT_DIR.resolve()}')",
        ]
    )


def data_loader_block(domain: str) -> str:
    lines = [
        "if DATA_PATH is None:",
        "    raise ValueError('Set DATA_PATH before running the notebook.')",
        "",
        "path = Path(DATA_PATH)",
        "suffix = path.suffix.lower()",
        "if suffix in {'.csv', '.tsv'}:",
        "    sep = '\\t' if suffix == '.tsv' else ','",
        "    data = pd.read_csv(path, sep=sep)",
        "    display(data.head())",
        "elif suffix in {'.xlsx', '.xls'}:",
        "    data = pd.read_excel(path)",
        "    display(data.head())",
    ]
    if domain == "astronomy":
        lines.extend(
            [
                "elif suffix in {'.fits', '.fit', '.fts', '.fz'}:",
                "    with fits.open(path) as hdus:",
                "        hdus.info()",
                "    image = fits.getdata(path)",
                "    plt.figure(figsize=(6, 5))",
                "    plt.imshow(np.asarray(image).squeeze(), origin='lower', cmap='gray')",
                "    plt.colorbar()",
                "    plt.show()",
                "elif suffix in {'.ecsv', '.vot', '.votable', '.xml'}:",
                "    data = Table.read(path)",
                "    display(data[:5])",
            ]
        )
    lines.extend(["else:", "    print('Add a custom loader for this format.')"])
    return "\n".join(lines)


def helper_block(domain: str) -> str:
    base = [
        "def save_current_figure(name):",
        "    path = OUTPUT_DIR / name",
        "    plt.gcf().tight_layout()",
        "    plt.savefig(path, dpi=160, bbox_inches='tight')",
        "    FIGURE_REGISTRY.append(path)",
        "    print(f'Saved figure: {path}')",
        "",
        "def write_json_summary(name, payload):",
        "    target = OUTPUT_DIR / name",
        "    with target.open('w', encoding='utf-8') as handle:",
        "        json.dump(payload, handle, indent=2, ensure_ascii=True)",
        "    print(f'Wrote summary: {target}')",
    ]
    if domain == "applied":
        base.extend(
            [
                "",
                "# Applied-analysis note:",
                "# Keep metrics, figures, and derived tables under OUTPUT_DIR so the notebook stays portable.",
            ]
        )
    return "\n".join(base)


def analysis_stub(domain: str) -> str:
    if domain == "applied":
        return "\n".join(
            [
                "# Add profiling, cleaning, modeling, and validation steps here.",
                "# Suggested structure:",
                "# 1. Data quality checks",
                "# 2. Feature or series preparation",
                "# 3. Model or benchmark estimation",
                "# 4. Metrics and exported result tables",
                "# 5. Final interpretation",
            ]
        )
    if domain == "astronomy":
        return "\n".join(
            [
                "# Add profiling, calibration, and analysis steps here.",
                "# Keep transformations explicit and rerunnable.",
            ]
        )
    return "\n".join(
        [
            "# Add profiling, cleaning, and analysis steps here.",
            "# Keep transformations explicit and rerunnable.",
        ]
    )


def validate_output_dir_name(output_dir_name: str) -> list[str]:
    if not output_dir_name or not output_dir_name.strip():
        return ["Output directory name is empty."]
    candidate = Path(output_dir_name)
    if candidate.is_absolute():
        return ["Output directory name must be project-relative, not absolute."]
    if ".." in candidate.parts:
        return ["Output directory name must not contain '..' path traversal segments."]
    return []


def input_warnings(data_path: str | None, runtime_profile: str) -> list[str]:
    warnings: list[str] = []
    if not data_path:
        return warnings
    path = Path(data_path)
    suffix = path.suffix.lower()
    if not path.exists():
        warnings.append("Data path does not exist yet; scaffold was created with a placeholder path.")
    if suffix == ".ipynb":
        warnings.append(
            "Data path is a notebook. This scaffold creates a new notebook and does not preserve, execute, or fill a professor-provided notebook; use notebook_workbench/coursework_notebook_fidelity_check for that route."
        )
    if path.is_absolute():
        warnings.append("Data path is absolute; consider replacing it with a project-relative path before sharing or using Colab.")
    if runtime_profile == "colab" and path.is_absolute():
        warnings.append("Colab-style notebooks should stage inputs explicitly instead of relying on a local absolute path.")
    return warnings


def build_payload(
    args,
    status: str,
    output_path: Path,
    warnings: list[str],
    blockers: list[str],
    *,
    error: str | None = None,
    notebook: dict | None = None,
) -> dict:
    findings = [*blockers, *warnings]
    metrics = {
        "cell_count": len(notebook.get("cells", [])) if notebook else 0,
        "warning_count": len(warnings),
        "blocking_count": len(blockers),
    }
    qa_status = status if status in {"ok", "warning", "blocked", "fail"} else "warning"
    artifacts = {
        "notebook": output_path if status in {"ok", "warning"} else None,
        "summary_json": getattr(args, "summary_json", None),
        "manifest_json": getattr(args, "manifest_json", None),
    }
    results = {
        "output": public_path(output_path),
        "title": args.title,
        "domain": args.domain,
        "language": args.language,
        "runtime_profile": args.runtime_profile,
        "data_path": public_path(args.data_path) if args.data_path else None,
        "output_dir_name": args.output_dir_name,
        "warnings": warnings,
        "blockers": blockers,
    }
    if error:
        results["error"] = error
    return build_tool_payload(
        TOOL_NAME,
        status=status,
        notes=findings,
        artifacts=artifacts,
        results=results,
        qa=standard_qa_payload(status=qa_status, findings=findings, metrics=metrics),
    )


def emit_or_print(payload: dict, args) -> None:
    if args.summary_json:
        emit_payload(payload, args.summary_json)
        return
    status = payload.get("status")
    results = payload.get("results", {})
    if status in {"ok", "warning"}:
        print(f"Notebook written to {Path(args.output).resolve()}")
        for warning in results.get("warnings", []):
            print(f"Warning: {warning}", file=sys.stderr)
    else:
        problems = results.get("blockers") or [results.get("error") or "Notebook scaffold failed."]
        print("; ".join(str(item) for item in problems), file=sys.stderr)


def build_notebook(
    title: str,
    domain: str,
    language: str,
    runtime_profile: str,
    data_path: str | None,
    output_dir_name: str,
    warnings: list[str] | None = None,
):
    text = TEXT[language]
    goals_key = f"goals_body_{domain}"
    workflow_key = f"workflow_body_{domain}"
    runtime_text = text["runtime_colab"] if runtime_profile == "colab" else text["runtime_local"]
    cells = [
        md_cell(f"# {title}\n\n{text['intro']}"),
        md_cell(f"{text['goals_heading']}\n\n{text[goals_key]}"),
        md_cell(f"{text['runtime_heading']}\n\n{runtime_text}"),
        md_cell(f"{text['outputs_heading']}\n\n{text['outputs_body']}"),
        code_cell(import_block(domain, runtime_profile)),
        md_cell(f"{text['workflow_heading']}\n\n{text[workflow_key]}"),
        code_cell(config_block(data_path, output_dir_name), collapsed=True),
        code_cell(helper_block(domain), collapsed=True),
        md_cell(f"{text['data_intake_heading']}\n\n{text['data_intake_body']}"),
        code_cell(data_loader_block(domain)),
        md_cell(f"{text['data_notes_heading']}\n\n{text['data_notes_body']}"),
        md_cell(f"{text['methodology_heading']}\n\n{text['methodology_body']}"),
        code_cell(analysis_stub(domain)),
        md_cell(f"{text['results_heading']}\n\n{text['results_body']}"),
        md_cell(text["conclusion_heading"] + "\n\n" + text["conclusion_body"]),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
            "scientific_data_analysis": {
                "tool": TOOL_NAME,
                "domain": domain,
                "language": language,
                "runtime_profile": runtime_profile,
                "data_path": data_path,
                "output_dir_name": output_dir_name,
                "warnings": list(warnings or []),
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main():
    args = parse_args()
    collision_status = _preflight_output_safety(args)
    if collision_status is not None:
        return collision_status
    output_path = Path(args.output)
    blockers = []
    warnings = input_warnings(args.data_path, args.runtime_profile)
    blockers.extend(validate_output_dir_name(args.output_dir_name))

    if output_path.suffix.lower() != ".ipynb":
        blockers.append("Output path must end with .ipynb.")
    if output_path.exists() and not args.overwrite:
        blockers.append(f"Output already exists: {output_path}. Use --overwrite to replace it.")
    if output_path.parent.exists() and not output_path.parent.is_dir():
        blockers.append(f"Output parent exists but is not a directory: {output_path.parent}")
    for label, raw_path in (("summary-json", args.summary_json), ("manifest-json", args.manifest_json)):
        if raw_path:
            parent = Path(raw_path).parent
            if parent.exists() and not parent.is_dir():
                blockers.append(f"{label} parent exists but is not a directory: {parent}")

    if blockers:
        status = "blocked" if output_path.exists() and not args.overwrite else "fail"
        payload = build_payload(args, status, output_path, warnings, blockers, error="Invalid notebook scaffold request.")
        emit_or_print(payload, args)
        return 2

    notebook = build_notebook(
        title=args.title,
        domain=args.domain,
        language=args.language,
        runtime_profile=args.runtime_profile,
        data_path=args.data_path,
        output_dir_name=args.output_dir_name,
        warnings=warnings,
    )
    status = "warning" if warnings else "ok"
    payload = build_payload(args, status, output_path, warnings, blockers, notebook=notebook)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(notebook, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    except OSError as exc:
        payload = build_payload(args, "fail", output_path, warnings, [f"Could not write notebook: {exc}"], error=str(exc))
        emit_or_print(payload, args)
        return 2
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[args.data_path] if args.data_path else [],
            outputs=[output_path, args.summary_json] if args.summary_json else [output_path],
            parameters={
                "title": args.title,
                "domain": args.domain,
                "language": args.language,
                "runtime_profile": args.runtime_profile,
                "output_dir_name": args.output_dir_name,
                "overwrite": args.overwrite,
            },
            command=" ".join(shlex.quote(part) for part in sys.argv),
            notes=warnings,
        )
    emit_or_print(payload, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
