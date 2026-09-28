#!/usr/bin/env python3
"""Analyze legacy fxcor outputs into RV and v sin i coursework summaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.legacy_spectroscopy_common import (
    compute_vhelio_from_vrel,
    csv_write,
    heliocentric_correction_kms,
    load_vsini_calibration,
    parse_float,
    read_header_with_warnings,
    weighted_mean,
)
from _internal.provenance_utils import public_path, standard_qa_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


TOOL_NAME = "legacy_rv_coursework_workbench.analyze"


class InputValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="Analyze parsed fxcor rows and derive RV/v sin i summaries.")
    analyze.add_argument("inputs", nargs="+", help="Parsed CSVs or fxcor summary JSONs.")
    analyze.add_argument("--output-dir", required=True)
    analyze.add_argument("--fits-root", help="Optional fits_p1 directory. If omitted, try to infer it from the workspace config.")
    analyze.add_argument("--calibration-csv", help="Optional FWHM-v sin i calibration CSV.")
    analyze.add_argument("--summary-json")
    analyze.add_argument("--manifest-json")
    return parser.parse_args()


def load_rows_from_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fail_validation(issues: list[str]) -> None:
    if issues:
        raise InputValidationError(issues)


def output_file_issue(path: str | Path | None, label: str) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.exists() and candidate.is_dir():
        return f"{label} apunta a un directorio, no a un archivo: {public_path(candidate)}"
    probe = candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"{label} no puede escribirse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def output_dir_issue(output_dir: Path) -> str | None:
    if output_dir.exists() and not output_dir.is_dir():
        return f"--output-dir existe pero no es un directorio: {public_path(output_dir)}"
    probe = output_dir.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"--output-dir no puede crearse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def blocked_payload(args, issues: list[str]) -> dict:
    return standard_tool_payload(
        TOOL_NAME,
        status="blocked",
        notes=[
            "Validacion de entrada fallida antes de calcular RV/v sin i.",
            "La ruta legacy se bloquea para evitar resultados con cabeceras, columnas, calibraciones o salidas incompletas.",
        ],
        artifacts={
            "summary_json": args.summary_json,
            "output_dir": args.output_dir,
        },
        results={
            "input_validation_issues": issues,
            "input_count": len(args.inputs or []),
            "fits_root": args.fits_root,
            "calibration_csv": args.calibration_csv,
        },
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"issue_count": len(issues)}),
    )


def emit_analyze_payload(
    payload: dict,
    args,
    *,
    manifest_inputs: list[Path] | None = None,
    manifest_outputs: list[Path] | None = None,
    manifest_parameters: dict | None = None,
    manifest_notes: list[str] | None = None,
) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        try:
            summary_path = Path(args.summary_json)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            write_manifest(
                args.manifest_json,
                inputs=manifest_inputs or [],
                outputs=manifest_outputs or [],
                parameters=manifest_parameters or {"tool": TOOL_NAME},
                command=" ".join(sys.argv),
                notes=manifest_notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def validate_raw_rows(raw_rows: list[dict], fits_root: Path) -> None:
    issues = []
    required_columns = ["aperture", "image_name", "template_image", "case_id", "mode"]
    for index, row in enumerate(raw_rows, start=1):
        missing = [name for name in required_columns if name not in row]
        if missing:
            issues.append(f"Fila {index}: faltan columnas requeridas: {', '.join(missing)}")
            continue
        try:
            int(float(str(row.get("aperture", "")).strip()))
        except ValueError:
            issues.append(f"Fila {index}: aperture no es numerico: {row.get('aperture')!r}")
    fail_validation(issues)

    checked: set[str] = set()
    for row in raw_rows:
        for field in ["image_name", "template_image"]:
            image_name = (row.get(field) or "").strip()
            if not image_name or image_name in checked:
                continue
            checked.add(image_name)
            path = fits_root / image_name
            if not path.exists():
                issues.append(f"No existe el FITS requerido por {field}: {path}")
                continue
            try:
                header, _, _ = read_header_with_warnings(path)
            except Exception as exc:
                issues.append(f"No se pudo leer header FITS de {path}: {exc}")
                continue
            missing_header = [key for key in ["RA", "DEC", "OBSERVAT"] if header.get(key) in (None, "")]
            if header.get("DATE-OBS") in (None, "") and header.get("MJD-OBS") in (None, ""):
                missing_header.append("DATE-OBS or MJD-OBS")
            if missing_header:
                issues.append(f"{path.name}: faltan metadatos heliocentricos minimos: {', '.join(missing_header)}")
    fail_validation(issues)


def validate_calibration_csv(path: Path | None) -> None:
    if path is None:
        return
    if not path.exists():
        raise InputValidationError([f"No existe la calibracion FWHM-v sin i indicada: {public_path(path)}"])
    if not path.is_file():
        raise InputValidationError([f"La calibracion FWHM-v sin i indicada no es un archivo: {public_path(path)}"])
    numeric_rows = 0
    issues = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, row in enumerate(csv.reader(handle), start=1):
                if len(row) < 2:
                    continue
                try:
                    float(row[0])
                    float(row[1])
                    numeric_rows += 1
                except ValueError:
                    if numeric_rows == 0:
                        continue
                    issues.append(f"Linea {line_number}: calibracion no numerica despues de filas validas: {row}")
    except OSError as exc:
        raise InputValidationError([f"No se pudo leer la calibracion FWHM-v sin i {public_path(path)}: {exc}"]) from exc
    if numeric_rows < 2:
        issues.append("La calibracion necesita al menos dos filas numericas FWHM,vsini.")
    fail_validation(issues)


def infer_workspace_config(path: Path) -> dict | None:
    for candidate in [path.parent / "fxcor_cases.json", path.parent.parent / "fxcor_cases.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise InputValidationError([f"No se pudo leer la configuracion inferida {public_path(candidate)}: {exc}"]) from exc
    return None


def expand_inputs(inputs: list[str]) -> tuple[list[Path], dict | None]:
    csv_paths = []
    inferred_config = None
    issues = []
    for raw in inputs:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            issues.append(f"No existe el input indicado: {public_path(path)}")
            continue
        if path.is_dir():
            issues.append(f"El input indicado es un directorio, no un CSV/JSON parseado: {public_path(path)}")
            continue
        if path.suffix.lower() == ".csv":
            csv_paths.append(path)
            if inferred_config is None:
                inferred_config = infer_workspace_config(path)
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f"No se pudo leer el resumen JSON {public_path(path)}: {exc}")
                continue
            parsed_count = 0
            for case_run in payload.get("results", {}).get("case_runs", []):
                csv_path = case_run.get("outcome", {}).get("parsed_csv")
                if csv_path:
                    parsed_count += 1
                    parsed_path = Path(csv_path).expanduser().resolve()
                    if parsed_path.exists() and parsed_path.is_file():
                        csv_paths.append(parsed_path)
                    else:
                        issues.append(f"El resumen JSON referencia un parsed_csv inexistente: {public_path(parsed_path)}")
            if parsed_count == 0:
                issues.append(f"El resumen JSON no contiene resultados case_runs con parsed_csv: {public_path(path)}")
            if inferred_config is None:
                inferred_config = infer_workspace_config(path)
            continue
        issues.append(f"Formato de input no soportado para analyze: {public_path(path)}")
    fail_validation(issues)
    deduped = []
    seen = set()
    for item in csv_paths:
        if str(item) not in seen:
            deduped.append(item)
            seen.add(str(item))
    return deduped, inferred_config


def robust_select(rows: list[dict], *, tdr_min: float, verr_max: float | None = None) -> list[dict]:
    selected = []
    for row in rows:
        if row.get("vrel_kms") is None or row.get("verr_kms") is None or row.get("tdr") is None:
            continue
        if row["tdr"] < tdr_min:
            continue
        if verr_max is not None and row["verr_kms"] > verr_max:
            continue
        selected.append(row)
    if len(selected) < 3:
        return selected
    import numpy as np

    values = np.array([item["vrel_kms"] for item in selected], dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    tolerance = max(12.0, 3.0 * 1.4826 * mad)
    return [item for item in selected if abs(item["vrel_kms"] - median) <= tolerance]


def thresholds_for_case(case_id: str, mode: str) -> tuple[float, float | None]:
    if mode == "single_rv":
        return 5.0, None
    if case_id.endswith("compB_rv"):
        return 3.0, 25.0
    if mode == "sb2_rv":
        return 3.0, 20.0
    return 3.0, None


def build_case_diagnostics(case_id: str, mode: str, case_rows: list[dict], selected: list[dict]) -> dict:
    usable_rows = [
        row
        for row in case_rows
        if row.get("vhelio_calc_kms") is not None and row.get("verr_kms") is not None and row.get("tdr") is not None
    ]
    selected_values = [row["vhelio_calc_kms"] for row in selected if row.get("vhelio_calc_kms") is not None]
    rejected_count = max(0, len(usable_rows) - len(selected_values))
    rejection_fraction = rejected_count / len(usable_rows) if usable_rows else None
    scatter = None
    if len(selected_values) >= 2:
        mean_value = sum(selected_values) / len(selected_values)
        scatter = math.sqrt(sum((value - mean_value) ** 2 for value in selected_values) / (len(selected_values) - 1))

    flags = []
    if mode == "sb2_rv":
        flags.append("sb2_manual_ccf_review_required")
    if len(selected_values) < 5:
        flags.append("few_orders_selected")
    if rejection_fraction is not None and rejection_fraction >= 0.4:
        flags.append("high_order_rejection")
    if scatter is not None and scatter >= 5.0:
        flags.append("large_order_scatter")

    return {
        "case_id": case_id,
        "mode": mode,
        "usable_orders_before_filter": len(usable_rows),
        "selected_orders": len(selected_values),
        "rejected_orders": rejected_count,
        "rejection_fraction": rejection_fraction,
        "selected_rv_scatter_kms": scatter,
        "quality_flags": flags,
    }


def rv_adoption_labels(mode: str, diagnostics: dict) -> tuple[str, str, str]:
    flags = set(diagnostics.get("quality_flags") or [])
    if mode == "sb2_rv":
        return "measured", "not_adopted", "not_robust"
    if {"high_order_rejection", "large_order_scatter"} & flags:
        return "measured", "measured_not_adopted", "not_robust"
    if "few_orders_selected" in flags:
        return "measured", "adopted_with_caution", "limited"
    return "measured", "adopted", "robust"


def vsini_quality_flags(row: dict, calibration_x) -> list[str]:
    flags = ["first_pass_fwhm_proxy", "manual_ccf_profile_review_required"]
    fwhm_pix = row.get("fwhm_pix")
    tdr = row.get("tdr")
    if fwhm_pix is None:
        flags.append("missing_fwhm")
    elif fwhm_pix < float(calibration_x.min()) or fwhm_pix > float(calibration_x.max()):
        flags.append("calibration_range_warning")
    if tdr is None or tdr < 8.0:
        flags.append("low_tdr")
    if row.get("case_id", "").startswith("pwand"):
        flags.append("compare_with_literature_or_istarmod")
    return flags


def vsini_adoption_labels(flags: list[str]) -> tuple[str, str, str]:
    # This route is deliberately conservative: FWHM-based v sin i is a first pass.
    if "calibration_range_warning" in flags or "low_tdr" in flags or "missing_fwhm" in flags:
        return "measured", "not_adopted", "not_robust"
    return "measured", "measured_not_adopted", "not_robust"


def normalize_rows(raw_rows: list[dict], fits_root: Path) -> list[dict]:
    h_obj_cache = {}
    h_tpl_cache = {}
    rows = []
    for raw in raw_rows:
        record = {key: value for key, value in raw.items()}
        for field in [
            "template_vhelio_kms",
            "shift_pix",
            "height",
            "fwhm_kms",
            "fwhm_pix",
            "tdr",
            "vrel_kms",
            "verr_kms",
            "veldisp_kms_per_pix",
        ]:
            record[field] = parse_float(record.get(field))
        record["aperture"] = int(float(record["aperture"]))
        image_name = record.get("image_name")
        template_image = record.get("template_image")
        if image_name:
            if image_name not in h_obj_cache:
                h_obj_cache[image_name] = heliocentric_correction_kms(fits_root / image_name)
            record["h_obj_kms"] = h_obj_cache[image_name]
        else:
            record["h_obj_kms"] = None
        if template_image:
            if template_image not in h_tpl_cache:
                h_tpl_cache[template_image] = heliocentric_correction_kms(fits_root / template_image)
            record["h_tpl_kms"] = h_tpl_cache[template_image]
        else:
            record["h_tpl_kms"] = None
        record["vobs_calc_kms"] = None
        record["vhelio_calc_kms"] = None
        if (
            record.get("vrel_kms") is not None
            and record.get("template_vhelio_kms") is not None
            and record.get("h_obj_kms") is not None
            and record.get("h_tpl_kms") is not None
        ):
            vobs, vhelio = compute_vhelio_from_vrel(
                record["vrel_kms"],
                record["template_vhelio_kms"],
                record["h_tpl_kms"],
                record["h_obj_kms"],
            )
            record["vobs_calc_kms"] = vobs
            record["vhelio_calc_kms"] = vhelio
        rows.append(record)
    return rows


def write_markdown(path: Path, rv_summaries: list[dict], vsini_rows: list[dict], notes: list[str]) -> None:
    lines = ["# Resumen reproducible de RV y v sin i", "", "## Velocidad radial", ""]
    if rv_summaries:
        for item in rv_summaries:
            flag_text = f" Flags: {item['quality_flags']}." if item.get("quality_flags") else ""
            lines.append(
                f"- {item['label']}: {item['vhelio_media_kms']:.4f} +/- {item['vhelio_err_media_kms']:.4f} km/s con {item['n_ordenes']} orden(es) [{item['ordenes_usados']}].{flag_text}"
            )
    else:
        lines.append("- No se pudieron consolidar casos RV con la informacion disponible.")
    lines.extend(["", "## v sin i", ""])
    if vsini_rows:
        for item in vsini_rows:
            flag_text = f" Flags: {', '.join(item.get('quality_flags') or [])}." if item.get("quality_flags") else ""
            lines.append(
                f"- {item['label']}: FWHM = {item['fwhm_pix']}, v sin i interpolado = {item['vsini_interp_kms']}, TDR = {item['tdr']}.{flag_text}"
            )
    else:
        lines.append("- No se pudo derivar ningun v sin i reproducible.")
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {item}" for item in notes)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_rv_by_case(path: Path, filtered_rows: list[dict]) -> None:
    if not filtered_rows:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = sorted({row["case_id"] for row in filtered_rows if row.get("vhelio_calc_kms") is not None})
    figure, axes = plt.subplots(len(labels), 1, figsize=(7, max(3, 2.6 * len(labels))), squeeze=False)
    for axis, case_id in zip(axes[:, 0], labels):
        rows = [row for row in filtered_rows if row["case_id"] == case_id and row.get("vhelio_calc_kms") is not None]
        axes_values = [row["aperture"] for row in rows]
        rv_values = [row["vhelio_calc_kms"] for row in rows]
        rv_err = [row["verr_kms"] for row in rows]
        axis.errorbar(axes_values, rv_values, yerr=rv_err, fmt="o")
        axis.set_title(case_id)
        axis.set_xlabel("Orden")
        axis.set_ylabel("RV helio [km/s]")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_vsini_calibration(path: Path, calibration_x, calibration_y, model, vsini_points: list[dict]) -> None:
    import numpy as np
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_plot = np.linspace(float(calibration_x.min()), float(calibration_x.max()), 400)
    y_plot = model(x_plot)
    figure = plt.figure(figsize=(7, 4.5))
    axis = figure.add_subplot(111)
    axis.plot(calibration_x, calibration_y, "o", label="Calibracion")
    axis.plot(x_plot, y_plot, "-", label="Interpolacion PCHIP")
    for item in vsini_points:
        if item.get("fwhm_pix") is None or item.get("vsini_interp_kms") is None:
            continue
        axis.plot(item["fwhm_pix"], item["vsini_interp_kms"], "s")
        axis.annotate(item["label"], (item["fwhm_pix"], item["vsini_interp_kms"]), xytext=(5, 5), textcoords="offset points", fontsize=8)
    axis.set_xlabel("FWHM de la CCF (pixeles)")
    axis.set_ylabel("v sin i (km/s)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def cmd_analyze(args):
    ensure_datanalysis_runtime("legacy_rv_coursework_workbench")
    configure_runtime("legacy_rv_coursework_workbench")
    output_dir = Path(args.output_dir).expanduser().resolve()
    preflight_issues = []
    for issue in [
        output_dir_issue(output_dir),
        output_file_issue(args.summary_json, "summary JSON"),
        output_file_issue(args.manifest_json, "manifest JSON"),
        output_file_issue(output_dir / "rv_orders_all.csv", "rv_orders_all.csv"),
        output_file_issue(output_dir / "rv_orders_filtered.csv", "rv_orders_filtered.csv"),
        output_file_issue(output_dir / "rv_summary.csv", "rv_summary.csv"),
        output_file_issue(output_dir / "vsini_summary.csv", "vsini_summary.csv"),
        output_file_issue(output_dir / "summary.md", "summary.md"),
    ]:
        if issue:
            preflight_issues.append(issue)
    figures_dir = output_dir / "figures"
    if figures_dir.exists() and not figures_dir.is_dir():
        preflight_issues.append(f"figures existe pero no es un directorio: {public_path(figures_dir)}")
    csv_inputs, inferred_config = expand_inputs(args.inputs)
    if not csv_inputs:
        preflight_issues.append("No se encontraron CSVs parseados utilizables.")
    fits_root = Path(args.fits_root).expanduser().resolve() if args.fits_root else None
    if fits_root is None and inferred_config is not None:
        fits_root = Path(inferred_config["practice_root"]) / "fits_p1"
    if fits_root is None:
        preflight_issues.append("Hace falta indicar --fits-root o usar un workspace fxcor que permita inferir fits_p1.")
    elif not fits_root.exists():
        preflight_issues.append(f"No existe --fits-root: {public_path(fits_root)}")
    elif not fits_root.is_dir():
        preflight_issues.append(f"--fits-root no es un directorio: {public_path(fits_root)}")

    calibration_csv = Path(args.calibration_csv).expanduser().resolve() if args.calibration_csv else None
    if calibration_csv is None and inferred_config is not None:
        candidate = Path(inferred_config["practice_root"]) / "FWHM_vsini_datafit.csv"
        if candidate.exists():
            calibration_csv = candidate
    calibration_data = None
    if calibration_csv is not None:
        validate_calibration_csv(calibration_csv)
        try:
            calibration_data = load_vsini_calibration(calibration_csv)
        except Exception as exc:
            preflight_issues.append(f"No se pudo cargar la calibracion FWHM-v sin i {public_path(calibration_csv)}: {exc}")

    fail_validation(preflight_issues)

    raw_rows = []
    for csv_path in csv_inputs:
        try:
            raw_rows.extend(load_rows_from_csv(csv_path))
        except (OSError, csv.Error) as exc:
            raise InputValidationError([f"No se pudo leer el CSV parseado {public_path(csv_path)}: {exc}"]) from exc
    if not raw_rows:
        raise InputValidationError(["Los CSVs parseados no contienen filas utilizables."])
    validate_raw_rows(raw_rows, fits_root)
    try:
        normalized_rows = normalize_rows(raw_rows, fits_root)
    except Exception as exc:
        raise InputValidationError([f"No se pudieron normalizar las filas ni calcular correcciones heliocentricas: {exc}"]) from exc

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputValidationError([f"No se pudo preparar el directorio de salida {public_path(output_dir)}: {exc}"]) from exc

    orders_all_csv = output_dir / "rv_orders_all.csv"
    fieldnames = list(normalized_rows[0].keys()) if normalized_rows else []
    if fieldnames:
        csv_write(orders_all_csv, normalized_rows, fieldnames)

    rv_rows = [row for row in normalized_rows if row.get("mode") in {"single_rv", "sb2_rv"}]
    filtered_rows = []
    rv_summaries = []
    rv_diagnostics = []
    notes = [
        "Las velocidades heliocentricas se reconstruyen fuera de IRAF cuando fxcor deja VHELIO en INDEF.",
        "La seleccion por orden es reproducible pero no sustituye una inspeccion humana de la CCF, especialmente en SB2.",
    ]
    for case_id in sorted({row["case_id"] for row in rv_rows}):
        case_rows = [row for row in rv_rows if row["case_id"] == case_id]
        tdr_min, verr_max = thresholds_for_case(case_id, case_rows[0].get("mode"))
        selected = robust_select(case_rows, tdr_min=tdr_min, verr_max=verr_max)
        filtered_rows.extend(selected)
        diagnostics = build_case_diagnostics(case_id, case_rows[0].get("mode"), case_rows, selected)
        rv_diagnostics.append(diagnostics)
        values = [row["vhelio_calc_kms"] for row in selected if row.get("vhelio_calc_kms") is not None]
        errors = [row["verr_kms"] for row in selected if row.get("vhelio_calc_kms") is not None and row.get("verr_kms") is not None]
        if values and errors:
            mean, err = weighted_mean(values, errors)
            rv_summaries.append(
                {
                    "case_id": case_id,
                    "label": case_rows[0].get("case_label") or case_id,
                    "mode": case_rows[0].get("mode"),
                    "n_ordenes": len(values),
                    "vhelio_media_kms": mean,
                    "vhelio_err_media_kms": err,
                    "ordenes_usados": ",".join(str(item["aperture"]) for item in selected if item.get("vhelio_calc_kms") is not None),
                    "quality_flags": ",".join(diagnostics["quality_flags"]),
                    "measurement_state": rv_adoption_labels(case_rows[0].get("mode"), diagnostics)[0],
                    "adoption_state": rv_adoption_labels(case_rows[0].get("mode"), diagnostics)[1],
                    "physical_robustness": rv_adoption_labels(case_rows[0].get("mode"), diagnostics)[2],
                }
            )
    for item in rv_diagnostics:
        if item["quality_flags"]:
            notes.append(f"{item['case_id']}: flags de seleccion por orden: {', '.join(item['quality_flags'])}.")

    orders_filtered_csv = output_dir / "rv_orders_filtered.csv"
    if filtered_rows:
        csv_write(orders_filtered_csv, filtered_rows, list(filtered_rows[0].keys()))
    rv_summary_csv = output_dir / "rv_summary.csv"
    if rv_summaries:
        csv_write(
            rv_summary_csv,
            rv_summaries,
            [
                "case_id",
                "label",
                "mode",
                "n_ordenes",
                "vhelio_media_kms",
                "vhelio_err_media_kms",
                "ordenes_usados",
                "quality_flags",
                "measurement_state",
                "adoption_state",
                "physical_robustness",
            ],
        )

    vsini_rows = []
    calibration_plot = None
    if calibration_data is not None:
        calibration_x, calibration_y, calibration_model = calibration_data
        for row in [item for item in normalized_rows if item.get("mode") == "vsini_fwhm"]:
            fwhm_pix = row.get("fwhm_pix")
            if fwhm_pix is None:
                vsini = None
            else:
                raw_vsini = calibration_model(fwhm_pix)
                vsini = None if raw_vsini is None or math.isnan(float(raw_vsini)) else float(raw_vsini)
            flags = vsini_quality_flags(row, calibration_x)
            measurement_state, adoption_state, physical_robustness = vsini_adoption_labels(flags)
            vsini_rows.append(
                {
                    "case_id": row["case_id"],
                    "label": row.get("case_label") or row["case_id"],
                    "apertura": row["aperture"],
                    "template": row.get("template_image"),
                    "fwhm_kms": row.get("fwhm_kms"),
                    "fwhm_pix": fwhm_pix,
                    "tdr": row.get("tdr"),
                    "vsini_interp_kms": vsini,
                    "quality_flags": flags,
                    "measurement_state": measurement_state,
                    "adoption_state": adoption_state,
                    "physical_robustness": physical_robustness,
                }
            )
        if vsini_rows:
            vsini_csv = output_dir / "vsini_summary.csv"
            csv_write(
                vsini_csv,
                vsini_rows,
                [
                    "case_id",
                    "label",
                    "apertura",
                    "template",
                    "fwhm_kms",
                    "fwhm_pix",
                    "tdr",
                    "vsini_interp_kms",
                    "quality_flags",
                    "measurement_state",
                    "adoption_state",
                    "physical_robustness",
                ],
            )
            calibration_plot = figures_dir / "calibracion_fwhm_vsini.png"
            plot_vsini_calibration(calibration_plot, calibration_x, calibration_y, calibration_model, vsini_rows)
        notes.append("Los valores de v sin i se deben interpretar como primera pasada automatica a partir de la calibracion FWHM-v sin i.")
        notes.append("Las tablas distinguen entre medido, adoptado y fisicamente robusto para evitar cierres excesivos en SB2 y v sin i.")
    else:
        notes.append("No se encontro una calibracion FWHM-v sin i, asi que la parte de v sin i queda incompleta.")

    rv_plot = figures_dir / "rv_por_orden.png"
    plot_rv_by_case(rv_plot, filtered_rows)
    summary_md = output_dir / "summary.md"
    write_markdown(summary_md, rv_summaries, vsini_rows, notes)

    qa_findings = []
    for item in rv_diagnostics:
        for flag in item.get("quality_flags", []):
            qa_findings.append({"case_id": item["case_id"], "finding": flag})
    for item in vsini_rows:
        for flag in item.get("quality_flags", []):
            qa_findings.append({"case_id": item["case_id"], "finding": flag})

    payload = standard_tool_payload(
        TOOL_NAME,
        status="ok" if rv_summaries else "warning",
        notes=notes,
        artifacts={
            "orders_all_csv": str(orders_all_csv) if orders_all_csv.exists() else None,
            "orders_filtered_csv": str(orders_filtered_csv) if orders_filtered_csv.exists() else None,
            "rv_summary_csv": str(rv_summary_csv) if rv_summary_csv.exists() else None,
            "vsini_summary_csv": str(output_dir / "vsini_summary.csv") if (output_dir / "vsini_summary.csv").exists() else None,
            "summary_md": str(summary_md),
            "rv_plot": str(rv_plot) if rv_plot.exists() else None,
            "calibration_plot": str(calibration_plot) if calibration_plot and calibration_plot.exists() else None,
        },
        results={
            "rv_summaries": rv_summaries,
            "rv_diagnostics": rv_diagnostics,
            "vsini_rows": vsini_rows,
            "fits_root": str(fits_root),
        },
        qa=standard_qa_payload(
            status="warning" if qa_findings else "ok",
            findings=qa_findings,
            metrics={
                "rv_case_count": len(rv_summaries),
                "vsini_case_count": len(vsini_rows),
            },
        ),
    )
    outputs = [summary_md]
    for candidate in [orders_all_csv, orders_filtered_csv, rv_summary_csv, output_dir / "vsini_summary.csv", rv_plot]:
        if candidate.exists():
            outputs.append(candidate)
    if calibration_plot and calibration_plot.exists():
        outputs.append(calibration_plot)
    manifest_inputs = [*csv_inputs, fits_root]
    if calibration_csv:
        manifest_inputs.append(calibration_csv)
    return emit_analyze_payload(
        payload,
        args,
        manifest_inputs=manifest_inputs,
        manifest_outputs=outputs,
        manifest_parameters={"tool": TOOL_NAME, "calibration_csv": str(calibration_csv) if calibration_csv else None},
        manifest_notes=notes,
    )


def main():
    args = parse_args()
    if args.command == "analyze":
        try:
            return cmd_analyze(args)
        except InputValidationError as exc:
            return emit_analyze_payload(blocked_payload(args, exc.issues), args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
