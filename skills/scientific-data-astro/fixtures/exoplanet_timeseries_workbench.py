#!/usr/bin/env python3
"""Reduce and analyze exoplanet-style time-series FITS sequences with QA and reporting."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from _internal.provenance_utils import environment_summary, write_manifest
from _internal.runtime_common import configure_runtime


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="FITS files or directories containing a time-series sequence and optional calibrations.")
    parser.add_argument("--object", dest="object_name", help="Target object name to select science frames.")
    parser.add_argument("--reference-frame", help="Optional reference frame filename.")
    parser.add_argument("--target-label", help="Optional detected source label to force as target.")
    parser.add_argument("--target-center", nargs=2, type=float, metavar=("X", "Y"), help="Optional target center in pixels.")
    parser.add_argument("--comparison-label", action="append", default=[], help="Optional detected source label to force as comparison.")
    parser.add_argument("--aperture-radii", nargs="+", type=float, default=[5.0, 7.0, 9.0, 11.0], help="Aperture radii to test. Default: 5 7 9 11")
    parser.add_argument("--annulus-inner-scale", type=float, default=1.7, help="Inner annulus radius scale relative to aperture radius.")
    parser.add_argument("--annulus-outer-scale", type=float, default=2.7, help="Outer annulus radius scale relative to aperture radius.")
    parser.add_argument("--max-sources", type=int, default=12, help="Maximum number of candidate sources to track.")
    parser.add_argument("--comparison-count", type=int, default=3, help="Number of comparison stars to use when auto-selecting.")
    parser.add_argument("--output-dir", required=True, help="Directory for products, reports, and optional reduced frames.")
    parser.add_argument("--skip-reduced-fits", action="store_true", help="Do not write per-frame reduced FITS products.")
    parser.add_argument("--summary-json", help="Optional summary JSON path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


@dataclass
class Source:
    label: str
    x: float
    y: float
    brightness: float
    distance_to_center: float


def load_dependencies():
    configure_runtime("exoplanet_timeseries_workbench")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.io import fits
    from astropy.time import Time
    from scipy.ndimage import gaussian_filter, maximum_filter

    return plt, np, fits, Time, gaussian_filter, maximum_filter


def iter_fits_paths(inputs: list[str]) -> list[Path]:
    paths = []
    seen = set()
    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() in {".fits", ".fit", ".fts", ".fz"}:
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path.resolve())
            continue
        if not path.is_dir():
            continue
        for item in sorted(path.rglob("*")):
            if ".ipynb_checkpoints" in item.parts:
                continue
            if item.is_file() and item.suffix.lower() in {".fits", ".fit", ".fts", ".fz"}:
                resolved = str(item.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                paths.append(item.resolve())
    return paths


def normalize_name(value: str | None) -> str:
    text = (value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


FRAME_TYPE_ALIASES = {
    "bias": {"bias", "biasframe", "zero", "zeroframe", "offset", "offsetframe"},
    "dark": {"dark", "darkframe", "darkcurrent", "darkcurrentframe"},
    "flat": {
        "flat",
        "flatframe",
        "flatfield",
        "flatfieldframe",
        "domeflat",
        "skyflat",
        "twilightflat",
    },
    "lamp": {"lamp", "lampframe"},
    "arc": {"arc", "arcframe", "comparisonlamp"},
    "comp": {"comp", "compframe"},
    "science": {"science", "scienceframe", "light", "lightframe", "object", "objectframe", "target"},
}


def canonical_frame_type(value: str | None) -> str:
    normalized = normalize_name(value)
    for canonical, aliases in FRAME_TYPE_ALIASES.items():
        if normalized in aliases:
            return canonical
    return normalized


def read_fits(fits, path: Path):
    with fits.open(path) as hdus:
        data = hdus[0].data.astype(float)
        header = hdus[0].header.copy()
    return data, header


def robust_sigma(np, values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 1.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    sigma = 1.4826 * mad
    return sigma if sigma > 0 else 1.0


def classify_frame(path: Path, header, data, Time):
    imagetyp = canonical_frame_type(header.get("IMAGETYP"))
    object_name = str(header.get("OBJECT", "")).strip()
    mjd = header.get("MJD-OBS")
    if mjd is None and header.get("DATE-OBS"):
        try:
            mjd = float(Time(header["DATE-OBS"], format="isot", scale="utc").mjd)
        except Exception:
            mjd = None
    return {
        "path": path,
        "name": path.name,
        "shape": tuple(int(x) for x in data.shape),
        "object_name": object_name,
        "object_norm": normalize_name(object_name),
        "imagetyp": imagetyp,
        "filter_id": str(
            header.get("INSFLID")
            or header.get("FILTER")
            or header.get("FILTNAME")
            or header.get("FILTNAM")
            or ""
        ).strip(),
        "exptime": float(header.get("EXPTIME", 0.0) or 0.0),
        "date_obs": header.get("DATE-OBS"),
        "mjd_obs": float(mjd) if mjd is not None else None,
        "airmass": float(header.get("AIRMASS", float("nan")) or float("nan")),
        "header": header,
        "raw": data,
    }


def choose_science_group(rows: list[dict], explicit_object: str | None):
    calibration_tags = {"bias", "flat", "dark", "lamp", "arc", "comp"}
    science = [row for row in rows if row["imagetyp"] not in calibration_tags]
    if not science:
        raise SystemExit("No non-calibration FITS frames were found.")
    if explicit_object:
        wanted = normalize_name(explicit_object)
        science = [row for row in science if row["object_norm"] == wanted]
        if not science:
            raise SystemExit(f"No science frames found for object {explicit_object!r}.")
        object_name = explicit_object
    else:
        counts = Counter(row["object_name"] or "[blank]" for row in science)
        object_name = counts.most_common(1)[0][0]
        object_norm = normalize_name(object_name if object_name != "[blank]" else "")
        science = [row for row in science if row["object_norm"] == object_norm]
    shape = Counter(row["shape"] for row in science).most_common(1)[0][0]
    science = [row for row in science if row["shape"] == shape]
    filter_counts = Counter(row["filter_id"] for row in science if row["filter_id"])
    preferred_filter = filter_counts.most_common(1)[0][0] if filter_counts else None
    if preferred_filter:
        filtered = [row for row in science if row["filter_id"] == preferred_filter]
        if filtered:
            science = filtered
    science = sorted(science, key=lambda row: (row["mjd_obs"] is None, row["mjd_obs"], row["name"]))
    return science, shape, preferred_filter, object_name


def pick_calibrations(rows: list[dict], shape: tuple[int, int], filter_id: str | None, median_science_exptime: float):
    biases = [row for row in rows if row["imagetyp"] == "bias" and row["shape"] == shape]
    darks = [row for row in rows if row["imagetyp"] == "dark" and row["shape"] == shape]
    darks = [
        row for row in darks if median_science_exptime <= 0 or row["exptime"] <= 0 or abs(row["exptime"] - median_science_exptime) <= max(5.0, 0.25 * median_science_exptime)
    ] or darks
    flats = []
    for row in rows:
        if row["imagetyp"] != "flat" or row["shape"] != shape:
            continue
        if filter_id and row["filter_id"] and row["filter_id"] != filter_id:
            continue
        median = float(row.get("median", float("nan")))
        saturated = int(row.get("saturated_pixels", 0))
        if math.isfinite(median) and 1000.0 <= median <= 60000.0 and saturated < max(1000, int(0.01 * shape[0] * shape[1])):
            flats.append(row)
    return biases, darks, flats


def build_master(np, rows: list[dict], method: str = "median"):
    if not rows:
        return None
    cube = np.stack([row["raw"] for row in rows], axis=0)
    return np.nanmedian(cube, axis=0) if method == "median" else np.nanmean(cube, axis=0)


def build_master_dark_rate(np, dark_rows: list[dict], master_bias):
    """Build a bias-subtracted dark-current image in detector units per second."""

    if not dark_rows:
        return None
    if master_bias is None:
        raise SystemExit(
            "Dark frames were found but no compatible bias frames are available; "
            "a raw dark cannot be exposure-scaled safely while it still contains the bias pedestal."
        )
    rates = []
    for row in dark_rows:
        exptime = float(row.get("exptime") or 0.0)
        if not math.isfinite(exptime) or exptime <= 0:
            raise SystemExit(f"Dark frame {row['name']} has no finite positive EXPTIME; dark-rate calibration is blocked.")
        rates.append((row["raw"] - master_bias) / exptime)
    return np.nanmedian(np.stack(rates, axis=0), axis=0)


def build_master_flat(np, flat_rows: list[dict], master_bias, master_dark_rate):
    if not flat_rows:
        return None, 0
    normalized = []
    for row in flat_rows:
        frame = row["raw"].copy()
        if master_bias is not None:
            frame = frame - master_bias
        if master_dark_rate is not None:
            exptime = float(row.get("exptime") or 0.0)
            if not math.isfinite(exptime) or exptime <= 0:
                raise SystemExit(f"Flat frame {row['name']} has no finite positive EXPTIME; scaled dark subtraction is blocked.")
            frame = frame - master_dark_rate * exptime
        frame[row["raw"] >= 65535] = np.nan
        median = float(np.nanmedian(frame))
        if not math.isfinite(median) or median <= 0:
            continue
        normalized.append(frame / median)
    if not normalized:
        return None, 0
    master_flat = np.nanmedian(np.stack(normalized, axis=0), axis=0)
    filled = int(np.sum(~np.isfinite(master_flat)))
    master_flat[~np.isfinite(master_flat)] = 1.0
    master_flat[master_flat <= 0] = 1.0
    master_flat /= float(np.nanmedian(master_flat))
    return master_flat, filled


def reduce_frame(np, row: dict, master_bias, master_dark_rate, master_flat):
    reduced = row["raw"].copy()
    history = []
    if master_bias is not None:
        reduced = reduced - master_bias
        history.append("bias")
    if master_dark_rate is not None:
        exptime = float(row.get("exptime") or 0.0)
        if not math.isfinite(exptime) or exptime <= 0:
            raise SystemExit(f"Science frame {row['name']} has no finite positive EXPTIME; scaled dark subtraction is blocked.")
        reduced = reduced - master_dark_rate * exptime
        history.append("dark_rate_scaled_by_exptime")
    if master_flat is not None:
        safe_flat = np.where(master_flat == 0, 1.0, master_flat)
        reduced = reduced / safe_flat
        history.append("flat")
    return reduced.astype(float), history


def detect_sources(np, gaussian_filter, maximum_filter, image, max_sources=12):
    smooth = gaussian_filter(image, 1.8)
    background = float(np.nanmedian(smooth))
    sigma = robust_sigma(np, smooth - background)
    mask = (smooth == maximum_filter(smooth, size=13)) & np.isfinite(smooth)
    mask &= smooth > background + 8.0 * sigma
    ys, xs = np.where(mask)
    strengths = smooth[ys, xs]
    order = np.argsort(strengths)[::-1]
    chosen = []
    cx = image.shape[1] / 2.0
    cy = image.shape[0] / 2.0
    for idx in order:
        x = float(xs[idx])
        y = float(ys[idx])
        if x < 40 or x > image.shape[1] - 40 or y < 40 or y > image.shape[0] - 40:
            continue
        if any(math.hypot(x - source.x, y - source.y) < 40.0 for source in chosen):
            continue
        chosen.append(Source(label=f"S{len(chosen) + 1}", x=x, y=y, brightness=float(strengths[idx]), distance_to_center=float(math.hypot(x - cx, y - cy))))
        if len(chosen) >= max_sources:
            break
    if not chosen:
        raise SystemExit("No suitable stars were detected in the reference frame.")
    return chosen


def local_centroid(np, data, x, y, box=11):
    half = box // 2
    xi = int(round(x))
    yi = int(round(y))
    x0 = max(0, xi - half)
    x1 = min(data.shape[1], xi + half + 1)
    y0 = max(0, yi - half)
    y1 = min(data.shape[0], yi + half + 1)
    stamp = data[y0:y1, x0:x1]
    if stamp.size == 0:
        return x, y
    yy, xx = np.indices(stamp.shape)
    baseline = float(np.nanmedian(stamp))
    weights = np.clip(stamp - baseline, a_min=0.0, a_max=None)
    norm = float(np.sum(weights))
    if not math.isfinite(norm) or norm <= 0:
        return x, y
    xc = x0 + float(np.sum(xx * weights) / norm)
    yc = y0 + float(np.sum(yy * weights) / norm)
    return xc, yc


def circular_masks(np, shape, x, y, radius, inner, outer):
    yy, xx = np.indices(shape)
    rr = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    return rr <= radius, (rr >= inner) & (rr <= outer)


def aperture_measure(np, reduced, raw, source: Source, radius: float, annulus_inner: float, annulus_outer: float):
    xc, yc = local_centroid(np, reduced, source.x, source.y, box=11)
    aperture, annulus = circular_masks(np, reduced.shape, xc, yc, radius, annulus_inner, annulus_outer)
    ap_values = reduced[aperture]
    ann_values = reduced[annulus]
    sky = float(np.nanmedian(ann_values)) if ann_values.size else 0.0
    sky_rms = float(np.nanstd(ann_values)) if ann_values.size else 0.0
    n_ap = int(np.sum(aperture))
    raw_flux = float(np.nansum(ap_values))
    net_flux = raw_flux - sky * n_ap
    uncertainty = float(np.sqrt(max(abs(net_flux), 0.0) + n_ap * sky_rms**2))
    saturated = int(np.sum(raw[aperture] >= 65535))
    return {
        "x_centroid": xc,
        "y_centroid": yc,
        "raw_flux": raw_flux,
        "net_flux": net_flux,
        "sky": sky,
        "sky_rms": sky_rms,
        "uncertainty": uncertainty,
        "saturated_pixels": saturated,
    }


def measure_series(np, reduced_rows: list[dict], sources: list[Source], radius: float, inner_scale: float, outer_scale: float):
    annulus_inner = radius * inner_scale
    annulus_outer = radius * outer_scale
    measurements = []
    for row in reduced_rows:
        frame_record = {
            "file": row["name"],
            "date_obs": row["date_obs"],
            "mjd_obs": row["mjd_obs"],
            "exptime": row["exptime"],
            "airmass": row["airmass"],
            "background_median": float(np.nanmedian(row["reduced"])),
            "background_sigma": float(robust_sigma(np, row["reduced"])),
            "frame_saturated_pixels": int(np.sum(row["raw"] >= 65535)),
            "sources": {},
        }
        for source in sources:
            frame_record["sources"][source.label] = aperture_measure(np, row["reduced"], row["raw"], source, radius, annulus_inner, annulus_outer)
        measurements.append(frame_record)
    return measurements


def choose_target_and_comparisons(np, sources: list[Source], measurements: list[dict], target_label: str | None, target_center: tuple[float, float] | None, comparison_labels: list[str], comparison_count: int):
    max_brightness = max(source.brightness for source in sources)
    diagnostics = []
    plausible_targets = []
    comparison_scores = []
    for source in sources:
        fluxes = np.array([frame["sources"][source.label]["net_flux"] for frame in measurements], dtype=float)
        saturated = np.array([frame["sources"][source.label]["saturated_pixels"] for frame in measurements], dtype=int)
        finite = np.isfinite(fluxes)
        if not np.any(finite):
            continue
        normalized = fluxes[finite] / np.nanmedian(fluxes[finite])
        scatter = 1.4826 * np.nanmedian(np.abs(normalized - np.nanmedian(normalized)))
        sat_fraction = float(np.mean(saturated > 0))
        diagnostics.append(
            {
                "label": source.label,
                "x": source.x,
                "y": source.y,
                "distance_to_center": source.distance_to_center,
                "brightness": source.brightness,
                "sat_fraction": sat_fraction,
                "scatter_norm": float(scatter),
                "is_target": False,
                "is_comparison": False,
            }
        )
        if sat_fraction <= 0.05 and source.brightness >= 0.2 * max_brightness:
            plausible_targets.append(source)
        if sat_fraction <= 0.05:
            comparison_scores.append((scatter, -source.brightness, source))
    if not plausible_targets:
        plausible_targets = list(sources)
    if target_label:
        target = next((source for source in sources if source.label == target_label), None)
        if target is None:
            raise SystemExit(f"Target label {target_label!r} was not detected.")
    elif target_center:
        tx, ty = target_center
        target = min(plausible_targets, key=lambda item: math.hypot(item.x - tx, item.y - ty))
    else:
        target = min(plausible_targets, key=lambda item: item.distance_to_center)
    if comparison_labels:
        comparisons = []
        for label in comparison_labels:
            match = next((source for source in sources if source.label == label), None)
            if match is None:
                raise SystemExit(f"Comparison label {label!r} was not detected.")
            if match.label != target.label:
                comparisons.append(match)
    else:
        comparison_scores = [item for item in comparison_scores if item[2].label != target.label]
        comparison_scores.sort(key=lambda item: (item[0], item[1]))
        comparisons = [item[2] for item in comparison_scores[: max(1, comparison_count)]]
    if not comparisons:
        raise SystemExit(
            "No se encontro ninguna estrella de comparacion valida. "
            "Indica --comparison-label, aumenta --max-sources o revisa deteccion/saturacion antes de producir curva diferencial."
        )
    for row in diagnostics:
        row["is_target"] = row["label"] == target.label
        row["is_comparison"] = any(row["label"] == source.label for source in comparisons)
    return target, comparisons, diagnostics


def build_light_curve(np, measurements: list[dict], target: Source, comparisons: list[Source]):
    if not comparisons:
        raise SystemExit("No hay estrellas de comparacion; se bloquea para evitar NaN en la curva diferencial.")
    rows = []
    valid_mjd = [frame["mjd_obs"] for frame in measurements if frame["mjd_obs"] is not None]
    first_mjd = float(valid_mjd[0]) if valid_mjd else None
    for idx, frame in enumerate(measurements):
        target_flux = float(frame["sources"][target.label]["net_flux"])
        comparison_fluxes = [float(frame["sources"][source.label]["net_flux"]) for source in comparisons]
        comparison_sum = float(np.sum(comparison_fluxes))
        differential = target_flux / comparison_sum if comparison_sum > 0 else float("nan")
        row = {
            "file": frame["file"],
            "date_obs": frame["date_obs"],
            "mjd_obs": frame["mjd_obs"],
            "frame_index": idx,
            "minutes_from_start": ((float(frame["mjd_obs"]) - first_mjd) * 24.0 * 60.0) if first_mjd is not None and frame["mjd_obs"] is not None else float(idx),
            "exptime": frame["exptime"],
            "airmass": frame["airmass"],
            "background_median": frame["background_median"],
            "background_sigma": frame["background_sigma"],
            "frame_saturated_pixels": frame["frame_saturated_pixels"],
            "target_flux": target_flux,
            "comparison_flux_sum": comparison_sum,
            "differential_flux": differential,
            "target_centroid_x": float(frame["sources"][target.label]["x_centroid"]),
            "target_centroid_y": float(frame["sources"][target.label]["y_centroid"]),
            "target_saturated_pixels": frame["sources"][target.label]["saturated_pixels"],
            "comparison_saturated_pixels": int(sum(frame["sources"][source.label]["saturated_pixels"] for source in comparisons)),
        }
        rows.append(row)
    finite_differentials = [row["differential_flux"] for row in rows if math.isfinite(row["differential_flux"])]
    if not finite_differentials:
        raise SystemExit(
            "No hay flujo diferencial finito: la suma de comparacion es no positiva o no finita en todos los frames."
        )
    scale = float(np.nanmedian(finite_differentials))
    if not math.isfinite(scale) or scale <= 0:
        raise SystemExit("La escala de normalizacion de la curva diferencial no es finita o no positiva.")
    for row in rows:
        row["normalized_flux"] = row["differential_flux"] / scale if scale and math.isfinite(row["differential_flux"]) else float("nan")
    return rows


def assess_light_curve_quality(np, rows: list[dict]):
    normalized = np.array([row["normalized_flux"] for row in rows], dtype=float)
    finite_normalized = normalized[np.isfinite(normalized)]
    if finite_normalized.size == 0:
        raise SystemExit("No hay puntos normalizados finitos; se bloquea para no emitir QA con NaN.")
    centroid_x = np.array([row["target_centroid_x"] for row in rows], dtype=float)
    centroid_y = np.array([row["target_centroid_y"] for row in rows], dtype=float)
    bg = np.array([row["background_sigma"] for row in rows], dtype=float)
    normalized_median = float(np.nanmedian(finite_normalized))
    flux_sigma = robust_sigma(np, finite_normalized - normalized_median)
    cx_med = float(np.nanmedian(centroid_x))
    cy_med = float(np.nanmedian(centroid_y))
    bg_med = float(np.nanmedian(bg))
    evaluated = []
    rejected = []
    for row in rows:
        flags = []
        centroid_offset = float(math.hypot(row["target_centroid_x"] - cx_med, row["target_centroid_y"] - cy_med))
        if row["target_saturated_pixels"] > 0 or row["comparison_saturated_pixels"] > 0:
            flags.append("saturation")
        if not math.isfinite(row["normalized_flux"]):
            flags.append("nonfinite_flux")
        elif flux_sigma > 0 and abs(row["normalized_flux"] - normalized_median) > 5.0 * flux_sigma:
            flags.append("flux_outlier")
        if centroid_offset > 2.5:
            flags.append("centroid_drift")
        if bg_med > 0 and row["background_sigma"] > 1.8 * bg_med:
            flags.append("background_noise")
        enriched = row.copy()
        enriched["target_centroid_offset"] = centroid_offset
        enriched["quality_flags"] = flags
        enriched["accepted"] = len(flags) == 0
        evaluated.append(enriched)
        if flags:
            rejected.append({"file": row["file"], "flags": flags})
    accepted = [row for row in evaluated if row["accepted"]]
    accepted_flux = np.array([row["normalized_flux"] for row in accepted], dtype=float) if accepted else np.array([], dtype=float)
    qa = {
        "frame_count": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "normalized_flux_median": normalized_median,
        "normalized_flux_sigma": float(flux_sigma),
        "accepted_rms": float(np.nanstd(accepted_flux)) if accepted_flux.size else None,
        "accepted_mad": float(1.4826 * np.nanmedian(np.abs(accepted_flux - np.nanmedian(accepted_flux)))) if accepted_flux.size else None,
        "target_centroid_median": [cx_med, cy_med],
        "background_sigma_median": bg_med,
        "rejected_frames": rejected,
    }
    return evaluated, qa


def radius_scan(np, reduced_rows, sources, target_label, target_center, comparison_labels, comparison_count, radii, inner_scale, outer_scale):
    selection_radius = radii[len(radii) // 2]
    selection_measurements = measure_series(np, reduced_rows, sources, selection_radius, inner_scale, outer_scale)
    target, comparisons, diagnostics = choose_target_and_comparisons(np, sources, selection_measurements, target_label, target_center, comparison_labels, comparison_count)
    results = []
    best = None
    for radius in radii:
        measurements = measure_series(np, reduced_rows, sources, radius, inner_scale, outer_scale)
        light_curve = build_light_curve(np, measurements, target, comparisons)
        evaluated, qa = assess_light_curve_quality(np, light_curve)
        result = {
            "radius": float(radius),
            "accepted_count": qa["accepted_count"],
            "accepted_rms": qa["accepted_rms"],
            "accepted_mad": qa["accepted_mad"],
            "target_label": target.label,
            "comparison_labels": [source.label for source in comparisons],
        }
        results.append(result)
        score = (qa["accepted_rms"] if qa["accepted_rms"] is not None else float("inf"), -qa["accepted_count"])
        if best is None or score < best[0]:
            best = (score, radius, measurements, evaluated, qa)
    assert best is not None
    return {
        "target": target,
        "comparisons": comparisons,
        "diagnostics": diagnostics,
        "radius_results": results,
        "best_radius": float(best[1]),
        "best_measurements": best[2],
        "best_light_curve": best[3],
        "best_qa": best[4],
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            for key, value in list(normalized.items()):
                if isinstance(value, list):
                    normalized[key] = ",".join(str(item) for item in value)
            writer.writerow(normalized)


def save_source_map(plt, np, path: Path, image, sources: list[Source], target: Source, comparisons: list[Source]):
    fig, ax = plt.subplots(figsize=(8, 8))
    vmin = float(np.nanpercentile(image, 5))
    vmax = float(np.nanpercentile(image, 99.5))
    ax.imshow(image, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
    comparison_labels = {source.label for source in comparisons}
    for source in sources:
        if source.label == target.label:
            color = "tab:red"
        elif source.label in comparison_labels:
            color = "tab:green"
        else:
            color = "tab:cyan"
        ax.scatter([source.x], [source.y], s=80, facecolors="none", edgecolors=color, linewidths=1.6)
        ax.text(source.x + 6, source.y + 6, source.label, color=color, fontsize=9)
    ax.set_title("Detected field sources")
    ax.set_xlabel("X [pix]")
    ax.set_ylabel("Y [pix]")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_lightcurve_plot(plt, path: Path, light_curve: list[dict]):
    accepted = [row for row in light_curve if row["accepted"]]
    rejected = [row for row in light_curve if not row["accepted"]]
    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 9), sharex=True)
    if accepted:
        axes[0].plot([row["minutes_from_start"] for row in accepted], [row["normalized_flux"] for row in accepted], "-o", ms=4, lw=1.0, color="tab:blue", label="accepted")
    if rejected:
        axes[0].scatter([row["minutes_from_start"] for row in rejected], [row["normalized_flux"] for row in rejected], marker="x", color="tab:red", label="rejected")
    axes[0].set_ylabel("Normalized flux")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.25)

    axes[1].plot([row["minutes_from_start"] for row in light_curve], [row["airmass"] for row in light_curve], "-o", ms=3, color="tab:orange")
    axes[1].set_ylabel("Airmass")
    axes[1].grid(alpha=0.25)

    axes[2].plot([row["minutes_from_start"] for row in light_curve], [row["target_centroid_offset"] for row in light_curve], "-o", ms=3, color="tab:green")
    axes[2].set_ylabel("Centroid offset [pix]")
    axes[2].set_xlabel("Minutes from start")
    axes[2].grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_report(path: Path, summary: dict):
    lines = [
        "# Exoplanet Time-Series Report",
        "",
        f"- Target object: `{summary['object_name']}`",
        f"- Science frames: `{summary['science_frame_count']}`",
        f"- Science shape: `{summary['science_shape'][1]}x{summary['science_shape'][0]}`",
        f"- Preferred filter: `{summary['science_filter'] or 'unknown'}`",
        f"- Best aperture radius: `{summary['best_aperture_radius']}` px",
        f"- Target source: `{summary['target_label']}`",
        f"- Comparison sources: `{', '.join(summary['comparison_labels'])}`",
        f"- Accepted frames: `{summary['qa']['accepted_count']}/{summary['qa']['frame_count']}`",
        f"- Accepted RMS: `{summary['qa']['accepted_rms']}`",
        f"- Accepted MAD: `{summary['qa']['accepted_mad']}`",
        "",
        "## Calibration Audit",
        "",
        f"- Bias frames: `{summary['calibration']['bias_count']}`",
        f"- Dark frames: `{summary['calibration']['dark_count']}`",
        f"- Flat frames: `{summary['calibration']['flat_count']}`",
        f"- Compatible flat available: `{summary['calibration']['has_compatible_flat']}`",
        f"- Master flat filled pixels: `{summary['calibration']['master_flat_filled_pixels']}`",
        "",
        "## Radius Scan",
        "",
    ]
    for item in summary["radius_scan"]:
        lines.append(
            f"- Radius `{item['radius']}` px -> accepted `{item['accepted_count']}`, RMS `{item['accepted_rms']}`, MAD `{item['accepted_mad']}`"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The workflow preserves raw FITS and works on derived products only.",
            "- Automatic target selection is operational unless the user pins a target label or pixel center.",
            "- Comparison-star selection prefers bright, unsaturated, low-scatter stars.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    plt, np, fits, Time, gaussian_filter, maximum_filter = load_dependencies()
    all_paths = iter_fits_paths(args.inputs)
    if not all_paths:
        raise SystemExit("No FITS files were found in the provided inputs.")

    rows = []
    for path in all_paths:
        data, header = read_fits(fits, path)
        row = classify_frame(path, header, data, Time)
        row["median"] = float(np.nanmedian(data))
        row["saturated_pixels"] = int(np.sum(data >= 65535))
        rows.append(row)

    science_rows, shape, filter_id, object_name = choose_science_group(rows, args.object_name)
    median_science_exptime = float(np.nanmedian([row["exptime"] for row in science_rows]))
    bias_rows, dark_rows, flat_rows = pick_calibrations(rows, shape, filter_id, median_science_exptime)
    master_bias = build_master(np, bias_rows)
    master_dark_rate = build_master_dark_rate(np, dark_rows, master_bias)
    master_flat, master_flat_filled_pixels = build_master_flat(np, flat_rows, master_bias, master_dark_rate)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reduced_dir = output_dir / "reduced_frames"
    if not args.skip_reduced_fits:
        reduced_dir.mkdir(parents=True, exist_ok=True)

    reduced_rows = []
    for row in science_rows:
        reduced, history = reduce_frame(np, row, master_bias, master_dark_rate, master_flat)
        item = dict(row)
        item["reduced"] = reduced
        item["reduction_steps"] = history
        reduced_rows.append(item)
        if not args.skip_reduced_fits:
            fits.PrimaryHDU(data=reduced.astype("float32"), header=row["header"]).writeto(
                reduced_dir / f"reduced_{row['name']}",
                overwrite=True,
                output_verify="ignore",
            )

    if args.reference_frame:
        reference = next((row for row in reduced_rows if row["name"] == args.reference_frame), None)
        if reference is None:
            raise SystemExit(f"Reference frame {args.reference_frame!r} was not found among the science frames.")
        reference_image = reference["reduced"]
    else:
        stack = np.stack([row["reduced"] for row in reduced_rows[: min(5, len(reduced_rows))]], axis=0)
        reference_image = np.nanmedian(stack, axis=0)

    sources = detect_sources(np, gaussian_filter, maximum_filter, reference_image, max_sources=args.max_sources)
    target_center = tuple(args.target_center) if args.target_center else None
    radius_result = radius_scan(
        np,
        reduced_rows,
        sources,
        args.target_label,
        target_center,
        args.comparison_label,
        args.comparison_count,
        sorted(set(float(radius) for radius in args.aperture_radii)),
        args.annulus_inner_scale,
        args.annulus_outer_scale,
    )
    target = radius_result["target"]
    comparisons = radius_result["comparisons"]
    diagnostics = radius_result["diagnostics"]
    light_curve = radius_result["best_light_curve"]
    qa = radius_result["best_qa"]

    source_map_path = output_dir / "source_map.png"
    light_curve_plot_path = output_dir / "light_curve.png"
    save_source_map(plt, np, source_map_path, reference_image, sources, target, comparisons)
    save_lightcurve_plot(plt, light_curve_plot_path, light_curve)

    diagnostics_csv = output_dir / "candidate_diagnostics.csv"
    radius_csv = output_dir / "radius_scan.csv"
    light_curve_csv = output_dir / "light_curve.csv"
    write_csv(diagnostics_csv, diagnostics, ["label", "x", "y", "distance_to_center", "brightness", "sat_fraction", "scatter_norm", "is_target", "is_comparison"])
    write_csv(radius_csv, radius_result["radius_results"], ["radius", "accepted_count", "accepted_rms", "accepted_mad", "target_label", "comparison_labels"])
    write_csv(
        light_curve_csv,
        light_curve,
        [
            "file",
            "date_obs",
            "mjd_obs",
            "frame_index",
            "minutes_from_start",
            "exptime",
            "airmass",
            "background_median",
            "background_sigma",
            "frame_saturated_pixels",
            "target_flux",
            "comparison_flux_sum",
            "differential_flux",
            "normalized_flux",
            "target_centroid_x",
            "target_centroid_y",
            "target_centroid_offset",
            "target_saturated_pixels",
            "comparison_saturated_pixels",
            "quality_flags",
            "accepted",
        ],
    )

    summary = {
        "tool": "exoplanet_timeseries_workbench",
        "environment": environment_summary(),
        "object_name": object_name,
        "science_frame_count": len(science_rows),
        "science_shape": list(shape),
        "science_filter": filter_id,
        "target_label": target.label,
        "comparison_labels": [source.label for source in comparisons],
        "best_aperture_radius": radius_result["best_radius"],
        "radius_scan": radius_result["radius_results"],
        "qa": qa,
        "calibration": {
            "bias_count": len(bias_rows),
            "dark_count": len(dark_rows),
            "flat_count": len(flat_rows),
            "has_compatible_flat": bool(flat_rows),
            "master_flat_filled_pixels": int(master_flat_filled_pixels),
            "median_science_exptime": median_science_exptime,
            "dark_model": "bias_subtracted_rate_per_second" if master_dark_rate is not None else None,
        },
        "products": {
            "source_map": str(source_map_path.resolve()),
            "light_curve_plot": str(light_curve_plot_path.resolve()),
            "candidate_diagnostics_csv": str(diagnostics_csv.resolve()),
            "radius_scan_csv": str(radius_csv.resolve()),
            "light_curve_csv": str(light_curve_csv.resolve()),
            "reduced_frames_dir": str(reduced_dir.resolve()) if reduced_dir.exists() else None,
        },
        "notes": [
            "Automatic target selection is operational and may need an external hint for definitive host-star identification.",
            "The best aperture radius is chosen from the tested grid by minimizing accepted-frame scatter.",
        ],
    }
    report_path = output_dir / "report.md"
    write_report(report_path, summary)
    summary["products"]["report_markdown"] = str(report_path.resolve())

    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")

    if args.manifest_json:
        outputs = [
            diagnostics_csv,
            radius_csv,
            light_curve_csv,
            source_map_path,
            light_curve_plot_path,
            report_path,
        ]
        if reduced_dir.exists():
            outputs.extend(sorted(reduced_dir.glob("*.fits")))
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=all_paths,
            outputs=outputs,
            parameters={
                "object_name": args.object_name,
                "target_label": args.target_label,
                "target_center": args.target_center,
                "comparison_labels": args.comparison_label,
                "aperture_radii": args.aperture_radii,
                "comparison_count": args.comparison_count,
            },
            command="exoplanet_timeseries_workbench.py",
            notes=summary["notes"],
            extra={"summary": summary},
        )


if __name__ == "__main__":
    main()
