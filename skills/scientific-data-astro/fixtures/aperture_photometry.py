#!/usr/bin/env python3
"""Measure simple circular aperture photometry on FITS images."""

import argparse
import csv
import json
import math
from pathlib import Path

from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload_best_effort


QUALITY_MESSAGES = {
    "non_positive_net_flux": "Net flux is non-positive. Only positive net flux contributes to source Poisson variance.",
    "aperture_truncated": "The aperture crosses the image boundary. Its flux is incomplete.",
    "annulus_truncated": "The background annulus crosses the image boundary.",
    "aperture_nonfinite": "Non-finite pixels were omitted from the aperture. The flux was not scaled to replace them.",
    "annulus_nonfinite": "Non-finite pixels were omitted from the background annulus.",
    "zero_sky_scatter": "The selected annulus has zero measured scatter. The error estimate may be optimistic.",
    "uncertainty_gain_unavailable": "Total uncertainty is unavailable without an explicit ADU gain in electrons per ADU.",
    "uncertainty_units_unavailable": "Total uncertainty is unavailable because the image does not declare supported count units.",
    "uncertainty_zero_variance": "Total uncertainty is unavailable because the modeled variance is zero.",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fits_path", help="Input FITS image.")
    parser.add_argument("--extension", help="Extension index or EXTNAME.")
    parser.add_argument("--center", nargs=2, type=float, metavar=("X", "Y"), action="append", help="Aperture center in pixel coordinates. Repeat for multiple apertures.")
    parser.add_argument("--positions-file", help="CSV/TXT file with x,y columns.")
    parser.add_argument("--radius", type=float, default=5.0, help="Aperture radius in pixels.")
    parser.add_argument("--annulus-inner", type=float, default=8.0, help="Inner background annulus radius in pixels.")
    parser.add_argument("--annulus-outer", type=float, default=12.0, help="Outer background annulus radius in pixels.")
    parser.add_argument("--auto-brightest", type=int, default=0, help="Auto-select the brightest N pixels as seed positions.")
    parser.add_argument("--units", choices=("electrons", "adu"), help="Count units when the FITS HDU has no BUNIT.")
    parser.add_argument("--gain", type=float, help="Positive gain in electrons per ADU for an ADU image.")
    parser.add_argument("--output-csv", help="Optional CSV output path.")
    parser.add_argument("--output-json", help="Optional JSON output path.")
    parser.add_argument("--summary-json", help="Optional standard-envelope JSON summary path.")
    return parser.parse_args()


def load_dependencies():
    import numpy as np
    from astropy.io import fits

    return np, fits


def choose_hdu(hdus, extension):
    if extension is None:
        for idx, hdu in enumerate(hdus):
            if getattr(hdu, "data", None) is not None and getattr(hdu.data, "ndim", 0) >= 2:
                return idx
        raise SystemExit("No image HDU found.")
    if extension.isdigit():
        return int(extension)
    for idx, hdu in enumerate(hdus):
        if str(hdu.name).strip().lower() == extension.strip().lower():
            return idx
    raise SystemExit(f"Could not find extension '{extension}'.")


def first_2d_plane(data, np):
    arr = np.asarray(data)
    while arr.ndim > 2:
        arr = arr[0]
    if arr.ndim != 2:
        raise SystemExit("Selected HDU does not contain a 2D image plane.")
    return arr.astype(float, copy=False)


def load_positions(path):
    positions = []
    with open(path, "r", errors="replace") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames and {"x", "y"} <= set(name.strip().lower() for name in reader.fieldnames):
            for row in reader:
                lowered = {k.strip().lower(): v for k, v in row.items()}
                positions.append((float(lowered["x"]), float(lowered["y"])))
        else:
            fh.seek(0)
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) >= 2:
                    positions.append((float(parts[0]), float(parts[1])))
    return positions


def dedupe_positions(np, candidates, min_sep=8.0):
    kept = []
    for x, y in candidates:
        if all(np.hypot(x - px, y - py) >= min_sep for px, py in kept):
            kept.append((x, y))
    return kept


def brightest_positions(np, data, n, margin=20):
    work = np.asarray(data, dtype=float).copy()
    if margin > 0 and min(work.shape) > 2 * margin:
        work[:margin, :] = np.nan
        work[-margin:, :] = np.nan
        work[:, :margin] = np.nan
        work[:, -margin:] = np.nan
    finite = np.isfinite(work)
    if not np.any(finite):
        return []
    flat_finite = np.flatnonzero(finite)
    intensities = work.ravel()[flat_finite]
    candidate_count = min(n * 20, flat_finite.size)
    flat_indices = flat_finite[np.argpartition(intensities, -candidate_count)[-candidate_count:]]
    coords = []
    for flat_index in flat_indices:
        y, x = np.unravel_index(flat_index, safe.shape)
        coords.append((work[y, x], float(x), float(y)))
    coords.sort(key=lambda item: item[2], reverse=True)
    coords.sort(key=lambda item: item[0], reverse=True)
    return dedupe_positions(np, [(x, y) for _, x, y in coords], min_sep=10.0)[:n]


def local_centroid(np, data, x, y, box_size=9):
    half = box_size // 2
    x0 = max(0, int(round(x)) - half)
    x1 = min(data.shape[1], int(round(x)) + half + 1)
    y0 = max(0, int(round(y)) - half)
    y1 = min(data.shape[0], int(round(y)) + half + 1)
    stamp = data[y0:y1, x0:x1]
    finite = np.isfinite(stamp)
    if not np.any(finite):
        return x, y
    yy, xx = np.indices(stamp.shape)
    weights = np.where(finite, np.maximum(stamp - np.median(stamp[finite]), 0.0), 0.0)
    if np.sum(weights) <= 0:
        return x, y
    xc = x0 + float(np.sum(xx * weights) / np.sum(weights))
    yc = y0 + float(np.sum(yy * weights) / np.sum(weights))
    return xc, yc


def circular_masks(np, shape, x, y, radius, inner, outer):
    yy, xx = np.indices(shape)
    rr = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    aperture = rr <= radius
    annulus = (rr >= inner) & (rr <= outer)
    return aperture, annulus


def validate_aperture_geometry(radius: float, inner: float, outer: float) -> None:
    values = (float(radius), float(inner), float(outer))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Aperture and annulus radii must be finite.")
    if radius <= 0:
        raise ValueError("Aperture radius must be positive.")
    if inner <= radius:
        raise ValueError("Background annulus inner radius must be larger than the aperture radius.")
    if outer <= inner:
        raise ValueError("Background annulus outer radius must be larger than its inner radius.")


def measurement_units(bunit, explicit_units, gain):
    declared = str(bunit or "").strip() or None
    normalized = (declared or "").casefold()
    header_units = None
    if normalized in {"e-", "e−", "electron", "electrons"}:
        header_units = "electrons"
    elif normalized == "adu":
        header_units = "adu"
    if explicit_units and declared and explicit_units != header_units:
        raise ValueError("--units cannot override the selected HDU's BUNIT.")
    resolved = header_units or explicit_units
    if gain is not None:
        if not math.isfinite(gain) or gain <= 0:
            raise ValueError("--gain must be finite and positive, in electrons per ADU.")
        if resolved != "adu":
            raise ValueError("--gain requires an ADU image. Declare --units adu for a unitless FITS HDU.")
    unit = {"electrons": "electron", "adu": "ADU"}.get(resolved)
    return declared, unit, 1.0 if resolved == "electrons" else gain


def measure_one(np, data, x, y, radius, inner, outer, *, flux_unit=None, effective_gain=None):
    validate_aperture_geometry(radius, inner, outer)
    rows, columns = data.shape
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < columns and 0 <= y < rows):
        raise ValueError("Aperture center must be finite and inside the selected image.")
    xc, yc = local_centroid(np, data, x, y)
    aperture, annulus = circular_masks(np, data.shape, xc, yc, radius, inner, outer)
    aperture_values = data[aperture]
    sky_values = data[annulus]
    finite_sky = sky_values[np.isfinite(sky_values)]
    finite_aperture = aperture_values[np.isfinite(aperture_values)]
    annulus_pixels = int(np.sum(annulus))
    aperture_pixels = int(np.sum(aperture))
    minimum_sky_pixels = max(5, int(math.ceil(0.25 * annulus_pixels)))
    if finite_sky.size < minimum_sky_pixels:
        raise ValueError(
            f"Background annulus has insufficient finite coverage: {finite_sky.size}/{annulus_pixels} pixels."
        )
    if finite_aperture.size == 0 or finite_aperture.size < math.ceil(0.5 * aperture_pixels):
        raise ValueError(
            f"Aperture has insufficient finite coverage: {finite_aperture.size}/{aperture_pixels} pixels."
        )
    sky_median = float(np.median(finite_sky))
    sky_rms = float(np.std(finite_sky, ddof=1))
    n_ap = int(finite_aperture.size)
    n_sky = int(finite_sky.size)
    raw_flux = float(np.sum(finite_aperture))
    net_flux = raw_flux - sky_median * n_ap
    sky_variance = sky_rms**2
    background_aperture_variance = n_ap * sky_variance
    background_median_variance = (math.pi / 2) * n_ap**2 * sky_variance / n_sky
    background_variance = background_aperture_variance + background_median_variance
    source_variance = max(net_flux, 0.0) / effective_gain if effective_gain is not None else None
    total_variance = source_variance + background_variance if source_variance is not None else None
    numbers = [raw_flux, net_flux, sky_median, sky_rms, background_variance]
    if total_variance is not None:
        numbers.append(total_variance)
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("Aperture flux or variance is outside the finite numeric range.")

    edge_distance = min(xc + 0.5, yc + 0.5, columns - 0.5 - xc, rows - 0.5 - yc)
    flags = []
    if radius > edge_distance:
        flags.append("aperture_truncated")
    if outer > edge_distance:
        flags.append("annulus_truncated")
    if n_ap < aperture_pixels:
        flags.append("aperture_nonfinite")
    if n_sky < annulus_pixels:
        flags.append("annulus_nonfinite")
    if sky_rms == 0:
        flags.append("zero_sky_scatter")
    if net_flux <= 0:
        flags.append("non_positive_net_flux")
    if total_variance is None:
        flags.append("uncertainty_gain_unavailable" if flux_unit == "ADU" else "uncertainty_units_unavailable")
    elif total_variance == 0:
        flags.append("uncertainty_zero_variance")
    return {
        "x_input": float(x),
        "y_input": float(y),
        "x_centroid": xc,
        "y_centroid": yc,
        "aperture_radius": float(radius),
        "annulus_inner": float(inner),
        "annulus_outer": float(outer),
        "n_aperture_pixels": n_ap,
        "n_annulus_pixels": n_sky,
        "aperture_finite_fraction": float(finite_aperture.size / aperture_pixels),
        "annulus_finite_fraction": float(finite_sky.size / annulus_pixels),
        "raw_flux": raw_flux,
        "sky_median": sky_median,
        "sky_rms": sky_rms,
        "net_flux": net_flux,
        "flux_unit": flux_unit,
        "variance_unit": f"{flux_unit}^2" if flux_unit else None,
        "source_poisson_variance": source_variance,
        "background_aperture_variance": background_aperture_variance,
        "background_median_variance": background_median_variance,
        "background_uncertainty": math.sqrt(background_variance),
        "uncertainty": math.sqrt(total_variance) if total_variance else None,
        "quality_flags": flags,
    }


def run_workbench(args) -> int:
    try:
        validate_aperture_geometry(args.radius, args.annulus_inner, args.annulus_outer)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    np, fits = load_dependencies()

    positions = []
    if args.center:
        positions.extend((float(x), float(y)) for x, y in args.center)
    if args.positions_file:
        positions.extend(load_positions(args.positions_file))

    with fits.open(args.fits_path, mode="readonly") as hdus:
        idx = choose_hdu(hdus, args.extension)
        data = first_2d_plane(hdus[idx].data, np)
        bunit, flux_unit, effective_gain = measurement_units(hdus[idx].header.get("BUNIT"), args.units, args.gain)

    if args.auto_brightest > 0:
        positions.extend(brightest_positions(np, data, args.auto_brightest))
    positions = dedupe_positions(np, positions)
    if not positions:
        raise SystemExit("No positions provided. Use --center, --positions-file, or --auto-brightest.")

    try:
        results = [
            measure_one(
                np, data, x, y, args.radius, args.annulus_inner, args.annulus_outer,
                flux_unit=flux_unit, effective_gain=effective_gain,
            )
            for x, y in positions
        ]
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    for aperture_index, result in enumerate(results, start=1):
        error = result["uncertainty"]
        uncertainty = f"{error:.6g}" if error is not None else "unavailable"
        unit = result["flux_unit"] or "native pixel-value sum"
        print(
            f"[{aperture_index}] x={result['x_centroid']:.3f}, y={result['y_centroid']:.3f}, "
            f"net_flux={result['net_flux']:.6g} ({unit}), uncertainty={uncertainty}"
        )
        for flag in result["quality_flags"]:
            print(f"    {QUALITY_MESSAGES[flag]}")

    if args.output_csv:
        out = Path(args.output_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows({**row, "quality_flags": json.dumps(row["quality_flags"])} for row in results)
        print(f"Saved CSV: {out.resolve()}")

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
        print(f"Saved JSON: {out.resolve()}")

    if args.summary_json:
        out = Path(args.summary_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        findings = [
            {"aperture_index": index, "finding": flag, "message": f"Aperture {index}: {QUALITY_MESSAGES[flag]}"}
            for index, row in enumerate(results, start=1) for flag in row["quality_flags"]
        ]
        payload = build_tool_payload(
            "aperture_photometry",
            status="warning" if findings else "ok",
            notes=[
                "The flux is the sum of finite aperture pixels minus the annulus median times their count. Coordinates use zero-based pixel centers.",
                "Background variance includes independent aperture scatter and a finite-annulus median term with the Gaussian approximation.",
                "The source Poisson term uses the positive net flux and the effective gain. The model excludes pixel correlations, gain error, and calibration systematics.",
            ],
            artifacts={"output_csv": args.output_csv, "output_json": args.output_json, "summary_json": str(out)},
            results={
                "fits_path": str(Path(args.fits_path).resolve()), "hdu_index": idx,
                "image_bunit": bunit, "declared_units": args.units, "flux_unit": flux_unit,
                "effective_gain_electrons_per_unit": effective_gain,
                "apertures": results, "aperture_count": len(results),
            },
            qa={
                "status": "warning" if findings else "ok",
                "findings": findings,
                "metrics": {"aperture_count": len(results)},
            },
            legacy={"fits_path": str(Path(args.fits_path).resolve()), "results": results},
            inputs=[args.fits_path, *([args.positions_file] if args.positions_file else [])],
        )
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
        print(f"Saved summary: {out.resolve()}")
    return 0


def emit_blocked(args, message: str) -> int:
    payload = build_blocked_payload(
        "aperture_photometry",
        message,
        notes=[
            "Aperture photometry stopped before measurements were published.",
            "The source FITS file was not modified.",
        ],
        artifacts={
            "summary_json": args.summary_json,
            "output_csv": args.output_csv,
            "output_json": args.output_json,
        },
        results={"fits_path": str(Path(args.fits_path).expanduser().resolve())},
        inputs=[Path(args.fits_path)],
    )
    emit_payload_best_effort(payload, args.summary_json)
    return 2


def main() -> int:
    args = parse_args()
    try:
        return run_workbench(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_blocked(args, str(exc) or "Aperture photometry was blocked.")
    except Exception as exc:
        return emit_blocked(args, f"Aperture photometry was blocked: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
