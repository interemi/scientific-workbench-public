#!/usr/bin/env python3
"""Measure simple circular aperture photometry on FITS images."""

import argparse
import csv
import json
import math
from pathlib import Path

from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload_best_effort


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
    safe = np.where(finite, work, -np.inf)
    flat_indices = np.argpartition(safe.ravel(), -max(n * 20, n))[-max(n * 20, n):]
    coords = []
    for flat_index in flat_indices:
        y, x = np.unravel_index(flat_index, safe.shape)
        coords.append((safe[y, x], float(x), float(y)))
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
    yy, xx = np.indices(stamp.shape)
    weights = np.clip(stamp - np.nanmedian(stamp), a_min=0.0, a_max=None)
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


def measure_one(np, data, x, y, radius, inner, outer):
    validate_aperture_geometry(radius, inner, outer)
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
    sky_rms = float(np.std(finite_sky))
    n_ap = int(finite_aperture.size)
    raw_flux = float(np.sum(finite_aperture))
    net_flux = raw_flux - sky_median * n_ap
    uncertainty = float(np.sqrt(max(abs(net_flux), 0.0) + n_ap * sky_rms**2))
    return {
        "x_input": float(x),
        "y_input": float(y),
        "x_centroid": xc,
        "y_centroid": yc,
        "aperture_radius": float(radius),
        "annulus_inner": float(inner),
        "annulus_outer": float(outer),
        "n_aperture_pixels": n_ap,
        "aperture_finite_fraction": float(finite_aperture.size / aperture_pixels),
        "annulus_finite_fraction": float(finite_sky.size / annulus_pixels),
        "raw_flux": raw_flux,
        "sky_median": sky_median,
        "sky_rms": sky_rms,
        "net_flux": net_flux,
        "uncertainty": uncertainty,
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

    with fits.open(args.fits_path) as hdus:
        idx = choose_hdu(hdus, args.extension)
        data = first_2d_plane(hdus[idx].data, np)

    if args.auto_brightest > 0:
        positions.extend(brightest_positions(np, data, args.auto_brightest))
    positions = dedupe_positions(np, positions)
    if not positions:
        raise SystemExit("No positions provided. Use --center, --positions-file, or --auto-brightest.")

    try:
        results = [
            measure_one(np, data, x, y, args.radius, args.annulus_inner, args.annulus_outer)
            for x, y in positions
        ]
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    for idx, result in enumerate(results, start=1):
        print(
            f"[{idx}] x={result['x_centroid']:.3f}, y={result['y_centroid']:.3f}, "
            f"net_flux={result['net_flux']:.6g}, uncertainty={result['uncertainty']:.6g}"
        )

    if args.output_csv:
        out = Path(args.output_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print(f"Saved CSV: {out.resolve()}")

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
        print(f"Saved JSON: {out.resolve()}")

    if args.summary_json:
        out = Path(args.summary_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        findings = []
        for idx, result in enumerate(results, start=1):
            if result.get("net_flux", 0) <= 0:
                findings.append({"aperture_index": idx, "finding": "non_positive_net_flux"})
        payload = build_tool_payload(
            "aperture_photometry",
            status="warning" if findings else "ok",
            notes=[
                "Simple circular aperture photometry: use as a first pass, not as a full calibrated photometric reduction.",
            ],
            artifacts={"output_csv": args.output_csv, "output_json": args.output_json, "summary_json": str(out)},
            results={"fits_path": str(Path(args.fits_path).resolve()), "apertures": results, "aperture_count": len(results)},
            qa={
                "status": "warning" if findings else "ok",
                "findings": findings,
                "metrics": {"aperture_count": len(results)},
            },
            legacy={"fits_path": str(Path(args.fits_path).resolve()), "results": results},
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
