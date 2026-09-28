#!/usr/bin/env python3
"""Measure a narrow Li I 6707.8 equivalent width in legacy echelle spectra."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.legacy_spectroscopy_common import multispec_wavelength_axis, parse_multispec_entries
from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest
from _internal.public_contract import build_blocked_payload, emit_payload_best_effort
from _internal.runtime_common import configure_runtime


DEFAULT_CONTINUUM_WINDOWS = [(6705.30, 6706.00), (6708.20, 6708.60)]
DEFAULT_INTEGRATION_WINDOW = (6706.05, 6707.85)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    measure = subparsers.add_parser("measure", help="Measure a first-pass local EW from a MULTISPE FITS order or a two-column ASCII spectrum.")
    measure.add_argument("fits_path", help="Input MULTISPE FITS spectrum or ASCII table with wavelength and flux in the first two numeric columns.")
    measure.add_argument("--output-dir", required=True)
    measure.add_argument("--order", type=int, help="1-based echelle order/aperture. If omitted, select the order containing the line.")
    measure.add_argument("--line-center", type=float, default=6707.8)
    measure.add_argument("--line-label", default="Li I 6707.8 A")
    measure.add_argument("--target-name")
    measure.add_argument("--continuum-window", nargs=2, type=float, action="append", metavar=("LEFT", "RIGHT"))
    measure.add_argument("--integration-window", nargs=2, type=float, default=DEFAULT_INTEGRATION_WINDOW, metavar=("LEFT", "RIGHT"))
    measure.add_argument("--continuum-degree", type=int, default=1)
    measure.add_argument("--literature-ew-ma", type=float)
    measure.add_argument("--skip-systematic-grid", action="store_true")
    measure.add_argument("--summary-json")
    measure.add_argument("--manifest-json")
    return parser.parse_args()


def summary_path_from_args(args) -> Path:
    if getattr(args, "summary_json", None):
        return Path(args.summary_json).expanduser().resolve()
    return Path(args.output_dir).expanduser().resolve() / "li6708_summary.json"


def save_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")


def blocked_payload(args, message: str) -> dict:
    summary_json = summary_path_from_args(args)
    output_dir = Path(args.output_dir).expanduser()
    input_path = Path(args.fits_path).expanduser()
    return build_blocked_payload(
        "li6708_equivalent_width_workbench.measure",
        message,
        notes=[
            message,
            "No equivalent-width measurement was completed and the input spectrum was not modified.",
        ],
        artifacts={
            "summary_json": str(summary_json),
            "output_dir": str(output_dir),
            "summary_csv": None,
            "summary_md": None,
            "plot": None,
        },
        results={
            "input_path": public_path(input_path),
            "input_format": None,
            "target": getattr(args, "target_name", None) or input_path.stem,
            "line_label": getattr(args, "line_label", "Li I 6707.8 A"),
            "line_center_rest_angstrom": getattr(args, "line_center", None),
            "error": message,
        },
        inputs=[input_path],
    )


def emit_blocked(args, message: str) -> int:
    payload = blocked_payload(args, message)
    emit_payload_best_effort(payload, summary_path_from_args(args))
    return 2


def sorted_spectrum(wavelength, flux):
    import numpy as np

    order = np.argsort(wavelength)
    return wavelength[order], flux[order]


def select_order(orders: list[dict], requested_order: int | None, line_center: float, integration_window: tuple[float, float]) -> dict:
    if requested_order is not None:
        for order in orders:
            if order["aperture_1based"] == requested_order:
                return order
        raise SystemExit(f"No se encontro el orden 1-based {requested_order} en el header MULTISPE.")
    left, right = integration_window
    candidates = [
        order
        for order in orders
        if order["lambda_min"] <= left and right <= order["lambda_max"]
    ]
    if not candidates:
        candidates = [order for order in orders if order["lambda_min"] <= line_center <= order["lambda_max"]]
    if not candidates:
        raise SystemExit("No se encontro ningun orden que cubra la linea o la ventana de integracion.")
    return sorted(candidates, key=lambda item: abs(item["lambda_center"] - line_center))[0]


def load_multispec_order(fits_path: Path, requested_order: int | None, line_center: float, integration_window: tuple[float, float]):
    import numpy as np
    from astropy.io import fits

    with fits.open(fits_path, memmap=False, ignore_missing_end=True) as hdul:
        header = hdul[0].header.copy()
        data = np.asarray(hdul[0].data, dtype=float)
    if data.ndim == 1:
        data = data.reshape(1, data.shape[0])
    if data.ndim != 2:
        raise SystemExit(f"Se esperaba un espectro 1D/2D, pero la forma FITS es {data.shape}.")

    orders = parse_multispec_entries(header, fallback_pixels=data.shape[-1])
    if not orders:
        raise SystemExit("No se pudieron parsear entradas WAT2/MULTISPE en el FITS.")
    selected_order = select_order(orders, requested_order, line_center, integration_window)
    index = selected_order["aperture_0based"]
    if index >= data.shape[0]:
        raise SystemExit(f"El orden {selected_order['aperture_1based']} apunta fuera de la matriz FITS {data.shape}.")
    pixels = data.shape[-1]
    wavelength = np.asarray(multispec_wavelength_axis(selected_order, pixels=pixels), dtype=float)
    return header, selected_order, *sorted_spectrum(wavelength, data[index])


def load_ascii_spectrum(path: Path):
    import re
    import numpy as np

    wavelengths = []
    fluxes = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = [token for token in re.split(r"[\s,;]+", line) if token]
        if len(tokens) < 2:
            continue
        try:
            wavelength = float(tokens[0])
            flux = float(tokens[1])
        except ValueError:
            continue
        if not math.isfinite(wavelength) or not math.isfinite(flux):
            raise SystemExit(f"Valor no finito en el espectro ASCII, linea {line_number}.")
        wavelengths.append(wavelength)
        fluxes.append(flux)
    if len(wavelengths) < 3:
        raise SystemExit(
            "No se pudieron leer al menos tres filas numericas de dos columnas desde el espectro ASCII. "
            "Use columnas longitud_de_onda flujo separadas por espacios, coma o tabulador."
        )
    return sorted_spectrum(np.asarray(wavelengths, dtype=float), np.asarray(fluxes, dtype=float))


def load_input_spectrum(path: Path, requested_order: int | None, line_center: float, integration_window: tuple[float, float]):
    suffix = path.suffix.lower()
    if suffix in {".fits", ".fit", ".fts", ".fz"}:
        header, order, wavelength, flux = load_multispec_order(path, requested_order, line_center, integration_window)
        return "fits", header, order, wavelength, flux
    if requested_order is not None:
        raise SystemExit("--order solo tiene sentido para FITS MULTISPE; no se aplica a espectros ASCII.")
    wavelength, flux = load_ascii_spectrum(path)
    order = {
        "aperture_1based": None,
        "aperture_0based": None,
        "lambda_min": float(wavelength[0]),
        "lambda_max": float(wavelength[-1]),
        "lambda_center": float(0.5 * (wavelength[0] + wavelength[-1])),
    }
    return "ascii", {}, order, wavelength, flux


def fit_continuum(wavelength, flux, windows: list[tuple[float, float]], degree: int):
    import numpy as np

    mask = np.zeros_like(wavelength, dtype=bool)
    for left, right in windows:
        mask |= (wavelength >= left) & (wavelength <= right)
    if int(mask.sum()) < degree + 2:
        raise ValueError("Las ventanas de continuo no contienen suficientes pixeles para el ajuste.")
    coeff = np.polyfit(wavelength[mask], flux[mask], degree)
    continuum = np.polyval(coeff, wavelength)
    return continuum, mask


def validate_measurement_windows(
    continuum_windows: list[tuple[float, float]],
    integration_window: tuple[float, float],
) -> None:
    integration_left, integration_right = integration_window
    if not all(math.isfinite(value) for value in integration_window) or integration_left >= integration_right:
        raise ValueError("La ventana de integracion debe tener limites finitos y crecientes.")
    if not continuum_windows:
        raise ValueError("Se requiere al menos una ventana de continuo.")
    for index, (left, right) in enumerate(continuum_windows, start=1):
        if not math.isfinite(left) or not math.isfinite(right) or left >= right:
            raise ValueError(f"La ventana de continuo {index} debe tener limites finitos y crecientes.")
        overlaps = max(left, integration_left) <= min(right, integration_right)
        if overlaps:
            raise ValueError(
                f"La ventana de continuo {index} ({left:g}, {right:g}) se solapa con la ventana "
                f"de integracion ({integration_left:g}, {integration_right:g})."
            )


def trapezoid(y, x) -> float:
    import numpy as np

    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def measure_ew(wavelength, flux, continuum_windows: list[tuple[float, float]], integration_window: tuple[float, float], degree: int) -> dict:
    import numpy as np

    validate_measurement_windows(continuum_windows, integration_window)
    continuum, continuum_mask = fit_continuum(wavelength, flux, continuum_windows, degree)
    if not np.all(np.isfinite(continuum)):
        raise ValueError("El continuo ajustado contiene valores no finitos.")
    if np.any(continuum <= 0):
        raise ValueError("El continuo ajustado contiene valores no positivos; revise ventanas o calibracion visual.")
    normalized = flux / continuum
    if not np.all(np.isfinite(normalized)):
        raise ValueError("La normalizacion produjo valores no finitos; revise flujo, continuo y entrada.")
    line_mask = (wavelength >= integration_window[0]) & (wavelength <= integration_window[1])
    if int(line_mask.sum()) < 2:
        raise ValueError("La ventana de integracion no contiene suficientes pixeles.")
    ew_angstrom = trapezoid(1.0 - normalized[line_mask], wavelength[line_mask])
    if not math.isfinite(ew_angstrom):
        raise ValueError("La EW calculada no es finita; revise ventanas y datos de entrada.")
    local_index = int(np.argmin(normalized[line_mask]))
    line_wavelengths = wavelength[line_mask]
    line_normalized = normalized[line_mask]
    continuum_rms = float(np.std(normalized[continuum_mask] - 1.0))
    pixel_step = float(abs(np.median(np.diff(wavelength))))
    random_like_ma = 1000.0 * continuum_rms * pixel_step * math.sqrt(int(line_mask.sum()))
    return {
        "continuum": continuum,
        "normalized": normalized,
        "continuum_mask": continuum_mask,
        "line_mask": line_mask,
        "ew_angstrom": ew_angstrom,
        "ew_milliangstrom": 1000.0 * ew_angstrom,
        "continuum_rms": continuum_rms,
        "line_center_observed": float(line_wavelengths[local_index]),
        "line_depth": float(1.0 - line_normalized[local_index]),
        "random_like_uncertainty_milliangstrom": random_like_ma,
    }


def systematic_grid(wavelength, flux, continuum_windows: list[tuple[float, float]], integration_window: tuple[float, float], degree: int) -> dict:
    import numpy as np

    if len(continuum_windows) != 2:
        return {"grid_count": 0, "ew_ma_std": None}
    offsets = [-0.10, 0.0, 0.10]
    values = []
    for c1_left in offsets:
        for c1_right in offsets:
            for c2_left in offsets:
                for c2_right in offsets:
                    shifted_continuum = [
                        (continuum_windows[0][0] + c1_left, continuum_windows[0][1] + c1_right),
                        (continuum_windows[1][0] + c2_left, continuum_windows[1][1] + c2_right),
                    ]
                    if shifted_continuum[0][0] >= shifted_continuum[0][1] or shifted_continuum[1][0] >= shifted_continuum[1][1]:
                        continue
                    for i_left in offsets:
                        for i_right in offsets:
                            shifted_integration = (integration_window[0] + i_left, integration_window[1] + i_right)
                            if shifted_integration[0] >= shifted_integration[1]:
                                continue
                            try:
                                measured = measure_ew(wavelength, flux, shifted_continuum, shifted_integration, degree)
                            except ValueError:
                                continue
                            values.append(measured["ew_milliangstrom"])
    if not values:
        return {"grid_count": 0, "ew_ma_std": None}
    array = np.asarray(values, dtype=float)
    return {
        "grid_count": int(array.size),
        "ew_ma_mean": float(np.mean(array)),
        "ew_ma_std": float(np.std(array)),
        "ew_ma_p16": float(np.percentile(array, 16)),
        "ew_ma_p50": float(np.percentile(array, 50)),
        "ew_ma_p84": float(np.percentile(array, 84)),
        "ew_ma_min": float(np.min(array)),
        "ew_ma_max": float(np.max(array)),
    }


def save_plot(path: Path, wavelength, flux, measurement: dict, continuum_windows: list[tuple[float, float]], integration_window: tuple[float, float], line_center: float, line_label: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    axes[0].plot(wavelength, flux, color="black", lw=1)
    axes[0].plot(wavelength, measurement["continuum"], color="tab:blue", lw=1.2)
    for left, right in continuum_windows:
        axes[0].axvspan(left, right, color="tab:green", alpha=0.15)
    axes[0].axvspan(integration_window[0], integration_window[1], color="tab:red", alpha=0.10)
    axes[0].set_ylabel("Flujo")
    axes[0].set_title(line_label)

    line_mask = measurement["line_mask"]
    axes[1].plot(wavelength, measurement["normalized"], color="black", lw=1)
    axes[1].fill_between(wavelength[line_mask], measurement["normalized"][line_mask], 1.0, color="tab:red", alpha=0.25)
    axes[1].axhline(1.0, color="tab:blue", lw=1, ls="--")
    axes[1].axvline(line_center, color="tab:orange", lw=1, ls="--")
    axes[1].set_ylabel("Flujo normalizado")
    axes[1].set_xlabel("Longitud de onda [A]")
    axes[1].text(
        0.03,
        0.08,
        f"EW = {measurement['ew_milliangstrom']:.1f} mA",
        transform=axes[1].transAxes,
        fontsize=10,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def write_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def write_markdown(path: Path, results: dict, notes: list[str]) -> None:
    lines = [
        f"# {results['line_label']}",
        "",
        f"- Objetivo: `{results['target']}`",
        f"- Entrada: `{results['input_path']}`",
        f"- Formato: `{results['input_format']}`",
        f"- Orden usado: `{results['order_1based'] if results['order_1based'] is not None else 'no aplica'}`",
        f"- Ventanas de continuo: `{results['continuum_windows_angstrom']}`",
        f"- Ventana de integracion: `{results['integration_window_angstrom']}`",
        f"- EW medida: `{results['ew_milliangstrom']:.1f} +/- {results['uncertainty_milliangstrom']:.1f} mA`",
        f"- Centro observado del minimo: `{results['line_center_observed_angstrom']:.3f} A`",
        "",
        "## Notas",
        "",
    ]
    lines.extend(f"- {item}" for item in notes)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_measure(args):
    ensure_datanalysis_runtime("li6708_equivalent_width_workbench")
    configure_runtime("li6708_equivalent_width_workbench")
    input_path = Path(args.fits_path).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"No existe la entrada indicada: {input_path}")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    integration_window = tuple(float(item) for item in args.integration_window)
    continuum_windows = [tuple(float(value) for value in item) for item in (args.continuum_window or DEFAULT_CONTINUUM_WINDOWS)]
    validate_measurement_windows(continuum_windows, integration_window)

    input_format, header, order, wavelength, flux = load_input_spectrum(input_path, args.order, args.line_center, integration_window)
    measurement = measure_ew(wavelength, flux, continuum_windows, integration_window, args.continuum_degree)
    grid = {} if args.skip_systematic_grid else systematic_grid(wavelength, flux, continuum_windows, integration_window, args.continuum_degree)
    grid_unc = grid.get("ew_ma_std")
    uncertainty_ma = float(
        math.hypot(
            measurement["random_like_uncertainty_milliangstrom"],
            max(5.0, float(grid_unc)) if grid_unc is not None else 5.0,
        )
    )

    target = args.target_name or header.get("OBJECT") or input_path.stem
    plot_path = figures_dir / "li6708_equivalent_width.png"
    save_plot(plot_path, wavelength, flux, measurement, continuum_windows, integration_window, args.line_center, args.line_label)

    notes = [
        "Medida local de primera pasada: revisar ventanas de continuo e integracion antes de usarla como resultado final.",
    ]
    if input_format == "ascii":
        notes.append("Entrada ASCII de dos columnas: no hay seleccion de orden ni metadatos MULTISPE.")
    if args.literature_ew_ma is not None:
        notes.append("Se incluye comparacion numerica con literatura indicada por el usuario.")
    qa_findings = []
    if measurement["continuum_rms"] > 0.05:
        qa_findings.append("continuum_rms_alto")
    if measurement["line_depth"] <= 0:
        qa_findings.append("linea_no_absorbida")
    qa_status = "warning" if qa_findings else "ok"

    results = {
        "target": str(target),
        "input_path": str(input_path),
        "input_format": input_format,
        "fits_path": str(input_path) if input_format == "fits" else None,
        "line_label": args.line_label,
        "line_center_rest_angstrom": args.line_center,
        "order_1based": order["aperture_1based"],
        "order_0based": order["aperture_0based"],
        "continuum_windows_angstrom": continuum_windows,
        "integration_window_angstrom": integration_window,
        "line_center_observed_angstrom": measurement["line_center_observed"],
        "line_depth": measurement["line_depth"],
        "ew_angstrom": measurement["ew_angstrom"],
        "ew_milliangstrom": measurement["ew_milliangstrom"],
        "uncertainty_milliangstrom": uncertainty_ma,
        "continuum_rms": measurement["continuum_rms"],
        "grid_systematics": grid,
        "literature_ew_milliangstrom": args.literature_ew_ma,
        "literature_delta_milliangstrom": (
            measurement["ew_milliangstrom"] - args.literature_ew_ma if args.literature_ew_ma is not None else None
        ),
    }

    csv_path = output_dir / "li6708_summary.csv"
    md_path = output_dir / "li6708_summary.md"
    summary_json = summary_path_from_args(args)
    write_csv(csv_path, {key: value for key, value in results.items() if not isinstance(value, dict)})
    write_markdown(md_path, results, notes)

    payload = standard_tool_payload(
        "li6708_equivalent_width_workbench.measure",
        status=qa_status,
        notes=notes,
        artifacts={"summary_json": str(summary_json), "summary_csv": str(csv_path), "summary_md": str(md_path), "plot": str(plot_path)},
        results=results,
        qa={"status": qa_status, "findings": qa_findings, "metrics": {"continuum_rms": measurement["continuum_rms"], "line_depth": measurement["line_depth"]}},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
    print(rendered)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(rendered + "\n", encoding="utf-8")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=[summary_json, csv_path, md_path, plot_path],
            parameters={"tool": "li6708_equivalent_width_workbench.measure", "line_center": args.line_center, "order": args.order},
            command=" ".join(sys.argv),
            notes=notes,
        )
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "measure":
            return cmd_measure(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_blocked(args, str(exc.code) or "Medida EW bloqueada.")
    except Exception as exc:
        return emit_blocked(args, f"Medida EW bloqueada: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
