#!/usr/bin/env python3
"""Fit narrow SB2 CCF traces order-by-order with a double Gaussian model."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, standard_qa_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


TOOL_NAME = "sb2_double_gaussian_workbench.fit"
TOOL_NAME_ORDERS = "sb2_double_gaussian_workbench.fit-orders"
FIT_METHOD = "Bounded least-squares fit of two Gaussians and a constant baseline"
ACCEPTANCE_FINDINGS = {
    "low_peak_separation": "The fitted peaks are closer than the requested minimum separation.",
    "sigma_out_of_range": "A fitted Gaussian width falls outside the review range of 2.5–120 km/s.",
    "non_positive_peak": "A fitted peak has a non-positive amplitude.",
}


class InputValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_fit_parser(name: str, help_text: str):
        fit = sub.add_parser(name, help=help_text)
        fit.add_argument("inputs", nargs="+", help="CCF CSVs with velocity_kms and ccf_value columns.")
        fit.add_argument("--output-dir", required=True)
        fit.add_argument("--fxcor-csv", action="append", default=[], help="Optional fxcor parsed CSV(s) for loose comparison.")
        fit.add_argument("--case-id", help="Optional case identifier override.")
        fit.add_argument("--min-separation", type=float, default=20.0, help="Minimum accepted separation between the two peaks, in km/s.")
        fit.add_argument("--summary-json")
        fit.add_argument("--manifest-json")

    add_fit_parser("fit-orders", "Fit one or more CCF CSVs with a double Gaussian model.")
    add_fit_parser("fit", "Public alias for fit-orders, kept for the registry-facing CLI contract.")
    return parser.parse_args()


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


def blocked_payload(args, issues: list[str], tool_name: str | None = None) -> dict:
    return standard_tool_payload(
        tool_name or TOOL_NAME,
        status="blocked",
        notes=[
            "Validacion de entrada fallida antes de ajustar las CCF SB2.",
            "El ajuste doble-gaussiano se bloquea para evitar tablas o figuras parciales que parezcan validas.",
        ],
        artifacts={"summary_json": args.summary_json, "output_dir": args.output_dir},
        results={
            "input_validation_issues": issues,
            "input_count": len(args.inputs or []),
            "fxcor_csv": list(args.fxcor_csv or []),
            "min_separation": args.min_separation,
            "measurement_summary": {"method": FIT_METHOD, "measurements": [], "diagnostics": [], "assumptions": []},
        },
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"issue_count": len(issues)}),
    )


def emit_fit_payload(
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
            summary_path = Path(args.summary_json).expanduser()
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
                parameters=manifest_parameters or {"tool": payload.get("tool", TOOL_NAME)},
                command=" ".join(sys.argv),
                notes=manifest_notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def read_ccf_csv(path: Path) -> dict:
    if not path.exists():
        raise InputValidationError([f"No existe el CCF CSV indicado: {public_path(path)}"])
    if not path.is_file():
        raise InputValidationError([f"El CCF CSV indicado no es un archivo: {public_path(path)}"])
    try:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise InputValidationError([f"No se pudo leer el CCF CSV {public_path(path)}: {exc}"]) from exc
    if not rows:
        raise InputValidationError([f"CSV sin filas: {public_path(path)}"])
    xs = []
    ys = []
    metadata = {"case_id": None, "aperture": None, "source_csv": str(path)}
    issues = []
    for row in rows:
        velocity = row.get("velocity_kms") or row.get("velocity") or row.get("rv_kms")
        ccf_value = row.get("ccf_value") or row.get("ccf") or row.get("correlation")
        if velocity is None or ccf_value is None:
            raise InputValidationError([f"El CSV {public_path(path)} necesita columnas velocity_kms/ccf_value."])
        try:
            velocity_value = float(velocity)
            ccf_numeric = float(ccf_value)
        except ValueError:
            issues.append(f"{public_path(path)}: fila con velocidad/CCF no numerica: {velocity!r}, {ccf_value!r}")
            continue
        if not math.isfinite(velocity_value) or not math.isfinite(ccf_numeric):
            issues.append(f"{public_path(path)}: fila con velocidad/CCF no finita: {velocity!r}, {ccf_value!r}")
            continue
        xs.append(velocity_value)
        ys.append(ccf_numeric)
        if row.get("aperture"):
            try:
                value = float(row["aperture"])
                if not math.isfinite(value) or not value.is_integer():
                    raise ValueError
                aperture = int(value)
                if metadata["aperture"] not in (None, aperture):
                    raise InputValidationError([f"{public_path(path)} contains multiple apertures. Supply one CCF per file."])
                metadata["aperture"] = aperture
            except ValueError:
                issues.append(f"{public_path(path)}: aperture no es numerico: {row['aperture']!r}")
        case_id = (row.get("case_id") or "").strip()
        if case_id:
            if metadata["case_id"] not in (None, case_id):
                raise InputValidationError([f"{public_path(path)} contains multiple case IDs. Supply one CCF per file."])
            metadata["case_id"] = case_id
    if len(xs) < 7:
        issues.append(f"{public_path(path)}: se necesitan al menos 7 puntos numericos para ajustar dos gaussianas.")
    if xs and max(xs) <= min(xs):
        issues.append(f"{public_path(path)}: el eje de velocidad no tiene rango util.")
    fail_validation(issues)
    return {"x": xs, "y": ys, "metadata": metadata}


def load_fxcor_rows(paths: list[str]) -> dict[tuple[str | None, int | None], list[dict]]:
    mapping: dict[tuple[str | None, int | None], list[dict]] = {}
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise InputValidationError([f"No existe el fxcor CSV indicado: {public_path(path)}"])
        if not path.is_file():
            raise InputValidationError([f"El fxcor CSV indicado no es un archivo: {public_path(path)}"])
        try:
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error) as exc:
            raise InputValidationError([f"No se pudo leer el fxcor CSV {public_path(path)}: {exc}"]) from exc
        for row in rows:
            case_id = row.get("case_id")
            aperture = row.get("aperture")
            try:
                key = (case_id, int(float(aperture)) if aperture else None)
            except ValueError as exc:
                raise InputValidationError([f"{public_path(path)}: aperture fxcor no es numerico: {aperture!r}"]) from exc
            mapping.setdefault(key, []).append(row)
    return mapping


def choose_initial_centers(x, y, min_sep: float) -> tuple[float, float]:
    ranked = sorted(zip(y, x), reverse=True)
    if len(ranked) < 2:
        return x[len(x) // 3], x[(2 * len(x)) // 3]
    first = ranked[0][1]
    second = None
    for _, candidate in ranked[1:]:
        if abs(candidate - first) >= min_sep:
            second = candidate
            break
    if second is None:
        second = ranked[min(1, len(ranked) - 1)][1]
    return tuple(sorted([first, second]))


def double_gaussian(x, baseline, amp1, center1, sigma1, amp2, center2, sigma2):
    import numpy as np

    return baseline + amp1 * np.exp(-0.5 * ((x - center1) / sigma1) ** 2) + amp2 * np.exp(-0.5 * ((x - center2) / sigma2) ** 2)


def fit_trace(x_values, y_values, min_separation: float) -> dict:
    import numpy as np
    import warnings
    from scipy.optimize import OptimizeWarning, curve_fit

    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("CCF velocity and correlation arrays must be matching one-dimensional arrays.")
    if x.size < 12 or np.unique(x).size < 12:
        raise ValueError(
            "A seven-parameter SB2 fit requires at least 12 distinct samples for a minimally constrained covariance."
        )
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("CCF samples must be finite before fitting.")
    baseline0 = float(np.percentile(y, 10))
    amp0 = max(1e-6, float(np.max(y) - baseline0))
    center1, center2 = choose_initial_centers(x, y, min_separation)
    sigma0 = max(5.0, min(40.0, 0.08 * (float(np.max(x)) - float(np.min(x)))))
    p0 = [baseline0, amp0, center1, sigma0, amp0 * 0.85, center2, sigma0]
    bounds = (
        [float(np.min(y)) - abs(amp0), 0.0, float(np.min(x)), 1.0, 0.0, float(np.min(x)), 1.0],
        [float(np.max(y)) + abs(amp0), abs(amp0) * 5.0, float(np.max(x)), 150.0, abs(amp0) * 5.0, float(np.max(x)), 150.0],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", OptimizeWarning)
        popt, pcov = curve_fit(double_gaussian, x, y, p0=p0, bounds=bounds, maxfev=30000)
    if not np.all(np.isfinite(popt)):
        raise ValueError("SB2 fit returned non-finite parameters.")
    if pcov.shape != (len(popt), len(popt)) or not np.all(np.isfinite(pcov)):
        raise ValueError("SB2 fit covariance is non-finite or incomplete.")
    covariance_diagonal = np.diag(pcov)
    if np.any(covariance_diagonal <= 0):
        raise ValueError("SB2 fit covariance is not positive on every fitted parameter.")
    if not np.isfinite(np.linalg.cond(pcov)) or np.linalg.cond(pcov) > 1.0e14:
        raise ValueError("SB2 fit covariance is numerically ill-conditioned.")
    baseline, amp1, center1, sigma1, amp2, center2, sigma2 = [float(item) for item in popt]
    perr = np.sqrt(np.diag(pcov))
    center_err_1 = float(perr[2])
    center_err_2 = float(perr[5])
    if not math.isfinite(center_err_1) or center_err_1 <= 0 or not math.isfinite(center_err_2) or center_err_2 <= 0:
        raise ValueError("SB2 component-center uncertainties are not finite and positive.")
    model_y = double_gaussian(x, *popt)
    residual = y - model_y
    rms = float(np.sqrt(np.mean(residual**2)))
    left = {"center_kms": center1, "center_err_kms": center_err_1, "sigma_kms": sigma1, "amplitude": amp1}
    right = {"center_kms": center2, "center_err_kms": center_err_2, "sigma_kms": sigma2, "amplitude": amp2}
    if left["center_kms"] > right["center_kms"]:
        left, right = right, left
    separation = right["center_kms"] - left["center_kms"]
    flags = []
    if separation < min_separation:
        flags.append("low_peak_separation")
    for component in [left, right]:
        sigma = component["sigma_kms"]
        if sigma < 2.5 or sigma > 120.0:
            flags.append("sigma_out_of_range")
            break
    if left["amplitude"] <= 0 or right["amplitude"] <= 0:
        flags.append("non_positive_peak")
    return {
        "baseline": baseline,
        "left": left,
        "right": right,
        "separation_kms": separation,
        "rms": rms,
        "flags": sorted(set(flags)),
        "model_y": model_y.tolist(),
    }


def compare_with_fxcor(fit_result: dict, fxcor_rows: list[dict]) -> list[dict]:
    comparisons = []
    fitted_centers = [fit_result["left"]["center_kms"], fit_result["right"]["center_kms"]]
    for row in fxcor_rows:
        raw_value = row.get("vrel_kms") or row.get("vhelio_calc_kms")
        if raw_value in (None, ""):
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        nearest = min(fitted_centers, key=lambda item: abs(item - value))
        comparisons.append(
            {
                "fxcor_value_kms": value,
                "nearest_double_gaussian_kms": nearest,
                "delta_kms": value - nearest,
            }
        )
    return comparisons


def weighted_component_mean(rows: list[dict], key: str) -> dict | None:
    usable = []
    for row in rows:
        if row.get("status") != "accepted":
            continue
        component = row.get(key) or {}
        center = component.get("center_kms")
        err = component.get("center_err_kms")
        if center is None or err is None or not math.isfinite(float(center)) or not math.isfinite(float(err)) or float(err) <= 0:
            continue
        usable.append((center, err))
    if not usable:
        return None
    weights = [1.0 / (err**2) for _, err in usable]
    total_weight = sum(weights)
    if not math.isfinite(total_weight) or total_weight <= 0:
        return None
    mean = sum(value * weight for (value, _), weight in zip(usable, weights)) / total_weight
    err = math.sqrt(1.0 / total_weight)
    return {"mean_kms": mean, "err_kms": err, "n_orders": len(usable)}


def summarize_cases(rows: list[dict]) -> list[dict]:
    from statistics import median

    cases = {}
    for row in rows:
        cases.setdefault(row["case_id"], []).append(row)
    summaries = []
    for case_id, orders in cases.items():
        accepted = [row for row in orders if row["status"] == "accepted"]
        summaries.append({
            "case_id": case_id,
            "accepted_count": len(accepted),
            "rejected_count": len(orders) - len(accepted),
            "component_a_summary": weighted_component_mean(accepted, "left"),
            "component_b_summary": weighted_component_mean(accepted, "right"),
            "median_ccf_residual_rms": median(row["rms"] for row in accepted) if accepted else None,
        })
    return summaries


def measurement_summary(cases: list[dict], min_separation: float) -> dict:
    measurements = []
    diagnostics = []
    for case in cases:
        prefix = f"{case['case_id']} · " if len(cases) > 1 else ""
        for key, name in [("component_a_summary", "Lower-velocity peak"), ("component_b_summary", "Higher-velocity peak")]:
            component = case[key]
            if component is not None:
                measurements.append({
                    "label": prefix + name, "value": component["mean_kms"], "unit": "km/s",
                    "uncertainty": component["err_kms"],
                })
        diagnostics.extend([
            {"label": prefix + "Orders accepted", "value": case["accepted_count"], "unit": "dimensionless"},
            {"label": prefix + "Orders rejected", "value": case["rejected_count"], "unit": "dimensionless"},
        ])
        if case["median_ccf_residual_rms"] is not None:
            diagnostics.append({
                "label": prefix + "Median CCF residual RMS",
                "value": case["median_ccf_residual_rms"], "unit": "CCF units",
            })
    return {
        "method": FIT_METHOD,
        "measurements": measurements,
        "diagnostics": diagnostics,
        "assumptions": [
            f"The minimum accepted peak separation is {min_separation:g} km/s.",
            "Peaks are ordered by fitted velocity within each trace. Stellar identity requires separate review.",
            "Per-case means use inverse-variance weights from formal fit errors. The combined errors assume independent orders.",
            "Formal errors use the local fit covariance and residual variance. They exclude calibration and template systematics.",
            "Traces with no case ID share the default case. Group orders from the same observation.",
        ],
    }


def plot_fit(path: Path, trace: dict, fit_result: dict, label: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(7, 4.5))
    axis = figure.add_subplot(111)
    axis.plot(trace["x"], trace["y"], "k.", label="CCF")
    axis.plot(trace["x"], fit_result["model_y"], "r-", label="Doble gaussiana")
    axis.axvline(fit_result["left"]["center_kms"], color="C0", linestyle="--", alpha=0.7, label="Comp. A")
    axis.axvline(fit_result["right"]["center_kms"], color="C1", linestyle="--", alpha=0.7, label="Comp. B")
    axis.set_xlabel("Velocidad [km/s]")
    axis.set_ylabel("CCF")
    axis.set_title(label)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def cmd_fit_orders(args):
    ensure_datanalysis_runtime("sb2_double_gaussian_workbench")
    configure_runtime("sb2_double_gaussian_workbench")
    tool_name = TOOL_NAME if args.command == "fit" else TOOL_NAME_ORDERS
    output_dir = Path(args.output_dir).expanduser().resolve()
    figures_dir = output_dir / "figures"
    preflight_issues = []
    for issue in [
        output_dir_issue(output_dir),
        output_file_issue(args.summary_json, "summary JSON"),
        output_file_issue(args.manifest_json, "manifest JSON"),
        output_file_issue(output_dir / "sb2_double_gaussian_orders.csv", "sb2_double_gaussian_orders.csv"),
        output_file_issue(output_dir / "summary.md", "summary.md"),
    ]:
        if issue:
            preflight_issues.append(issue)
    if figures_dir.exists() and not figures_dir.is_dir():
        preflight_issues.append(f"figures existe pero no es un directorio: {public_path(figures_dir)}")
    if not math.isfinite(args.min_separation) or args.min_separation <= 0:
        preflight_issues.append("--min-separation debe ser un numero finito y positivo.")
    fail_validation(preflight_issues)

    traces = [read_ccf_csv(Path(raw).expanduser().resolve()) for raw in args.inputs]
    fxcor_mapping = load_fxcor_rows(args.fxcor_csv)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputValidationError([f"No se pudo preparar el directorio de salida {public_path(output_dir)}: {exc}"]) from exc

    order_rows = []
    notes = [
        "Este helper ajusta una doble gaussiana por orden para SB2; no sustituye la inspeccion humana de la CCF.",
        "Usa la salida como carril reproducible para decidir que ordenes aceptar, rechazar o revisar.",
    ]
    for index, trace in enumerate(traces, 1):
        metadata = trace["metadata"]
        case_id = args.case_id or metadata.get("case_id") or "sb2_case"
        aperture = metadata.get("aperture") or index
        key = (metadata.get("case_id"), metadata.get("aperture"))
        fxcor_rows = fxcor_mapping.get(key, []) or fxcor_mapping.get((args.case_id, metadata.get("aperture")), [])
        try:
            fit_result = fit_trace(trace["x"], trace["y"], args.min_separation)
        except Exception as exc:
            notes.append(f"{case_id} orden {aperture}: ajuste doble-gaussiano fallido: {exc}")
            order_rows.append(
                {
                    "case_id": case_id,
                    "aperture": aperture,
                    "source_csv": metadata["source_csv"],
                    "status": "rejected",
                    "acceptance_flags": "fit_failed",
                    "fit_error": str(exc),
                    "center_left_kms": None,
                    "center_left_err_kms": None,
                    "sigma_left_kms": None,
                    "center_right_kms": None,
                    "center_right_err_kms": None,
                    "sigma_right_kms": None,
                    "separation_kms": None,
                    "rms": None,
                    "fxcor_comparison": [],
                    "figure_path": None,
                    "left": None,
                    "right": None,
                }
            )
            continue
        comparisons = compare_with_fxcor(fit_result, fxcor_rows)
        status = "accepted" if not fit_result["flags"] else "rejected"
        figure_path = figures_dir / f"trace_{index:03d}_order_{aperture:03d}.png"
        plot_fit(figure_path, trace, fit_result, f"{case_id} orden {aperture}")
        order_rows.append(
            {
                "case_id": case_id,
                "aperture": aperture,
                "source_csv": metadata["source_csv"],
                "status": status,
                "acceptance_flags": ";".join(fit_result["flags"]),
                "center_left_kms": fit_result["left"]["center_kms"],
                "center_left_err_kms": fit_result["left"]["center_err_kms"],
                "sigma_left_kms": fit_result["left"]["sigma_kms"],
                "center_right_kms": fit_result["right"]["center_kms"],
                "center_right_err_kms": fit_result["right"]["center_err_kms"],
                "sigma_right_kms": fit_result["right"]["sigma_kms"],
                "separation_kms": fit_result["separation_kms"],
                "rms": fit_result["rms"],
                "fxcor_comparison": comparisons,
                "figure_path": str(figure_path),
                "left": fit_result["left"],
                "right": fit_result["right"],
            }
        )

    cases = summarize_cases(order_rows)
    table_path = output_dir / "sb2_double_gaussian_orders.csv"
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "case_id",
            "aperture",
            "source_csv",
            "status",
            "acceptance_flags",
            "fit_error",
            "center_left_kms",
            "center_left_err_kms",
            "sigma_left_kms",
            "center_right_kms",
            "center_right_err_kms",
            "sigma_right_kms",
            "separation_kms",
            "rms",
            "figure_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in order_rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    summary_md = output_dir / "summary.md"
    lines = ["# SB2 Double Gaussian Summary", ""]
    accepted = [row for row in order_rows if row["status"] == "accepted"]
    lines.append(f"- Ordenes aceptados: `{len(accepted)}` / `{len(order_rows)}`")
    for case in cases:
        lines.extend(["", f"## Caso {case['case_id']}", ""])
        for key, label in [("component_a_summary", "Pico de menor velocidad"), ("component_b_summary", "Pico de mayor velocidad")]:
            component = case[key]
            if component:
                lines.append(
                    f"- {label}: `{component['mean_kms']:.3f} +/- {component['err_kms']:.3f} km/s` "
                    f"con `{component['n_orders']}` ordenes. Incertidumbre formal."
                )
    lines.extend(["", "## Ordenes rechazados", ""])
    rejected = [row for row in order_rows if row["status"] != "accepted"]
    if rejected:
        for row in rejected:
            reason = row.get("fit_error") or row["acceptance_flags"]
            lines.append(f"- Caso {row['case_id']}, orden {row['aperture']}: {reason}")
    else:
        lines.append("- Ninguno.")
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    status = "warning" if rejected else "ok"
    findings = []
    for row in rejected:
        reason = row.get("fit_error") or " ".join(
            ACCEPTANCE_FINDINGS[flag] for flag in row["acceptance_flags"].split(";")
        )
        findings.append({
            "aperture": row["aperture"],
            "flags": row["acceptance_flags"],
            "case_id": row["case_id"],
            "message": f"{row['case_id']}, order {row['aperture']}: {reason}",
        })
    single_case = cases[0] if len(cases) == 1 else {}
    payload = standard_tool_payload(
        tool_name,
        status=status,
        notes=notes,
        artifacts={
            "summary_json": args.summary_json,
            "orders_csv": str(table_path),
            "summary_md": str(summary_md),
            "figures_dir": str(figures_dir),
        },
        results={
            "order_rows": order_rows,
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "component_a_summary": single_case.get("component_a_summary"),
            "component_b_summary": single_case.get("component_b_summary"),
            "case_summaries": cases,
            "measurement_summary": measurement_summary(cases, args.min_separation),
        },
        qa=standard_qa_payload(
            status=status,
            findings=findings,
            metrics={"order_count": len(order_rows), "accepted_count": len(accepted)},
        ),
    )
    outputs = [table_path, summary_md, *(Path(row["figure_path"]) for row in order_rows if row["figure_path"])]
    if args.summary_json:
        outputs.append(Path(args.summary_json).expanduser())
    manifest_inputs = [Path(raw).expanduser().resolve() for raw in args.inputs]
    manifest_inputs.extend(Path(raw).expanduser().resolve() for raw in args.fxcor_csv)
    return emit_fit_payload(
        payload,
        args,
        manifest_inputs=manifest_inputs,
        manifest_outputs=outputs,
        manifest_parameters={"tool": tool_name, "min_separation": args.min_separation, "case_id": args.case_id},
        manifest_notes=notes,
    )


def main():
    args = parse_args()
    if args.command in {"fit-orders", "fit"}:
        tool_name = TOOL_NAME if args.command == "fit" else TOOL_NAME_ORDERS
        try:
            return cmd_fit_orders(args)
        except InputValidationError as exc:
            return emit_fit_payload(blocked_payload(args, exc.issues, tool_name), args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
