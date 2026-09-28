#!/usr/bin/env python3
"""Inspect, normalize, export, and fit 1D spectra from FITS or ASCII-like files."""

import argparse
import json
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload_best_effort
from _internal.runtime_common import configure_runtime
from _internal.tabular_io import read_table_any, write_table_any


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input spectrum file.")
    parser.add_argument("--wavelength-col", help="Column name for wavelength-like axis.")
    parser.add_argument("--flux-col", help="Column name for flux.")
    parser.add_argument("--error-col", help="Optional uncertainty column name.")
    parser.add_argument("--trace-row", type=int, help="Optional row to use when extracting a 1D spectrum from a 2D FITS image.")
    parser.add_argument("--spatial-half-width", type=int, default=3, help="Half-width in rows for automatic 2D extraction. Default: 3.")
    parser.add_argument("--background-inner-half-width", type=int, default=5, help="Inner half-width for local background windows in 2D extraction.")
    parser.add_argument("--background-outer-half-width", type=int, default=10, help="Outer half-width for local background windows in 2D extraction.")
    parser.add_argument("--trace-degree", type=int, default=2, help="Polynomial degree for the traced 2D spectrum center.")
    parser.add_argument(
        "--optimal-extraction",
        action="store_true",
        help=(
            "Use an experimental profile-weighted extraction. This is not a fully iterative "
            "Horne optimal extraction and is always reported as experimental."
        ),
    )
    parser.add_argument("--order-count", type=int, default=1, help="Number of candidate spectral orders to detect in 2D data.")
    parser.add_argument("--order-index", type=int, default=0, help="Detected order index to extract when multiple orders are found.")
    parser.add_argument("--calibration-table", help="Optional table with pixel and wavelength columns for polynomial wavelength calibration.")
    parser.add_argument("--calibration-degree", type=int, default=3, help="Polynomial degree for wavelength calibration fits.")
    parser.add_argument("--line-window", nargs=2, type=float, metavar=("CENTER", "WIDTH"), help="Fit a gaussian line in a local window.")
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Use continuum-normalized flux for plots and exports; line fits remain in raw-flux space.",
    )
    parser.add_argument("--output-table", help="Optional exported table with wavelength, flux, continuum, and residual columns.")
    parser.add_argument("--extract-all-orders-dir", help="Optional directory to export every detected order from a 2D spectrum.")
    parser.add_argument("--trace-plot", help="Optional PNG diagnostic for 2D spectral extraction.")
    parser.add_argument("--plot", help="Optional PNG output.")
    parser.add_argument("--html-report", help="Optional interactive HTML report.")
    parser.add_argument("--summary-json", help="Optional JSON output.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def load_dependencies():
    configure_runtime("spectral_workbench")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.io import fits
    from astropy.table import Table
    from scipy.optimize import curve_fit
    from scipy.signal import find_peaks, medfilt

    return plt, np, fits, Table, curve_fit, medfilt, find_peaks


def emit_dependency_blocked(args, message):
    input_path = Path(args.input).expanduser()
    payload = build_blocked_payload(
        "spectral_workbench",
        message,
        notes=[
            message,
            "No spectral products were written and the input spectrum was not modified.",
        ],
        artifacts={
            "summary_json": args.summary_json,
            "output_table": args.output_table,
            "plot": args.plot,
            "trace_plot": args.trace_plot,
            "html_report": args.html_report,
            "manifest_json": args.manifest_json,
        },
        results={"path": str(input_path.resolve()), "line_fit": None},
        inputs=[input_path],
    )
    emit_payload_best_effort(payload, args.summary_json)
    return 2


def sanitize_meta(meta):
    cleaned = {}
    for key, value in meta.items():
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                value = str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[str(key)] = value
        else:
            cleaned[str(key)] = str(value)
    return cleaned


def wavelength_from_header(np, header, n, axis=1):
    crval = header.get(f"CRVAL{axis}")
    cdelt = header.get(f"CDELT{axis}", header.get(f"CD{axis}_{axis}"))
    crpix = header.get(f"CRPIX{axis}", 1.0)
    if crval is None or cdelt is None:
        return np.arange(n, dtype=float)
    pixels = np.arange(n, dtype=float) + 1.0
    return crval + (pixels - crpix) * cdelt


def orient_2d_array(np, array):
    if array.shape[1] >= array.shape[0]:
        oriented = array
        dispersion_axis = 1
        orientation = "axis1"
    else:
        oriented = array.T
        dispersion_axis = 2
        orientation = "axis2"
    return oriented, dispersion_axis, orientation


def detect_order_centers(np, find_peaks, oriented, order_count=1):
    spatial_profile = np.nanmedian(oriented, axis=1)
    finite = np.isfinite(spatial_profile)
    if not np.any(finite):
        raise SystemExit("Could not identify a valid spatial trace in the 2D spectrum.")
    prominence = max(float(np.nanstd(spatial_profile)) * 0.5, 1.0)
    distance = max(4, oriented.shape[0] // max(3, order_count * 4))
    peaks, props = find_peaks(np.nan_to_num(spatial_profile, nan=np.nanmedian(spatial_profile)), prominence=prominence, distance=distance)
    if peaks.size == 0:
        peaks = np.array([int(np.nanargmax(spatial_profile))])
    scores = spatial_profile[peaks]
    ranked = [int(peaks[idx]) for idx in np.argsort(scores)[::-1][: max(1, order_count)]]
    return ranked, spatial_profile


def trace_order(np, oriented, seed_row, spatial_half_width=3, trace_degree=2):
    n_rows, n_cols = oriented.shape
    centers = []
    x_values = []
    previous = float(seed_row)
    search_half_width = max(3, spatial_half_width * 3)
    for col in range(n_cols):
        lo = max(0, int(round(previous)) - search_half_width)
        hi = min(n_rows, int(round(previous)) + search_half_width + 1)
        profile = oriented[lo:hi, col].astype(float)
        finite = np.isfinite(profile)
        if not np.any(finite):
            continue
        profile = np.where(finite, profile, np.nanmedian(profile[finite]))
        background = np.nanpercentile(profile, 20)
        weights = np.clip(profile - background, 0.0, None)
        if np.sum(weights) <= 0:
            center = previous
        else:
            local_rows = np.arange(lo, hi, dtype=float)
            center = float(np.sum(local_rows * weights) / np.sum(weights))
        centers.append(center)
        x_values.append(col)
        previous = center
    if len(x_values) < 3:
        return np.full(n_cols, float(seed_row))
    degree = min(trace_degree, len(x_values) - 1)
    coefficients = np.polyfit(x_values, centers, degree)
    trace = np.polyval(coefficients, np.arange(n_cols))
    return trace


def extract_order_flux(np, oriented, trace, spatial_half_width=3, bg_inner=5, bg_outer=10, optimal=False):
    n_rows, n_cols = oriented.shape
    flux = np.zeros(n_cols, dtype=float)
    variance = np.zeros(n_cols, dtype=float)
    background = np.zeros(n_cols, dtype=float)
    for col in range(n_cols):
        center = float(trace[col])
        low = max(0, int(round(center)) - spatial_half_width)
        high = min(n_rows, int(round(center)) + spatial_half_width + 1)
        science = oriented[low:high, col].astype(float)
        bg_values = []
        bg_low0 = max(0, int(round(center)) - bg_outer)
        bg_low1 = max(0, int(round(center)) - bg_inner)
        bg_high0 = min(n_rows, int(round(center)) + bg_inner + 1)
        bg_high1 = min(n_rows, int(round(center)) + bg_outer + 1)
        if bg_low1 > bg_low0:
            bg_values.extend(oriented[bg_low0:bg_low1, col].astype(float).tolist())
        if bg_high1 > bg_high0:
            bg_values.extend(oriented[bg_high0:bg_high1, col].astype(float).tolist())
        bg_array = np.asarray(bg_values, dtype=float)
        bg_level = float(np.nanmedian(bg_array)) if bg_array.size else 0.0
        bg_rms = float(np.nanstd(bg_array)) if bg_array.size else 0.0
        background[col] = bg_level
        signal = science - bg_level
        if optimal:
            profile = np.clip(signal, 0.0, None)
            profile[~np.isfinite(profile)] = 0.0
            profile_sum = float(np.sum(profile))
            if profile_sum <= 0:
                flux[col] = float(np.nansum(signal))
                variance[col] = float(np.nansum(np.abs(science)) + (bg_rms**2) * signal.size)
                continue
            profile /= profile_sum
            pixel_variance = np.abs(science) + bg_rms**2
            finite_positive = pixel_variance[np.isfinite(pixel_variance) & (pixel_variance > 0)]
            variance_floor = float(np.nanmedian(finite_positive)) * 1.0e-12 if finite_positive.size else 1.0e-12
            pixel_variance = np.where(np.isfinite(pixel_variance), np.maximum(pixel_variance, variance_floor), np.nan)
            valid = np.isfinite(signal) & np.isfinite(pixel_variance) & (pixel_variance > 0)
            denominator = float(np.sum((profile[valid] ** 2) / pixel_variance[valid]))
            if denominator <= 0 or not np.isfinite(denominator):
                flux[col] = float(np.nansum(signal))
                variance[col] = float(np.nansum(np.abs(science)) + (bg_rms**2) * signal.size)
                continue
            flux[col] = float(np.sum(profile[valid] * signal[valid] / pixel_variance[valid]) / denominator)
            variance[col] = float(1.0 / denominator)
        else:
            flux[col] = float(np.nansum(signal))
            variance[col] = float(np.nansum(np.abs(science)) + (bg_rms**2) * signal.size)
    error = np.sqrt(np.clip(variance, 0.0, None))
    return flux, error, background


def read_fits_spectrum(
    np,
    fits,
    find_peaks,
    path,
    error_col=None,
    trace_row=None,
    spatial_half_width=3,
    bg_inner=5,
    bg_outer=10,
    trace_degree=2,
    optimal_extraction=False,
    order_count=1,
    order_index=0,
):
    with fits.open(path) as hdus:
        for hdu in hdus:
            data = getattr(hdu, "data", None)
            if data is None:
                continue
            if getattr(data, "names", None):
                names = list(data.names)
                lower = {name.lower(): name for name in names}
                for x_name in ["wavelength", "lambda", "wave", "x"]:
                    for y_name in ["flux", "intensity", "y"]:
                        if x_name in lower and y_name in lower:
                            err_name = None
                            if error_col and error_col.lower() in lower:
                                err_name = lower[error_col.lower()]
                            else:
                                for candidate in ["error", "err", "uncertainty", "sigma", "flux_err", "flux_error"]:
                                    if candidate in lower:
                                        err_name = lower[candidate]
                                        break
                            x_column = lower[x_name]
                            y_column = lower[y_name]
                            x_index = names.index(x_column) + 1
                            y_index = names.index(y_column) + 1
                            meta = {
                                "source": "fits_table_hdu",
                                "x_col": x_column,
                                "y_col": y_column,
                                "error_col": err_name,
                                "axis_name": x_column,
                                "flux_name": y_column,
                                "axis_unit": hdu.header.get(f"TUNIT{x_index}"),
                                "flux_unit": hdu.header.get(f"TUNIT{y_index}"),
                            }
                            error = np.asarray(data[err_name], dtype=float) if err_name else None
                            return (
                                np.asarray(data[x_column], dtype=float),
                                np.asarray(data[y_column], dtype=float),
                                error,
                                sanitize_meta(meta),
                                None,
                            )
            arr = np.asarray(data)
            arr = np.squeeze(arr)
            if arr.ndim == 1:
                meta = {
                    "source": "fits_image_hdu",
                    "object": hdu.header.get("OBJECT"),
                    "instrument": hdu.header.get("INSTRUME"),
                    "date_obs": hdu.header.get("DATE-OBS"),
                    "axis_name": hdu.header.get("CTYPE1", "Axis"),
                    "axis_unit": hdu.header.get("CUNIT1"),
                    "flux_unit": hdu.header.get("BUNIT"),
                }
                return wavelength_from_header(np, hdu.header, arr.size, axis=1), arr.astype(float), None, sanitize_meta(meta), None
            if arr.ndim == 2:
                oriented, dispersion_axis, orientation = orient_2d_array(np, arr.astype(float))
                order_centers, spatial_profile = detect_order_centers(np, find_peaks, oriented, order_count=order_count)
                if trace_row is not None:
                    chosen_seed = int(trace_row)
                else:
                    chosen_seed = order_centers[min(max(order_index, 0), len(order_centers) - 1)]
                trace = trace_order(
                    np,
                    oriented,
                    chosen_seed,
                    spatial_half_width=spatial_half_width,
                    trace_degree=trace_degree,
                )
                extracted, error, background = extract_order_flux(
                    np,
                    oriented,
                    trace,
                    spatial_half_width=spatial_half_width,
                    bg_inner=bg_inner,
                    bg_outer=bg_outer,
                    optimal=optimal_extraction,
                )
                meta = {
                    "source": "fits_2d_hdu",
                    "object": hdu.header.get("OBJECT"),
                    "instrument": hdu.header.get("INSTRUME"),
                    "date_obs": hdu.header.get("DATE-OBS"),
                    "axis_name": hdu.header.get(f"CTYPE{dispersion_axis}", "Axis"),
                    "axis_unit": hdu.header.get(f"CUNIT{dispersion_axis}"),
                    "flux_unit": hdu.header.get("BUNIT"),
                    "extraction_mode": "experimental_profile_weighted_2d" if optimal_extraction else "aperture_sum_2d",
                    "trace_row": int(chosen_seed),
                    "orientation": orientation,
                    "order_count_detected": len(order_centers),
                    "order_index": int(order_index),
                }
                return (
                    wavelength_from_header(np, hdu.header, extracted.size, axis=dispersion_axis),
                    extracted,
                    error,
                    sanitize_meta(meta),
                    {
                        "trace_row": int(chosen_seed),
                        "extract_from_row": int(max(0, round(chosen_seed) - spatial_half_width)),
                        "extract_to_row": int(min(oriented.shape[0] - 1, round(chosen_seed) + spatial_half_width)),
                        "spatial_profile": spatial_profile.tolist(),
                        "trace_centers": trace.tolist(),
                        "background": background.tolist(),
                        "orientation": orientation,
                        "dispersion_axis": dispersion_axis,
                        "detected_order_centers": [int(item) for item in order_centers],
                    },
                )
    raise SystemExit("Could not find a 1D spectrum in the FITS file.")


def read_ascii_spectrum(np, Table, path, wavelength_col=None, flux_col=None, error_col=None):
    table = read_table_any(Table, path)
    names = list(table.colnames)
    lower = {name.lower(): name for name in names}
    if wavelength_col is None:
        for candidate in ["wavelength", "lambda", "wave", "x", "pixel"]:
            if candidate in lower:
                wavelength_col = lower[candidate]
                break
    if flux_col is None:
        for candidate in ["flux", "intensity", "y", "counts"]:
            if candidate in lower:
                flux_col = lower[candidate]
                break
    if error_col is None:
        for candidate in ["error", "err", "uncertainty", "sigma", "flux_err", "flux_error"]:
            if candidate in lower:
                error_col = lower[candidate]
                break
    if wavelength_col is None or flux_col is None:
        numeric = []
        for name in names:
            try:
                table[name].astype(float)
                numeric.append(name)
            except Exception:
                continue
        if len(numeric) >= 2:
            wavelength_col = wavelength_col or numeric[0]
            flux_col = flux_col or numeric[1]
            if error_col is None and len(numeric) >= 3:
                error_col = numeric[2]
        else:
            raise SystemExit("Could not infer wavelength and flux columns.")
    error = np.asarray(table[error_col], dtype=float) if error_col else None
    return (
        np.asarray(table[wavelength_col], dtype=float),
        np.asarray(table[flux_col], dtype=float),
        error,
        sanitize_meta(
            {
                "source": "table",
                "x_col": wavelength_col,
                "y_col": flux_col,
                "error_col": error_col,
                "axis_name": wavelength_col,
                "flux_name": flux_col,
            }
        ),
        None,
    )


def continuum_estimate(medfilt, flux, kernel_size=None):
    kernel = kernel_size or min(101, max(5, (len(flux) // 20) * 2 + 1))
    if kernel % 2 == 0:
        kernel += 1
    return medfilt(flux, kernel_size=kernel)


def apply_wavelength_calibration(np, Table, path, degree):
    calibration = read_table_any(Table, path)
    lower = {name.lower(): name for name in calibration.colnames}
    pixel_name = next((lower[name] for name in ["pixel", "x", "column"] if name in lower), None)
    wave_name = next((lower[name] for name in ["wavelength", "lambda", "wave"] if name in lower), None)
    if pixel_name is None or wave_name is None:
        raise SystemExit("Calibration table must include pixel/x and wavelength columns.")
    pixels = np.asarray(calibration[pixel_name], dtype=float)
    wavelengths = np.asarray(calibration[wave_name], dtype=float)
    coefficients = np.polyfit(pixels, wavelengths, min(degree, len(pixels) - 1))
    model = np.polyval(coefficients, pixels)
    residual_rms = float(np.sqrt(np.mean((model - wavelengths) ** 2)))
    return coefficients.tolist(), residual_rms


def gaussian(x, amp, mu, sigma, offset):
    import numpy as np

    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + offset


def safe_divide(np, numerator, denominator):
    with np.errstate(divide="ignore", invalid="ignore"):
        result = numerator / denominator
    return result


def robust_rms(np, values):
    finite = np.asarray(values)[np.isfinite(values)]
    if finite.size == 0:
        return None
    mad = np.median(np.abs(finite - np.median(finite)))
    return float(1.4826 * mad)


def fit_line(np, curve_fit, wavelength, flux, continuum, center, width, *, normalize_output=False):
    mask = (wavelength >= center - width / 2.0) & (wavelength <= center + width / 2.0)
    if np.sum(mask) < 5:
        raise SystemExit("Not enough samples in the requested line window.")
    x = wavelength[mask]
    y = flux[mask]
    cont = continuum[mask]
    residual = y - cont
    peak_index = int(np.argmax(np.abs(residual)))
    amp0 = float(residual[peak_index])
    mu0 = float(x[peak_index])
    sigma0 = max(width / 8.0, (x[-1] - x[0]) / 10.0)
    offset0 = float(np.median(cont))
    popt, _ = curve_fit(gaussian, x, y, p0=[amp0, mu0, sigma0, offset0], maxfev=20000)
    model_raw = gaussian(x, *popt)
    amplitude = float(popt[0])
    sigma = float(abs(popt[2]))
    offset = float(popt[3])
    if not np.isfinite(offset) or abs(offset) <= np.finfo(float).eps:
        raise SystemExit("Gaussian line fit has a zero or non-finite continuum offset; equivalent width is undefined.")
    equivalent_width_fit = float(-amplitude * sigma * np.sqrt(2.0 * np.pi) / offset)
    integrate = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    with np.errstate(divide="ignore", invalid="ignore"):
        equivalent_width_integral = float(integrate(1.0 - (y / cont), x))
    if not np.isfinite(equivalent_width_fit) or not np.isfinite(equivalent_width_integral):
        raise SystemExit("Equivalent-width calculation produced a non-finite value; inspect the continuum and line window.")
    difference = float(abs(equivalent_width_fit - equivalent_width_integral))
    scale = max(abs(equivalent_width_fit), abs(equivalent_width_integral), np.finfo(float).eps)
    relative_difference = float(difference / scale)
    consistent = bool(relative_difference <= 0.25)
    if normalize_output:
        if np.any(~np.isfinite(cont)) or np.any(np.abs(cont) <= np.finfo(float).eps):
            raise SystemExit("Continuum is zero or non-finite inside the line window; normalized fit model is undefined.")
        fit_model = model_raw / cont
    else:
        fit_model = model_raw
    return {
        "window_center": float(center),
        "window_width": float(width),
        "amplitude": amplitude,
        "center": float(popt[1]),
        "sigma": sigma,
        "fwhm": float(2.354820045 * sigma),
        "offset": offset,
        "equivalent_width": equivalent_width_fit,
        "equivalent_width_method": "gaussian_fit",
        "equivalent_width_fit": equivalent_width_fit,
        "equivalent_width_integral": equivalent_width_integral,
        "equivalent_width_absolute_difference": difference,
        "equivalent_width_relative_difference": relative_difference,
        "equivalent_width_consistent": consistent,
        "line_kind": "emission" if amplitude > 0 else "absorption",
        "fit_flux_space": "raw",
        "fit_model_space": "normalized" if normalize_output else "raw",
        "fit_x": x.tolist(),
        "fit_model": fit_model.tolist(),
    }


def equivalent_width_qa(summary):
    line_fits = []
    if isinstance(summary.get("line_fit"), dict):
        line_fits.append(("line_fit", summary["line_fit"]))
    for index, order in enumerate(summary.get("all_orders") or []):
        if isinstance(order.get("line_fit"), dict):
            line_fits.append((f"all_orders[{index}].line_fit", order["line_fit"]))
    inconsistent = [
        (label, fit)
        for label, fit in line_fits
        if fit.get("equivalent_width_consistent") is False
    ]
    findings = [
        (
            f"{label}: line_equivalent_width_fit_integral_inconsistent "
            f"(relative_difference={fit.get('equivalent_width_relative_difference'):.6g})"
        )
        for label, fit in inconsistent
    ]
    metrics = {
        "line_fit_count": len(line_fits),
        "equivalent_width_inconsistent_count": len(inconsistent),
        "equivalent_width_relative_difference": (
            summary.get("line_fit", {}).get("equivalent_width_relative_difference")
            if isinstance(summary.get("line_fit"), dict)
            else None
        ),
    }
    return findings, metrics


def axis_label(meta):
    name = meta.get("axis_name") or meta.get("x_col") or "Axis"
    unit = meta.get("axis_unit")
    if unit:
        return f"{name} [{unit}]"
    return str(name)


def flux_label(meta, normalized=False):
    if normalized:
        return "Normalized flux"
    name = meta.get("flux_name") or meta.get("y_col") or "Flux"
    unit = meta.get("flux_unit")
    if unit:
        return f"{name} [{unit}]"
    return str(name)


def prepare_spectrum(np, medfilt, wavelength, flux, error, normalize):
    finite = np.isfinite(wavelength) & np.isfinite(flux)
    if error is not None:
        finite &= np.isfinite(error)
    wavelength = wavelength[finite]
    flux = flux[finite]
    if error is not None:
        error = error[finite]
    order = np.argsort(wavelength)
    wavelength = wavelength[order]
    flux = flux[order]
    if error is not None:
        error = error[order]
    continuum = continuum_estimate(medfilt, flux)
    normalized_flux = safe_divide(np, flux, continuum)
    residual = flux - continuum
    normalized_error = safe_divide(np, error, continuum) if error is not None else None
    display_flux = normalized_flux if normalize else flux
    display_continuum = np.ones_like(continuum) if normalize else continuum
    display_error = normalized_error if normalize else error
    rms = robust_rms(np, residual)
    continuum_level = float(np.nanmedian(np.abs(continuum))) if len(continuum) else None
    snr_proxy = float(continuum_level / rms) if rms not in (None, 0.0) and continuum_level is not None else None
    return {
        "wavelength": wavelength,
        "flux": flux,
        "error": error,
        "continuum": continuum,
        "normalized_flux": normalized_flux,
        "residual": residual,
        "normalized_error": normalized_error,
        "display_flux": display_flux,
        "display_continuum": display_continuum,
        "display_error": display_error,
        "rms": rms,
        "snr_proxy": snr_proxy,
    }


def main():
    args = parse_args()
    try:
        ensure_datanalysis_runtime("spectral_workbench")
        plt, np, fits, Table, curve_fit, medfilt, find_peaks = load_dependencies()
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_dependency_blocked(args, str(exc.code) or "Spectral dependencies are unavailable.")
    except (ImportError, ModuleNotFoundError) as exc:
        return emit_dependency_blocked(args, f"Spectral dependencies are unavailable: {type(exc).__name__}: {exc}")
    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    if path.suffix.lower() in {".fits", ".fit", ".fts", ".fz"}:
        wavelength, flux, error, meta, diagnostic = read_fits_spectrum(
            np,
            fits,
            find_peaks,
            path,
            args.error_col,
            trace_row=args.trace_row,
            spatial_half_width=args.spatial_half_width,
            bg_inner=args.background_inner_half_width,
            bg_outer=args.background_outer_half_width,
            trace_degree=args.trace_degree,
            optimal_extraction=args.optimal_extraction,
            order_count=args.order_count,
            order_index=args.order_index,
        )
    else:
        wavelength, flux, error, meta, diagnostic = read_ascii_spectrum(np, Table, path, args.wavelength_col, args.flux_col, args.error_col)

    calibration_info = None
    if args.calibration_table:
        coefficients, residual_rms = apply_wavelength_calibration(np, Table, args.calibration_table, args.calibration_degree)
        pixel_axis = np.arange(len(wavelength), dtype=float)
        wavelength = np.polyval(coefficients, pixel_axis)
        calibration_info = {
            "path": str(Path(args.calibration_table).resolve()),
            "coefficients": coefficients,
            "residual_rms": residual_rms,
            "degree": int(args.calibration_degree),
        }

    processed = prepare_spectrum(np, medfilt, wavelength, flux, error, args.normalize)
    wavelength = processed["wavelength"]
    flux = processed["flux"]
    error = processed["error"]
    continuum = processed["continuum"]
    normalized_flux = processed["normalized_flux"]
    residual = processed["residual"]
    normalized_error = processed["normalized_error"]
    display_flux = processed["display_flux"]
    display_continuum = processed["display_continuum"]
    display_error = processed["display_error"]
    rms = processed["rms"]
    snr_proxy = processed["snr_proxy"]

    summary = {
        "path": str(path.resolve()),
        "count": int(len(wavelength)),
        "wavelength_min": float(np.min(wavelength)),
        "wavelength_max": float(np.max(wavelength)),
        "flux_min": float(np.min(flux)),
        "flux_max": float(np.max(flux)),
        "normalized": bool(args.normalize),
        "axis_label": axis_label(meta),
        "flux_label": flux_label(meta, normalized=args.normalize),
        "median_step": float(np.median(np.diff(wavelength))) if len(wavelength) > 1 else None,
        "continuum_median": float(np.nanmedian(continuum)),
        "residual_rms": rms,
        "snr_proxy": snr_proxy,
        "uncertainty_available": error is not None,
        "meta": meta,
    }
    if diagnostic is not None:
        summary["diagnostic"] = {
            key: value for key, value in diagnostic.items() if key != "spatial_profile"
        }
    if calibration_info is not None:
        summary["calibration"] = calibration_info
    if args.normalize:
        summary["normalized_flux_min"] = float(np.nanmin(display_flux))
        summary["normalized_flux_max"] = float(np.nanmax(display_flux))
    if args.line_window:
        summary["line_fit"] = fit_line(
            np,
            curve_fit,
            wavelength,
            flux,
            continuum,
            args.line_window[0],
            args.line_window[1],
            normalize_output=args.normalize,
        )
    extra_outputs = []
    if args.extract_all_orders_dir and diagnostic is not None and diagnostic.get("detected_order_centers"):
        order_dir = Path(args.extract_all_orders_dir)
        order_dir.mkdir(parents=True, exist_ok=True)
        order_summaries = []
        for order_number, center in enumerate(diagnostic.get("detected_order_centers", [])):
            order_wave, order_flux, order_error, order_meta, order_diag = read_fits_spectrum(
                np,
                fits,
                find_peaks,
                path,
                args.error_col,
                trace_row=int(center),
                spatial_half_width=args.spatial_half_width,
                bg_inner=args.background_inner_half_width,
                bg_outer=args.background_outer_half_width,
                trace_degree=args.trace_degree,
                optimal_extraction=args.optimal_extraction,
                order_count=1,
                order_index=0,
            )
            order_calibration = None
            if args.calibration_table:
                coefficients, residual_rms = apply_wavelength_calibration(np, Table, args.calibration_table, args.calibration_degree)
                order_wave = np.polyval(coefficients, np.arange(len(order_wave), dtype=float))
                order_calibration = {
                    "coefficients": coefficients,
                    "residual_rms": residual_rms,
                    "degree": int(args.calibration_degree),
                }
            order_processed = prepare_spectrum(np, medfilt, order_wave, order_flux, order_error, args.normalize)
            order_summary = {
                "order_number": int(order_number),
                "trace_row": int(center),
                "samples": int(len(order_processed["wavelength"])),
                "wavelength_min": float(np.min(order_processed["wavelength"])),
                "wavelength_max": float(np.max(order_processed["wavelength"])),
                "snr_proxy": order_processed["snr_proxy"],
                "meta": order_meta,
                "diagnostic": {key: value for key, value in (order_diag or {}).items() if key != "spatial_profile"},
            }
            if order_calibration is not None:
                order_summary["calibration"] = order_calibration
            if args.line_window:
                order_summary["line_fit"] = fit_line(
                    np,
                    curve_fit,
                    order_processed["wavelength"],
                    order_processed["flux"],
                    order_processed["continuum"],
                    args.line_window[0],
                    args.line_window[1],
                    normalize_output=args.normalize,
                )
            export = Table()
            export["wavelength"] = order_processed["wavelength"]
            export["flux"] = order_processed["flux"]
            export["continuum"] = order_processed["continuum"]
            export["normalized_flux"] = order_processed["normalized_flux"]
            export["residual"] = order_processed["residual"]
            if order_processed["error"] is not None:
                export["flux_error"] = order_processed["error"]
                export["normalized_error"] = order_processed["normalized_error"]
            table_path = order_dir / f"order_{order_number:02d}.ecsv"
            json_path = order_dir / f"order_{order_number:02d}.json"
            write_table_any(export, table_path)
            json_path.write_text(json.dumps(order_summary, indent=2, ensure_ascii=True) + "\n")
            extra_outputs.extend([str(table_path.resolve()), str(json_path.resolve())])
            order_summary["table_path"] = str(table_path.resolve())
            order_summary["summary_json"] = str(json_path.resolve())
            order_summaries.append(order_summary)
        summary["all_orders_dir"] = str(order_dir.resolve())
        summary["all_orders"] = order_summaries
        print(f"Saved all-order exports: {order_dir.resolve()}")

    print(f"Spectrum: {path.resolve()}")
    print(f"Samples: {summary['count']}")
    print(f"Axis range: {summary['wavelength_min']:.6g} -> {summary['wavelength_max']:.6g}")
    print(f"Flux range: {summary['flux_min']:.6g} -> {summary['flux_max']:.6g}")
    if summary["snr_proxy"] is not None:
        print(f"SNR proxy: {summary['snr_proxy']:.6g}")
    if "line_fit" in summary:
        print(f"Line center: {summary['line_fit']['center']:.6g}")
        print(f"Line kind: {summary['line_fit']['line_kind']}")
        print(f"Equivalent width: {summary['line_fit']['equivalent_width']:.6g}")

    if args.plot:
        out = Path(args.plot)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig = plt.figure(figsize=(8, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(wavelength, display_flux, lw=1.0, label="flux")
        ax.plot(wavelength, display_continuum, lw=1.0, label="continuum", color="tab:orange")
        if display_error is not None:
            ax.fill_between(
                wavelength,
                display_flux - display_error,
                display_flux + display_error,
                color="tab:blue",
                alpha=0.15,
                linewidth=0.0,
                label="uncertainty",
            )
        if "line_fit" in summary:
            fit = summary["line_fit"]
            ax.plot(fit["fit_x"], fit["fit_model"], color="tab:red", lw=1.2, label="gaussian fit")
        ax.set_xlabel(summary["axis_label"])
        ax.set_ylabel(summary["flux_label"])
        ax.set_title(path.name)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        print(f"Saved plot: {out.resolve()}")

    if args.trace_plot and diagnostic is not None:
        out = Path(args.trace_plot)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig = plt.figure(figsize=(7.5, 3.8))
        ax = fig.add_subplot(111)
        profile = np.asarray(diagnostic["spatial_profile"], dtype=float)
        rows = np.arange(profile.size)
        ax.plot(rows, profile, lw=1.2, color="tab:blue")
        ax.axvline(diagnostic["trace_row"], color="tab:red", lw=1.0, label="trace row")
        ax.axvspan(diagnostic["extract_from_row"], diagnostic["extract_to_row"], color="tab:orange", alpha=0.2, label="extraction window")
        ax.set_xlabel("Spatial row")
        ax.set_ylabel("Median signal")
        ax.set_title(f"2D extraction diagnostic: {path.name}")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        print(f"Saved trace plot: {out.resolve()}")

    if args.html_report:
        out = Path(args.html_report)
        try:
            import plotly.graph_objects as go
        except Exception as exc:
            summary["html_report_skipped"] = f"{exc.__class__.__name__}: {exc}"
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            fig = go.Figure()
            fig.add_scatter(x=wavelength, y=display_flux, mode="lines", name="flux")
            fig.add_scatter(x=wavelength, y=display_continuum, mode="lines", name="continuum")
            if "line_fit" in summary:
                fit = summary["line_fit"]
                fig.add_scatter(x=fit["fit_x"], y=fit["fit_model"], mode="lines", name="gaussian fit")
            fig.update_layout(title=path.name, xaxis_title=summary["axis_label"], yaxis_title=summary["flux_label"])
            fig.write_html(out, include_plotlyjs="cdn")
            summary["html_report"] = str(out.resolve())
            print(f"Saved HTML report: {out.resolve()}")

    if args.output_table:
        export = Table()
        export["wavelength"] = wavelength
        export["flux"] = flux
        export["continuum"] = continuum
        export["normalized_flux"] = normalized_flux
        export["residual"] = residual
        if error is not None:
            export["flux_error"] = error
            export["normalized_error"] = normalized_error
        if diagnostic is not None and "background" in diagnostic:
            export["background"] = np.asarray(diagnostic["background"], dtype=float)
        out = Path(args.output_table)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_table_any(export, out)
        print(f"Saved table: {out.resolve()}")

    if args.summary_json:
        out = Path(args.summary_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        qa_findings = []
        if summary.get("snr_proxy") is not None and summary["snr_proxy"] < 5:
            qa_findings.append("low_snr_proxy")
        if args.optimal_extraction:
            qa_findings.append("experimental_profile_weighted_extraction_not_iterative_horne")
        equivalent_width_findings, equivalent_width_metrics = equivalent_width_qa(summary)
        qa_findings.extend(equivalent_width_findings)
        payload = build_tool_payload(
            "spectral_workbench",
            status="warning" if qa_findings else "ok",
            notes=[
                "Spectral diagnostics are first-pass measurements; continuum windows, calibration, and line IDs still need domain review.",
            ],
            artifacts={
                "summary_json": str(out),
                "output_table": args.output_table,
                "plot": args.plot,
                "trace_plot": args.trace_plot,
                "html_report": args.html_report,
                "all_orders_dir": summary.get("all_orders_dir"),
            },
            results=summary,
            qa={
                "status": "warning" if qa_findings else "ok",
                "findings": qa_findings,
                "metrics": {
                    "sample_count": summary.get("count"),
                    "snr_proxy": summary.get("snr_proxy"),
                    "order_count": len(summary.get("all_orders") or []),
                    **equivalent_width_metrics,
                },
            },
            legacy=summary,
        )
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
        print(f"Saved summary: {out.resolve()}")
    if args.manifest_json:
        from _internal.provenance_utils import write_manifest

        outputs = [item for item in [args.output_table, args.trace_plot, args.plot, args.summary_json, args.html_report] if item]
        outputs.extend(extra_outputs)
        write_manifest(
            args.manifest_json,
            inputs=[path] + ([args.calibration_table] if args.calibration_table else []),
            outputs=outputs,
            parameters={
                "normalize": args.normalize,
                "optimal_extraction": args.optimal_extraction,
                "order_count": args.order_count,
                "order_index": args.order_index,
            },
            command="spectral_workbench.py",
        )
        print(f"Saved manifest: {Path(args.manifest_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
