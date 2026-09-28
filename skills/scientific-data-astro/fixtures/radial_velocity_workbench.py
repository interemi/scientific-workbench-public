#!/usr/bin/env python3
"""Inspect, document, and package manual radial-velocity fitting work around Systemic."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

from _internal.public_contract import build_tool_payload
from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from _internal.radial_velocity_systemic import inspect_systemic_input
from _internal.runtime_common import compile_latex_project, configure_runtime


TEXT = {
    "es": {
        "title_prefix": "Analisis de velocidad radial",
        "readme_title": "Ruta de trabajo para analisis RV con Systemic",
        "notes_title": "Notas de sesion",
        "objective_heading": "## Objetivo",
        "data_heading": "## Datos y backend usado",
        "initial_heading": "## Inspeccion inicial de velocidad radial",
        "period_heading": "## Busqueda de periodos y FAP",
        "fit_heading": "## Modelo ajustado",
        "phased_heading": "## Velocidad radial en fase por planeta",
        "dynamics_heading": "## Comportamiento dinamico",
        "conclusions_heading": "## Conclusiones y limitaciones",
        "caveats_subheading": "### Limitaciones",
        "pending": "Pendiente",
        "no_figure": "No se aporto figura para esta seccion.",
        "no_planets": "No se definieron planetas en el manifiesto.",
        "package_title": "Paquete de sesion RV",
        "raw_rv_caption": "Velocidad radial observada",
        "initial_periodogram_caption": "Periodograma inicial",
        "fitted_rv_caption": "Ajuste final de velocidad radial",
        "statistics_caption": "Estadisticas del ajuste",
        "residual_periodogram_caption": "Periodograma residual",
        "phased_caption_prefix": "Curva en fase",
        "dynamics_caption": "Evolucion dinamica",
        "planet_label_prefix": "Planeta",
        "period_label": "Periodo",
        "planet_count_label": "Planetas en el modelo",
        "chi2_label": "chi2 antes/despues",
        "rms_label": "RMS antes/despues",
        "integration_horizon_label": "Horizonte de integracion",
        "system_label": "Sistema",
        "source_files_label": "Ficheros fuente",
        "dataset_count_label": "Datasets RV",
        "samples_label": "muestras",
        "units_label": "unidades",
        "included_items_heading": "## Elementos incluidos",
        "package_notes_heading": "## Notas",
        "package_note_1": "Este paquete esta pensado para la entrega o archivo de una sesion manual de velocidad radial.",
        "package_note_2": "Conviene dejar fuera los datos RV crudos salvo que quieras una copia autocontenida.",
        "validation_ok": "El manifiesto esta listo para generar informe.",
        "validation_warnings": "El manifiesto tiene avisos que conviene revisar antes del informe.",
        "validation_heading": "Validacion del manifiesto",
    },
    "en": {
        "title_prefix": "Radial-velocity analysis",
        "readme_title": "Systemic-oriented RV workflow",
        "notes_title": "Session notes",
        "objective_heading": "## Objective",
        "data_heading": "## Data and backend used",
        "initial_heading": "## Initial radial-velocity inspection",
        "period_heading": "## Period search and FAP",
        "fit_heading": "## Fitted model",
        "phased_heading": "## Phased radial velocity by planet",
        "dynamics_heading": "## Dynamical behavior",
        "conclusions_heading": "## Conclusions and caveats",
        "caveats_subheading": "### Caveats",
        "pending": "Pending",
        "no_figure": "No figure was provided for this section.",
        "no_planets": "No planets were defined in the manifest.",
        "package_title": "RV session package",
        "raw_rv_caption": "Observed radial velocity",
        "initial_periodogram_caption": "Initial periodogram",
        "fitted_rv_caption": "Final radial-velocity fit",
        "statistics_caption": "Fit statistics",
        "residual_periodogram_caption": "Residual periodogram",
        "phased_caption_prefix": "Phased RV",
        "dynamics_caption": "Dynamical evolution",
        "planet_label_prefix": "Planet",
        "period_label": "Period",
        "planet_count_label": "Planets in the model",
        "chi2_label": "chi2 before/after",
        "rms_label": "RMS before/after",
        "integration_horizon_label": "Integration horizon",
        "system_label": "System",
        "source_files_label": "Source files",
        "dataset_count_label": "RV datasets",
        "samples_label": "samples",
        "units_label": "units",
        "included_items_heading": "## Included items",
        "package_notes_heading": "## Notes",
        "package_note_1": "This package is intended for handoff or archiving of a manual radial-velocity session.",
        "package_note_2": "Keep raw RV inputs outside the package unless you explicitly want a copied bundle.",
        "validation_ok": "The manifest is ready for report generation.",
        "validation_warnings": "The manifest has warnings worth reviewing before building the report.",
        "validation_heading": "Manifest validation",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect .sys, .vels, or directories with Systemic-style RV inputs.")
    inspect_parser.add_argument("input_path", help="A .sys, .vels, or directory.")
    inspect_parser.add_argument("--summary-json", help="Optional output JSON path.")
    inspect_parser.add_argument("--manifest-json", help="Optional provenance manifest.")

    scaffold_parser = subparsers.add_parser("scaffold-session", help="Create an editable session bundle for manual RV work.")
    scaffold_parser.add_argument("output_dir", help="Directory where the session bundle will be created.")
    scaffold_parser.add_argument("inputs", nargs="*", help="Optional .sys, .vels, or directories to prefill source metadata.")
    scaffold_parser.add_argument("--backend", choices=["systemic-live", "systemic-local", "generic-rv"], default="systemic-live")
    scaffold_parser.add_argument("--system-name", help="Optional explicit system name.")
    scaffold_parser.add_argument("--language", choices=["es", "en"], default="es")
    scaffold_parser.add_argument("--title", help="Optional session/report title.")
    scaffold_parser.add_argument("--planet-count", type=int, default=0, help="Preseed N planet sections in the session manifest.")
    scaffold_parser.add_argument("--overwrite", action="store_true")
    scaffold_parser.add_argument("--manifest-json", help="Optional provenance manifest for the scaffold command.")

    report_parser = subparsers.add_parser("build-report", help="Build markdown, LaTeX, and summary outputs from a session manifest.")
    report_parser.add_argument("session_manifest", help="Path to session_manifest.json.")
    report_parser.add_argument("--output-dir", help="Optional output directory. Default: manifest directory.")
    report_parser.add_argument("--language", choices=["es", "en"], help="Override report language.")
    report_parser.add_argument("--manifest-json", help="Optional provenance manifest for the build-report command.")

    validate_parser = subparsers.add_parser("validate-manifest", help="Validate a session manifest before building the report.")
    validate_parser.add_argument("session_manifest", help="Path to session_manifest.json.")
    validate_parser.add_argument("--summary-json", help="Optional output JSON path.")
    validate_parser.add_argument("--language", choices=["es", "en"], help="Override validation language.")
    validate_parser.add_argument("--manifest-json", help="Optional provenance manifest for the validation command.")

    package_parser = subparsers.add_parser("package", help="Bundle a session folder into a handoff zip.")
    package_parser.add_argument("session_dir", help="Session directory created by scaffold-session.")
    package_parser.add_argument("--output-zip", required=True, help="ZIP file to create.")
    package_parser.add_argument("--title", help="Optional package title.")
    package_parser.add_argument("--manifest-json", help="Optional provenance manifest for the package command.")

    return parser.parse_args()


def _save_json(path: Path, payload: dict) -> None:
    if path.parent.exists() and not path.parent.is_dir():
        raise OSError(f"summary-json parent is not a directory: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _text_for(language: str) -> dict:
    return TEXT.get(language, TEXT["es"])


def _format_value(value, digits: int = 4) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _format_measurement(value, digits: int = 4) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, (int, float)):
        number = float(value)
        if number == 0:
            return "0"
        absolute = abs(number)
        if absolute < 1e-4 or absolute >= 1e4:
            return f"{number:.3e}"
        return f"{number:.{digits}f}"
    return str(value)


def _resolve_manifest_path(base_dir: Path, raw_value: str | None) -> Path | None:
    if not raw_value:
        return None
    candidate = Path(str(raw_value)).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _is_blank(value) -> bool:
    return value is None or str(value).strip() == ""


def _prefill_from_inputs(inputs: list[str]) -> dict:
    source_files = []
    systems = []
    dataset_only = []
    for raw in inputs:
        path = Path(raw).resolve()
        source_files.append(public_path(path))
        payload = inspect_systemic_input(path)
        mode = payload.get("mode")
        if mode == "system":
            systems.append(payload)
        elif mode == "dataset":
            dataset_only.append(payload)
        elif mode == "directory":
            systems.extend(payload.get("systems", []))
            dataset_only.extend(payload.get("standalone_datasets", []))
    prefill = {
        "source_files": source_files,
        "system_name": None,
        "star_metadata": {
            "name": None,
            "mass_solar": None,
            "hd": None,
            "hip": None,
            "teff_k": None,
            "ra_deg": None,
            "dec_deg": None,
        },
        "rv_datasets": [],
        "workflow_notes": [],
    }
    if len(systems) == 1:
        system = systems[0]
        prefill["system_name"] = system.get("system_name")
        prefill["star_metadata"] = system.get("star_metadata", prefill["star_metadata"])
        for dataset in system.get("rv_datasets", []):
            prefill["rv_datasets"].append(
                {
                    "label": dataset.get("dataset_label") or dataset.get("reference") or dataset.get("filename"),
                    "source": dataset.get("resolved_path") or dataset.get("path"),
                    "sample_count": dataset.get("sample_count"),
                    "value_units": dataset.get("value_units"),
                    "metadata": dataset.get("metadata", {}),
                    "jd_span_days": dataset.get("jd_span_days"),
                }
            )
    elif systems:
        prefill["workflow_notes"].append(
            "Multiple systems were discovered in the provided inputs; set `system_name`, choose the datasets you used, and trim the manifest by hand."
        )
    else:
        for dataset in dataset_only:
            prefill["rv_datasets"].append(
                {
                    "label": dataset.get("dataset_label") or dataset.get("filename"),
                    "source": dataset.get("path"),
                    "sample_count": dataset.get("sample_count"),
                    "value_units": dataset.get("value_units"),
                    "metadata": dataset.get("metadata", {}),
                    "jd_span_days": dataset.get("jd_span_days"),
                }
            )
    if dataset_only and not systems:
        prefill["workflow_notes"].append(
            "The session was prefilled from standalone `.vels` files rather than a `.sys` system definition."
        )
    return prefill


def _iter_inspected_datasets(payload: dict):
    mode = payload.get("mode")
    if mode == "dataset":
        yield payload
    elif mode == "system":
        for dataset in payload.get("rv_datasets", []):
            yield dataset
    elif mode == "directory":
        for system in payload.get("systems", []):
            yield from _iter_inspected_datasets(system)
        for dataset in payload.get("standalone_datasets", []):
            yield dataset


def _inspect_metrics(payload: dict) -> dict:
    datasets = list(_iter_inspected_datasets(payload))
    missing_dataset_count = sum(1 for item in datasets if item.get("exists") is False)
    existing_datasets = [item for item in datasets if item.get("exists") is not False]
    sample_count_total = sum(int(item.get("sample_count") or 0) for item in existing_datasets)
    malformed_row_count = sum(int(item.get("malformed_rows") or 0) for item in existing_datasets)
    nonfinite_value_row_count = sum(int(item.get("nonfinite_value_rows") or 0) for item in existing_datasets)
    invalid_error_row_count = sum(int(item.get("invalid_error_rows") or 0) for item in existing_datasets)
    nonpositive_error_row_count = sum(int(item.get("nonpositive_error_rows") or 0) for item in existing_datasets)
    missing_error_row_count = sum(int(item.get("missing_error_rows") or 0) for item in existing_datasets)
    zero_sample_dataset_count = sum(1 for item in existing_datasets if int(item.get("sample_count") or 0) == 0)
    return {
        "mode": payload.get("mode"),
        "rv_dataset_count": len(datasets),
        "existing_dataset_count": len(existing_datasets),
        "missing_dataset_count": missing_dataset_count,
        "sample_count_total": sample_count_total,
        "malformed_row_count": malformed_row_count,
        "nonfinite_value_row_count": nonfinite_value_row_count,
        "invalid_error_row_count": invalid_error_row_count,
        "nonpositive_error_row_count": nonpositive_error_row_count,
        "missing_error_row_count": missing_error_row_count,
        "zero_sample_dataset_count": zero_sample_dataset_count,
    }


def _inspect_qa(payload: dict) -> dict:
    metrics = _inspect_metrics(payload)
    findings = []
    if metrics["missing_dataset_count"]:
        findings.append(f"{metrics['missing_dataset_count']} RV dataset reference(s) could not be resolved.")
    if metrics["zero_sample_dataset_count"]:
        findings.append(f"{metrics['zero_sample_dataset_count']} RV dataset(s) contain no valid JD/RV samples.")
    if metrics["malformed_row_count"]:
        findings.append(f"{metrics['malformed_row_count']} malformed RV row(s) were skipped.")
    if metrics["nonfinite_value_row_count"]:
        findings.append(f"{metrics['nonfinite_value_row_count']} RV row(s) with non-finite JD/RV values were skipped.")
    if metrics["invalid_error_row_count"]:
        findings.append(f"{metrics['invalid_error_row_count']} RV uncertainty value(s) were non-numeric or non-finite.")
    if metrics["nonpositive_error_row_count"]:
        findings.append(f"{metrics['nonpositive_error_row_count']} RV uncertainty value(s) were <= 0 and excluded from the error range.")
    if metrics["missing_error_row_count"]:
        findings.append(f"{metrics['missing_error_row_count']} RV row(s) did not include an uncertainty column.")
    if metrics["rv_dataset_count"] == 0:
        findings.append("No Systemic RV datasets were discovered in the inspected input.")
    if metrics["sample_count_total"] == 0:
        findings.append("No valid RV samples were available for manual fitting.")
    blocking = metrics["rv_dataset_count"] == 0 or metrics["sample_count_total"] == 0
    status = "blocked" if blocking else "warning" if findings else "ok"
    return {"status": status, "findings": findings, "metrics": metrics}


def _public_target_from_args(args) -> str | None:
    for attribute in ("input_path", "session_manifest", "session_dir"):
        raw_value = getattr(args, attribute, None)
        if raw_value:
            return public_path(Path(raw_value).expanduser().resolve())
    return None


def _tool_name_from_args(args) -> str:
    command = getattr(args, "command", "inspect") or "inspect"
    return f"radial_velocity_workbench.{command}"


def _blocked_payload(args, message: str, *, status: str = "blocked") -> dict:
    return build_tool_payload(
        _tool_name_from_args(args),
        status=status,
        notes=[message],
        artifacts={
            "summary_json": getattr(args, "summary_json", None),
            "manifest_json": getattr(args, "manifest_json", None),
        },
        results={
            "input_path": _public_target_from_args(args),
            "blocked_reason": message,
        },
        qa={
            "status": status,
            "findings": [message],
            "metrics": {"blocking_count": 1 if status == "blocked" else 0},
        },
    )


def _emit_blocked(args, message: str, *, status: str = "blocked") -> int:
    payload = _blocked_payload(args, message, status=status)
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if getattr(args, "summary_json", None):
        try:
            _save_json(Path(args.summary_json), payload)
        except Exception as exc:
            print(f"Could not write summary JSON: {exc}", file=sys.stderr)
    return 2 if status == "blocked" else 1


def _default_session_manifest(args, prefill: dict) -> dict:
    system_name = args.system_name or prefill.get("system_name") or ""
    title = args.title or f"{_text_for(args.language)['title_prefix']} - {system_name or 'Systemic'}"
    planets = []
    for index in range(max(args.planet_count or 0, 0)):
        planet_number = index + 1
        planets.append(
            {
                "label": f"{_text_for(args.language)['planet_label_prefix']} {planet_number}",
                "period_days": None,
                "phased_rv_figure": f"figures/phased_planet{planet_number}.png",
                "notes": "",
            }
        )
    return {
        "schema_version": "1.0",
        "tool": "radial_velocity_workbench",
        "language": args.language,
        "title": title,
        "backend": args.backend,
        "system_name": system_name,
        "source_files": prefill.get("source_files", []),
        "star_metadata": prefill.get(
            "star_metadata",
            {
                "name": None,
                "mass_solar": None,
                "hd": None,
                "hip": None,
                "teff_k": None,
                "ra_deg": None,
                "dec_deg": None,
            },
        ),
        "rv_datasets": prefill.get("rv_datasets", []),
        "objective": "",
        "initial_search": {
            "raw_rv_figure": "figures/raw_rv.png",
            "initial_periodogram_figure": "figures/initial_periodogram.png",
            "dominant_periods_days": [],
            "false_alarm_probabilities": [],
            "notes": "",
        },
        "fitted_model": {
            "planet_count": len(planets) or None,
            "fitted_rv_figure": "figures/fitted_rv.png",
            "statistics_figure": "figures/statistics.png",
            "residual_periodogram_figure": "figures/residual_periodogram.png",
            "chi2_before": None,
            "chi2_after": None,
            "rms_before": None,
            "rms_after": None,
            "optimization_notes": "",
        },
        "dynamics": {
            "integration_horizon": "1000 years" if args.language == "en" else "1000 anos",
            "dynamics_figure": "figures/dynamics.png",
            "notes": "",
        },
        "conclusions": "",
        "caveats": "",
        "workflow_notes": prefill.get("workflow_notes", []),
        "report_readiness_notes": [],
        "validation": {},
        "planets": planets,
    }


def _build_session_readme(language: str) -> str:
    text = _text_for(language)
    if language == "en":
        body = [
            f"# {text['readme_title']}",
            "",
            "This bundle is meant for a manual-in-the-loop radial-velocity analysis, usually performed in Systemic Live or the local Systemic app.",
            "",
            "## Recommended workflow",
            "",
            "1. Inspect `.sys` and `.vels` inputs with `radial_velocity_workbench.py inspect`.",
            "2. Perform the fitting manually in Systemic Live or the local app.",
            "3. Export the key figures into `figures/`.",
            "4. Fill `session_manifest.json` with periods, FAP, chi2, RMS, and short notes.",
            "5. Run `validate-manifest` to check for missing figures or metrics before rendering.",
            "6. Run `build-report` to create Markdown, LaTeX, and optionally PDF outputs.",
            "7. Run `package` when you need a single handoff zip.",
            "",
            "## Expected figures",
            "",
            "- `raw_rv.png`",
            "- `initial_periodogram.png`",
            "- `fitted_rv.png`",
            "- `statistics.png`",
            "- `residual_periodogram.png`",
            "- `phased_planetN.png`",
            "- `dynamics.png`",
        ]
    else:
        body = [
            f"# {text['readme_title']}",
            "",
            "Este bundle esta pensado para un analisis de velocidad radial con humano en el loop, normalmente realizado en Systemic Live o en la app local de Systemic.",
            "",
            "## Flujo recomendado",
            "",
            "1. Inspecciona los `.sys` y `.vels` con `radial_velocity_workbench.py inspect`.",
            "2. Haz el ajuste manual en Systemic Live o en la app local.",
            "3. Exporta las figuras clave dentro de `figures/`.",
            "4. Rellena `session_manifest.json` con periodos, FAP, chi2, RMS y notas cortas.",
            "5. Ejecuta `validate-manifest` para revisar huecos antes de renderizar el informe.",
            "6. Ejecuta `build-report` para generar Markdown, LaTeX y opcionalmente PDF.",
            "7. Ejecuta `package` cuando quieras un zip final de entrega.",
            "",
            "## Figuras esperadas",
            "",
            "- `raw_rv.png`",
            "- `initial_periodogram.png`",
            "- `fitted_rv.png`",
            "- `statistics.png`",
            "- `residual_periodogram.png`",
            "- `phased_planetN.png`",
            "- `dynamics.png`",
            "",
            "## Mejores practicas",
            "",
            "- Usa `--planet-count` en `scaffold-session` si ya sabes cuantas curvas en fase vas a exportar.",
            "- Mantén valores como `chi2`, `RMS` y `FAP` en el manifiesto, no solo dentro de capturas.",
            "- Si algo sigue pendiente, dejalo explicito y luego valida con `validate-manifest`.",
        ]
    return "\n".join(body) + "\n"


def _build_session_notes(language: str) -> str:
    if language == "en":
        lines = [
            f"# {_text_for(language)['notes_title']}",
            "",
            "- Record which backend you used (`systemic-live`, `systemic-local`, or `generic-rv`).",
            "- Note which parameters were allowed to vary during optimization.",
            "- Record the periods and FAP values you considered relevant before and after fitting.",
            "- If a figure is missing, leave the manifest field empty rather than inventing a path.",
            "- If chi2 or RMS are unavailable, keep them as `null` and explain the reason in notes.",
            "- Run `validate-manifest` before `build-report` so the missing pieces are explicit.",
        ]
    else:
        lines = [
            f"# {_text_for(language)['notes_title']}",
            "",
            "- Anota el backend usado (`systemic-live`, `systemic-local` o `generic-rv`).",
            "- Apunta que parametros dejaste variar durante `Optimize fit`.",
            "- Registra los periodos y FAP que consideraste relevantes antes y despues del ajuste.",
            "- Si falta una figura, deja vacio el campo correspondiente del manifiesto en lugar de inventar una ruta.",
            "- Si no tienes chi2 o RMS, dejalos como `null` y explica el motivo en las notas.",
            "- Ejecuta `validate-manifest` antes de `build-report` para detectar huecos a tiempo.",
        ]
    return "\n".join(lines) + "\n"


def _relative_or_public(base_dir: Path, raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    candidate = _resolve_manifest_path(base_dir, raw_value)
    if candidate is None:
        return None
    try:
        return str(candidate.relative_to(base_dir))
    except ValueError:
        return public_path(candidate)


def _existing_figure_text(base_dir: Path, raw_value: str | None) -> tuple[str | None, bool]:
    if not raw_value:
        return None, False
    candidate = _resolve_manifest_path(base_dir, raw_value)
    if candidate and candidate.exists():
        try:
            return str(candidate.relative_to(base_dir)), True
        except ValueError:
            return str(candidate), True
    return raw_value, False


def _render_signal_lines(periods: list, faps: list, pending_text: str) -> list[str]:
    total = max(len(periods), len(faps))
    if total == 0:
        return [pending_text]
    lines = []
    for index in range(total):
        period = periods[index] if index < len(periods) else None
        fap = faps[index] if index < len(faps) else None
        period_text = _format_measurement(period) or pending_text
        fap_text = _format_measurement(fap, digits=6) or pending_text
        lines.append(f"- P = `{period_text}` d | FAP = `{fap_text}`")
    return lines


def _report_title(manifest: dict, text: dict) -> str:
    return manifest.get("title") or text["title_prefix"]


def _planet_label(planet: dict, index: int, text: dict) -> str:
    return planet.get("label") or f"{text['planet_label_prefix']} {index}"


def _normalize_horizon(value: str | None, language: str) -> str | None:
    if value in (None, ""):
        return value
    if language == "es":
        return str(value).replace("years", "anos").replace("year", "ano")
    return str(value)


def _markdown_figure(base_dir: Path, raw_value: str | None, caption: str, text: dict) -> list[str]:
    location, exists = _existing_figure_text(base_dir, raw_value)
    if exists and location:
        return [f"![{caption}]({location})", ""]
    return [f"- {text['no_figure']}", ""]


def _tex_escape(value: str) -> str:
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
    text = unicodedata.normalize("NFC", str(value))
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _latex_figure(base_dir: Path, raw_value: str | None, caption: str, text: dict) -> list[str]:
    location, exists = _existing_figure_text(base_dir, raw_value)
    if exists and location:
        return [
            r"\begin{figure}[h]",
            r"\centering",
            rf"\includegraphics[width=\linewidth]{{\detokenize{{{location}}}}}",
            rf"\caption{{{_tex_escape(caption)}}}",
            r"\end{figure}",
            "",
        ]
    return [r"\noindent " + _tex_escape(text["no_figure"]), ""]


def _render_markdown_report(manifest: dict, manifest_dir: Path, language: str) -> str:
    text = _text_for(language)
    initial = manifest.get("initial_search", {})
    fitted = manifest.get("fitted_model", {})
    planets = manifest.get("planets", [])
    dynamics = manifest.get("dynamics", {})
    lines = [
        f"# {_report_title(manifest, text)}",
        "",
        text["objective_heading"],
        "",
        manifest.get("objective") or text["pending"],
        "",
        text["data_heading"],
        "",
        f"- Backend: `{manifest.get('backend') or text['pending']}`",
        f"- {text['system_label']}: `{manifest.get('system_name') or text['pending']}`",
        f"- {text['source_files_label']}: `{len(manifest.get('source_files', []))}`",
        f"- {text['dataset_count_label']}: `{len(manifest.get('rv_datasets', []))}`",
        "",
    ]
    star_metadata = manifest.get("star_metadata", {})
    if any(value is not None and value != "" for value in star_metadata.values()):
        lines.extend(["### Metadata estelar" if language == "es" else "### Stellar metadata", ""])
        for key, value in star_metadata.items():
            if value not in (None, ""):
                lines.append(f"- `{key}`: `{_format_value(value)}`")
        lines.append("")
    if manifest.get("rv_datasets"):
        lines.extend(["### Datasets RV", ""])
        for dataset in manifest["rv_datasets"]:
            lines.append(
                f"- `{dataset.get('label') or text['pending']}` | {text['samples_label']} `{dataset.get('sample_count') if dataset.get('sample_count') is not None else text['pending']}` | {text['units_label']} `{dataset.get('value_units') or text['pending']}`"
            )
        lines.append("")
    lines.extend(
        [
            text["initial_heading"],
            "",
            initial.get("notes") or text["pending"],
            "",
        ]
    )
    lines.extend(_markdown_figure(manifest_dir, initial.get("raw_rv_figure"), text["raw_rv_caption"], text))
    lines.extend(
        [
            text["period_heading"],
            "",
            *(_render_signal_lines(initial.get("dominant_periods_days", []), initial.get("false_alarm_probabilities", []), text["pending"])),
            "",
        ]
    )
    lines.extend(_markdown_figure(manifest_dir, initial.get("initial_periodogram_figure"), text["initial_periodogram_caption"], text))
    lines.extend(
        [
            text["fit_heading"],
            "",
            f"- {text['planet_count_label']}: `{fitted.get('planet_count') if fitted.get('planet_count') is not None else text['pending']}`",
            f"- {text['chi2_label']}: `{_format_measurement(fitted.get('chi2_before')) or text['pending']}` -> `{_format_measurement(fitted.get('chi2_after')) or text['pending']}`",
            f"- {text['rms_label']}: `{_format_measurement(fitted.get('rms_before')) or text['pending']}` -> `{_format_measurement(fitted.get('rms_after')) or text['pending']}`",
            "",
            fitted.get("optimization_notes") or text["pending"],
            "",
        ]
    )
    lines.extend(_markdown_figure(manifest_dir, fitted.get("fitted_rv_figure"), text["fitted_rv_caption"], text))
    lines.extend(_markdown_figure(manifest_dir, fitted.get("statistics_figure"), text["statistics_caption"], text))
    lines.extend(_markdown_figure(manifest_dir, fitted.get("residual_periodogram_figure"), text["residual_periodogram_caption"], text))
    lines.extend([text["phased_heading"], ""])
    if planets:
        for index, planet in enumerate(planets, start=1):
            label = _planet_label(planet, index, text)
            lines.extend(
                [
                    f"### {label}",
                    "",
                    f"- {text['period_label']}: `{_format_measurement(planet.get('period_days')) or text['pending']}` d",
                    planet.get("notes") or text["pending"],
                    "",
                ]
            )
            lines.extend(_markdown_figure(manifest_dir, planet.get("phased_rv_figure"), f"{text['phased_caption_prefix']} - {label}", text))
    else:
        lines.extend([text["no_planets"], ""])
    lines.extend(
        [
            text["dynamics_heading"],
            "",
            f"- {text['integration_horizon_label']}: `{_normalize_horizon(dynamics.get('integration_horizon'), language) or text['pending']}`",
            dynamics.get("notes") or text["pending"],
            "",
        ]
    )
    lines.extend(_markdown_figure(manifest_dir, dynamics.get("dynamics_figure"), text["dynamics_caption"], text))
    lines.extend(
        [
            text["conclusions_heading"],
            "",
            manifest.get("conclusions") or text["pending"],
            "",
            text["caveats_subheading"],
            "",
            manifest.get("caveats") or text["pending"],
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _render_latex_report(manifest: dict, manifest_dir: Path, language: str) -> str:
    text = _text_for(language)
    initial = manifest.get("initial_search", {})
    fitted = manifest.get("fitted_model", {})
    planets = manifest.get("planets", [])
    dynamics = manifest.get("dynamics", {})
    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage{hyperref}",
        rf"\title{{{_tex_escape(_report_title(manifest, text))}}}",
        r"\author{Scientific Data Analysis Skill}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section{Objective}" if language == "en" else r"\section{Objetivo}",
        _tex_escape(manifest.get("objective") or text["pending"]),
        "",
        r"\section{Data and backend used}" if language == "en" else r"\section{Datos y backend usado}",
        r"\begin{itemize}",
        rf"\item Backend: \texttt{{{_tex_escape(manifest.get('backend') or text['pending'])}}}",
        rf"\item {_tex_escape(text['system_label'])}: \texttt{{{_tex_escape(manifest.get('system_name') or text['pending'])}}}",
        rf"\item {_tex_escape(text['source_files_label'])}: \texttt{{{len(manifest.get('source_files', []))}}}",
        rf"\item {_tex_escape(text['dataset_count_label'])}: \texttt{{{len(manifest.get('rv_datasets', []))}}}",
        r"\end{itemize}",
        "",
    ]
    star_metadata = manifest.get("star_metadata", {})
    if any(value is not None and value != "" for value in star_metadata.values()):
        lines.extend([r"\subsection{Stellar metadata}" if language == "en" else r"\subsection{Metadatos estelares}", r"\begin{itemize}"])
        for key, value in star_metadata.items():
            if value not in (None, ""):
                lines.append(rf"\item \texttt{{{_tex_escape(key)}}}: {_tex_escape(_format_value(value))}")
        lines.extend([r"\end{itemize}", ""])
    if manifest.get("rv_datasets"):
        lines.extend(
            [
                r"\subsection{RV datasets}",
                r"\begin{longtable}{p{0.26\linewidth}p{0.18\linewidth}p{0.16\linewidth}p{0.22\linewidth}}",
                r"\toprule Label & Samples & Units & Span (days) \\ \midrule",
            ]
        )
        for dataset in manifest["rv_datasets"]:
            lines.append(
                rf"{_tex_escape(dataset.get('label') or text['pending'])} & {_tex_escape(str(dataset.get('sample_count') if dataset.get('sample_count') is not None else text['pending']))} & {_tex_escape(dataset.get('value_units') or text['pending'])} & {_tex_escape(_format_value(dataset.get('jd_span_days')) or text['pending'])} \\"
            )
        lines.extend([r"\bottomrule", r"\end{longtable}", ""])
    lines.extend(
        [
            r"\section{Initial radial-velocity inspection}" if language == "en" else r"\section{Inspeccion inicial de velocidad radial}",
            _tex_escape(initial.get("notes") or text["pending"]),
            "",
        ]
    )
    lines.extend(_latex_figure(manifest_dir, initial.get("raw_rv_figure"), text["raw_rv_caption"], text))
    lines.extend([r"\section{Period search and FAP}" if language == "en" else r"\section{Busqueda de periodos y FAP}", r"\begin{itemize}"])
    for item in _render_signal_lines(initial.get("dominant_periods_days", []), initial.get("false_alarm_probabilities", []), text["pending"]):
        lines.append(rf"\item {_tex_escape(item.lstrip('- ').strip())}")
    lines.extend([r"\end{itemize}", ""])
    lines.extend(_latex_figure(manifest_dir, initial.get("initial_periodogram_figure"), text["initial_periodogram_caption"], text))
    lines.extend(
        [
            r"\section{Fitted model}" if language == "en" else r"\section{Modelo ajustado}",
            r"\begin{itemize}",
            rf"\item {_tex_escape(text['planet_count_label'])}: \texttt{{{_tex_escape(str(fitted.get('planet_count') if fitted.get('planet_count') is not None else text['pending']))}}}",
            rf"\item {_tex_escape(text['chi2_label'])}: \texttt{{{_tex_escape(_format_measurement(fitted.get('chi2_before')) or text['pending'])}}} $\rightarrow$ \texttt{{{_tex_escape(_format_measurement(fitted.get('chi2_after')) or text['pending'])}}}",
            rf"\item {_tex_escape(text['rms_label'])}: \texttt{{{_tex_escape(_format_measurement(fitted.get('rms_before')) or text['pending'])}}} $\rightarrow$ \texttt{{{_tex_escape(_format_measurement(fitted.get('rms_after')) or text['pending'])}}}",
            r"\end{itemize}",
            _tex_escape(fitted.get("optimization_notes") or text["pending"]),
            "",
        ]
    )
    lines.extend(_latex_figure(manifest_dir, fitted.get("fitted_rv_figure"), text["fitted_rv_caption"], text))
    lines.extend(_latex_figure(manifest_dir, fitted.get("statistics_figure"), text["statistics_caption"], text))
    lines.extend(_latex_figure(manifest_dir, fitted.get("residual_periodogram_figure"), text["residual_periodogram_caption"], text))
    lines.extend([r"\section{Phased radial velocity by planet}" if language == "en" else r"\section{Velocidad radial en fase por planeta}", ""])
    if planets:
        for index, planet in enumerate(planets, start=1):
            label = _planet_label(planet, index, text)
            lines.extend(
                [
                    rf"\subsection{{{_tex_escape(label)}}}",
                    rf"\noindent {_tex_escape(text['period_label'])}: \texttt{{{_tex_escape(_format_measurement(planet.get('period_days')) or text['pending'])}}} d\\",
                    _tex_escape(planet.get("notes") or text["pending"]),
                    "",
                ]
            )
            lines.extend(_latex_figure(manifest_dir, planet.get("phased_rv_figure"), f"{text['phased_caption_prefix']} - {label}", text))
    else:
        lines.extend([_tex_escape(text["no_planets"]), ""])
    lines.extend(
        [
            r"\section{Dynamical behavior}" if language == "en" else r"\section{Comportamiento dinamico}",
            rf"\noindent {_tex_escape(text['integration_horizon_label'])}: \texttt{{{_tex_escape(_normalize_horizon(dynamics.get('integration_horizon'), language) or text['pending'])}}}\\",
            _tex_escape(dynamics.get("notes") or text["pending"]),
            "",
        ]
    )
    lines.extend(_latex_figure(manifest_dir, dynamics.get("dynamics_figure"), text["dynamics_caption"], text))
    lines.extend(
        [
            r"\section{Conclusions and caveats}" if language == "en" else r"\section{Conclusiones y limitaciones}",
            _tex_escape(manifest.get("conclusions") or text["pending"]),
            "",
            r"\subsection{Caveats}" if language == "en" else r"\subsection{Limitaciones}",
            _tex_escape(manifest.get("caveats") or text["pending"]),
            "",
            r"\end{document}",
        ]
    )
    return "\n".join(lines) + "\n"


def _figure_is_missing(base_dir: Path, raw_value) -> bool:
    if _is_blank(raw_value):
        return True
    candidate = _resolve_manifest_path(base_dir, raw_value)
    return candidate is None or not candidate.exists() or not candidate.is_file()


def _is_nonfinite_number(value) -> bool:
    return isinstance(value, float) and not math.isfinite(value)


def _collect_nonfinite_numbers(value, path: str = "$") -> list[str]:
    findings = []
    if _is_nonfinite_number(value):
        return [path]
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path != "$" else str(key)
            findings.extend(_collect_nonfinite_numbers(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_collect_nonfinite_numbers(child, f"{path}[{index}]"))
    return findings


def _collect_dataset_warnings(manifest: dict) -> list[str]:
    warnings = []
    rv_datasets = manifest.get("rv_datasets", [])
    if not isinstance(rv_datasets, list):
        return ["rv_datasets.not_list"]
    for index, dataset in enumerate(rv_datasets):
        if not isinstance(dataset, dict):
            warnings.append(f"rv_datasets[{index}].not_object")
            continue
        if _is_blank(dataset.get("source")):
            warnings.append(f"rv_datasets[{index}].source")
        if _is_blank(dataset.get("value_units")):
            warnings.append(f"rv_datasets[{index}].value_units")
        sample_count = dataset.get("sample_count")
        if sample_count is None:
            warnings.append(f"rv_datasets[{index}].sample_count")
        elif isinstance(sample_count, (int, float)) and sample_count <= 0:
            warnings.append(f"rv_datasets[{index}].sample_count_nonpositive")
    return warnings


def _collect_planet_warnings(manifest: dict) -> list[str]:
    warnings = []
    planets = manifest.get("planets", [])
    if not isinstance(planets, list):
        return ["planets.not_list"]
    for index, planet in enumerate(planets):
        if not isinstance(planet, dict):
            warnings.append(f"planets[{index}].not_object")
            continue
        if planet.get("period_days") is None or _is_nonfinite_number(planet.get("period_days")):
            warnings.append(f"planets[{index}].period_days")
    return warnings


def _is_finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _collect_domain_errors(manifest: dict, base_dir: Path) -> list[str]:
    errors = []
    initial = manifest.get("initial_search")
    initial = initial if isinstance(initial, dict) else {}
    periods = initial.get("dominant_periods_days", [])
    faps = initial.get("false_alarm_probabilities", [])
    if not isinstance(periods, list):
        errors.append("initial_search.dominant_periods_days.not_list")
        periods = []
    if not isinstance(faps, list):
        errors.append("initial_search.false_alarm_probabilities.not_list")
        faps = []
    for index, value in enumerate(periods):
        if not _is_finite_number(value) or float(value) <= 0:
            errors.append(f"initial_search.dominant_periods_days[{index}].not_positive_finite")
    for index, value in enumerate(faps):
        if not _is_finite_number(value) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"initial_search.false_alarm_probabilities[{index}].outside_0_1")
    if faps and len(faps) != len(periods):
        errors.append("initial_search.period_fap_count_mismatch")

    planets = manifest.get("planets")
    planets = planets if isinstance(planets, list) else []
    for index, planet in enumerate(planets):
        if not isinstance(planet, dict):
            continue
        period = planet.get("period_days")
        if period is not None and (not _is_finite_number(period) or float(period) <= 0):
            errors.append(f"planets[{index}].period_days.not_positive_finite")

    fitted = manifest.get("fitted_model")
    fitted = fitted if isinstance(fitted, dict) else {}
    for key in ("chi2_before", "chi2_after", "rms_before", "rms_after"):
        value = fitted.get(key)
        if value is not None and (not _is_finite_number(value) or float(value) < 0):
            errors.append(f"fitted_model.{key}.negative_or_nonfinite")

    for index, dataset in enumerate(manifest.get("rv_datasets", [])):
        if not isinstance(dataset, dict) or _is_blank(dataset.get("source")):
            continue
        source = str(dataset["source"]).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*://", source, flags=re.IGNORECASE):
            continue
        resolved = _resolve_manifest_path(base_dir, source)
        if resolved is None or not resolved.is_file():
            errors.append(f"rv_datasets[{index}].source.not_existing_file")

    star = manifest.get("star_metadata")
    star = star if isinstance(star, dict) else {}
    for key in ("mass_solar", "teff_k"):
        value = star.get(key)
        if value is not None and value != "" and (not _is_finite_number(value) or float(value) <= 0):
            errors.append(f"star_metadata.{key}.not_positive_finite")
    ra = star.get("ra_deg")
    if ra not in (None, "") and (not _is_finite_number(ra) or not 0.0 <= float(ra) < 360.0):
        errors.append("star_metadata.ra_deg.outside_0_360")
    dec = star.get("dec_deg")
    if dec not in (None, "") and (not _is_finite_number(dec) or not -90.0 <= float(dec) <= 90.0):
        errors.append("star_metadata.dec_deg.outside_minus90_90")
    return list(dict.fromkeys(errors))


def _collect_missing_items(manifest: dict, base_dir: Path) -> dict:
    initial = manifest.get("initial_search", {})
    fitted = manifest.get("fitted_model", {})
    dynamics = manifest.get("dynamics", {})
    initial = initial if isinstance(initial, dict) else {}
    fitted = fitted if isinstance(fitted, dict) else {}
    dynamics = dynamics if isinstance(dynamics, dict) else {}
    missing_figures = []
    for label, raw_value in [
        ("initial_search.raw_rv_figure", initial.get("raw_rv_figure")),
        ("initial_search.initial_periodogram_figure", initial.get("initial_periodogram_figure")),
        ("fitted_model.fitted_rv_figure", fitted.get("fitted_rv_figure")),
        ("fitted_model.statistics_figure", fitted.get("statistics_figure")),
        ("fitted_model.residual_periodogram_figure", fitted.get("residual_periodogram_figure")),
        ("dynamics.dynamics_figure", dynamics.get("dynamics_figure")),
    ]:
        if _figure_is_missing(base_dir, raw_value):
            missing_figures.append(label)
    for index, planet in enumerate(manifest.get("planets", []), start=1):
        if not isinstance(planet, dict):
            continue
        if _figure_is_missing(base_dir, planet.get("phased_rv_figure")):
            missing_figures.append(f"planets[{index - 1}].phased_rv_figure")
    missing_metrics = []
    for key in ["chi2_before", "chi2_after", "rms_before", "rms_after"]:
        if fitted.get(key) is None or _is_nonfinite_number(fitted.get(key)):
            missing_metrics.append(f"fitted_model.{key}")
    return {"missing_figures": missing_figures, "missing_metrics": missing_metrics}


def _validate_manifest_payload(manifest: dict, base_dir: Path, language: str) -> dict:
    text = _text_for(language)
    completeness = _collect_missing_items(manifest, base_dir)
    fitted_model = manifest.get("fitted_model", {})
    fitted_model = fitted_model if isinstance(fitted_model, dict) else {}
    warnings = []
    if not manifest.get("system_name"):
        warnings.append("system_name")
    if not manifest.get("objective"):
        warnings.append("objective")
    if not manifest.get("rv_datasets"):
        warnings.append("rv_datasets")
    expected_planets = fitted_model.get("planet_count")
    if expected_planets is None:
        warnings.append("fitted_model.planet_count")
    elif not isinstance(expected_planets, int) or expected_planets < 0:
        warnings.append("fitted_model.planet_count_invalid")
    if not manifest.get("conclusions"):
        warnings.append("conclusions")
    planets = manifest.get("planets", [])
    planets = planets if isinstance(planets, list) else []
    if isinstance(expected_planets, int) and expected_planets >= 0 and expected_planets != len(planets):
        warnings.append("planets.count_mismatch")
    warnings.extend(_collect_dataset_warnings(manifest))
    warnings.extend(_collect_planet_warnings(manifest))
    domain_errors = _collect_domain_errors(manifest, base_dir)
    nonfinite_numeric_values = _collect_nonfinite_numbers(manifest)
    if nonfinite_numeric_values:
        warnings.append("nonfinite_numeric_values")
    findings = list(
        dict.fromkeys(
            domain_errors
            + warnings
            + completeness["missing_figures"]
            + completeness["missing_metrics"]
            + nonfinite_numeric_values
        )
    )
    status = "fail" if domain_errors else ("ok" if not findings else "warning")
    message = text["validation_ok"] if status == "ok" else text["validation_warnings"]
    return {
        "tool": "radial_velocity_workbench",
        "command": "validate-manifest",
        "status": status,
        "message": message,
        "language": language,
        "system_name": manifest.get("system_name"),
        "planet_count": expected_planets,
        "warnings": list(dict.fromkeys(warnings)),
        "domain_errors": domain_errors,
        "nonfinite_numeric_values": nonfinite_numeric_values,
        "findings": findings,
        "completeness": completeness,
    }


def do_inspect(args):
    inspection = inspect_systemic_input(args.input_path)
    inspection["inspected_input"] = public_path(Path(args.input_path).resolve())
    qa = _inspect_qa(inspection)
    legacy_payload = dict(inspection)
    legacy_payload["tool"] = "radial_velocity_workbench"
    legacy_payload["command"] = "inspect"
    note = "Use this inspector before starting a manual Systemic session so dataset counts, spans, and metadata are explicit."
    payload = build_tool_payload(
        "radial_velocity_workbench.inspect",
        status=qa["status"],
        notes=[note],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results=inspection,
        qa=qa,
        legacy=legacy_payload,
    )
    if args.summary_json:
        _save_json(Path(args.summary_json), payload)
        print(f"Saved summary: {public_path(args.summary_json)}")
    else:
        print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[args.input_path],
            outputs=[args.summary_json] if args.summary_json else [],
            parameters={"command": "inspect"},
            command="radial_velocity_workbench.py inspect",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 2 if qa["status"] == "blocked" else 0


def do_scaffold_session(args):
    configure_runtime("radial_velocity_workbench")
    output_dir = Path(args.output_dir)
    manifest_path = output_dir / "session_manifest.json"
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise SystemExit("Output directory is not empty. Use --overwrite if you want to reuse it.")
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    prefill = _prefill_from_inputs(args.inputs)
    manifest = _default_session_manifest(args, prefill)
    manifest_path.write_text(json.dumps(sanitize_payload(manifest), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    notes_path = output_dir / "notes.md"
    readme_path = output_dir / "README.md"
    notes_path.write_text(_build_session_notes(args.language), encoding="utf-8")
    readme_path.write_text(_build_session_readme(args.language), encoding="utf-8")
    outputs = [manifest_path, notes_path, readme_path, figures_dir]
    print(f"Saved session manifest: {public_path(manifest_path)}")
    print(f"Saved notes: {public_path(notes_path)}")
    print(f"Saved README: {public_path(readme_path)}")
    print(f"Created figures directory: {public_path(figures_dir)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=args.inputs,
            outputs=outputs,
            parameters={"backend": args.backend, "language": args.language, "planet_count": args.planet_count},
            command="radial_velocity_workbench.py scaffold-session",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


def do_validate_manifest(args):
    manifest_path = Path(args.session_manifest).resolve()
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Session manifest not found: {manifest_path}") from None
    except OSError as exc:
        raise SystemExit(f"Could not read session manifest: {exc}") from None
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Session manifest is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.") from None
    if not isinstance(manifest, dict):
        raise SystemExit("Session manifest must be a JSON object.")
    language = args.language or manifest.get("language") or "es"
    validation = sanitize_payload(_validate_manifest_payload(manifest, manifest_path.parent, language))
    summary = build_tool_payload(
        "radial_velocity_workbench.validate-manifest",
        status=validation["status"],
        notes=[validation["message"]],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results=validation,
        qa={
            "status": validation["status"],
            "findings": validation["findings"],
            "metrics": {
                "warning_count": len(validation["warnings"]),
                "missing_figure_count": len(validation["completeness"]["missing_figures"]),
                "missing_metric_count": len(validation["completeness"]["missing_metrics"]),
                "nonfinite_numeric_count": len(validation["nonfinite_numeric_values"]),
                "domain_error_count": len(validation["domain_errors"]),
            },
        },
        legacy=validation,
    )
    if args.summary_json:
        _save_json(Path(args.summary_json), summary)
        print(f"Saved validation summary: {public_path(args.summary_json)}")
    else:
        print(json.dumps(sanitize_payload(summary), indent=2, ensure_ascii=True))
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[manifest_path],
            outputs=[args.summary_json] if args.summary_json else [],
            parameters={"language": language},
            command="radial_velocity_workbench.py validate-manifest",
            extra={"validation_summary": summary},
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 1 if validation["status"] == "fail" else 0


def do_build_report(args):
    configure_runtime("radial_velocity_workbench")
    manifest_path = Path(args.session_manifest).resolve()
    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    language = args.language or manifest.get("language") or "es"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else manifest_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    report_md = output_dir / "rv_analysis_report.md"
    report_tex = output_dir / "rv_analysis_report.tex"
    report_pdf = output_dir / "rv_analysis_report.pdf"
    summary_json = output_dir / "summary.json"

    md_text = _render_markdown_report(manifest, manifest_dir, language)
    tex_text = _render_latex_report(manifest, manifest_dir, language)
    report_md.write_text(md_text, encoding="utf-8")
    report_tex.write_text(tex_text, encoding="utf-8")

    latex_result = compile_latex_project(report_tex)
    validation_summary = _validate_manifest_payload(manifest, manifest_dir, language)
    completeness = validation_summary["completeness"]
    outputs = [report_md, report_tex, summary_json]
    if latex_result.get("success") and report_pdf.exists():
        outputs.append(report_pdf)
    summary = sanitize_payload(
        {
            "tool": "radial_velocity_workbench",
            "command": "build-report",
            "session_manifest": public_path(manifest_path),
            "output_dir": public_path(output_dir),
            "system_name": manifest.get("system_name"),
            "backend": manifest.get("backend"),
            "language": language,
            "planet_count": manifest.get("fitted_model", {}).get("planet_count"),
            "rv_dataset_count": len(manifest.get("rv_datasets", [])),
            "completeness": completeness,
            "validation": validation_summary,
            "latex": latex_result,
            "outputs": [public_path(item) for item in outputs],
        }
    )
    _save_json(summary_json, summary)
    print(f"Saved markdown report: {public_path(report_md)}")
    print(f"Saved LaTeX report: {public_path(report_tex)}")
    print(f"Saved summary: {public_path(summary_json)}")
    if latex_result.get("success") and report_pdf.exists():
        print(f"Saved PDF report: {public_path(report_pdf)}")
    elif latex_result.get("attempted"):
        print("PDF compilation was attempted but did not succeed.")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[manifest_path],
            outputs=outputs,
            parameters={"language": language},
            command="radial_velocity_workbench.py build-report",
            extra={"build_summary": summary},
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


def _package_inputs(session_dir: Path) -> list[Path]:
    candidates = [
        session_dir / "session_manifest.json",
        session_dir / "notes.md",
        session_dir / "README.md",
        session_dir / "rv_analysis_report.md",
        session_dir / "rv_analysis_report.tex",
        session_dir / "rv_analysis_report.pdf",
        session_dir / "summary.json",
        session_dir / "figures",
    ]
    return [item for item in candidates if item.exists()]


def do_package(args):
    session_dir = Path(args.session_dir).resolve()
    if not session_dir.exists():
        raise SystemExit(f"Session directory not found: {session_dir}")
    output_zip = Path(args.output_zip).resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "session_manifest.json"
    manifest_language = "es"
    manifest_title = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_language = manifest.get("language") or "es"
            manifest_title = manifest.get("title")
        except Exception:
            manifest = None
    else:
        manifest = None
    text = _text_for(manifest_language)
    title = args.title or manifest_title or text["package_title"]
    readme = output_zip.with_suffix(".README.md")
    index_json = output_zip.with_suffix(".index.json")
    package_inputs = _package_inputs(session_dir)
    readme_lines = [f"# {title}", "", text["included_items_heading"], ""]
    for item in package_inputs:
        readme_lines.append(f"- `{public_path(item)}`")
    readme_lines.extend(["", text["package_notes_heading"], "", f"- {text['package_note_1']}", f"- {text['package_note_2']}"])
    readme.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    index_payload = {
        "title": title,
        "session_dir": public_path(session_dir),
        "included": [public_path(item) for item in package_inputs],
        "language": manifest_language,
        "environment": environment_summary(),
    }
    index_json.write_text(json.dumps(sanitize_payload(index_payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(readme, arcname=readme.name)
        archive.write(index_json, arcname=index_json.name)
        for item in package_inputs:
            if item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        archive.write(child, arcname=str(child.relative_to(session_dir.parent)))
            else:
                archive.write(item, arcname=str(item.relative_to(session_dir.parent)))
    outputs = [output_zip, readme, index_json]
    print(f"Saved package: {public_path(output_zip)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[session_dir],
            outputs=outputs,
            parameters={"title": title},
            command="radial_velocity_workbench.py package",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


def main():
    args = parse_args()
    try:
        if args.command == "inspect":
            return do_inspect(args)
        elif args.command == "scaffold-session":
            do_scaffold_session(args)
        elif args.command == "validate-manifest":
            return do_validate_manifest(args)
        elif args.command == "build-report":
            do_build_report(args)
        else:
            do_package(args)
    except SystemExit as exc:
        if args.command in {"inspect", "validate-manifest"}:
            return _emit_blocked(args, str(exc) or "Radial-velocity inspection was blocked.")
        raise
    except Exception as exc:
        if args.command in {"inspect", "validate-manifest"}:
            return _emit_blocked(args, str(exc) or "Radial-velocity inspection was blocked.")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
