#!/usr/bin/env python3
"""Fit a first-order photometric calibration solution from standard-star measurements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload, emit_payload_best_effort
from _internal.runtime_common import configure_runtime, suppress_fd_output

ensure_datanalysis_runtime("photometric_solution")
configure_runtime("photometric_solution")

import numpy as np
with suppress_fd_output(True):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

from _internal.provenance_utils import public_path, write_manifest
from _internal.tabular_io import read_table_any


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_table", help="Table with standard-star measurements (`.csv`, `.tsv`, `.ecsv`, `.fits`, ...).")
    parser.add_argument("--inst-mag-col", default="inst_mag", help="Column for instrumental magnitudes.")
    parser.add_argument("--std-mag-col", default="std_mag", help="Column for calibrated/standard magnitudes.")
    parser.add_argument("--airmass-col", default="airmass", help="Column for airmass.")
    parser.add_argument("--color-col", help="Optional color-index column, e.g. `B-V`.")
    parser.add_argument("--error-col", help="Optional uncertainty column on `(std_mag - inst_mag)`.")
    parser.add_argument("--include-color-term", action="store_true", help="Fit a linear color term when --color-col is present.")
    parser.add_argument("--summary-json", help="Optional summary JSON using the standard top-level envelope.")
    parser.add_argument("--output-json", help="Optional summary JSON.")
    parser.add_argument("--coefficients-csv", help="Optional CSV with fitted coefficients.")
    parser.add_argument("--residual-csv", help="Optional CSV with per-star residual diagnostics.")
    parser.add_argument("--residual-plot", help="Optional output PNG for residual diagnostics.")
    parser.add_argument("--report-md", help="Optional markdown summary report.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    return parser.parse_args()


def summary_path_from_args(args) -> Path | None:
    paths = summary_paths_from_args(args)
    return paths[0] if paths else None


def summary_paths_from_args(args) -> list[Path]:
    paths = []
    seen = set()
    for raw_path in (getattr(args, "summary_json", None), getattr(args, "output_json", None)):
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def summary_artifact_value(paths: list[Path]):
    rendered = [str(path) for path in paths]
    if not rendered:
        return None
    return rendered[0] if len(rendered) == 1 else rendered


def emit_payload_to_paths(payload: dict, paths: list[Path], *, best_effort: bool = False) -> str:
    emitter = emit_payload_best_effort if best_effort else emit_payload
    if not paths:
        return emitter(payload, None)
    rendered = emitter(payload, paths[0])
    for path in paths[1:]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        except OSError:
            if not best_effort:
                raise
    return rendered


def blocked_payload(args, message: str) -> dict:
    summary_paths = summary_paths_from_args(args)
    input_path = Path(getattr(args, "input_table", "")).expanduser()
    return build_blocked_payload(
        "photometric_solution",
        message,
        notes=[
            message,
            "No photometric coefficients were fitted and no input table was modified.",
        ],
        artifacts={
            "summary_json": summary_artifact_value(summary_paths),
            "coefficients_csv": getattr(args, "coefficients_csv", None),
            "residual_csv": getattr(args, "residual_csv", None),
            "residual_plot": getattr(args, "residual_plot", None),
            "report_md": getattr(args, "report_md", None),
            "manifest_json": getattr(args, "manifest_json", None),
        },
        results={
            "input_table": public_path(input_path),
            "row_count": 0,
            "fitted_model": None,
            "parameters": {},
            "error": message,
        },
        inputs=[input_path],
    )


def emit_blocked(args, message: str) -> int:
    payload = blocked_payload(args, message)
    emit_payload_to_paths(payload, summary_paths_from_args(args), best_effort=True)
    return 2


def read_table(path: Path) -> pd.DataFrame:
    try:
        from astropy.table import Table

        table = read_table_any(Table, path)
        return table.to_pandas()
    except Exception:
        suffix = path.suffix.lower()
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t")
        return pd.read_csv(path)


def numeric_column(work: pd.DataFrame, column: str, label: str) -> np.ndarray:
    try:
        values = pd.to_numeric(work[column], errors="raise").to_numpy(dtype=float)
    except Exception as exc:
        raise SystemExit(f"Column '{column}' for {label} must be numeric. Could not convert values: {exc}")
    if not np.all(np.isfinite(values)):
        raise SystemExit(f"Column '{column}' for {label} contains non-finite values.")
    return values


def weighted_lstsq(design: np.ndarray, values: np.ndarray, sigma: np.ndarray | None):
    weights = np.ones_like(values) if sigma is None else 1.0 / np.square(sigma)
    w_sqrt = np.sqrt(weights)
    xw = design * w_sqrt[:, None]
    yw = values * w_sqrt
    normal_matrix = xw.T @ xw
    if np.linalg.cond(normal_matrix) > 1e12:
        raise SystemExit(
            "The photometric solution is ill-conditioned. Broaden the airmass/color coverage or fit fewer terms."
        )
    beta, _, _, _ = np.linalg.lstsq(xw, yw, rcond=None)
    base_covariance = np.linalg.inv(normal_matrix)
    model = design @ beta
    residuals = values - model
    dof = len(values) - design.shape[1]
    if dof > 0:
        if sigma is None:
            scale = float(np.sum(np.square(residuals)) / dof)
        else:
            # Supplied sigma values are absolute measurement uncertainties.
            # Their covariance is already encoded in (X^T W X)^-1 and must not
            # collapse when an exact or over-fitting data set has chi^2 << dof.
            scale = 1.0
    else:
        scale = 1.0
    covariance = base_covariance * max(scale, 1.0e-12)
    return beta, covariance, weights, residuals


def build_design(df: pd.DataFrame, args) -> tuple[np.ndarray, list[str]]:
    columns = ["zero_point", "extinction"]
    pieces = [np.ones(len(df), dtype=float), df[args.airmass_col].to_numpy(dtype=float)]
    if args.include_color_term:
        if not args.color_col:
            raise SystemExit("--include-color-term requires --color-col.")
        columns.append("color_term")
        pieces.append(df[args.color_col].to_numpy(dtype=float))
    design = np.column_stack(pieces)
    return design, columns


def save_coefficients(path: Path, names: list[str], values: np.ndarray, errors: np.ndarray):
    rows = [{"parameter": name, "value": float(value), "uncertainty": float(error)} for name, value, error in zip(names, values, errors)]
    pd.DataFrame(rows).to_csv(path, index=False)


def save_residuals(path: Path, work: pd.DataFrame, observed_offset: np.ndarray, model: np.ndarray, residuals: np.ndarray, sigma: np.ndarray | None):
    frame = work.copy()
    frame["observed_offset_mag"] = observed_offset
    frame["model_offset_mag"] = model
    frame["residual_mag"] = residuals
    if sigma is not None:
        frame["normalized_residual"] = residuals / sigma
    frame.to_csv(path, index=False)


def plot_residuals(path: Path, df: pd.DataFrame, args, residuals: np.ndarray):
    fig, axes = plt.subplots(1, 2 if args.include_color_term else 1, figsize=(9 if args.include_color_term else 5.2, 4.1))
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])

    axes[0].axhline(0.0, color="0.35", linewidth=1.0, linestyle="--")
    axes[0].scatter(df[args.airmass_col], residuals, color="tab:blue", s=28)
    axes[0].set_xlabel("Airmass")
    axes[0].set_ylabel("Residual (mag)")
    axes[0].set_title("Residuals vs airmass")
    axes[0].grid(True, alpha=0.3)

    if args.include_color_term:
        axes[1].axhline(0.0, color="0.35", linewidth=1.0, linestyle="--")
        axes[1].scatter(df[args.color_col], residuals, color="tab:orange", s=28)
        axes[1].set_xlabel(args.color_col)
        axes[1].set_ylabel("Residual (mag)")
        axes[1].set_title("Residuals vs color")
        axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_quality_flags(work: pd.DataFrame, args, residuals: np.ndarray, sigma: np.ndarray | None, parameter_count: int):
    flags = []
    airmass_span = float(work[args.airmass_col].max() - work[args.airmass_col].min())
    if airmass_span < 0.25:
        flags.append("Airmass coverage is narrow; extinction may be weakly constrained.")
    if len(work) < parameter_count + 3:
        flags.append("Only a small number of standards are available relative to the fitted parameter count.")
    if args.include_color_term and args.color_col:
        color_span = float(work[args.color_col].max() - work[args.color_col].min())
        if color_span < 0.3:
            flags.append("Color coverage is narrow; the fitted color term may be unstable.")
    if sigma is not None:
        normalized = np.abs(residuals / sigma)
        if float(np.max(normalized)) > 3.0:
            flags.append("At least one standard exceeds a 3-sigma residual; inspect for outliers or catalog mismatches.")
    elif float(np.max(np.abs(residuals))) > 0.05:
        flags.append("Residual scatter exceeds 0.05 mag for at least one standard; check transparency and input consistency.")
    return flags


def write_report(path: Path, summary: dict):
    lines = [
        "# Photometric Solution Report",
        "",
        f"- Input table: `{summary['input_table']}`",
        f"- Row count used: `{summary['row_count']}`",
        f"- Model: `{summary['fitted_model']}`",
        "",
        "## Coefficients",
        "",
    ]
    for name, payload in summary["parameters"].items():
        lines.append(f"- `{name}` = `{payload['value']:.6f} +/- {payload['uncertainty']:.6f}`")
    lines.extend(
        [
            "",
            "## Diagnostics",
            "",
            f"- RMS residual: `{summary['rms_residual_mag']:.6f}` mag",
            f"- Median absolute residual: `{summary['median_abs_residual_mag']:.6f}` mag",
            f"- Reduced chi-square: `{summary['reduced_chi2']}`",
            f"- Airmass range: `{summary['coverage']['airmass_min']:.4f}` to `{summary['coverage']['airmass_max']:.4f}`",
        ]
    )
    if summary["coverage"].get("color_min") is not None:
        lines.append(
            f"- Color range: `{summary['coverage']['color_min']:.4f}` to `{summary['coverage']['color_max']:.4f}`"
        )
    if summary["quality_flags"]:
        lines.extend(["", "## Quality Flags", ""])
        lines.extend([f"- {item}" for item in summary["quality_flags"]])
    lines.extend(["", "## Notes", ""])
    lines.extend([f"- {item}" for item in summary["notes"]])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_solution(args) -> int:
    input_path = Path(args.input_table).expanduser()
    if not input_path.exists():
        raise SystemExit(f"Input table does not exist: {input_path}")
    df = read_table(input_path)

    required = [args.inst_mag_col, args.std_mag_col, args.airmass_col]
    if args.include_color_term:
        if not args.color_col:
            raise SystemExit("--include-color-term requires --color-col.")
        required.append(args.color_col)
    missing = [name for name in required if name not in df.columns]
    if missing:
        available = ", ".join(str(name) for name in df.columns)
        raise SystemExit(
            "Missing required columns: "
            + ", ".join(str(name) for name in missing)
            + f". Available columns: {available or '[none]'}. "
            "Pass --inst-mag-col, --std-mag-col, --airmass-col and optionally --color-col for non-standard names."
        )

    work = df.dropna(subset=[name for name in required if name]).copy()
    if args.error_col:
        if args.error_col not in work.columns:
            raise SystemExit(f"Missing uncertainty column: {args.error_col}")
        work = work.dropna(subset=[args.error_col]).copy()

    if len(work) < 3:
        raise SystemExit("Need at least three valid rows to fit a photometric solution.")

    inst_mag = numeric_column(work, args.inst_mag_col, "instrumental magnitude")
    std_mag = numeric_column(work, args.std_mag_col, "standard magnitude")
    airmass = numeric_column(work, args.airmass_col, "airmass")
    work[args.inst_mag_col] = inst_mag
    work[args.std_mag_col] = std_mag
    work[args.airmass_col] = airmass
    if args.include_color_term and args.color_col:
        work[args.color_col] = numeric_column(work, args.color_col, "color term")
    observed_offset = std_mag - inst_mag
    sigma = numeric_column(work, args.error_col, "offset uncertainty") if args.error_col else None
    if sigma is not None and np.any(sigma <= 0):
        raise SystemExit("All supplied uncertainties must be positive.")
    if sigma is not None:
        work[args.error_col] = sigma

    design, parameter_names = build_design(work, args)
    beta, covariance, weights, residuals = weighted_lstsq(design, observed_offset, sigma)
    model = design @ beta
    parameter_errors = np.sqrt(np.diag(covariance))

    dof = max(len(work) - len(parameter_names), 1)
    if sigma is None:
        rms = float(np.sqrt(np.mean(np.square(residuals))))
        reduced_chi2 = None
    else:
        chi2 = float(np.sum(np.square(residuals / sigma)))
        reduced_chi2 = chi2 / dof
        rms = float(np.sqrt(np.average(np.square(residuals), weights=weights)))
    median_abs_residual = float(np.median(np.abs(residuals)))
    quality_flags = build_quality_flags(work, args, residuals, sigma, len(parameter_names))

    coverage = {
        "airmass_min": float(work[args.airmass_col].min()),
        "airmass_max": float(work[args.airmass_col].max()),
        "airmass_span": float(work[args.airmass_col].max() - work[args.airmass_col].min()),
        "color_min": None,
        "color_max": None,
        "color_span": None,
    }
    if args.include_color_term and args.color_col:
        coverage["color_min"] = float(work[args.color_col].min())
        coverage["color_max"] = float(work[args.color_col].max())
        coverage["color_span"] = float(work[args.color_col].max() - work[args.color_col].min())

    summary = {
        "input_table": public_path(input_path),
        "row_count": int(len(work)),
        "fitted_model": "std_mag - inst_mag = zero_point + extinction*airmass" + (" + color_term*color" if args.include_color_term else ""),
        "parameters": {
            name: {"value": float(value), "uncertainty": float(error)}
            for name, value, error in zip(parameter_names, beta, parameter_errors)
        },
        "rms_residual_mag": rms,
        "median_abs_residual_mag": median_abs_residual,
        "reduced_chi2": reduced_chi2,
        "residual_range_mag": [float(np.min(residuals)), float(np.max(residuals))],
        "coverage": coverage,
        "quality_flags": quality_flags,
        "notes": [
            "This is a first-order linear photometric solution intended for standard-star calibration tables.",
            "Interpret the extinction term in the context of the sign convention used here: std_mag - inst_mag = zero_point + extinction*airmass (+ color term).",
            "If the standards are sparse or poorly distributed in airmass/color, treat the solution as provisional.",
            "Check residuals against airmass and color before trusting the coefficients as a night-wide calibration.",
        ],
    }
    summary_json_paths = summary_paths_from_args(args)
    payload = build_tool_payload(
        "photometric_solution",
        status="warning" if quality_flags else "ok",
        notes=summary["notes"],
        artifacts={
            "summary_json": summary_artifact_value(summary_json_paths),
            "coefficients_csv": args.coefficients_csv,
            "residual_csv": args.residual_csv,
            "residual_plot": args.residual_plot,
            "report_md": args.report_md,
            "manifest_json": args.manifest_json,
        },
        results=summary,
        qa={
            "status": "warning" if quality_flags else "ok",
            "findings": quality_flags,
            "metrics": {
                "row_count": summary["row_count"],
                "rms_residual_mag": summary["rms_residual_mag"],
                "median_abs_residual_mag": summary["median_abs_residual_mag"],
            },
        },
        legacy=summary,
    )

    print(json.dumps(summary, indent=2, ensure_ascii=True))

    outputs = []
    if summary_json_paths:
        emit_payload_to_paths(payload, summary_json_paths)
        outputs.extend(summary_json_paths)
        for output_json in summary_json_paths:
            print(f"Saved summary: {public_path(output_json)}")
    if args.coefficients_csv:
        coeff_path = Path(args.coefficients_csv)
        coeff_path.parent.mkdir(parents=True, exist_ok=True)
        save_coefficients(coeff_path, parameter_names, beta, parameter_errors)
        outputs.append(coeff_path)
        print(f"Saved coefficients: {public_path(coeff_path)}")
    if args.residual_csv:
        residual_csv = Path(args.residual_csv)
        residual_csv.parent.mkdir(parents=True, exist_ok=True)
        save_residuals(residual_csv, work, observed_offset, model, residuals, sigma)
        outputs.append(residual_csv)
        print(f"Saved residual diagnostics: {public_path(residual_csv)}")
    if args.residual_plot:
        plot_path = Path(args.residual_plot)
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plot_residuals(plot_path, work, args, residuals)
        outputs.append(plot_path)
        print(f"Saved residual plot: {public_path(plot_path)}")
    if args.report_md:
        report_path = Path(args.report_md)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report_path, summary)
        outputs.append(report_path)
        print(f"Saved report: {public_path(report_path)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=outputs,
            parameters={
                "inst_mag_col": args.inst_mag_col,
                "std_mag_col": args.std_mag_col,
                "airmass_col": args.airmass_col,
                "color_col": args.color_col,
                "include_color_term": args.include_color_term,
                "error_col": args.error_col,
            },
            command="photometric_solution.py",
            notes=summary["notes"],
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_solution(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_blocked(args, str(exc.code) or "Photometric solution blocked.")
    except Exception as exc:
        return emit_blocked(args, f"Photometric solution blocked: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
