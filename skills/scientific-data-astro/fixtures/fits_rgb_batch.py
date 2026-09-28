#!/usr/bin/env python3
"""Build small reproducible RGB products from grouped FITS images.

This is a narrow visual-product helper, not a full CCD reduction pipeline. It
preserves source FITS files, stacks repeated frames per filter, aligns final
filter stacks, writes PNG products, and records the alignment/provenance choices
needed to review the result later.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _internal.provenance_utils import build_manifest, public_path, sha256_file, standard_qa_payload
from _internal.public_contract import build_tool_payload, emit_payload

FITS_SUFFIXES = {".fits", ".fit", ".fts"}
FILTER_KEYS = ("FILTER", "FILTNAM", "FILTNAME", "FILTER1", "INSFILTE", "INSFLNAM")
OBJECT_KEYS = ("OBJECT", "OBJNAME", "TARGNAME", "TARGET")
DEFAULT_REFERENCE_ORDER = ("R", "I", "V", "G", "B", "CLEAR", "L", "H-ALPHA")
RGB_MODE_LABELS = {"true_rgb", "ha_rgb", "pseudo_bv", "pseudo_ir", "single_channel"}


@dataclass
class FitsRecord:
    path: Path
    relative_path: str
    status: str
    category: str
    object_name: str | None = None
    filter_name: str | None = None
    setup: str = "default"
    image_hdu: int | None = None
    shape: tuple[int, int] | None = None
    exptime: float | None = None
    wcs_present: bool = False
    wcs_valid: bool = False
    wcs_warning: str | None = None
    finite_fraction: float | None = None
    nonfinite_pixels: int = 0
    reduction_stage_guess: str = "unknown"
    error: str | None = None


@dataclass
class FilterStack:
    filter_name: str
    data: Any
    header: Any
    source_records: list[FitsRecord]
    stack_path: Path | None = None
    aligned_path: Path | None = None
    alignment_method: str = "reference"
    shift_yx: tuple[float, float] | None = None
    footprint_fraction: float | None = None


@dataclass
class GroupResult:
    group_id: str
    object_name: str
    setup: str
    shape: tuple[int, int]
    filters: list[str]
    output_mode: str
    status: str
    png_path: Path | None = None
    alignment_qa_path: Path | None = None
    notes: list[str] = field(default_factory=list)
    qa_findings: list[str] = field(default_factory=list)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, help="Folder containing FITS files to inventory and group.")
    parser.add_argument("--output-dir", required=True, help="Folder for derived RGB products and reports.")
    parser.add_argument("--summary-json", help="Optional path for the standard JSON envelope.")
    parser.add_argument("--max-files", type=int, help="Optional cap for quick testing on large trees.")
    parser.add_argument("--run-id", help="Optional run identifier. Defaults to UTC timestamp.")
    parser.add_argument(
        "--clean-derived",
        action="store_true",
        help="Quarantine only files owned by a previous fits_rgb_batch manifest before writing.",
    )
    parser.add_argument(
        "--alignment-mode",
        choices=("auto", "wcs", "phase", "none"),
        default="auto",
        help="How to align final filter stacks. Auto prefers WCS, then phase correlation.",
    )
    parser.add_argument(
        "--stretch-percentiles",
        nargs=2,
        type=float,
        default=(1.0, 99.5),
        metavar=("LOW", "HIGH"),
        help="Percentiles used for channel normalization.",
    )
    parser.add_argument(
        "--qa-residual-threshold",
        type=float,
        default=2.0,
        help="Warn when simple peak residuals between channels exceed this many pixels.",
    )
    parser.add_argument(
        "--no-stacks",
        action="store_true",
        help="Do not persist intermediate stacked/aligned FITS products; PNG and reports are still written.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty output directory without --clean-derived.",
    )
    return parser.parse_args(argv)


def dependency_block() -> str | None:
    missing = []
    for module_name in ("numpy", "astropy", "matplotlib", "scipy"):
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)
    if missing:
        return "Missing required package(s) for FITS RGB batch: " + ", ".join(missing)
    return None


def import_runtime():
    import numpy as np
    from astropy.io import fits
    from astropy.stats import sigma_clip
    from astropy.wcs import WCS
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from scipy.ndimage import shift as ndi_shift

    try:
        from reproject import reproject_interp
    except Exception:
        reproject_interp = None
    try:
        from skimage.registration import phase_cross_correlation
    except Exception:
        phase_cross_correlation = None
    return {
        "np": np,
        "fits": fits,
        "sigma_clip": sigma_clip,
        "WCS": WCS,
        "plt": plt,
        "ndi_shift": ndi_shift,
        "reproject_interp": reproject_interp,
        "phase_cross_correlation": phase_cross_correlation,
    }


def package_versions() -> dict[str, str | None]:
    versions = {}
    for name in ("numpy", "astropy", "reproject", "skimage", "scipy", "matplotlib"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", None)
        except Exception:
            versions[name] = None
    return versions


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper().replace(" ", "").replace("_", "-")
    if not text:
        return None
    mapping = {
        "SDSSG": "G",
        "SDSS-G": "G",
        "SDSSR": "R",
        "SDSS-R": "R",
        "SDSSI": "I",
        "SDSS-I": "I",
        "G": "G",
        "R": "R",
        "I": "I",
        "B": "B",
        "V": "V",
        "U": "U",
        "CLEAR": "CLEAR",
        "L": "L",
        "LUM": "L",
        "LUMINANCE": "L",
        "HA": "H-ALPHA",
        "HALPHA": "H-ALPHA",
        "H-ALPHA": "H-ALPHA",
        "H-ALFA": "H-ALPHA",
        "OIII": "OIII",
        "O-III": "OIII",
        "SII": "SII",
        "S-II": "SII",
    }
    if text in mapping:
        return mapping[text]
    if "HALPHA" in text or "H-ALPHA" in text or "656" in text or "658" in text:
        return "H-ALPHA"
    if text.startswith("SDSS") and text[-1] in {"G", "R", "I"}:
        return text[-1]
    return None


def clean_name(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value).strip())
    text = "_".join(part for part in text.split("_") if part)
    return text or fallback


def infer_from_filename(path: Path) -> tuple[str | None, str | None, str]:
    stem = path.stem
    tokens = [token for token in stem.replace("-", "_").split("_") if token]
    filt = None
    setup_parts = []
    object_tokens = []
    for token in tokens:
        candidate_filter = normalize_filter(token)
        if filt is None and candidate_filter is not None:
            filt = candidate_filter
            continue
        if len(token) >= 2 and token[0].upper() in {"B", "T"} and token[1:].isdigit():
            setup_parts.append(token.upper())
            continue
        if filt is None:
            object_tokens.append(token)
    setup = "_".join(setup_parts[:2]) if setup_parts else "default"
    obj = " ".join(object_tokens).strip() or None
    return obj, filt, setup


def choose_image_hdu(hdul) -> int | None:
    for idx, hdu in enumerate(hdul):
        data = getattr(hdu, "data", None)
        if data is None:
            continue
        shape = getattr(data, "shape", None)
        if shape and len(shape) >= 2:
            return idx
    return None


def header_value(header, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in header and header.get(key) not in (None, ""):
            return header.get(key)
    return None


def wcs_diagnostic(header, runtime) -> tuple[bool, str | None]:
    keys = ("CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2")
    present = {key for key in keys if header.get(key) not in (None, "")}
    has_wcs_hint = bool(present or any(key.startswith(("CD", "PC", "CDELT")) for key in header))
    if not has_wcs_hint:
        return False, None
    missing = [key for key in keys if header.get(key) in (None, "")]
    has_scale = (
        header.get("CDELT1") not in (None, "")
        and header.get("CDELT2") not in (None, "")
    ) or (
        header.get("CD1_1") not in (None, "")
        and header.get("CD2_2") not in (None, "")
    )
    if not has_scale:
        missing.append("CDELT/CD matrix")
    if missing:
        return False, "Incomplete celestial WCS metadata: missing " + ", ".join(missing)
    try:
        wcs = runtime["WCS"](header).celestial
        if not wcs.has_celestial:
            return False, "WCS keywords are present but Astropy does not consider them celestial."
    except Exception as exc:
        return False, f"WCS keywords are present but could not be parsed: {exc}"
    return True, None


def guess_reduction_stage(path: Path, header) -> str:
    text = " ".join([str(path).lower(), str(header.get("IMAGETYP", "")).lower(), str(header.get("HISTORY", "")).lower()])
    if any(term in text for term in ("calibrated", "reduced", "flat", "biascorr", "processed")):
        return "possibly_reduced"
    if any(term in text for term in ("raw", "light frame", "object")):
        return "possibly_raw"
    return "unknown"


def inspect_fits_tree(input_root: Path, max_files: int | None, runtime) -> list[FitsRecord]:
    fits = runtime["fits"]
    records: list[FitsRecord] = []
    paths = sorted(path for path in input_root.rglob("*") if path.suffix.lower() in FITS_SUFFIXES)
    if max_files is not None:
        paths = paths[:max_files]
    for path in paths:
        relative = str(path.relative_to(input_root))
        try:
            with fits.open(path, memmap=False) as hdul:
                hdu_idx = choose_image_hdu(hdul)
                if hdu_idx is None:
                    records.append(FitsRecord(path, relative, "ok", "non_image"))
                    continue
                hdu = hdul[hdu_idx]
                header = hdu.header
                data = hdu.data
                if data is None or len(data.shape) < 2:
                    records.append(FitsRecord(path, relative, "ok", "non_image"))
                    continue
                data2d = data[0] if len(data.shape) > 2 else data
                obj_file, filt_file, setup = infer_from_filename(path)
                obj = header_value(header, OBJECT_KEYS) or obj_file or path.parent.name
                filt = normalize_filter(header_value(header, FILTER_KEYS)) or filt_file
                shape = (int(data2d.shape[-2]), int(data2d.shape[-1]))
                arr = runtime["np"].asarray(data2d, dtype=float)
                finite_count = int(runtime["np"].isfinite(arr).sum())
                total_count = int(arr.size)
                nonfinite_pixels = total_count - finite_count
                finite_fraction = float(finite_count / total_count) if total_count else None
                wcs_valid, wcs_warning = wcs_diagnostic(header, runtime)
                records.append(
                    FitsRecord(
                        path=path,
                        relative_path=relative,
                        status="ok",
                        category="image2d",
                        object_name=str(obj).strip() if obj else None,
                        filter_name=filt,
                        setup=setup,
                        image_hdu=hdu_idx,
                        shape=shape,
                        exptime=float(header.get("EXPTIME")) if header.get("EXPTIME") not in (None, "") else None,
                        wcs_present=wcs_valid or bool(wcs_warning),
                        wcs_valid=wcs_valid,
                        wcs_warning=wcs_warning,
                        finite_fraction=finite_fraction,
                        nonfinite_pixels=nonfinite_pixels,
                        reduction_stage_guess=guess_reduction_stage(path, header),
                    )
                )
        except Exception as exc:
            records.append(FitsRecord(path, relative, "warning", "unreadable", error=str(exc)))
    return records


def write_inventory(records: list[FitsRecord], path: Path) -> None:
    fields = [
        "path",
        "relative_path",
        "status",
        "category",
        "object_name",
        "filter_name",
        "setup",
        "shape",
        "image_hdu",
        "exptime",
        "wcs_present",
        "wcs_valid",
        "wcs_warning",
        "finite_fraction",
        "nonfinite_pixels",
        "reduction_stage_guess",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "path": public_path(record.path),
                    "relative_path": record.relative_path,
                    "status": record.status,
                    "category": record.category,
                    "object_name": record.object_name,
                    "filter_name": record.filter_name,
                    "setup": record.setup,
                    "shape": "x".join(map(str, record.shape)) if record.shape else "",
                    "image_hdu": record.image_hdu,
                    "exptime": record.exptime,
                    "wcs_present": record.wcs_present,
                    "wcs_valid": record.wcs_valid,
                    "wcs_warning": record.wcs_warning,
                    "finite_fraction": record.finite_fraction,
                    "nonfinite_pixels": record.nonfinite_pixels,
                    "reduction_stage_guess": record.reduction_stage_guess,
                    "error": record.error,
                }
            )


def group_records(records: list[FitsRecord]) -> dict[tuple[str, str, tuple[int, int]], dict[str, list[FitsRecord]]]:
    grouped: dict[tuple[str, str, tuple[int, int]], dict[str, list[FitsRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if record.category != "image2d" or record.shape is None:
            continue
        if not record.object_name or not record.filter_name:
            continue
        key = (clean_name(record.object_name, "object"), clean_name(record.setup, "default"), record.shape)
        grouped[key][record.filter_name].append(record)
    return grouped


def read_image(record: FitsRecord, runtime):
    np = runtime["np"]
    fits = runtime["fits"]
    with fits.open(record.path, memmap=False) as hdul:
        hdu = hdul[record.image_hdu or 0]
        data = hdu.data
        if data is None:
            raise ValueError(f"No data in {record.path}")
        data2d = data[0] if len(data.shape) > 2 else data
        arr = np.asarray(data2d, dtype=float)
        arr[~np.isfinite(arr)] = np.nan
        return arr, hdu.header.copy()


def robust_stack(records: list[FitsRecord], runtime):
    np = runtime["np"]
    sigma_clip = runtime["sigma_clip"]
    arrays = []
    header = None
    for record in records:
        data, hdr = read_image(record, runtime)
        arrays.append(data)
        if header is None:
            header = hdr
    cube = np.stack(arrays, axis=0)
    if cube.shape[0] == 1:
        stacked = cube[0]
    else:
        clipped = sigma_clip(cube, sigma=4.0, axis=0, masked=True)
        stacked = np.ma.median(clipped, axis=0).filled(np.nan)
    return stacked.astype(float), header


def write_fits(path: Path, data, header, runtime, note: str) -> None:
    fits = runtime["fits"]
    path.parent.mkdir(parents=True, exist_ok=True)
    header = header.copy()
    header["HISTORY"] = note
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def aligned_output_header(stack: FilterStack, reference: FilterStack, info: dict[str, Any], runtime):
    """Preserve channel metadata while updating only alignment-dependent WCS."""

    header = stack.header.copy()
    method = info.get("method")
    if method == "wcs_reproject_interp":
        try:
            source_wcs_header = runtime["WCS"](header).celestial.to_header(relax=True)
            for key in source_wcs_header:
                if key in header:
                    del header[key]
        except Exception:
            pass
        reference_wcs_header = runtime["WCS"](reference.header).celestial.to_header(relax=True)
        header.update(reference_wcs_header)
    elif method == "phase_cross_correlation" and info.get("shift_yx") is not None:
        shift_y, shift_x = (float(value) for value in info["shift_yx"])
        if "CRPIX1" in header:
            header["CRPIX1"] = float(header["CRPIX1"]) + shift_x
        if "CRPIX2" in header:
            header["CRPIX2"] = float(header["CRPIX2"]) + shift_y
    header["HISTORY"] = (
        f"Alignment grid derived with method={method or 'unknown'}; channel FILTER/EXPTIME metadata preserved."
    )
    return header


def choose_channels(filters: set[str]) -> tuple[str, dict[str, str] | None, list[str]]:
    notes = []
    if {"H-ALPHA", "R", "V", "B"}.issubset(filters):
        notes.append("H-alpha is available; broadband R/V/B is used for RGB and H-alpha is blended into red.")
        return "ha_rgb", {"red": "R", "green": "V", "blue": "B", "ha": "H-ALPHA"}, notes
    if {"R", "G", "B"}.issubset(filters):
        return "true_rgb", {"red": "R", "green": "G", "blue": "B"}, notes
    if {"R", "V", "B"}.issubset(filters):
        return "true_rgb", {"red": "R", "green": "V", "blue": "B"}, notes
    if {"I", "V", "B"}.issubset(filters):
        notes.append("Using I as red channel because R is not available.")
        return "true_rgb", {"red": "I", "green": "V", "blue": "B"}, notes
    if {"H-ALPHA", "V", "B"}.issubset(filters):
        notes.append("Using H-alpha as red channel; label as ha_rgb, not broadband true RGB.")
        return "ha_rgb", {"red": "H-ALPHA", "green": "V", "blue": "B"}, notes
    if {"B", "V"}.issubset(filters):
        notes.append("Only B and V broad bands are available; output is pseudo_bv.")
        return "pseudo_bv", {"red": "V", "green": "V", "blue": "B"}, notes
    if {"I", "R"}.issubset(filters):
        notes.append("Only red/IR bands are available; output is pseudo_ir.")
        return "pseudo_ir", {"red": "I", "green": "R", "blue": "R"}, notes
    broad = [item for item in DEFAULT_REFERENCE_ORDER if item in filters]
    if broad:
        notes.append("Only one usable visual channel is available; output is single_channel.")
        return "single_channel", {"red": broad[0], "green": broad[0], "blue": broad[0]}, notes
    return "no_rgb_plan", None, ["No supported channel combination was found."]


def reference_filter_for(channel_map: dict[str, str]) -> str:
    available = set(channel_map.values())
    for item in DEFAULT_REFERENCE_ORDER:
        if item in available:
            return item
    return next(iter(available))


def align_stack(stack: FilterStack, reference: FilterStack, mode: str, runtime) -> tuple[Any, dict[str, Any]]:
    np = runtime["np"]
    WCS = runtime["WCS"]
    reproject_interp = runtime["reproject_interp"]
    ndi_shift = runtime["ndi_shift"]
    phase_cross_correlation = runtime["phase_cross_correlation"]
    if stack.filter_name == reference.filter_name:
        return stack.data, {"method": "reference", "shift_yx": [0.0, 0.0], "footprint_fraction": 1.0}

    stack_wcs_valid, stack_wcs_warning = wcs_diagnostic(stack.header, runtime)
    reference_wcs_valid, reference_wcs_warning = wcs_diagnostic(reference.header, runtime)
    can_wcs = mode in {"auto", "wcs"} and reproject_interp is not None
    if can_wcs and stack_wcs_valid and reference_wcs_valid:
        try:
            target_header = reference.header.copy()
            target_header["NAXIS"] = 2
            target_header["NAXIS1"] = int(reference.data.shape[1])
            target_header["NAXIS2"] = int(reference.data.shape[0])
            reprojected, footprint = reproject_interp((stack.data, WCS(stack.header).celestial), target_header)
            finite_footprint = footprint[np.isfinite(footprint)]
            footprint_fraction = float(np.nanmean(finite_footprint > 0.0)) if finite_footprint.size else 0.0
            return reprojected, {
                "method": "wcs_reproject_interp",
                "shift_yx": None,
                "footprint_fraction": footprint_fraction,
            }
        except Exception as exc:
            if mode == "wcs":
                raise
            wcs_error = str(exc)
    else:
        reasons = []
        if reproject_interp is None:
            reasons.append("reproject is not installed")
        if stack_wcs_warning:
            reasons.append(f"{stack.filter_name}: {stack_wcs_warning}")
        if reference_wcs_warning:
            reasons.append(f"{reference.filter_name}: {reference_wcs_warning}")
        if not stack_wcs_valid and not stack_wcs_warning:
            reasons.append(f"{stack.filter_name}: no celestial WCS")
        if not reference_wcs_valid and not reference_wcs_warning:
            reasons.append(f"{reference.filter_name}: no celestial WCS")
        wcs_error = "; ".join(reasons) or "WCS unavailable."
        if mode == "wcs":
            raise RuntimeError(f"WCS alignment requested but unavailable: {wcs_error}")

    if mode in {"auto", "phase"} and phase_cross_correlation is not None:
        ref = np.nan_to_num(reference.data, nan=float(np.nanmedian(reference.data)))
        img = np.nan_to_num(stack.data, nan=float(np.nanmedian(stack.data)))
        shift_yx, error, _ = phase_cross_correlation(ref, img, upsample_factor=10)
        shifted = ndi_shift(stack.data, shift=shift_yx, order=1, mode="constant", cval=np.nan, prefilter=False)
        return shifted, {
            "method": "phase_cross_correlation",
            "shift_yx": [float(shift_yx[0]), float(shift_yx[1])],
            "registration_error": float(error),
            "footprint_fraction": float(np.mean(np.isfinite(shifted))),
            "wcs_fallback_reason": wcs_error,
        }

    if mode == "phase":
        raise RuntimeError("Phase correlation requested but skimage.registration is unavailable.")
    return stack.data, {
        "method": "none",
        "shift_yx": [0.0, 0.0],
        "footprint_fraction": float(np.mean(np.isfinite(stack.data))),
        "wcs_fallback_reason": wcs_error,
    }


def normalize_channel(data, percentiles: tuple[float, float], runtime):
    np = runtime["np"]
    arr = np.asarray(data, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr, dtype=float)
    lo, hi = np.nanpercentile(finite, percentiles)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo = float(np.nanmin(finite))
        hi = float(np.nanmax(finite))
    if hi <= lo:
        return np.zeros_like(arr, dtype=float)
    clipped = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    return np.arcsinh(8.0 * clipped) / np.arcsinh(8.0)


def peak_centroid(data, runtime) -> tuple[float, float] | None:
    np = runtime["np"]
    arr = np.asarray(data, dtype=float)
    if not np.isfinite(arr).any():
        return None
    threshold = np.nanpercentile(arr, 99.0)
    weights = arr.copy()
    weights[~np.isfinite(weights)] = 0.0
    weights = weights - np.nanmin(weights)
    weights[weights < max(threshold - np.nanmin(arr), 0.0)] = 0.0
    total = float(np.sum(weights))
    if total <= 0:
        y, x = np.unravel_index(int(np.nanargmax(arr)), arr.shape)
        return float(y), float(x)
    yy, xx = np.indices(arr.shape)
    return float(np.sum(yy * weights) / total), float(np.sum(xx * weights) / total)


def write_rgb_png(path: Path, channel_arrays: dict[str, Any], percentiles: tuple[float, float], runtime) -> dict[str, Any]:
    np = runtime["np"]
    plt = runtime["plt"]
    red = normalize_channel(channel_arrays["red"], percentiles, runtime)
    green = normalize_channel(channel_arrays["green"], percentiles, runtime)
    blue = normalize_channel(channel_arrays["blue"], percentiles, runtime)
    rgb = np.dstack([red, green, blue])
    rgb[~np.isfinite(rgb)] = 0.0
    rgb = np.clip(rgb, 0.0, 1.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(path, rgb, origin="lower")
    return {
        "shape": list(rgb.shape),
        "percentiles": list(percentiles),
        "finite_fraction": float(np.mean(np.isfinite(rgb))),
    }


def source_quality_warnings(filter_records: dict[str, list[FitsRecord]]) -> list[str]:
    warnings = []
    for records in filter_records.values():
        for record in records:
            if record.nonfinite_pixels:
                warnings.append(
                    f"{record.relative_path} contains {record.nonfinite_pixels} non-finite pixel(s); NaN/Inf values were ignored for stacking/rendering."
                )
            if record.wcs_warning:
                warnings.append(f"{record.relative_path} has incomplete or invalid WCS: {record.wcs_warning}")
    return warnings


def process_group(
    key: tuple[str, str, tuple[int, int]],
    filter_records: dict[str, list[FitsRecord]],
    dirs: dict[str, Path],
    args: argparse.Namespace,
    runtime,
) -> tuple[GroupResult, dict[str, Any]]:
    np = runtime["np"]
    object_name, setup, shape = key
    group_id = "__".join([clean_name(object_name, "object"), clean_name(setup, "default"), f"{shape[1]}x{shape[0]}"])
    mode, channel_map, notes = choose_channels(set(filter_records))
    source_warnings = source_quality_warnings(filter_records)
    if not channel_map:
        result = GroupResult(group_id, object_name, setup, shape, sorted(filter_records), mode, "warning", notes=notes, qa_findings=source_warnings)
        return result, {"group_id": group_id, "status": "warning", "notes": notes, "warnings": source_warnings}

    stacks: dict[str, FilterStack] = {}
    for filt, records in sorted(filter_records.items()):
        data, header = robust_stack(records, runtime)
        stack = FilterStack(filt, data, header, records)
        if not args.no_stacks:
            stack.stack_path = dirs["stacked"] / f"{group_id}_{filt}_stack.fits"
            write_fits(stack.stack_path, data, header, runtime, "Derived stack from fits_rgb_batch.py; source files preserved.")
        stacks[filt] = stack

    reference_filter = reference_filter_for(channel_map)
    reference_stack = stacks[reference_filter]
    aligned: dict[str, Any] = {}
    alignment_report = {
        "group_id": group_id,
        "object_name": object_name,
        "setup": setup,
        "shape": list(shape),
        "output_mode": mode,
        "reference_filter": reference_filter,
        "channels": channel_map,
        "alignment": {},
        "peak_residuals_px": {},
        "warnings": list(source_warnings),
    }
    for filt, stack in stacks.items():
        if filt not in set(channel_map.values()):
            continue
        aligned_data, info = align_stack(stack, reference_stack, args.alignment_mode, runtime)
        stack.alignment_method = info.get("method", "unknown")
        stack.shift_yx = tuple(info["shift_yx"]) if info.get("shift_yx") is not None else None
        stack.footprint_fraction = info.get("footprint_fraction")
        aligned[filt] = aligned_data
        alignment_report["alignment"][filt] = info
        if not args.no_stacks:
            stack.aligned_path = dirs["aligned"] / f"{group_id}_{filt}_aligned.fits"
            output_header = aligned_output_header(stack, reference_stack, info, runtime)
            write_fits(
                stack.aligned_path,
                aligned_data,
                output_header,
                runtime,
                "Derived aligned stack from fits_rgb_batch.py; source files preserved.",
            )

    if "ha" in channel_map and channel_map["ha"] in aligned:
        red_key = channel_map["red"]
        ha = normalize_channel(aligned[channel_map["ha"]], tuple(args.stretch_percentiles), runtime)
        red = normalize_channel(aligned[red_key], tuple(args.stretch_percentiles), runtime)
        aligned["_red_blend"] = np.maximum(red, 0.65 * red + 0.35 * ha)
        channel_arrays = {
            "red": aligned["_red_blend"],
            "green": aligned[channel_map["green"]],
            "blue": aligned[channel_map["blue"]],
        }
    else:
        channel_arrays = {
            "red": aligned[channel_map["red"]],
            "green": aligned[channel_map["green"]],
            "blue": aligned[channel_map["blue"]],
        }

    reference_centroid = peak_centroid(aligned[reference_filter], runtime)
    for filt, data in aligned.items():
        if filt.startswith("_"):
            continue
        centroid = peak_centroid(data, runtime)
        if reference_centroid and centroid:
            residual = float(np.hypot(centroid[0] - reference_centroid[0], centroid[1] - reference_centroid[1]))
            alignment_report["peak_residuals_px"][filt] = residual
            if residual > args.qa_residual_threshold:
                alignment_report["warnings"].append(
                    f"{filt} peak residual is {residual:.2f} px relative to {reference_filter}; visually inspect color seams."
                )

    if any(record.reduction_stage_guess == "unknown" for records in filter_records.values() for record in records):
        notes.append("Calibration/reduction state is not fully verified; treat output as visual RGB unless upstream reduction is confirmed.")

    png_path = dirs["rgb"] / f"{group_id}_{mode}.png"
    png_info = write_rgb_png(png_path, channel_arrays, tuple(args.stretch_percentiles), runtime)
    alignment_report["png"] = public_path(png_path)
    alignment_report["png_info"] = png_info
    alignment_qa_path = dirs["reports"] / f"{group_id}_alignment_qa.json"
    alignment_qa_path.write_text(json.dumps(alignment_report, indent=2, ensure_ascii=True), encoding="utf-8")

    status = "warning" if alignment_report["warnings"] else "ok"
    result = GroupResult(
        group_id=group_id,
        object_name=object_name,
        setup=setup,
        shape=shape,
        filters=sorted(filter_records),
        output_mode=mode,
        status=status,
        png_path=png_path,
        alignment_qa_path=alignment_qa_path,
        notes=notes,
        qa_findings=alignment_report["warnings"],
    )
    report = {
        "group_id": group_id,
        "status": status,
        "object_name": object_name,
        "setup": setup,
        "shape": list(shape),
        "filters": sorted(filter_records),
        "output_mode": mode,
        "png": public_path(png_path),
        "alignment_qa": public_path(alignment_qa_path),
        "notes": notes,
        "warnings": alignment_report["warnings"],
        "owned_outputs": [
            public_path(path)
            for stack in stacks.values()
            for path in (stack.stack_path, stack.aligned_path)
            if path is not None
        ]
        + [public_path(png_path), public_path(alignment_qa_path)],
    }
    return result, report


def write_group_summary(results: list[GroupResult], path: Path) -> None:
    fields = [
        "group_id",
        "status",
        "object_name",
        "setup",
        "shape",
        "filters",
        "output_mode",
        "png_path",
        "alignment_qa_path",
        "notes",
        "qa_findings",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "group_id": item.group_id,
                    "status": item.status,
                    "object_name": item.object_name,
                    "setup": item.setup,
                    "shape": "x".join(map(str, item.shape)),
                    "filters": ",".join(item.filters),
                    "output_mode": item.output_mode,
                    "png_path": public_path(item.png_path) if item.png_path else "",
                    "alignment_qa_path": public_path(item.alignment_qa_path) if item.alignment_qa_path else "",
                    "notes": " | ".join(item.notes),
                    "qa_findings": " | ".join(item.qa_findings),
                }
            )


def _owned_outputs_from_manifest(output_dir: Path) -> list[Path]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            "--clean-derived requires an existing manifest.json created by fits_rgb_batch; "
            "no manifest-owned cleanup can be proven."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not validate the previous fits_rgb_batch manifest: {exc}") from None
    extra = manifest.get("extra") if isinstance(manifest, dict) else None
    if not isinstance(extra, dict) or extra.get("owner") != "fits_rgb_batch":
        raise SystemExit("--clean-derived refused: manifest.json does not declare owner=fits_rgb_batch.")
    raw_owned = extra.get("owned_outputs")
    if not isinstance(raw_owned, list) or not raw_owned:
        raise SystemExit("--clean-derived refused: manifest.json has no explicit owned_outputs list.")
    owned = []
    root = output_dir.resolve()
    for raw in raw_owned:
        relative = Path(str(raw))
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"Unsafe owned output path in manifest: {raw!r}")
        candidate = (root / relative).resolve()
        if not is_relative_to(candidate, root) or candidate == root:
            raise SystemExit(f"Owned output escapes output-dir: {raw!r}")
        owned.append(candidate)
    return owned


def quarantine_manifest_owned_outputs(output_dir: Path) -> Path:
    owned = _owned_outputs_from_manifest(output_dir)
    quarantine = output_dir / ".trash" / datetime.now(timezone.utc).strftime("fits_rgb_batch_%Y%m%dT%H%M%S%fZ")
    for source in sorted(owned, key=lambda item: len(item.parts), reverse=True):
        if not source.exists() or not source.is_file():
            continue
        relative = source.relative_to(output_dir.resolve())
        destination = quarantine / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    return quarantine


def prepare_output_dirs(output_dir: Path, clean: bool, force: bool) -> dict[str, Path]:
    if output_dir.exists() and any(output_dir.iterdir()) and not clean and not force:
        raise SystemExit(
            f"Output directory is not empty: {output_dir}. Use --clean-derived or --force to make reruns explicit."
        )
    dirs = {
        "root": output_dir,
        "rgb": output_dir / "rgb_png",
        "stacked": output_dir / "stacked_fits",
        "aligned": output_dir / "aligned_stacked_fits",
        "reports": output_dir / "reports",
    }
    if clean:
        quarantine_manifest_owned_outputs(output_dir)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def nearest_existing_parent(path: Path) -> Path:
    parent = path.parent
    while parent and not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent


def validate_summary_json_path(summary_json: str | None) -> str | None:
    if not summary_json:
        return None
    path = Path(summary_json).expanduser()
    if path.exists() and not path.is_file():
        return f"--summary-json must point to a file path, not a directory: {public_path(path)}"
    parent = nearest_existing_parent(path)
    if parent.exists() and not parent.is_dir():
        return f"--summary-json parent is not a directory: {public_path(parent)}"
    return None


def validate_paths(input_root: Path, output_dir: Path, args: argparse.Namespace) -> str | None:
    summary_error = validate_summary_json_path(args.summary_json)
    if summary_error:
        return summary_error
    if not input_root.exists():
        return f"Input root does not exist: {public_path(input_root)}"
    if not input_root.is_dir():
        return f"Input root must be a directory: {public_path(input_root)}"
    if output_dir == input_root or is_relative_to(output_dir, input_root):
        return (
            "Output directory must be outside input-root so derived PNG/FITS products do not pollute "
            f"the source scan tree: output_dir={public_path(output_dir)} input_root={public_path(input_root)}"
        )
    if output_dir.exists() and not output_dir.is_dir():
        return f"Output directory path exists but is not a directory: {public_path(output_dir)}"
    parent = nearest_existing_parent(output_dir)
    if parent.exists() and not parent.is_dir():
        return f"Output directory parent is not a directory: {public_path(parent)}"
    if output_dir.exists() and any(output_dir.iterdir()) and not args.clean_derived and not args.force:
        return f"Output directory is not empty: {public_path(output_dir)}. Use --clean-derived or --force to make reruns explicit."
    if output_dir.exists() and any(output_dir.iterdir()) and args.clean_derived:
        try:
            _owned_outputs_from_manifest(output_dir)
        except SystemExit as exc:
            return str(exc)
    return None


def emit_blocked(reason: str, args: argparse.Namespace, input_root: Path | None = None, output_dir: Path | None = None) -> int:
    artifacts = {"summary_json": args.summary_json}
    if output_dir is not None:
        artifacts["output_dir"] = output_dir
    results = {"blocking_reason": reason}
    if input_root is not None:
        results["input_root"] = public_path(input_root)
    if output_dir is not None:
        results["output_dir"] = public_path(output_dir)
    payload = build_tool_payload(
        "fits_rgb_batch",
        status="blocked",
        notes=[
            "Batch RGB/FITS visual workflow did not run because preflight blocked it.",
            "No input FITS files were modified.",
        ],
        artifacts=artifacts,
        results=results,
        qa=standard_qa_payload(status="blocked", findings=[reason]),
        include_environment=True,
    )
    safe_summary = None if validate_summary_json_path(args.summary_json) else args.summary_json
    emit_payload(payload, safe_summary)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_root = Path(args.input_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    path_error = validate_paths(input_root, output_dir, args)
    if path_error:
        return emit_blocked(path_error, args, input_root, output_dir)
    blocked = dependency_block()
    if blocked:
        return emit_blocked(blocked, args, input_root, output_dir)
    runtime = import_runtime()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dirs = prepare_output_dirs(output_dir, args.clean_derived, args.force)
    inventory_path = output_dir / "fits_inventory.csv"
    group_summary_path = output_dir / "rgb_group_summary.csv"
    run_summary_path = output_dir / "run_summary.json"
    manifest_path = output_dir / "manifest.json"

    records = inspect_fits_tree(input_root, args.max_files, runtime)
    write_inventory(records, inventory_path)
    grouped = group_records(records)
    results: list[GroupResult] = []
    group_reports: list[dict[str, Any]] = []
    for key, filter_records in sorted(grouped.items()):
        result, report = process_group(key, filter_records, dirs, args, runtime)
        results.append(result)
        group_reports.append(report)
    write_group_summary(results, group_summary_path)

    qa_findings = [finding for item in results for finding in item.qa_findings]
    if not records:
        qa_findings.append("No FITS files were found under input-root.")
    elif not grouped:
        qa_findings.append("No image2d FITS records with both object and filter metadata could be grouped.")
    elif not any(item.png_path for item in results):
        qa_findings.append("No RGB or pseudo-RGB PNG products were written from the detected groups.")
    blocked_groups = [report for report in group_reports if report["status"] not in {"ok", "warning"}]
    warning_groups = [report for report in group_reports if report["status"] == "warning"]
    modes = {mode: sum(1 for item in results if item.output_mode == mode) for mode in RGB_MODE_LABELS}
    run_summary = {
        "run_id": run_id,
        "input_root": public_path(input_root),
        "output_dir": public_path(output_dir),
        "counts": {
            "fits_records": len(records),
            "image2d_records": sum(1 for record in records if record.category == "image2d"),
            "groups_considered": len(grouped),
            "groups_written": len([item for item in results if item.png_path]),
            "warning_groups": len(warning_groups),
            "blocked_groups": len(blocked_groups),
        },
        "modes": modes,
        "parameters": {
            "alignment_mode": args.alignment_mode,
            "stretch_percentiles": list(args.stretch_percentiles),
            "qa_residual_threshold": args.qa_residual_threshold,
            "max_files": args.max_files,
            "no_stacks": args.no_stacks,
        },
        "reports": {
            "fits_inventory": public_path(inventory_path),
            "rgb_group_summary": public_path(group_summary_path),
            "manifest": public_path(manifest_path),
        },
        "group_reports": group_reports,
        "package_versions": package_versions(),
        "script_path": public_path(Path(__file__)),
        "script_sha256": sha256_file(Path(__file__)),
        "command": " ".join([sys.executable, *sys.argv]),
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=True), encoding="utf-8")
    owned_output_paths = [inventory_path, group_summary_path, run_summary_path, manifest_path]
    if args.summary_json:
        summary_candidate = Path(args.summary_json).expanduser().resolve()
        if is_relative_to(summary_candidate, output_dir):
            owned_output_paths.append(summary_candidate)
    for report in group_reports:
        for raw_path in report.get("owned_outputs", []):
            candidate = Path(str(raw_path).replace("~", str(Path.home()))).expanduser().resolve()
            if is_relative_to(candidate, output_dir):
                owned_output_paths.append(candidate)
    owned_output_relpaths = sorted(
        {
            str(path.resolve().relative_to(output_dir))
            for path in owned_output_paths
            if is_relative_to(path.resolve(), output_dir)
        }
    )
    manifest = build_manifest(
        inputs=[input_root],
        outputs=[output_dir, inventory_path, group_summary_path, run_summary_path],
        parameters=run_summary["parameters"],
        command=run_summary["command"],
        notes=[
            "Source FITS files are preserved; outputs are derived visual products.",
            "Calibration state is guessed from names/headers only and is not a full CCD reduction audit.",
        ],
        extra={
            "package_versions": run_summary["package_versions"],
            "run_id": run_id,
            "owner": "fits_rgb_batch",
            "owned_outputs": owned_output_relpaths,
        },
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    status = "warning" if qa_findings or warning_groups else "ok"
    rgb_previews = [item.png_path for item in results if item.png_path]
    alignment_qa_json = [item.alignment_qa_path for item in results if item.alignment_qa_path]
    artifact_map = {
        "output_dir": output_dir,
        "rgb_png": dirs["rgb"],
        "rgb_previews": rgb_previews,
        "stacked_fits": None if args.no_stacks else dirs["stacked"],
        "aligned_stacked_fits": None if args.no_stacks else dirs["aligned"],
        "reports": dirs["reports"],
        "alignment_qa_json": alignment_qa_json,
        "fits_inventory": inventory_path,
        "rgb_group_table": group_summary_path,
        "run_summary": run_summary_path,
        "manifest": manifest_path,
    }
    if args.summary_json:
        artifact_map["summary_json"] = Path(args.summary_json)
    payload = build_tool_payload(
        "fits_rgb_batch",
        status=status,
        notes=[
            "Batch RGB/FITS visual workflow completed without modifying source FITS files.",
            "Use alignment_qa.json files and RGB PNGs for visual review before using products in slides or reports.",
        ],
        artifacts=artifact_map,
        results=run_summary,
        qa=standard_qa_payload(
            status="warning" if qa_findings else "ok",
            findings=qa_findings,
            metrics=run_summary["counts"],
        ),
        include_environment=True,
    )
    emit_payload(payload, args.summary_json)
    return 0 if status in {"ok", "warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
