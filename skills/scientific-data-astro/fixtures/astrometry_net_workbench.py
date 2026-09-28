#!/usr/bin/env python3
"""Non-destructive Astrometry.net web integration with FITS-aware preflight hints."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import warnings
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime, find_executable, suppress_fd_output

try:
    from astrometry_index_healthcheck import scan_index_dir
except Exception:  # pragma: no cover - optional helper import
    scan_index_dir = None

ensure_datanalysis_runtime("astrometry_net_workbench")
configure_runtime("astrometry_net_workbench")

with suppress_fd_output(True):
    import numpy as np
    import requests
    from astropy import units as u
    from astropy.coordinates import Angle
    from astropy.io import fits
    from astropy.wcs import FITSFixedWarning, WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

warnings.filterwarnings("ignore", category=FITSFixedWarning)


API_BASE_DEFAULT = "https://nova.astrometry.net"
DOWNLOADABLE_PRODUCTS = {
    "wcs": ("wcs_file", ".fits"),
    "new_fits": ("new_fits_file", ".fits"),
    "rdls": ("rdls_file", ".fits"),
    "axy": ("axy_file", ".fits"),
    "corr": ("corr_file", ".fits"),
    "annotated_display": ("annotated_display", ".jpg"),
    "red_green_image_display": ("red_green_image_display", ".jpg"),
    "extraction_image_display": ("extraction_image_display", ".jpg"),
}
LOCAL_STANDARD_PRODUCTS = {
    "wcs": ".wcs",
    "new_fits": ".new",
    "rdls": ".rdls",
    "axy": ".axy",
    "corr": ".corr",
    "match": ".match",
    "solved": ".solved",
    "index_xyls": "-indx.xyls",
    "annotation_png": "-ngc.png",
    "objects_png": "-objs.png",
    "index_overlay_png": "-indx.png",
}
RA_HEADER_KEYS = ["RA", "OBJRA", "TELRA", "OBJCTRA", "OBJ-RA", "OBJ_RA"]
DEC_HEADER_KEYS = ["DEC", "OBJDEC", "TELDEC", "OBJCTDEC", "OBJ-DEC", "OBJ_DEC"]
SCALE_HEADER_KEYS = ["PIXSCALE", "SECPIX", "SECPIX1", "SECPIX2", "SCALE", "SCALEX", "SCALEY"]
PEER_FILTER_KEYS = ["FILTER", "FILTNAM", "FILTNAME", "FILTER1", "INSFLID", "INSFILTE"]
DEFAULT_PRIVATE_KEY_PATH = Path("~/.codex/secrets/astrometry_net_api_key").expanduser()
FALLBACK_PRIVATE_KEY_PATHS = [
    Path("~/.codex/credentials/astrometry_net_api_key").expanduser(),
    Path("~/.config/codex/astrometry_net_api_key").expanduser(),
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    outputs = argparse.ArgumentParser(add_help=False)
    outputs.add_argument("--summary-json", help="Optional machine-readable summary JSON.")
    outputs.add_argument("--report-md", help="Optional markdown report path.")
    outputs.add_argument("--manifest-json", help="Optional provenance manifest path.")

    common = argparse.ArgumentParser(add_help=False, parents=[outputs])
    common.add_argument("path", help="Path to the local image or FITS file to inspect or upload.")

    hints = argparse.ArgumentParser(add_help=False)
    hints.add_argument("--center-ra", type=float, help="Optional center RA in degrees.")
    hints.add_argument("--center-dec", type=float, help="Optional center Dec in degrees.")
    hints.add_argument("--radius-deg", type=float, help="Optional search radius in degrees.")
    hints.add_argument("--scale-units", default="arcsecperpix", choices=["arcsecperpix", "degwidth", "arcminwidth"], help="Units for the scale arguments.")
    hints.add_argument("--scale-type", choices=["ul", "ev"], help="Override Astrometry.net scale_type.")
    hints.add_argument("--scale-lower", type=float, help="Lower scale bound.")
    hints.add_argument("--scale-upper", type=float, help="Upper scale bound.")
    hints.add_argument("--scale-est", type=float, help="Estimated scale.")
    hints.add_argument("--scale-err", type=float, default=25.0, help="Percentage error on --scale-est.")
    hints.add_argument("--downsample-factor", type=float, help="Optional Astrometry.net downsample factor.")
    hints.add_argument("--tweak-order", type=int, help="Optional Astrometry.net tweak_order.")
    hints.add_argument("--use-sextractor", action="store_true", help="Request SExtractor/source-extractor source detection.")
    hints.add_argument("--crpix-center", action="store_true", help="Request CRPIX to be set to the image center.")
    hints.add_argument("--parity", type=int, choices=[0, 1, 2], help="Optional parity hint.")

    preflight = subparsers.add_parser("preflight", parents=[common], help="Inspect a local file and infer useful Astrometry.net hints.")
    preflight.add_argument("--radius-deg", type=float, help="Optional search radius override in degrees.")
    preflight.add_argument("--scale-est", type=float, help="Optional estimated pixel scale in arcsec/pixel.")
    preflight.add_argument("--scale-err", type=float, default=25.0, help="Optional percentage error on --scale-est.")
    preflight.add_argument("--scale-lower", type=float, help="Optional lower bound in arcsec/pixel.")
    preflight.add_argument("--scale-upper", type=float, help="Optional upper bound in arcsec/pixel.")

    solve = subparsers.add_parser("solve-web", parents=[common, hints], help="Submit a copied file to nova.astrometry.net and download results.")
    solve.add_argument("--output-dir", required=True, help="Directory for downloaded products and logs.")
    solve.add_argument("--api-key", help="Astrometry.net API key. Defaults to ASTROMETRY_NET_API_KEY.")
    solve.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL of the Astrometry.net web service.")
    solve.add_argument("--publicly-visible", default="n", choices=["y", "n"], help="Whether to make the submission publicly visible.")
    solve.add_argument("--allow-modifications", default="d", choices=["d", "y", "n", "sa"], help="Astrometry.net allow_modifications setting.")
    solve.add_argument("--allow-commercial-use", default="d", choices=["d", "y", "n"], help="Astrometry.net allow_commercial_use setting.")
    solve.add_argument("--poll-sec", type=float, default=10.0, help="Polling interval in seconds.")
    solve.add_argument("--timeout-sec", type=float, default=900.0, help="Maximum wall time to wait for the solve.")
    solve.add_argument(
        "--download-product",
        action="append",
        choices=sorted(DOWNLOADABLE_PRODUCTS),
        default=[],
        help="Additional downloadable regular-result products. Repeat as needed.",
    )

    solve_url = subparsers.add_parser("solve-web-url", parents=[outputs, hints], help="Submit a remote URL to nova.astrometry.net and download results.")
    solve_url.add_argument("url", help="Remote image URL to submit through Astrometry.net url_upload.")
    solve_url.add_argument("--output-dir", required=True, help="Directory for downloaded products and logs.")
    solve_url.add_argument("--api-key", help="Astrometry.net API key. Defaults to env or private key files.")
    solve_url.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL of the Astrometry.net web service.")
    solve_url.add_argument("--publicly-visible", default="n", choices=["y", "n"], help="Whether to make the submission publicly visible.")
    solve_url.add_argument("--allow-modifications", default="d", choices=["d", "y", "n", "sa"], help="Astrometry.net allow_modifications setting.")
    solve_url.add_argument("--allow-commercial-use", default="d", choices=["d", "y", "n"], help="Astrometry.net allow_commercial_use setting.")
    solve_url.add_argument("--poll-sec", type=float, default=10.0, help="Polling interval in seconds.")
    solve_url.add_argument("--timeout-sec", type=float, default=900.0, help="Maximum wall time to wait for the solve.")
    solve_url.add_argument(
        "--download-product",
        action="append",
        choices=sorted(DOWNLOADABLE_PRODUCTS),
        default=[],
        help="Additional downloadable regular-result products. Repeat as needed.",
    )

    solve_local = subparsers.add_parser("solve-local", parents=[common, hints], help="Run a local solve-field command when Astrometry.net is installed on the machine.")
    solve_local.add_argument("--output-dir", required=True, help="Directory for local solve outputs.")
    solve_local.add_argument("--solve-field-bin", help="Optional explicit path to solve-field.")
    solve_local.add_argument("--backend-config", help="Optional backend config file for solve-field.")
    solve_local.add_argument("--index-dir", action="append", default=[], help="Optional index directory for solve-field. Repeat as needed.")
    solve_local.add_argument("--index-file", action="append", default=[], help="Optional explicit Astrometry.net index file. Repeat as needed.")
    solve_local.add_argument("--cpulimit-sec", type=int, help="Optional solve-field CPU time limit in seconds.")
    solve_local.add_argument("--wall-timeout-sec", type=int, help="Optional wall-clock timeout in seconds for the solve-field subprocess.")
    solve_local.add_argument("--overwrite", action="store_true", help="Pass --overwrite to solve-field.")
    solve_local.add_argument("--continue-run", action="store_true", help="Pass --continue to solve-field.")
    solve_local.add_argument("--skip-solved", action="store_true", help="Pass --skip-solved to solve-field.")
    solve_local.add_argument("--no-plots", action="store_true", help="Pass --no-plots to solve-field.")
    solve_local.add_argument("--depth", help="Optional solve-field --depth value.")
    solve_local.add_argument("--objs", type=int, help="Optional solve-field --objs limit.")
    solve_local.add_argument("--nsigma", type=float, help="Optional solve-field --nsigma threshold for source extraction.")
    solve_local.add_argument("--verify-wcs", help="Optional path to an existing WCS file for --verify.")
    solve_local.add_argument("--no-verify", action="store_true", help="Pass --no-verify to ignore any existing WCS headers.")

    solve_local_best = subparsers.add_parser("solve-local-best-effort", parents=[common, hints], help="Try a cautious best-effort local solve, including an aggressive compact-field single-frame retry before peer stacking when appropriate.")
    solve_local_best.add_argument("--output-dir", required=True, help="Directory for results and logs.")
    solve_local_best.add_argument("--solve-field-bin", help="Optional explicit path to solve-field.")
    solve_local_best.add_argument("--backend-config", help="Optional backend config file for solve-field.")
    solve_local_best.add_argument("--index-dir", action="append", default=[], help="Optional index directory for solve-field. Repeat as needed.")
    solve_local_best.add_argument("--index-file", action="append", default=[], help="Optional explicit Astrometry.net index file. Repeat as needed.")
    solve_local_best.add_argument("--cpulimit-sec", type=int, help="Optional solve-field CPU time limit in seconds.")
    solve_local_best.add_argument("--wall-timeout-sec", type=int, help="Optional wall-clock timeout in seconds for the solve-field subprocess.")
    solve_local_best.add_argument("--overwrite", action="store_true", help="Pass --overwrite to solve-field.")
    solve_local_best.add_argument("--continue-run", action="store_true", help="Pass --continue to solve-field.")
    solve_local_best.add_argument("--skip-solved", action="store_true", help="Pass --skip-solved to solve-field.")
    solve_local_best.add_argument("--no-plots", action="store_true", help="Pass --no-plots to solve-field.")
    solve_local_best.add_argument("--depth", help="Optional solve-field --depth value.")
    solve_local_best.add_argument("--objs", type=int, help="Optional solve-field --objs limit.")
    solve_local_best.add_argument("--nsigma", type=float, help="Optional solve-field --nsigma threshold for source extraction.")
    solve_local_best.add_argument("--verify-wcs", help="Optional path to an existing WCS file for --verify.")
    solve_local_best.add_argument("--no-verify", action="store_true", help="Pass --no-verify to ignore any existing WCS headers.")
    solve_local_best.add_argument("--peer-count", type=int, default=13, help="If a compact imaging field is detected, try stacking this many peers.")
    solve_local_best.add_argument(
        "--same-object",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require identical, non-empty OBJECT values when building a peer stack (safe default).",
    )
    solve_local_best.add_argument(
        "--same-exptime",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require matching, finite EXPTIME values when building a peer stack (safe default).",
    )
    solve_local_best.add_argument("--max-separation-index", type=int, default=32, help="Maximum index distance from the seed frame when selecting peers.")
    solve_local_best.add_argument("--fallback-scale-est", type=float, help="Fallback plate scale in arcsec/pixel for compact-field retries.")
    solve_local_best.add_argument("--fallback-scale-err", type=float, default=20.0, help="Percentage error for --fallback-scale-est.")

    stack = subparsers.add_parser("stack-peers", parents=[common], help="Build a local median stack from nearby peer FITS frames in the same sequence.")
    stack.add_argument("--output-path", required=True, help="Output FITS path for the derived median stack.")
    stack.add_argument("--peer-count", type=int, default=13, help="Target number of peer frames to include, counting the input frame.")
    stack.add_argument(
        "--same-object",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require identical, non-empty OBJECT values when selecting peers (safe default).",
    )
    stack.add_argument(
        "--same-exptime",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require matching, finite EXPTIME values when selecting peers (safe default).",
    )
    stack.add_argument("--max-separation-index", type=int, default=32, help="Maximum index distance from the seed frame when selecting peers.")
    stack.add_argument("--peer-strategy", choices=["nearest", "forward_window", "backward_window"], default="nearest", help="Peer-selection strategy for the derived stack.")
    stack.add_argument(
        "--allow-unregistered-stack",
        action="store_true",
        help=(
            "Explicitly allow an unregistered diagnostic stack when phase registration cannot be validated. "
            "Such a result is always WARNING and must not be used as a solved astrometric product."
        ),
    )

    best = subparsers.add_parser("solve-web-best-effort", parents=[common, hints], help="Try a cautious best-effort web solve, including peer stacking for compact imaging when appropriate.")
    best.add_argument("--output-dir", required=True, help="Directory for results and logs.")
    best.add_argument("--api-key", help="Astrometry.net API key. Defaults to env or private key files.")
    best.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL of the Astrometry.net web service.")
    best.add_argument("--publicly-visible", default="n", choices=["y", "n"], help="Whether to make the submission publicly visible.")
    best.add_argument("--allow-modifications", default="d", choices=["d", "y", "n", "sa"], help="Astrometry.net allow_modifications setting.")
    best.add_argument("--allow-commercial-use", default="d", choices=["d", "y", "n"], help="Astrometry.net allow_commercial_use setting.")
    best.add_argument("--poll-sec", type=float, default=10.0, help="Polling interval in seconds.")
    best.add_argument("--timeout-sec", type=float, default=900.0, help="Maximum wall time to wait for the solve.")
    best.add_argument("--peer-count", type=int, default=13, help="If a compact imaging field is detected, try stacking this many peers.")
    best.add_argument(
        "--same-object",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require identical, non-empty OBJECT values when building a peer stack (safe default).",
    )
    best.add_argument(
        "--same-exptime",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require matching, finite EXPTIME values when building a peer stack (safe default).",
    )
    best.add_argument("--max-separation-index", type=int, default=32, help="Maximum index distance from the seed frame when selecting peers.")
    best.add_argument("--fallback-scale-est", type=float, help="Fallback plate scale in arcsec/pixel for compact-field retries.")
    best.add_argument("--fallback-scale-err", type=float, default=20.0, help="Percentage error for --fallback-scale-est.")
    best.add_argument(
        "--download-product",
        action="append",
        choices=sorted(DOWNLOADABLE_PRODUCTS),
        default=[],
        help="Additional downloadable regular-result products. Repeat as needed.",
    )

    auth = subparsers.add_parser(
        "auth-check",
        parents=[outputs],
        help="Validate Astrometry.net credentials without uploading any local file.",
    )
    auth.add_argument("--api-key", help="Astrometry.net API key. Defaults to env or private key files.")
    auth.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL of the Astrometry.net web service.")

    verify = subparsers.add_parser("verify-existing-wcs", parents=[common], help="Inspect a FITS with an existing celestial WCS and create a small verification bundle.")
    verify.add_argument("--output-dir", required=True, help="Directory for verification outputs and visual quicklooks.")
    return parser.parse_args()


def _is_fits(path: Path) -> bool:
    return path.suffix.lower() in {".fits", ".fit", ".fts", ".fz"}


def _parse_angle(value, is_ra: bool):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        pass
    unit = u.hourangle if is_ra else u.deg
    try:
        return float(Angle(text, unit=unit).deg)
    except Exception:
        return None


def _first_image_hdu(path: Path):
    if not _is_fits(path):
        return None, None, None
    with fits.open(path, memmap=False) as hdus:
        for index, hdu in enumerate(hdus):
            data = getattr(hdu, "data", None)
            if data is None:
                continue
            array = np.asarray(data)
            while array.ndim > 2:
                array = array[0]
            if array.ndim == 2:
                return index, hdu.header.copy(), tuple(int(v) for v in array.shape)
    return None, None, None


def _first_celestial_wcs_hdu(path: Path):
    if not _is_fits(path):
        return None, None, None, False
    with fits.open(path, memmap=False) as hdus:
        for index, hdu in enumerate(hdus):
            header = getattr(hdu, "header", None)
            if header is None:
                continue
            try:
                wcs = WCS(header)
            except Exception:
                continue
            if not getattr(wcs, "has_celestial", False):
                continue
            data = getattr(hdu, "data", None)
            if data is None:
                return index, header.copy(), None, False
            array = np.asarray(data)
            while array.ndim > 2:
                array = array[0]
            if array.ndim == 2:
                return index, header.copy(), tuple(int(v) for v in array.shape), True
            return index, header.copy(), None, False
    return None, None, None, False


def build_astrometry_dependency_preflight(args, mode: str) -> dict:
    remote_services = []
    missing_binaries = []
    optional_backend_missing = []
    blocking_findings = []
    warning_findings = []
    network_required = mode in {"solve-web", "solve-web-url", "solve-web-best-effort"}
    if network_required:
        remote_services.append(getattr(args, "api_base", API_BASE_DEFAULT).rstrip("/"))
    if mode in {"preflight", "solve-local", "solve-local-best-effort"}:
        solve_field_bin = getattr(args, "solve_field_bin", None) or find_executable(["solve-field"])
        if solve_field_bin is None:
            optional_backend_missing.append("Local astrometry solving needs solve-field on PATH or via --solve-field-bin.")
            missing_binaries.append("solve-field")
        if getattr(args, "backend_config", None):
            config_path = Path(args.backend_config).expanduser()
            if not config_path.exists():
                blocking_findings.append(f"Backend config file not found: {public_path(config_path)}")
        if getattr(args, "index_dir", None):
            resolved = [Path(item).expanduser() for item in getattr(args, "index_dir", [])]
            missing_dirs = [public_path(item) for item in resolved if not item.exists()]
            if missing_dirs:
                warning_findings.append("Some local index directories do not exist: " + ", ".join(missing_dirs))
    if blocking_findings:
        status = "blocked"
    elif warning_findings or optional_backend_missing or missing_binaries or network_required:
        status = "warning"
    else:
        status = "ok"
    recommendation = "Local diagnostics look usable."
    if network_required:
        recommendation = "Web solves need working network access and Astrometry.net service availability."
    if missing_binaries:
        recommendation = "Install or point the tool to solve-field before relying on local astrometry solves."
    if blocking_findings:
        recommendation = "Fix the blocking local backend issues before retrying astrometry execution."
    return {
        "status": status,
        "missing_python_modules": [],
        "missing_binaries": missing_binaries,
        "network_required": network_required,
        "remote_services_detected": remote_services,
        "optional_backend_missing": optional_backend_missing,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
        "recommendation": recommendation,
    }


def infer_center_from_header(header):
    if header is None:
        return None
    for ra_key in RA_HEADER_KEYS:
        for dec_key in DEC_HEADER_KEYS:
            if ra_key in header and dec_key in header:
                ra_deg = _parse_angle(header.get(ra_key), is_ra=True)
                dec_deg = _parse_angle(header.get(dec_key), is_ra=False)
                if ra_deg is not None and dec_deg is not None:
                    return {
                        "ra_deg": ra_deg,
                        "dec_deg": dec_deg,
                        "source": f"{ra_key}/{dec_key}",
                    }
    try:
        wcs = WCS(header)
        if getattr(wcs, "has_celestial", False):
            crval = getattr(wcs.wcs, "crval", None)
            if crval is not None and len(crval) >= 2:
                return {
                    "ra_deg": float(crval[0]),
                    "dec_deg": float(crval[1]),
                    "source": "WCS CRVAL",
                }
    except Exception:
        pass
    return None


def infer_scale_from_header(header):
    if header is None:
        return None
    for key in SCALE_HEADER_KEYS:
        if key in header:
            try:
                value = float(header[key])
                if value > 0:
                    return {"arcsec_per_pixel": value, "source": key}
            except Exception:
                continue
    try:
        wcs = WCS(header)
        if getattr(wcs, "has_celestial", False):
            scales = proj_plane_pixel_scales(wcs.celestial) * 3600.0
            finite = [float(item) for item in scales if np.isfinite(item) and item > 0]
            if finite:
                return {
                    "arcsec_per_pixel": float(np.mean(finite)),
                    "source": "WCS pixel scale",
                }
    except Exception:
        pass
    return None


def estimate_field_extent(shape, scale):
    if not shape or not scale:
        return None
    try:
        height_pix, width_pix = shape
        arcsec_per_pix = float(scale["arcsec_per_pixel"])
    except Exception:
        return None
    return {
        "width_deg": (width_pix * arcsec_per_pix) / 3600.0,
        "height_deg": (height_pix * arcsec_per_pix) / 3600.0,
    }


def infer_instrument_scale_hint(header, fit_assessment: dict | None = None):
    if header is None:
        return None
    instrument = str(header.get("INSTRUME", "")).strip().lower()
    telescope = str(header.get("TELESCOP", "")).strip().lower()
    classification = (fit_assessment or {}).get("classification")
    if classification not in {"likely_direct_imaging", "likely_compact_direct_imaging"}:
        return None
    if instrument == "cafos 2.2" or telescope == "ca-2.2":
        return {
            "arcsec_per_pixel": 0.525,
            "source": "CAFOS 2.2 default imaging scale heuristic",
            "scale_err_pct": 12.0,
        }
    return None


def infer_existing_astrometric_solution(header, shape):
    if header is None:
        return None
    try:
        wcs = WCS(header)
        if not getattr(wcs, "has_celestial", False):
            return None
        center = None
        if shape and len(shape) == 2:
            height_pix, width_pix = shape
            x_center = (float(width_pix) - 1.0) / 2.0
            y_center = (float(height_pix) - 1.0) / 2.0
            try:
                ra_deg, dec_deg = wcs.celestial.pixel_to_world_values(x_center, y_center)
                if np.isfinite(ra_deg) and np.isfinite(dec_deg):
                    center = {"ra_deg": float(ra_deg), "dec_deg": float(dec_deg), "source": "WCS image center"}
            except Exception:
                center = None
        if center is None:
            center = infer_center_from_header(header)
        scale = infer_scale_from_header(header)
        ctype = None
        try:
            ctype = [str(item) for item in wcs.celestial.wcs.ctype]
        except Exception:
            ctype = None
        return {
            "has_celestial_wcs": True,
            "center": center,
            "scale": scale,
            "ctype": ctype,
        }
    except Exception:
        return None


def parse_local_solve_stdout(stdout_text: str) -> dict:
    result = {}
    if not stdout_text:
        return result
    source_count = re.search(r"simplexy:\s+found\s+(\d+)\s+sources", stdout_text)
    if source_count:
        result["source_count"] = int(source_count.group(1))
    solved_index = re.search(r"Field \d+: solved with index (\S+)\.", stdout_text)
    if solved_index:
        result["solved_index_file"] = solved_index.group(1)
    center = re.search(
        r"Field center: \(RA H:M:S, Dec D:M:S\) = \(([^,]+),([^)]+)\)\.\s*Field center: \(RA,Dec\) = \(([-+0-9.eE]+),([-+0-9.eE]+)\) deg\.",
        stdout_text,
        re.MULTILINE,
    )
    if center:
        result["center_ra_deg"] = float(center.group(3))
        result["center_dec_deg"] = float(center.group(4))
    size = re.search(
        r"Field size: ([0-9.eE+-]+) x ([0-9.eE+-]+) arcminutes",
        stdout_text,
    )
    if size:
        result["field_width_arcmin"] = float(size.group(1))
        result["field_height_arcmin"] = float(size.group(2))
    rotation = re.search(
        r"Field rotation angle: up is ([+-]?[0-9.eE+-]+) degrees",
        stdout_text,
    )
    if rotation:
        result["rotation_deg"] = float(rotation.group(1))
    parity = re.search(r"Field parity: (\w+)", stdout_text)
    if parity:
        result["parity"] = parity.group(1)
    return result


def parse_backend_config_index_dirs(config_path: Path) -> list[Path]:
    if not config_path.exists():
        return []
    index_dirs: list[Path] = []
    for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("add_path"):
            continue
        raw_value = line[len("add_path") :].strip()
        candidate_strings: list[str] = []
        if raw_value:
            candidate_strings.append(raw_value)
        try:
            candidate_strings.extend(shlex.split(raw_value, comments=False, posix=True))
        except Exception:
            pass
        for token in candidate_strings:
            candidate = Path(token).expanduser()
            if candidate.exists() and candidate.is_dir():
                index_dirs.append(candidate.resolve())
    return index_dirs


def collect_local_index_dirs(args) -> list[Path]:
    dirs: list[Path] = []
    for item in args.index_dir or []:
        candidate = Path(item).expanduser()
        if candidate.exists() and candidate.is_dir():
            dirs.append(candidate.resolve())
    if args.backend_config:
        dirs.extend(parse_backend_config_index_dirs(Path(args.backend_config).expanduser()))
    deduped: list[Path] = []
    seen = set()
    for item in dirs:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(item)
    return deduped


def summarize_local_index_health(index_dirs: list[Path]) -> dict | None:
    if not index_dirs or scan_index_dir is None:
        return None
    summaries = []
    suspicious_total = 0
    for index_dir in index_dirs:
        try:
            raw = scan_index_dir(index_dir, suspicious_bytes=4096)
        except Exception:
            continue
        suspicious_total += int(raw.get("suspicious_small_file_count") or 0)
        summaries.append(
            {
                "index_dir": raw.get("index_dir"),
                "file_count": raw.get("file_count"),
                "total_size_gib": raw.get("total_size_gib"),
                "series_counts": raw.get("series_counts"),
                "suspicious_small_file_count": raw.get("suspicious_small_file_count"),
                "suspicious_small_files": raw.get("suspicious_small_files"),
            }
        )
    if not summaries:
        return None
    return {
        "checked_dirs": [item["index_dir"] for item in summaries],
        "any_suspicious_small_files": bool(suspicious_total),
        "suspicious_small_file_count": suspicious_total,
        "dirs": summaries,
    }


def build_scale_bounds(scale_est: float | None, scale_err_pct: float | None):
    if scale_est is None:
        return None
    err_fraction = max(float(scale_err_pct or 0.0), 0.0) / 100.0
    lower = scale_est * max(0.0, 1.0 - err_fraction)
    upper = scale_est * (1.0 + err_fraction)
    if lower <= 0 or upper <= 0:
        return None
    return {"lower": lower, "upper": upper}


def robust_sigma(values):
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    median = float(np.nanmedian(finite))
    mad = float(np.nanmedian(np.abs(finite - median)))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.nanstd(finite))
    return sigma if np.isfinite(sigma) and sigma > 0 else None


def image_quality_proxy(image) -> dict:
    array = np.asarray(image, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return {
            "median": None,
            "robust_sigma": None,
            "saturation_pixels": None,
            "bright_pixels": None,
            "estimated_peak_count": None,
            "quality_score": None,
        }
    median = float(np.nanmedian(finite))
    sigma = robust_sigma(finite)
    saturation = int(np.sum(finite >= 65535))
    bright_pixels = None
    peak_count = None
    quality_score = None
    if sigma is not None and sigma > 0:
        threshold = median + 5.0 * sigma
        mask = array > threshold
        bright_pixels = int(np.sum(mask))
        core = mask[1:-1, 1:-1]
        if core.size:
            neighborhood = [
                mask[:-2, :-2],
                mask[:-2, 1:-1],
                mask[:-2, 2:],
                mask[1:-1, :-2],
                mask[1:-1, 2:],
                mask[2:, :-2],
                mask[2:, 1:-1],
                mask[2:, 2:],
            ]
            local_max = np.ones_like(core, dtype=bool)
            center_values = array[1:-1, 1:-1]
            for neighbor in [
                array[:-2, :-2],
                array[:-2, 1:-1],
                array[:-2, 2:],
                array[1:-1, :-2],
                array[1:-1, 2:],
                array[2:, :-2],
                array[2:, 1:-1],
                array[2:, 2:],
            ]:
                local_max &= center_values >= neighbor
            peak_count = int(np.sum(core & local_max))
            quality_score = float(max(0, peak_count) + 0.002 * max(0, bright_pixels or 0) - 0.01 * saturation)
    return {
        "median": median,
        "robust_sigma": sigma,
        "saturation_pixels": saturation,
        "bright_pixels": bright_pixels,
        "estimated_peak_count": peak_count,
        "quality_score": quality_score,
    }


def render_fits_qa_png(input_path: Path, output_path: Path, title: str | None = None, annotations_payload: dict | None = None, wcs_header_path: Path | None = None):
    with suppress_fd_output(True):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

    hdu_index, header, _shape = _first_image_hdu(input_path)
    if header is None:
        return None
    with fits.open(input_path, memmap=False) as hdus:
        data = np.asarray(hdus[hdu_index].data)
    while data.ndim > 2:
        data = data[0]
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return None
    vmin, vmax = np.percentile(finite, [1, 99])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        vmin = float(np.nanmin(finite))
        vmax = float(np.nanmax(finite))
        if vmin == vmax:
            vmax = vmin + 1.0
    wcs_header = header
    if wcs_header_path is not None and Path(wcs_header_path).exists():
        try:
            wcs_header = fits.getheader(wcs_header_path)
        except Exception:
            wcs_header = header
    try:
        maybe_wcs = WCS(wcs_header)
        has_celestial = bool(getattr(maybe_wcs, "has_celestial", False))
    except Exception:
        maybe_wcs = None
        has_celestial = False
    figure = plt.figure(figsize=(7, 6))
    if has_celestial:
        axis = figure.add_subplot(111, projection=maybe_wcs.celestial)
        axis.set_xlabel("RA")
        axis.set_ylabel("Dec")
        try:
            axis.coords.grid(color="white", alpha=0.35, linestyle=":")
        except Exception:
            pass
    else:
        axis = figure.add_subplot(111)
        axis.set_xlabel("X (pixel)")
        axis.set_ylabel("Y (pixel)")
    artist = axis.imshow(data, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
    if annotations_payload and isinstance(annotations_payload.get("annotations"), list):
        for item in annotations_payload["annotations"]:
            x = item.get("pixelx")
            y = item.get("pixely")
            radius = item.get("radius", 12.0)
            if x is None or y is None:
                continue
            circle = plt.Circle((x, y), radius=max(4.0, min(float(radius), 80.0)), fill=False, ec="tab:orange", lw=1.1, alpha=0.9)
            axis.add_patch(circle)
            names = item.get("names") or []
            if names:
                axis.text(x + 4, y + 4, str(names[0]), color="tab:orange", fontsize=7, ha="left", va="bottom")
    figure.colorbar(artist, ax=axis, fraction=0.046, pad=0.04)
    axis.set_title(title or input_path.name)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return public_path(output_path.resolve())


def materialize_publicish_path(value) -> Path | None:
    if not value:
        return None
    candidate = Path(str(value).replace("~", str(Path.home()))).expanduser()
    try:
        return candidate.resolve() if candidate.exists() else candidate
    except Exception:
        return candidate


def build_compact_visual_review(input_path: Path, output_dir: Path, solved_payload: dict, stack_path: Path | None = None, review_label: str | None = None) -> tuple[dict, list[Path]]:
    downloaded_products = solved_payload.get("downloaded_products") or {}
    wcs_header_path = materialize_publicish_path(downloaded_products.get("wcs"))
    if wcs_header_path is None or not wcs_header_path.exists():
        return {}, []
    input_shape = _first_image_hdu(input_path)[2]
    stack_shape = _first_image_hdu(stack_path)[2] if stack_path and stack_path.exists() else None
    if stack_path is not None and stack_path.exists():
        if input_shape and stack_shape and tuple(input_shape) == tuple(stack_shape):
            review_source = input_path
            review_basis = "original_input_with_stack_derived_wcs"
            title = review_label or f"Compact-field review on original frame: {input_path.name}"
        else:
            review_source = stack_path
            review_basis = "derived_stack_with_solved_wcs"
            title = review_label or f"Compact-field review on derived stack: {stack_path.name}"
    else:
        review_source = input_path
        review_basis = "original_input_with_solved_wcs"
        title = review_label or f"Compact-field review: {input_path.name}"
    review_output = output_dir / "compact_visual_review.png"
    review_png = render_fits_qa_png(
        review_source,
        review_output,
        title=title,
        wcs_header_path=wcs_header_path,
    )
    if not review_png:
        return {}, []
    return (
        {
            "review_image": review_png,
            "review_basis": review_basis,
            "review_source": public_path(review_source.resolve()),
            "wcs_header": public_path(wcs_header_path.resolve()),
            "teaching_note": "Use this quicklook as a light visual sanity check before trusting a rescued compact-field solution in a report or class notebook.",
        },
        [review_output],
    )


def build_existing_wcs_verification(path: Path) -> dict:
    path = path.resolve()
    preflight = build_preflight(path, argparse.Namespace())
    existing = preflight.get("existing_astrometric_solution")
    if not existing:
        raise SystemExit(f"No celestial WCS was detected in {path}.")
    image_hdu_index = preflight.get("image_hdu_index")
    wcs_hdu_index = preflight.get("wcs_hdu_index")
    data = None
    header = None
    has_image_data = False
    if image_hdu_index is not None:
        with fits.open(path, memmap=False) as hdus:
            hdu = hdus[image_hdu_index]
            data = np.asarray(hdu.data)
            header = hdu.header.copy()
        while data.ndim > 2:
            data = data[0]
        has_image_data = data.ndim == 2
    elif wcs_hdu_index is not None:
        with fits.open(path, memmap=False) as hdus:
            header = hdus[wcs_hdu_index].header.copy()
    corners_world = []
    if has_image_data and header is not None:
        wcs = WCS(header).celestial
        height, width = data.shape
        corners_pix = [(0.0, 0.0), (width - 1.0, 0.0), (0.0, height - 1.0), (width - 1.0, height - 1.0)]
        for x_pix, y_pix in corners_pix:
            try:
                ra_deg, dec_deg = wcs.pixel_to_world_values(x_pix, y_pix)
                corners_world.append({"x": x_pix, "y": y_pix, "ra_deg": float(ra_deg), "dec_deg": float(dec_deg)})
            except Exception:
                continue
    header_center = infer_center_from_header(header)
    wcs_center = existing.get("center")
    center_offset_arcsec = None
    if header_center and wcs_center:
        dra = (header_center["ra_deg"] - wcs_center["ra_deg"]) * np.cos(np.deg2rad(wcs_center["dec_deg"]))
        ddec = header_center["dec_deg"] - wcs_center["dec_deg"]
        center_offset_arcsec = float(np.hypot(dra, ddec) * 3600.0)
    notes = [
        "This path verifies an existing celestial WCS instead of requesting a new blind solve.",
        "A non-zero header-vs-WCS center offset is not automatically an error; it may reflect approximate telescope pointing metadata.",
    ]
    result_status = "verified_existing_wcs"
    if not has_image_data:
        result_status = "wcs_header_only"
        notes.append("A celestial WCS was found, but no 2D image plane was available for corner and image-quality verification.")
    return {
        "tool": "astrometry_net_workbench",
        "mode": "verify-existing-wcs",
        "result_status": result_status,
        "input_path": public_path(path),
        "preflight": preflight,
        "wcs_center": wcs_center,
        "header_center": header_center,
        "center_offset_arcsec": center_offset_arcsec,
        "field_corners": corners_world,
        "image_quality_proxy": image_quality_proxy(data) if has_image_data else None,
        "has_image_data": has_image_data,
        "notes": notes,
    }


def parse_sequence_index(path: Path) -> tuple[str, int] | None:
    stem = path.stem
    for separator in ["_", "-"]:
        if separator in stem:
            prefix, suffix = stem.rsplit(separator, 1)
            if suffix.isdigit():
                return prefix, int(suffix)
    return None


def classify_fits_kind(path: Path, header, shape, existing_wcs: dict | None = None) -> dict:
    stem = path.stem.lower()
    object_text = str(header.get("OBJECT", "") if header is not None else "").lower()
    text = f"{stem} {object_text}"
    aspect_ratio = None
    if shape and min(shape) > 0:
        aspect_ratio = max(shape) / min(shape)
    if existing_wcs and existing_wcs.get("has_celestial_wcs"):
        return {
            "classification": "already_astrometrically_calibrated",
            "recommended_action": "reuse_existing_wcs",
            "reason": "the FITS header already exposes a celestial WCS solution; prefer reusing or verifying it before submitting a new blind solve",
            "aspect_ratio": aspect_ratio,
        }
    spectroscopy_tokens = ["g100", "g-100", "grism", "arc", "hghe", "wavecal", "spectro"]
    compact_tokens = ["toi", "qatar", "wd", "trappist", "transit"]
    likely_spectroscopy = any(token in text for token in spectroscopy_tokens) or (aspect_ratio is not None and aspect_ratio >= 1.35)
    likely_compact = (
        not likely_spectroscopy
        and shape is not None
        and max(shape) <= 800
    )
    if likely_spectroscopy:
        return {
            "classification": "likely_spectroscopy_or_arc",
            "recommended_action": "avoid_plate_solve",
            "reason": "filename/header tokens and image geometry look more like spectroscopy or calibration than direct imaging",
            "aspect_ratio": aspect_ratio,
        }
    if likely_compact:
        recommendation = "stack_peers_then_solve"
        if any(token in text for token in compact_tokens):
            reason = "compact direct-imaging field; peer stacking is often more reliable than single-frame blind solving"
        else:
            reason = "small direct-imaging field; peer stacking may improve the solve"
        return {
            "classification": "likely_compact_direct_imaging",
            "recommended_action": recommendation,
            "reason": reason,
            "aspect_ratio": aspect_ratio,
        }
    return {
        "classification": "likely_direct_imaging",
        "recommended_action": "solve_directly",
        "reason": "shape and metadata look compatible with ordinary direct imaging",
        "aspect_ratio": aspect_ratio,
    }


def select_peer_frames(path: Path, header, shape, peer_count: int, same_object: bool, same_exptime: bool, max_separation_index: int):
    return select_peer_frames_with_strategy(
        path,
        header,
        shape,
        peer_count=peer_count,
        same_object=same_object,
        same_exptime=same_exptime,
        max_separation_index=max_separation_index,
        strategy="nearest",
    )


def _normalized_peer_header_value(value) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value).strip()).casefold()
    return normalized or None


def _peer_filter_value(header) -> str | None:
    for key in PEER_FILTER_KEYS:
        value = _normalized_peer_header_value(header.get(key))
        if value:
            return value
    return None


def _finite_header_float(header, key: str) -> float | None:
    try:
        value = float(header.get(key))
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _collect_peer_candidates(path: Path, header, shape, same_object: bool, same_exptime: bool, max_separation_index: int):
    seq = parse_sequence_index(path)
    if seq is None:
        return None, []
    prefix, target_index = seq
    object_value = _normalized_peer_header_value(header.get("OBJECT")) if header is not None else None
    filter_value = _peer_filter_value(header) if header is not None else None
    exptime = _finite_header_float(header, "EXPTIME") if header is not None else None
    seed_path = path.resolve()
    candidates = []
    for candidate in sorted(path.parent.glob(f"{prefix}_*.fits")):
        parsed = parse_sequence_index(candidate)
        if parsed is None or parsed[0] != prefix:
            continue
        distance = abs(parsed[1] - target_index)
        if distance > max_separation_index:
            continue
        try:
            with fits.open(candidate, memmap=False) as hdus:
                data = getattr(hdus[0], "data", None)
                cand_shape = None if data is None else tuple(int(v) for v in np.asarray(data).shape[-2:])
                cand_header = hdus[0].header.copy()
        except Exception:
            continue
        is_seed = candidate.resolve() == seed_path
        if shape is not None and cand_shape != tuple(shape):
            continue
        cand_object = _normalized_peer_header_value(cand_header.get("OBJECT"))
        if same_object and not is_seed:
            if object_value is None or cand_object is None or cand_object != object_value:
                continue
        cand_filter = _peer_filter_value(cand_header)
        if not is_seed and (filter_value is not None or cand_filter is not None):
            if filter_value is None or cand_filter is None or cand_filter != filter_value:
                continue
        if same_exptime and not is_seed:
            cand_exptime = _finite_header_float(cand_header, "EXPTIME")
            if exptime is None or cand_exptime is None or abs(cand_exptime - exptime) > 1e-6:
                continue
        candidates.append({"distance": distance, "index": parsed[1], "path": candidate})
    candidates.sort(key=lambda item: item["index"])
    return target_index, candidates


def _window_selection(candidates: list[dict], target_index: int, peer_count: int, before_count: int, after_count: int):
    if not candidates:
        return []
    target_positions = [idx for idx, item in enumerate(candidates) if item["index"] == target_index]
    if not target_positions:
        return []
    target_pos = target_positions[0]
    start = target_pos - before_count
    end = target_pos + after_count + 1
    if start < 0:
        end += -start
        start = 0
    if end > len(candidates):
        start = max(0, start - (end - len(candidates)))
        end = len(candidates)
    selected = candidates[start:end]
    if len(selected) > peer_count:
        selected = selected[:peer_count]
    return [item["path"] for item in selected]


def select_peer_frames_with_strategy(path: Path, header, shape, peer_count: int, same_object: bool, same_exptime: bool, max_separation_index: int, strategy: str = "nearest"):
    target_index, candidates = _collect_peer_candidates(
        path,
        header,
        shape,
        same_object=same_object,
        same_exptime=same_exptime,
        max_separation_index=max_separation_index,
    )
    if target_index is None:
        return []
    if strategy == "nearest":
        ranked = sorted(candidates, key=lambda item: (item["distance"], item["index"]))
        selected = [item["path"] for item in ranked[: max(1, peer_count)]]
    elif strategy == "forward_window":
        before_count = max(0, (peer_count - 1) // 3)
        after_count = max(0, peer_count - 1 - before_count)
        selected = _window_selection(candidates, target_index, peer_count, before_count, after_count)
    elif strategy == "backward_window":
        after_count = max(0, (peer_count - 1) // 3)
        before_count = max(0, peer_count - 1 - after_count)
        selected = _window_selection(candidates, target_index, peer_count, before_count, after_count)
    else:
        selected = []
    return selected


def _registration_ready_image(data):
    array = np.asarray(data, dtype=float)
    finite = np.isfinite(array)
    if int(np.sum(finite)) < max(25, int(0.5 * array.size)):
        raise ValueError("insufficient finite pixels for phase registration")
    median = float(np.nanmedian(array))
    prepared = np.where(finite, array, median) - median
    scale = float(np.nanstd(prepared))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("image has no measurable structure for phase registration")
    return prepared / scale


def _registration_correlation(reference, aligned) -> tuple[float, float]:
    finite = np.isfinite(reference) & np.isfinite(aligned)
    overlap = float(np.mean(finite))
    if int(np.sum(finite)) < 25:
        return overlap, float("nan")
    ref_values = np.asarray(reference[finite], dtype=float)
    aligned_values = np.asarray(aligned[finite], dtype=float)
    ref_values -= np.mean(ref_values)
    aligned_values -= np.mean(aligned_values)
    denominator = float(np.sqrt(np.sum(ref_values**2) * np.sum(aligned_values**2)))
    correlation = float(np.sum(ref_values * aligned_values) / denominator) if denominator > 0 else float("nan")
    return overlap, correlation


def build_peer_stack(paths: list[Path], output_path: Path, *, allow_unregistered: bool = False) -> dict:
    if len(paths) < 3:
        raise SystemExit(
            "At least three metadata-compatible peer frames are required for a safe astrometric stack; "
            f"found {len(paths)}."
        )
    arrays = []
    header = None
    for path in paths:
        with fits.open(path, memmap=False) as hdus:
            data = np.asarray(hdus[0].data, dtype=np.float32)
            arrays.append(data)
            if header is None:
                header = hdus[0].header.copy()
    registration = []
    registration_warning = None
    try:
        from scipy.ndimage import shift as ndimage_shift
        from skimage.registration import phase_cross_correlation

        reference = arrays[0]
        reference_prepared = _registration_ready_image(reference)
        registered_arrays = [reference]
        registration.append(
            {
                "path": public_path(paths[0].resolve()),
                "shift_yx": [0.0, 0.0],
                "overlap_fraction": 1.0,
                "correlation": 1.0,
            }
        )
        for path, array in zip(paths[1:], arrays[1:]):
            prepared = _registration_ready_image(array)
            shift_yx, _error, _phase = phase_cross_correlation(
                reference_prepared,
                prepared,
                upsample_factor=10,
            )
            if not np.all(np.isfinite(shift_yx)):
                raise ValueError(f"non-finite phase shift for {path.name}")
            shift_norm = float(np.hypot(*shift_yx))
            if shift_norm > 0.35 * min(reference.shape):
                raise ValueError(f"implausibly large phase shift ({shift_norm:.3f} px) for {path.name}")
            aligned = ndimage_shift(array, shift=shift_yx, order=1, mode="constant", cval=np.nan, prefilter=False)
            overlap, correlation = _registration_correlation(reference, aligned)
            if overlap < 0.60 or not np.isfinite(correlation) or correlation < 0.50:
                raise ValueError(
                    f"registration QA failed for {path.name}: overlap={overlap:.3f}, correlation={correlation:.3f}"
                )
            registered_arrays.append(aligned)
            registration.append(
                {
                    "path": public_path(path.resolve()),
                    "shift_yx": [float(shift_yx[0]), float(shift_yx[1])],
                    "overlap_fraction": overlap,
                    "correlation": correlation,
                }
            )
        arrays_for_stack = registered_arrays
        registration_status = "registered"
    except Exception as exc:
        if not allow_unregistered:
            raise SystemExit(
                "Peer-stack registration could not be validated; refusing an unregistered astrometric stack: "
                f"{exc}"
            ) from None
        arrays_for_stack = arrays
        registration_status = "unregistered_opt_in"
        registration_warning = f"Unregistered stack explicitly allowed after registration failure: {exc}"
        registration = []
    median_stack = np.nanmedian(np.stack(arrays_for_stack, axis=0), axis=0)
    quality = image_quality_proxy(median_stack)
    if header is not None and "BLANK" in header:
        del header["BLANK"]
    header["HISTORY"] = f"Median stack built from {len(paths)} peer frames for Astrometry.net best-effort solving"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=median_stack, header=header).writeto(output_path, overwrite=True)
    return {
        "stack_path": public_path(output_path.resolve()),
        "member_count": len(paths),
        "members": [public_path(path.resolve()) for path in paths],
        "quality_proxy": quality,
        "registration_status": registration_status,
        "registration": registration,
        "registration_warning": registration_warning,
    }


def build_preflight(path: Path, args) -> dict:
    path = path.resolve()
    payload = {
        "tool": "astrometry_net_workbench",
        "mode": "preflight",
        "input_path": public_path(path),
        "input_exists": path.exists(),
        "input_kind": "fits" if _is_fits(path) else "generic-image-or-file",
    }
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")
    hdu_index, header, shape = _first_image_hdu(path)
    wcs_hdu_index, wcs_header, wcs_shape, wcs_has_image = _first_celestial_wcs_hdu(path)
    header_for_subset = header or wcs_header
    wcs_probe_header = wcs_header or header
    wcs_probe_shape = wcs_shape or shape
    payload["image_hdu_index"] = hdu_index
    payload["image_shape"] = list(shape) if shape else None
    payload["wcs_hdu_index"] = wcs_hdu_index
    payload["wcs_hdu_has_image_data"] = bool(wcs_has_image) if wcs_hdu_index is not None else None
    payload["wcs_shape"] = list(wcs_shape) if wcs_shape else None
    if header_for_subset is not None:
        payload["header_subset"] = {
            key: header_for_subset.get(key)
            for key in ["OBJECT", "DATE-OBS", "EXPTIME", "FILTER", "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2"]
            if key in header_for_subset
        }
    existing_wcs = infer_existing_astrometric_solution(wcs_probe_header, wcs_probe_shape)
    center = infer_center_from_header(header_for_subset)
    scale = infer_scale_from_header(wcs_probe_header or header_for_subset)
    field_extent = estimate_field_extent(shape, scale)
    fit_assessment = classify_fits_kind(path, header_for_subset, shape, existing_wcs=existing_wcs)
    instrument_scale_hint = infer_instrument_scale_hint(header_for_subset, fit_assessment)
    payload["inferred_center"] = center
    payload["inferred_scale"] = scale
    payload["instrument_scale_hint"] = instrument_scale_hint
    payload["estimated_field_extent"] = field_extent
    payload["existing_astrometric_solution"] = existing_wcs
    payload["fit_assessment"] = fit_assessment
    payload["dependency_preflight"] = build_astrometry_dependency_preflight(args, mode="preflight")
    if _is_fits(path) and hdu_index is not None:
        with fits.open(path, memmap=False) as hdus:
            data = np.asarray(hdus[hdu_index].data)
        while data.ndim > 2:
            data = data[0]
        payload["image_quality_proxy"] = image_quality_proxy(data)
    elif existing_wcs:
        payload["image_quality_proxy"] = None

    solve_hints = {}
    if center:
        solve_hints["center_ra"] = center["ra_deg"]
        solve_hints["center_dec"] = center["dec_deg"]
    radius_deg = getattr(args, "radius_deg", None)
    scale_lower = getattr(args, "scale_lower", None)
    scale_upper = getattr(args, "scale_upper", None)
    scale_est = getattr(args, "scale_est", None)
    scale_err = getattr(args, "scale_err", 25.0)
    if radius_deg is not None:
        solve_hints["radius"] = radius_deg
    elif center:
        solve_hints["radius"] = 1.0
    if scale_lower is not None and scale_upper is not None:
        solve_hints.update(
            {
                "scale_type": "ul",
                "scale_units": "arcsecperpix",
                "scale_lower": scale_lower,
                "scale_upper": scale_upper,
            }
        )
    elif scale_est is not None:
        solve_hints.update(
            {
                "scale_type": "ev",
                "scale_units": "arcsecperpix",
                "scale_est": scale_est,
                "scale_err": scale_err,
            }
        )
    elif scale:
        solve_hints.update(
            {
                "scale_type": "ev",
                "scale_units": "arcsecperpix",
                "scale_est": scale["arcsec_per_pixel"],
                "scale_err": scale_err,
            }
        )
    elif instrument_scale_hint:
        solve_hints.update(
            {
                "scale_type": "ev",
                "scale_units": "arcsecperpix",
                "scale_est": instrument_scale_hint["arcsec_per_pixel"],
                "scale_err": instrument_scale_hint["scale_err_pct"],
            }
        )
    payload["suggested_solve_hints"] = solve_hints
    local_hints = {}
    if solve_hints.get("center_ra") is not None and solve_hints.get("center_dec") is not None:
        local_hints["ra"] = solve_hints["center_ra"]
        local_hints["dec"] = solve_hints["center_dec"]
        if solve_hints.get("radius") is not None:
            local_hints["radius"] = solve_hints["radius"]
    if solve_hints.get("scale_type") == "ul":
        local_hints["scale_low"] = solve_hints.get("scale_lower")
        local_hints["scale_high"] = solve_hints.get("scale_upper")
        local_hints["scale_units"] = solve_hints.get("scale_units")
    elif solve_hints.get("scale_type") == "ev":
        bounds = build_scale_bounds(solve_hints.get("scale_est"), solve_hints.get("scale_err"))
        if bounds:
            local_hints["scale_low"] = bounds["lower"]
            local_hints["scale_high"] = bounds["upper"]
            local_hints["scale_units"] = solve_hints.get("scale_units")
    payload["suggested_local_solve_args"] = local_hints
    payload["notes"] = [
        "Astrometry.net usually solves faster and more reliably when you provide approximate scale and sky position.",
        "Treat the inferred FITS hints as starting points, not as guaranteed truth.",
        "Astrometry.net is designed to prefer no answer over a false positive solve.",
    ]
    if fit_assessment.get("recommended_action") == "reuse_existing_wcs":
        payload["notes"].append("A celestial WCS is already present in this FITS header; reusing or verifying it is usually preferable to requesting a new blind solve.")
    elif fit_assessment.get("recommended_action") == "avoid_plate_solve":
        payload["notes"].append("This file looks more like spectroscopy or calibration than a normal imaging field; avoid blind plate solving unless you have a very specific reason.")
    elif fit_assessment.get("recommended_action") == "stack_peers_then_solve":
        payload["recommended_operational_local_route"] = "solve-local-best-effort"
        payload["diagnostic_local_route"] = "solve-local"
        payload["notes"].append(
            "This looks like a compact imaging field; use solve-local-best-effort as the normal operational path and treat plain solve-local as a stricter diagnostic."
        )
    if center is None:
        payload["notes"].append("No RA/Dec-like center hint was found in the FITS header.")
    if scale is None and scale_est is None and scale_lower is None and instrument_scale_hint is None:
        payload["notes"].append("No pixel-scale hint was inferred; consider supplying one manually.")
    elif scale is None and instrument_scale_hint is not None:
        payload["notes"].append("A cautious instrument-based scale hint was inferred because the FITS matches a known direct-imaging setup.")
    if hdu_index is None and existing_wcs:
        payload["notes"].append("A celestial WCS was detected, but no 2D image plane was available for image-quality QA.")
    return payload


class AstrometryNetClient:
    def __init__(self, api_key: str, api_base: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.session_key = None

    def _api_url(self, suffix: str) -> str:
        return f"{self.api_base}/api/{suffix.lstrip('/')}"

    def _json_post(self, suffix: str, payload: dict, files=None):
        response = requests.post(
            self._api_url(suffix),
            data={"request-json": json.dumps(payload)},
            files=files,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def _json_get(self, suffix: str):
        response = requests.get(self._api_url(suffix), timeout=120)
        response.raise_for_status()
        return response.json()

    def login(self):
        result = self._json_post("login", {"apikey": self.api_key})
        if result.get("status") != "success" or not result.get("session"):
            raise RuntimeError(f"Astrometry.net login failed: {result}")
        self.session_key = result["session"]
        return result

    def upload_file(self, path: Path, submission_args: dict):
        if not self.session_key:
            self.login()
        payload = {
            "session": self.session_key,
            **submission_args,
        }
        with path.open("rb") as handle:
            result = self._json_post(
                "upload",
                payload,
                files={"file": (path.name, handle, "application/octet-stream")},
            )
        return result

    def upload_url(self, url: str, submission_args: dict):
        if not self.session_key:
            self.login()
        payload = {
            "session": self.session_key,
            "url": url,
            **submission_args,
        }
        return self._json_post("url_upload", payload)

    def submission_status(self, subid: int):
        return self._json_get(f"submissions/{subid}")

    def job_status(self, jobid: int):
        return self._json_get(f"jobs/{jobid}")

    def job_info(self, jobid: int):
        return self._json_get(f"jobs/{jobid}/info/")

    def calibration(self, jobid: int):
        return self._json_get(f"jobs/{jobid}/calibration/")

    def annotations(self, jobid: int):
        return self._json_get(f"jobs/{jobid}/annotations/")

    def objects_in_field(self, jobid: int):
        return self._json_get(f"jobs/{jobid}/objects_in_field/")

    def machine_tags(self, jobid: int):
        return self._json_get(f"jobs/{jobid}/machine_tags/")

    def download_regular_file(self, route_name: str, jobid: int, destination: Path):
        response = requests.get(f"{self.api_base}/{route_name}/{jobid}", timeout=240)
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination


def find_solve_field(explicit_bin: str | None = None) -> str | None:
    if explicit_bin:
        candidate = str(Path(explicit_bin).expanduser())
        return candidate if Path(candidate).exists() else None
    return shutil.which("solve-field")


def collect_local_products(base_path: Path) -> dict:
    outputs = {}
    for label, suffix in LOCAL_STANDARD_PRODUCTS.items():
        candidate = Path(f"{base_path}{suffix}")
        if candidate.exists():
            outputs[label] = public_path(candidate)
    return outputs


def _read_key_file(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except Exception:
        return None
    return None


def _key_file_permission_note(path: Path) -> str | None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except Exception:
        return None
    if mode & 0o077:
        return "private key file permissions are broader than 600"
    return None


def discover_api_key(cli_value: str | None) -> tuple[str, dict]:
    if cli_value:
        return cli_value.strip(), {"source": "cli"}

    env_key = os.environ.get("ASTROMETRY_NET_API_KEY", "").strip()
    if env_key:
        return env_key, {"source": "env:ASTROMETRY_NET_API_KEY"}

    env_file = os.environ.get("ASTROMETRY_NET_API_KEY_FILE", "").strip()
    if env_file:
        env_file_path = Path(env_file).expanduser()
        key = _read_key_file(env_file_path)
        if key:
            return key, {
                "source": "env:ASTROMETRY_NET_API_KEY_FILE",
                "key_file": public_path(env_file_path),
                "warnings": [note for note in [_key_file_permission_note(env_file_path)] if note],
            }

    candidate_paths = [DEFAULT_PRIVATE_KEY_PATH, *FALLBACK_PRIVATE_KEY_PATHS]
    for candidate in candidate_paths:
        key = _read_key_file(candidate)
        if key:
            return key, {
                "source": "private-key-file",
                "key_file": public_path(candidate),
                "warnings": [note for note in [_key_file_permission_note(candidate)] if note],
            }

    raise SystemExit(
        "No Astrometry.net API key found. Supply --api-key, set ASTROMETRY_NET_API_KEY, set ASTROMETRY_NET_API_KEY_FILE, or store a private key in ~/.codex/secrets/astrometry_net_api_key."
    )


def sanitize_login_payload(login_result: dict) -> dict:
    status = login_result.get("status")
    message = login_result.get("message")
    if status == "success":
        message = "authentication succeeded"
    elif isinstance(message, str) and "authenticated user" in message.lower():
        message = "authentication response received"
    return {
        "status": status,
        "message": message,
        "session_received": bool(login_result.get("session")),
    }


def build_submission_args(args, preflight: dict) -> dict:
    submission = {
        "publicly_visible": args.publicly_visible,
        "allow_modifications": args.allow_modifications,
        "allow_commercial_use": args.allow_commercial_use,
    }
    center_ra = args.center_ra
    center_dec = args.center_dec
    if center_ra is None and preflight.get("inferred_center"):
        center_ra = preflight["inferred_center"]["ra_deg"]
    if center_dec is None and preflight.get("inferred_center"):
        center_dec = preflight["inferred_center"]["dec_deg"]
    if center_ra is not None and center_dec is not None:
        submission["center_ra"] = center_ra
        submission["center_dec"] = center_dec
        if args.radius_deg is not None:
            submission["radius"] = args.radius_deg
        elif preflight.get("suggested_solve_hints", {}).get("radius") is not None:
            submission["radius"] = preflight["suggested_solve_hints"]["radius"]
    if args.downsample_factor is not None:
        submission["downsample_factor"] = args.downsample_factor
    if args.tweak_order is not None:
        submission["tweak_order"] = args.tweak_order
    if args.use_sextractor:
        submission["use_sextractor"] = True
    if args.crpix_center:
        submission["crpix_center"] = True
    if args.parity is not None:
        submission["parity"] = args.parity

    if args.scale_type:
        submission["scale_type"] = args.scale_type
    if args.scale_units:
        submission["scale_units"] = args.scale_units

    if submission.get("scale_type") == "ul" or (args.scale_lower is not None and args.scale_upper is not None):
        submission["scale_type"] = "ul"
        submission["scale_lower"] = args.scale_lower if args.scale_lower is not None else preflight.get("suggested_solve_hints", {}).get("scale_lower")
        submission["scale_upper"] = args.scale_upper if args.scale_upper is not None else preflight.get("suggested_solve_hints", {}).get("scale_upper")
    elif args.scale_est is not None or preflight.get("suggested_solve_hints", {}).get("scale_est") is not None:
        submission["scale_type"] = "ev"
        submission["scale_est"] = args.scale_est if args.scale_est is not None else preflight["suggested_solve_hints"].get("scale_est")
        submission["scale_err"] = args.scale_err
    else:
        submission.pop("scale_units", None)

    return {key: value for key, value in submission.items() if value is not None}


def wait_for_job(client: AstrometryNetClient, subid: int, poll_sec: float, timeout_sec: float):
    started = time.time()
    seen_jobs = []
    while True:
        submission = client.submission_status(subid)
        jobs = [job for job in submission.get("jobs", []) if job]
        if jobs:
            seen_jobs = jobs
            break
        if time.time() - started > timeout_sec:
            raise TimeoutError(f"Timed out waiting for a job id from submission {subid}.")
        time.sleep(poll_sec)
    jobid = int(seen_jobs[0])
    while True:
        status = client.job_status(jobid)
        if status.get("status") == "success":
            return submission, jobid, status
        if status.get("status") == "failure":
            raise RuntimeError(f"Astrometry.net job {jobid} failed: {status}")
        if time.time() - started > timeout_sec:
            raise TimeoutError(f"Timed out waiting for Astrometry.net job {jobid}.")
        time.sleep(poll_sec)


def download_products(client: AstrometryNetClient, jobid: int, output_dir: Path, requested_products: list[str], original_input_path: Path | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    json_payloads = {
        "calibration": client.calibration(jobid),
        "annotations": client.annotations(jobid),
        "info": client.job_info(jobid),
        "objects_in_field": client.objects_in_field(jobid),
        "machine_tags": client.machine_tags(jobid),
    }
    for name, payload in json_payloads.items():
        destination = output_dir / f"{name}.json"
        destination.write_text(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        outputs[name] = public_path(destination)
    required_products = {"new_fits", "wcs"}
    for product in sorted(set(["new_fits", "wcs"] + list(requested_products))):
        route_name, suffix = DOWNLOADABLE_PRODUCTS[product]
        destination = output_dir / f"{product}{suffix}"
        try:
            client.download_regular_file(route_name, jobid, destination)
            outputs[product] = public_path(destination)
        except Exception as exc:
            if product in required_products:
                raise
            error_path = output_dir / f"{product}.download_error.txt"
            error_path.write_text(clean_known_stderr(str(exc)) + "\n", encoding="utf-8")
            outputs[f"{product}_download_error"] = public_path(error_path)
    quicklook_target = output_dir / "qa_wcs_quicklook.png"
    qa_source = None
    qa_wcs = None
    if original_input_path is not None and (output_dir / "wcs.fits").exists():
        qa_source = Path(original_input_path)
        qa_wcs = output_dir / "wcs.fits"
    elif (output_dir / "new_fits.fits").exists():
        qa_source = output_dir / "new_fits.fits"
    if qa_source is not None:
        try:
            quicklook = render_fits_qa_png(
                qa_source,
                quicklook_target,
                title=f"Astrometry.net solved image {jobid}",
                annotations_payload=json_payloads.get("annotations"),
                wcs_header_path=qa_wcs,
            )
            if quicklook:
                outputs["qa_wcs_quicklook"] = quicklook
        except Exception as exc:
            error_path = output_dir / "qa_wcs_quicklook_error.txt"
            error_path.write_text(clean_known_stderr(str(exc)) + "\n", encoding="utf-8")
            outputs["qa_wcs_quicklook_error"] = public_path(error_path)
    return outputs


def write_report(path: Path, payload: dict):
    lines = [
        "# Astrometry.net Solve Report",
        "",
        f"- Mode: `{payload['mode']}`",
    ]
    if payload.get("input_path"):
        lines.insert(3, f"- Input: `{payload['input_path']}`")
    if payload.get("input_url"):
        lines.insert(3, f"- Input URL: `{payload['input_url']}`")
    if payload["mode"] == "preflight":
        hints = payload.get("suggested_solve_hints") or {}
        lines.extend(
            [
                "",
                "## Inferred Hints",
                "",
                f"- Center: `{payload.get('inferred_center')}`",
                f"- Scale: `{payload.get('inferred_scale')}`",
                f"- Estimated field extent: `{payload.get('estimated_field_extent')}`",
                f"- Existing astrometric solution: `{payload.get('existing_astrometric_solution')}`",
                f"- FIT assessment: `{payload.get('fit_assessment')}`",
                f"- Image quality proxy: `{payload.get('image_quality_proxy')}`",
                f"- Recommended operational local route: `{payload.get('recommended_operational_local_route')}`",
                f"- Diagnostic-only local route: `{payload.get('diagnostic_local_route')}`",
                f"- Suggested submission hints: `{hints}`",
                f"- Suggested local solve args: `{payload.get('suggested_local_solve_args')}`",
            ]
        )
    elif payload["mode"] == "verify-existing-wcs":
        lines.extend(
            [
                f"- Existing WCS center: `{payload.get('wcs_center')}`",
                f"- Header center: `{payload.get('header_center')}`",
                f"- Header-vs-WCS offset (arcsec): `{payload.get('center_offset_arcsec')}`",
                f"- Image quality proxy: `{payload.get('image_quality_proxy')}`",
                "",
                "## Field Corners",
                "",
            ]
        )
        for item in payload.get("field_corners", []):
            lines.append(f"- `{item}`")
        if payload.get("verification_products"):
            lines.extend(["", "## Verification Products", ""])
            for key, value in sorted((payload.get("verification_products") or {}).items()):
                lines.append(f"- `{key}`: `{value}`")
    elif payload["mode"] == "auth-check":
        lines.extend(
            [
                f"- API base: `{payload['api_base']}`",
                f"- Credential source: `{payload.get('credential_source')}`",
                f"- Credential file: `{payload.get('credential_file')}`",
                f"- Login status: `{payload.get('login', {}).get('status')}`",
                f"- Session received: `{payload.get('login', {}).get('session_received')}`",
            ]
        )
    elif payload["mode"] == "solve-local":
        lines.extend(
            [
                f"- solve-field binary: `{payload.get('solve_field_bin')}`",
                f"- Return code: `{payload.get('returncode')}`",
                f"- Solved flag: `{payload.get('solved')}`",
                f"- Stdout log: `{payload.get('stdout_log')}`",
                f"- Stderr log: `{payload.get('stderr_log')}`",
                "",
                "## Calibration",
                "",
                f"- Center: `{payload.get('calibration', {}).get('center')}`",
                f"- Scale: `{payload.get('calibration', {}).get('scale')}`",
                "",
                "## Index Directory Health",
                "",
                f"- Health summary: `{payload.get('index_dir_health')}`",
                f"- Recommended operational route: `{payload.get('recommended_operational_route')}`",
                "",
                "## Local Products",
                "",
            ]
        )
        for key, value in sorted((payload.get("downloaded_products") or {}).items()):
            lines.append(f"- `{key}`: `{value}`")
    elif payload["mode"] == "stack-peers":
        lines.extend(
            [
                f"- Seed input: `{payload.get('input_path')}`",
                f"- Output stack: `{payload.get('stack_path')}`",
                f"- Members: `{payload.get('member_count')}`",
                f"- Peer selection: `{payload.get('peer_selection')}`",
                f"- Preflight: `{payload.get('preflight', {}).get('fit_assessment')}`",
                f"- Quality proxy: `{payload.get('quality_proxy')}`",
            ]
        )
    elif payload["mode"] == "solve-web-best-effort":
        lines.extend(
            [
                f"- Result status: `{payload.get('result_status')}`",
                f"- Final strategy: `{payload.get('final_strategy')}`",
                f"- Fit assessment: `{payload.get('fit_assessment')}`",
                f"- Existing astrometric solution: `{payload.get('preflight', {}).get('existing_astrometric_solution')}`",
                f"- Image quality proxy: `{payload.get('preflight', {}).get('image_quality_proxy')}`",
                "",
                "## Attempts",
                "",
            ]
        )
        for attempt in payload.get("attempts", []):
            lines.append(f"- `{attempt}`")
        if payload.get("existing_wcs_verification"):
            verification = payload.get("existing_wcs_verification") or {}
            lines.extend(
                [
                    "",
                    "## Existing WCS Verification",
                    "",
                    f"- WCS center: `{verification.get('wcs_center')}`",
                    f"- Header center: `{verification.get('header_center')}`",
                    f"- Header-vs-WCS offset (arcsec): `{verification.get('center_offset_arcsec')}`",
                    f"- Image quality proxy: `{verification.get('image_quality_proxy')}`",
                ]
            )
            if verification.get("verification_products"):
                lines.extend(["", "## Verification Products", ""])
                for key, value in sorted((verification.get("verification_products") or {}).items()):
                    lines.append(f"- `{key}`: `{value}`")
        if payload.get("calibration"):
            lines.extend(["", "## Final Calibration", ""])
            calibration = payload.get("calibration") or {}
            for key in ["ra", "dec", "pixscale", "radius", "orientation", "parity"]:
                if key in calibration:
                    lines.append(f"- `{key}`: `{calibration[key]}`")
        if payload.get("downloaded_products"):
            lines.extend(["", "## Final Products", ""])
            for key, value in sorted((payload.get("downloaded_products") or {}).items()):
                lines.append(f"- `{key}`: `{value}`")
    elif payload["mode"] == "solve-local-best-effort":
        lines.extend(
            [
                f"- Result status: `{payload.get('result_status')}`",
                f"- Final strategy: `{payload.get('final_strategy')}`",
                f"- Fit assessment: `{payload.get('fit_assessment')}`",
                f"- Existing astrometric solution: `{payload.get('preflight', {}).get('existing_astrometric_solution')}`",
                f"- Image quality proxy: `{payload.get('preflight', {}).get('image_quality_proxy')}`",
                "",
                "## Attempts",
                "",
            ]
        )
        for attempt in payload.get("attempts", []):
            lines.append(f"- `{attempt}`")
        if payload.get("stack_details"):
            lines.extend(["", "## Stack Details", "", f"- `{payload.get('stack_details')}`"])
        if payload.get("compact_visual_review"):
            lines.extend(["", "## Compact Visual Review", ""])
            for key, value in sorted((payload.get("compact_visual_review") or {}).items()):
                lines.append(f"- `{key}`: `{value}`")
        if payload.get("final_solve", {}).get("index_dir_health"):
            lines.extend(
                [
                    "",
                    "## Index Directory Health",
                    "",
                    f"- `{payload.get('final_solve', {}).get('index_dir_health')}`",
                ]
            )
        if payload.get("existing_wcs_verification"):
            verification = payload.get("existing_wcs_verification") or {}
            lines.extend(
                [
                    "",
                    "## Existing WCS Verification",
                    "",
                    f"- WCS center: `{verification.get('wcs_center')}`",
                    f"- Header center: `{verification.get('header_center')}`",
                    f"- Header-vs-WCS offset (arcsec): `{verification.get('center_offset_arcsec')}`",
                    f"- Image quality proxy: `{verification.get('image_quality_proxy')}`",
                ]
            )
        if payload.get("calibration"):
            lines.extend(["", "## Final Calibration", ""])
            calibration = payload.get("calibration") or {}
            for key in ["center", "scale"]:
                if key in calibration:
                    lines.append(f"- `{key}`: `{calibration[key]}`")
        if payload.get("downloaded_products"):
            lines.extend(["", "## Final Products", ""])
            for key, value in sorted((payload.get("downloaded_products") or {}).items()):
                lines.append(f"- `{key}`: `{value}`")
    else:
        lines.extend(
            [
                f"- API base: `{payload['api_base']}`",
                f"- Credential source: `{payload.get('credential_source')}`",
                f"- Credential file: `{payload.get('credential_file')}`",
                f"- Fit assessment: `{payload.get('preflight', {}).get('fit_assessment')}`",
                f"- Submission id: `{payload['submission']['subid']}`",
                f"- Job id: `{payload['job']['jobid']}`",
                "",
                "## Calibration",
                "",
            ]
        )
        calibration = payload.get("calibration") or {}
        for key in ["ra", "dec", "pixscale", "radius", "orientation", "parity"]:
            if key in calibration:
                lines.append(f"- `{key}`: `{calibration[key]}`")
        lines.extend(["", "## Downloaded Products", ""])
        for key, value in sorted((payload.get("downloaded_products") or {}).items()):
            lines.append(f"- `{key}`: `{value}`")
    if payload.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend([f"- {item}" for item in payload["notes"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_preflight(args):
    payload = build_preflight(Path(args.path), args)
    return payload, []


def run_verify_existing_wcs(args):
    input_path = Path(args.path).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_existing_wcs_verification(input_path)
    verification_products = {}
    quicklook = render_fits_qa_png(input_path, output_dir / "existing_wcs_quicklook.png", title=f"Existing WCS verification: {input_path.name}")
    if quicklook:
        verification_products["existing_wcs_quicklook"] = quicklook
    payload["verification_products"] = verification_products
    return payload, [output_dir]


def clone_args(args, **overrides):
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def dedupe_strings(items):
    seen = set()
    ordered = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def astrometry_status(payload: dict) -> str:
    # The app-facing status must never be more optimistic than the QA payload.
    return build_astrometry_qa(payload)["status"]


def build_astrometry_qa(payload: dict) -> dict:
    mode = payload.get("mode")
    findings = []
    metrics = {}
    if mode == "auth-check":
        success = payload.get("status") == "success"
        return {
            "status": "ok" if success else "fail",
            "findings": [] if success else ["Astrometry.net authentication did not succeed."],
            "metrics": {"authenticated": success},
        }
    if mode == "preflight":
        fit = payload.get("fit_assessment") or {}
        quality = payload.get("image_quality_proxy") or {}
        metrics = {
            "image_hdu_index": payload.get("image_hdu_index"),
            "wcs_hdu_index": payload.get("wcs_hdu_index"),
            "has_existing_wcs": bool(payload.get("existing_astrometric_solution")),
            "has_center_hint": bool(payload.get("inferred_center")),
            "has_scale_hint": bool(payload.get("inferred_scale") or payload.get("instrument_scale_hint")),
            "fit_classification": fit.get("classification"),
        }
        dep = payload.get("dependency_preflight") or {}
        findings.extend(dep.get("blocking_findings") or [])
        findings.extend(dep.get("warning_findings") or [])
        if fit.get("recommended_action") == "avoid_plate_solve":
            findings.append(fit.get("reason") or "Input does not look like a normal direct-imaging plate-solve target.")
        if payload.get("inferred_center") is None and not payload.get("existing_astrometric_solution"):
            findings.append("No RA/Dec-like center hint was inferred; blind solving may still work but preflight is under-constrained.")
        if (
            payload.get("inferred_scale") is None
            and payload.get("instrument_scale_hint") is None
            and not payload.get("existing_astrometric_solution")
        ):
            findings.append("No pixel-scale hint was inferred; consider supplying --scale-est or scale bounds.")
        if quality:
            if quality.get("median") is None:
                findings.append("No finite image pixels were available for image-quality proxy.")
            elif quality.get("estimated_peak_count") == 0:
                findings.append("No robust bright-source peaks were detected by the light image-quality proxy.")
        status = "warning" if dep.get("status") in {"warning", "blocked"} or findings else "ok"
        return {"status": status, "findings": findings, "metrics": metrics}
    if mode == "verify-existing-wcs":
        quality = payload.get("image_quality_proxy") or {}
        products = payload.get("verification_products") or {}
        metrics = {
            "has_image_data": payload.get("has_image_data"),
            "field_corner_count": len(payload.get("field_corners") or []),
            "center_offset_arcsec": payload.get("center_offset_arcsec"),
            "has_finite_image_pixels": quality.get("median") is not None if quality else None,
            "has_quicklook": bool(products.get("existing_wcs_quicklook")),
        }
        status = "ok"
        if payload.get("result_status") == "wcs_header_only":
            status = "warning"
            findings.append("Celestial WCS exists, but no 2D image plane was available for full visual QA.")
        elif payload.get("has_image_data") and quality.get("median") is None:
            status = "warning"
            findings.append("Celestial WCS exists, but image data has no finite pixels for visual QA.")
        elif payload.get("has_image_data") and not products.get("existing_wcs_quicklook"):
            status = "warning"
            findings.append("Celestial WCS exists, but the verification quicklook could not be generated.")
        if payload.get("has_image_data") and len(payload.get("field_corners") or []) < 4:
            status = "warning"
            findings.append("Celestial WCS exists, but not all image corners could be transformed to sky coordinates.")
        return {"status": status, "findings": findings, "metrics": metrics}
    if mode == "stack-peers":
        member_count = int(payload.get("member_count") or 0)
        metrics = {
            "member_count": member_count,
            "result_status": payload.get("result_status"),
            "registration_status": payload.get("registration_status"),
        }
        if payload.get("result_status") == "stack_built_registered" and member_count >= 3:
            return {"status": "ok", "findings": [], "metrics": metrics}
        if payload.get("result_status") == "stack_built_unregistered" and member_count >= 3:
            return {
                "status": "warning",
                "findings": [
                    payload.get("registration_warning")
                    or "The peer stack was explicitly built without validated geometric registration."
                ],
                "metrics": metrics,
            }
        return {
            "status": "fail",
            "findings": ["A safe peer stack was not built from at least three compatible frames."],
            "metrics": metrics,
        }
    result_status = payload.get("result_status")
    metrics = {
        "result_status": result_status,
        "downloaded_product_count": len(payload.get("downloaded_products") or {}),
        "attempt_count": len(payload.get("attempts") or []),
        "source_count": payload.get("source_count"),
    }
    if result_status == "solved":
        status = "ok"
    elif result_status in {"skipped_existing_wcs", "skipped_unsuitable_input"}:
        status = "warning"
        findings.append("The route completed with a controlled skip rather than a fresh solve.")
    elif result_status == "wcs_header_only":
        status = "warning"
        findings.append("Verification found WCS metadata but not a usable image plane.")
    else:
        status = "fail"
        findings.append("Astrometry did not finish with a solved or reusable state.")
    return {"status": status, "findings": findings, "metrics": metrics}


def collect_astrometry_artifacts(payload: dict, args, extra_outputs: list[Path]) -> dict:
    artifacts = {}
    if getattr(args, "summary_json", None):
        artifacts["summary_json"] = args.summary_json
    if getattr(args, "report_md", None):
        artifacts["report_md"] = args.report_md
    for key in ("downloaded_products", "verification_products"):
        value = payload.get(key)
        if value:
            artifacts[key] = value
    if payload.get("compact_visual_review"):
        artifacts["compact_visual_review"] = payload["compact_visual_review"]
    realized_outputs = [public_path(item) for item in extra_outputs if isinstance(item, Path) and item.exists()]
    if realized_outputs:
        artifacts["generated_outputs"] = realized_outputs
    return artifacts


def standardize_astrometry_payload(payload: dict, args, extra_outputs: list[Path]) -> dict:
    qa = build_astrometry_qa(payload)
    legacy = dict(payload)
    return standard_tool_payload(
        "astrometry_net_workbench",
        status=astrometry_status(payload),
        notes=payload.get("notes", []),
        artifacts=collect_astrometry_artifacts(payload, args, extra_outputs),
        results=payload,
        qa=qa,
        legacy=legacy,
    )


def emit_blocked_payload(args, message: str, *, status: str = "blocked") -> int:
    payload = standard_tool_payload(
        "astrometry_net_workbench",
        status=status,
        notes=[message],
        artifacts={
            "summary_json": getattr(args, "summary_json", None),
            "report_md": getattr(args, "report_md", None),
            "manifest_json": getattr(args, "manifest_json", None),
        },
        results={
            "mode": getattr(args, "command", None),
            "input_path": public_path(Path(args.path)) if hasattr(args, "path") else None,
            "input_url": getattr(args, "url", None),
            "blocked_reason": message,
        },
        qa={
            "status": status,
            "findings": [message],
            "metrics": {"blocking_count": 1 if status == "blocked" else 0},
        },
    )
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    summary_json = getattr(args, "summary_json", None)
    if summary_json:
        try:
            summary_path = Path(summary_json)
            if summary_path.parent.exists() and not summary_path.parent.is_dir():
                print(f"Could not write summary JSON because parent is not a directory: {summary_path.parent}", file=sys.stderr)
            else:
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(rendered, encoding="utf-8")
        except Exception as exc:
            print(clean_known_stderr(f"Could not write summary JSON: {exc}"), file=sys.stderr)
    return 2 if status == "blocked" else 1


def write_summary_payload(path: str | None, payload: dict) -> None:
    if not path:
        return
    summary_path = Path(path)
    if summary_path.parent.exists() and not summary_path.parent.is_dir():
        raise OSError(f"summary-json parent is not a directory: {summary_path.parent}")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _build_web_solve_payload(mode: str, input_marker: str, args, preflight: dict, key_info: dict, login_result: dict, upload_result: dict, submission: dict, jobid: int, job_status: dict, calibration: dict, downloaded: dict):
    return {
        "tool": "astrometry_net_workbench",
        "mode": mode,
        input_marker.split(":", 1)[0]: input_marker.split(":", 1)[1],
        "api_base": args.api_base.rstrip("/"),
        "credential_source": key_info.get("source"),
        "credential_file": key_info.get("key_file"),
        "credential_warnings": key_info.get("warnings", []),
        "login": sanitize_login_payload(login_result),
        "submission": {
            "subid": int(upload_result["subid"]),
            "hash": upload_result.get("hash"),
            "arguments": build_submission_args(args, preflight),
            "status_snapshot": submission,
        },
        "job": {
            "jobid": int(jobid),
            "status": job_status.get("status"),
        },
        "calibration": calibration,
        "downloaded_products": downloaded,
        "preflight": preflight,
        "notes": [
            "Astrometry.net products were downloaded from the same web solve used by the browser interface.",
            "Keep downloaded products as derived outputs and leave the original data source untouched.",
            "The official project emphasizes avoiding false positives even if that means returning no solution.",
        ],
    }


def _run_web_solve_for_path(input_path: Path, output_dir: Path, args, preflight: dict | None = None, mode: str = "solve-web"):
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = preflight or build_preflight(input_path, args)
    api_key, key_info = discover_api_key(args.api_key)
    client = AstrometryNetClient(api_key=api_key, api_base=args.api_base)
    login_result = client.login()
    submission_args = build_submission_args(args, preflight)
    upload_result = client.upload_file(input_path, submission_args)
    if upload_result.get("status") != "success" or "subid" not in upload_result:
        raise RuntimeError(f"Astrometry.net upload failed: {upload_result}")
    submission, jobid, job_status = wait_for_job(
        client,
        int(upload_result["subid"]),
        poll_sec=args.poll_sec,
        timeout_sec=args.timeout_sec,
    )
    calibration = client.calibration(jobid)
    downloaded = download_products(client, jobid, output_dir, args.download_product, original_input_path=input_path)
    payload = _build_web_solve_payload(
        mode,
        f"input_path:{public_path(input_path)}",
        args,
        preflight,
        key_info,
        login_result,
        upload_result,
        submission,
        jobid,
        job_status,
        calibration,
        downloaded,
    )
    payload["solved_input_path"] = public_path(input_path)
    return payload, [output_dir]


def run_auth_check(args):
    api_key, key_info = discover_api_key(args.api_key)
    client = AstrometryNetClient(api_key=api_key, api_base=args.api_base)
    login_result = client.login()
    payload = {
        "tool": "astrometry_net_workbench",
        "mode": "auth-check",
        "api_base": args.api_base.rstrip("/"),
        "credential_source": key_info.get("source"),
        "credential_file": key_info.get("key_file"),
        "credential_warnings": key_info.get("warnings", []),
        "login": sanitize_login_payload(login_result),
        "notes": [
            "This command validates Astrometry.net authentication without uploading any local file.",
            "Prefer a private key file or environment variable over hardcoding API keys into the skill itself.",
        ],
    }
    return payload, []


def run_solve_web(args):
    input_path = Path(args.path).resolve()
    output_dir = Path(args.output_dir).resolve()
    return _run_web_solve_for_path(input_path, output_dir, args, preflight=build_preflight(input_path, args), mode="solve-web")


def run_solve_web_url(args):
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = {
        "tool": "astrometry_net_workbench",
        "mode": "url-preflight",
        "submitted_url": args.url,
        "suggested_solve_hints": build_submission_args(args, {}),
        "notes": [
            "URL submissions skip FITS header inference because the remote file is not inspected locally first.",
            "Provide center/scale hints explicitly when you know them.",
        ],
    }
    api_key, key_info = discover_api_key(args.api_key)
    client = AstrometryNetClient(api_key=api_key, api_base=args.api_base)
    login_result = client.login()
    submission_args = build_submission_args(args, preflight)
    upload_result = client.upload_url(args.url, submission_args)
    if upload_result.get("status") != "success" or "subid" not in upload_result:
        raise RuntimeError(f"Astrometry.net url_upload failed: {upload_result}")
    submission, jobid, job_status = wait_for_job(
        client,
        int(upload_result["subid"]),
        poll_sec=args.poll_sec,
        timeout_sec=args.timeout_sec,
    )
    calibration = client.calibration(jobid)
    downloaded = download_products(client, jobid, output_dir, args.download_product)
    payload = _build_web_solve_payload(
        "solve-web-url",
        f"input_url:{args.url}",
        args,
        preflight,
        key_info,
        login_result,
        upload_result,
        submission,
        jobid,
        job_status,
        calibration,
        downloaded,
    )
    return payload, [output_dir]


def run_stack_peers(args):
    input_path = Path(args.path).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    output_path = Path(args.output_path).resolve()
    preflight = build_preflight(input_path, args)
    _hdu_index, header, shape = _first_image_hdu(input_path)
    peers = select_peer_frames_with_strategy(
        input_path,
        header,
        shape,
        peer_count=args.peer_count,
        same_object=args.same_object,
        same_exptime=args.same_exptime,
        max_separation_index=args.max_separation_index,
        strategy=args.peer_strategy,
    )
    stack_info = build_peer_stack(peers, output_path, allow_unregistered=args.allow_unregistered_stack)
    payload = {
        "tool": "astrometry_net_workbench",
        "mode": "stack-peers",
        "input_path": public_path(input_path),
        "stack_path": public_path(output_path),
        "member_count": stack_info["member_count"],
        "result_status": (
            "stack_built_registered"
            if stack_info["registration_status"] == "registered"
            else "stack_built_unregistered"
        ),
        "registration_status": stack_info["registration_status"],
        "registration": stack_info["registration"],
        "registration_warning": stack_info["registration_warning"],
        "members": stack_info["members"],
        "peer_selection": {
            "peer_count_requested": args.peer_count,
            "same_object": bool(args.same_object),
            "same_exptime": bool(args.same_exptime),
            "max_separation_index": args.max_separation_index,
            "peer_strategy": args.peer_strategy,
        },
        "preflight": preflight,
        "manifest_input_paths": [public_path(item) for item in peers],
        "notes": [
            "This derived stack is non-destructive and intended only as a best-effort helper for difficult compact imaging fields.",
            "Median stacking nearby peers can increase source detectability for blind astrometric solving.",
        ],
    }
    return payload, [output_path]


def run_solve_web_best_effort(args):
    input_path = Path(args.path).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = build_preflight(input_path, args)
    fit = preflight.get("fit_assessment") or {}
    attempts = []
    manifest_inputs = [public_path(input_path)]
    instrument_scale_hint = preflight.get("instrument_scale_hint") or {}
    automatic_scale_est = instrument_scale_hint.get("arcsec_per_pixel")
    automatic_scale_err = instrument_scale_hint.get("scale_err_pct", 12.0)

    if fit.get("recommended_action") == "reuse_existing_wcs":
        verification_dir = output_dir / "existing_wcs_verification"
        verification_dir.mkdir(parents=True, exist_ok=True)
        verification = build_existing_wcs_verification(input_path)
        verification_products = {}
        quicklook = render_fits_qa_png(
            input_path,
            verification_dir / "existing_wcs_quicklook.png",
            title=f"Existing WCS verification: {input_path.name}",
        )
        if quicklook:
            verification_products["existing_wcs_quicklook"] = quicklook
        verification["verification_products"] = verification_products
        manifest_inputs = dedupe_strings(manifest_inputs)
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-web-best-effort",
            "input_path": public_path(input_path),
            "result_status": "skipped_existing_wcs",
            "final_strategy": "reuse_existing_wcs",
            "fit_assessment": fit,
            "preflight": preflight,
            "existing_wcs_verification": verification,
            "attempts": [{"strategy": "preflight", "status": "skipped", "reason": fit.get("reason")}],
            "manifest_input_paths": manifest_inputs,
            "notes": [
                "The file already exposes a celestial WCS solution, so the cautious path is to reuse or verify it instead of sending a new blind solve.",
            ],
        }
        return payload, [output_dir, verification_dir]

    if fit.get("recommended_action") == "avoid_plate_solve":
        manifest_inputs = dedupe_strings(manifest_inputs)
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-web-best-effort",
            "input_path": public_path(input_path),
            "result_status": "skipped_unsuitable_input",
            "final_strategy": "avoid_plate_solve",
            "fit_assessment": fit,
            "preflight": preflight,
            "attempts": [{"strategy": "preflight", "status": "skipped", "reason": fit.get("reason")}],
            "manifest_input_paths": manifest_inputs,
            "notes": [
                "This input looks more like spectroscopy or calibration than a normal imaging frame, so best-effort mode skipped the blind solve.",
            ],
        }
        return payload, [output_dir]

    def record_attempt(strategy: str, status: str, input_marker: Path, **extra):
        attempt = {
            "strategy": strategy,
            "status": status,
            "input_path": public_path(input_marker),
        }
        attempt.update(extra)
        attempts.append(attempt)

    if fit.get("recommended_action") == "stack_peers_then_solve":
        _hdu_index, header, shape = _first_image_hdu(input_path)
        tried_member_sets = set()
        stack_strategies = ["nearest", "forward_window", "backward_window"]
        peer_counts_seen = []
        stack_candidates = []
        for stack_strategy in stack_strategies:
            peers = select_peer_frames_with_strategy(
                input_path,
                header,
                shape,
                peer_count=args.peer_count,
                same_object=args.same_object,
                same_exptime=args.same_exptime,
                max_separation_index=args.max_separation_index,
                strategy=stack_strategy,
            )
            peer_counts_seen.append(len(peers))
            if len(peers) < 3:
                continue
            peer_key = tuple(str(item) for item in peers)
            if peer_key in tried_member_sets:
                continue
            tried_member_sets.add(peer_key)
            stack_path = output_dir / f"{input_path.stem}_{stack_strategy}_stack{len(peers)}.fits"
            stack_info = build_peer_stack(peers, stack_path)
            manifest_inputs.extend(stack_info["members"])
            stack_candidates.append((stack_info.get("quality_proxy", {}).get("quality_score") or float("-inf"), stack_strategy, stack_path, stack_info))
        for _score, stack_strategy, stack_path, stack_info in sorted(stack_candidates, key=lambda item: item[0], reverse=True):
            stack_args = args
            if args.scale_lower is None and args.scale_upper is None and args.scale_est is None:
                if args.fallback_scale_est is not None:
                    stack_args = clone_args(args, scale_est=args.fallback_scale_est, scale_err=args.fallback_scale_err)
                elif automatic_scale_est is not None:
                    stack_args = clone_args(args, scale_est=automatic_scale_est, scale_err=automatic_scale_err)
            stack_preflight = build_preflight(stack_path, stack_args)
            try:
                solved_payload, solved_outputs = _run_web_solve_for_path(
                    stack_path,
                    output_dir / f"stack_solve_{stack_strategy}",
                    stack_args,
                    preflight=stack_preflight,
                    mode="solve-web",
                )
                record_attempt(
                    "stacked_web_solve",
                    "success",
                    stack_path,
                    member_count=stack_info["member_count"],
                    peer_strategy=stack_strategy,
                    quality_proxy=stack_info.get("quality_proxy"),
                    output_dir=public_path((output_dir / f"stack_solve_{stack_strategy}").resolve()),
                )
                payload = {
                    "tool": "astrometry_net_workbench",
                    "mode": "solve-web-best-effort",
                    "input_path": public_path(input_path),
                    "result_status": "solved",
                    "final_strategy": f"stacked_web_solve:{stack_strategy}",
                    "fit_assessment": fit,
                    "preflight": preflight,
                    "stack_details": {**stack_info, "peer_strategy": stack_strategy},
                    "attempts": attempts,
                    "calibration": solved_payload.get("calibration"),
                    "downloaded_products": solved_payload.get("downloaded_products"),
                    "final_solve": solved_payload,
                    "manifest_input_paths": dedupe_strings(manifest_inputs),
                    "notes": [
                        "Compact imaging fields can solve more reliably after stacking nearby frames from the same sequence.",
                        "The original input was left untouched; only a derived temporary stack was submitted.",
                    ],
                }
                return payload, [output_dir, *solved_outputs, stack_path]
            except Exception as exc:
                record_attempt(
                    "stacked_web_solve",
                    "failed",
                    stack_path,
                    member_count=stack_info["member_count"],
                    peer_strategy=stack_strategy,
                    quality_proxy=stack_info.get("quality_proxy"),
                    error=clean_known_stderr(str(exc)),
                )
        if max(peer_counts_seen or [0]) < 3:
            record_attempt(
                "stack-peers",
                "insufficient_peers",
                input_path,
                peer_count_found=max(peer_counts_seen or [0]),
            )

    direct_args = args
    if args.scale_lower is None and args.scale_upper is None and args.scale_est is None:
        if args.fallback_scale_est is not None:
            direct_args = clone_args(args, scale_est=args.fallback_scale_est, scale_err=args.fallback_scale_err)
        elif automatic_scale_est is not None:
            direct_args = clone_args(args, scale_est=automatic_scale_est, scale_err=automatic_scale_err)
    direct_preflight = build_preflight(input_path, direct_args)
    try:
        solved_payload, solved_outputs = _run_web_solve_for_path(
            input_path,
            output_dir / "direct_solve",
            direct_args,
            preflight=direct_preflight,
            mode="solve-web",
        )
        record_attempt("direct_web_solve", "success", input_path, output_dir=public_path((output_dir / "direct_solve").resolve()))
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-web-best-effort",
            "input_path": public_path(input_path),
            "result_status": "solved",
            "final_strategy": "direct_web_solve",
            "fit_assessment": fit,
            "preflight": preflight,
            "attempts": attempts,
            "calibration": solved_payload.get("calibration"),
            "downloaded_products": solved_payload.get("downloaded_products"),
            "final_solve": solved_payload,
            "manifest_input_paths": dedupe_strings(manifest_inputs),
            "notes": [
                "Best-effort mode fell back to a direct web solve for this input.",
            ],
        }
        return payload, [output_dir, *solved_outputs]
    except Exception as exc:
        record_attempt("direct_web_solve", "failed", input_path, error=clean_known_stderr(str(exc)))
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-web-best-effort",
            "input_path": public_path(input_path),
            "result_status": "failed",
            "final_strategy": "no_successful_strategy",
            "fit_assessment": fit,
            "preflight": preflight,
            "attempts": attempts,
            "manifest_input_paths": dedupe_strings(manifest_inputs),
            "notes": [
                "Best-effort mode tried the safe strategies it had available and none produced a successful solve.",
            ],
        }
        return payload, [output_dir]


def run_solve_local_best_effort(args):
    input_path = Path(args.path).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = build_preflight(input_path, args)
    fit = preflight.get("fit_assessment") or {}
    attempts = []
    manifest_inputs = [public_path(input_path)]
    instrument_scale_hint = preflight.get("instrument_scale_hint") or {}
    automatic_scale_est = instrument_scale_hint.get("arcsec_per_pixel")
    automatic_scale_err = instrument_scale_hint.get("scale_err_pct", 12.0)
    compact_field = fit.get("classification") == "likely_compact_direct_imaging" or fit.get("recommended_action") == "stack_peers_then_solve"

    if fit.get("recommended_action") == "reuse_existing_wcs":
        verification_dir = output_dir / "existing_wcs_verification"
        verification_dir.mkdir(parents=True, exist_ok=True)
        verification = build_existing_wcs_verification(input_path)
        verification_products = {}
        quicklook = render_fits_qa_png(
            input_path,
            verification_dir / "existing_wcs_quicklook.png",
            title=f"Existing WCS verification: {input_path.name}",
        )
        if quicklook:
            verification_products["existing_wcs_quicklook"] = quicklook
        verification["verification_products"] = verification_products
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-local-best-effort",
            "input_path": public_path(input_path),
            "result_status": "skipped_existing_wcs",
            "final_strategy": "reuse_existing_wcs",
            "fit_assessment": fit,
            "preflight": preflight,
            "existing_wcs_verification": verification,
            "attempts": [{"strategy": "preflight", "status": "skipped", "reason": fit.get("reason")}],
            "manifest_input_paths": dedupe_strings(manifest_inputs),
            "notes": [
                "The file already exposes a celestial WCS solution, so the cautious local path is to reuse or verify it instead of forcing a new solve-field run.",
            ],
        }
        return payload, [output_dir, verification_dir]

    if fit.get("recommended_action") == "avoid_plate_solve":
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-local-best-effort",
            "input_path": public_path(input_path),
            "result_status": "skipped_unsuitable_input",
            "final_strategy": "avoid_plate_solve",
            "fit_assessment": fit,
            "preflight": preflight,
            "attempts": [{"strategy": "preflight", "status": "skipped", "reason": fit.get("reason")}],
            "manifest_input_paths": dedupe_strings(manifest_inputs),
            "notes": [
                "This input looks more like spectroscopy or calibration than a normal imaging frame, so best-effort local mode skipped the blind solve.",
            ],
        }
        return payload, [output_dir]

    def record_attempt(strategy: str, status: str, input_marker: Path, **extra):
        attempt = {
            "strategy": strategy,
            "status": status,
            "input_path": public_path(input_marker),
        }
        attempt.update(extra)
        attempts.append(attempt)

    def build_local_args(path: Path, local_output_dir: Path):
        local_args = clone_args(
            args,
            command="solve-local",
            path=str(path),
            output_dir=str(local_output_dir),
        )
        if args.scale_lower is None and args.scale_upper is None and args.scale_est is None:
            if args.fallback_scale_est is not None:
                local_args = clone_args(local_args, scale_est=args.fallback_scale_est, scale_err=args.fallback_scale_err)
            elif automatic_scale_est is not None:
                local_args = clone_args(local_args, scale_est=automatic_scale_est, scale_err=automatic_scale_err)
        return local_args

    direct_args = build_local_args(input_path, output_dir / "direct_solve")
    solved_payload, solved_outputs = run_solve_local(direct_args)
    if solved_payload.get("result_status") == "solved":
        record_attempt(
            "direct_local_solve",
            "success",
            input_path,
            source_count=solved_payload.get("source_count"),
            output_dir=public_path((output_dir / "direct_solve").resolve()),
        )
        compact_visual_review = {}
        compact_visual_outputs = []
        if compact_field:
            compact_visual_review, compact_visual_outputs = build_compact_visual_review(
                input_path,
                output_dir / "direct_solve",
                solved_payload,
                review_label=f"Compact-field review after direct local solve: {input_path.name}",
            )
        payload = {
            "tool": "astrometry_net_workbench",
            "mode": "solve-local-best-effort",
            "input_path": public_path(input_path),
            "result_status": "solved",
            "final_strategy": "direct_local_solve",
            "fit_assessment": fit,
            "preflight": preflight,
            "attempts": attempts,
            "calibration": solved_payload.get("calibration"),
            "downloaded_products": solved_payload.get("downloaded_products"),
            "compact_visual_review": compact_visual_review,
            "final_solve": solved_payload,
            "manifest_input_paths": dedupe_strings(manifest_inputs),
            "notes": [
                "Best-effort local mode resolved this field directly with solve-field.",
            ],
        }
        return payload, [output_dir, *solved_outputs, *compact_visual_outputs]

    record_attempt(
        "direct_local_solve",
        solved_payload.get("result_status") or "failed",
        input_path,
        source_count=solved_payload.get("source_count"),
        failed_index_count=solved_payload.get("failed_index_loads", {}).get("count"),
    )
    if compact_field:
        aggressive_nsigma = args.nsigma if args.nsigma is not None else 4.0
        aggressive_depth = args.depth or "1-25"
        aggressive_args = clone_args(
            direct_args,
            output_dir=str(output_dir / "direct_aggressive"),
            nsigma=aggressive_nsigma,
            depth=aggressive_depth,
            crpix_center=True,
            overwrite=True,
        )
        aggressive_payload, aggressive_outputs = run_solve_local(aggressive_args)
        if aggressive_payload.get("result_status") == "solved":
            record_attempt(
                "direct_local_aggressive_compact",
                "success",
                input_path,
                source_count=aggressive_payload.get("source_count"),
                nsigma=aggressive_nsigma,
                depth=aggressive_depth,
                output_dir=public_path((output_dir / "direct_aggressive").resolve()),
            )
            compact_visual_review, compact_visual_outputs = build_compact_visual_review(
                input_path,
                output_dir / "direct_aggressive",
                aggressive_payload,
                review_label=f"Compact-field review after aggressive single-frame retry: {input_path.name}",
            )
            payload = {
                "tool": "astrometry_net_workbench",
                "mode": "solve-local-best-effort",
                "input_path": public_path(input_path),
                "result_status": "solved",
                "final_strategy": "direct_local_aggressive_compact",
                "fit_assessment": fit,
                "preflight": preflight,
                "attempts": attempts,
                "calibration": aggressive_payload.get("calibration"),
                "downloaded_products": aggressive_payload.get("downloaded_products"),
                "compact_visual_review": compact_visual_review,
                "final_solve": aggressive_payload,
                "manifest_input_paths": dedupe_strings(manifest_inputs),
                "notes": [
                    "Compact single-frame fields can need a more permissive source-extraction threshold before solve-field locks onto the geometry.",
                    f"This recovery pass retried the original frame with an aggressive local extraction threshold (nsigma={aggressive_nsigma:g}) before falling back to peer stacking.",
                ],
            }
            return payload, [output_dir, *aggressive_outputs, *compact_visual_outputs]
        record_attempt(
            "direct_local_aggressive_compact",
            aggressive_payload.get("result_status") or "failed",
            input_path,
            source_count=aggressive_payload.get("source_count"),
            nsigma=aggressive_nsigma,
            depth=aggressive_depth,
            failed_index_count=aggressive_payload.get("failed_index_loads", {}).get("count"),
        )
    if fit.get("recommended_action") == "stack_peers_then_solve":
        _hdu_index, header, shape = _first_image_hdu(input_path)
        tried_member_sets = set()
        peer_counts_seen = []
        stack_candidates = []
        for stack_strategy in ["backward_window", "nearest", "forward_window"]:
            peers = select_peer_frames_with_strategy(
                input_path,
                header,
                shape,
                peer_count=args.peer_count,
                same_object=args.same_object,
                same_exptime=args.same_exptime,
                max_separation_index=args.max_separation_index,
                strategy=stack_strategy,
            )
            peer_counts_seen.append(len(peers))
            if len(peers) < 3:
                continue
            peer_key = tuple(str(item) for item in peers)
            if peer_key in tried_member_sets:
                continue
            tried_member_sets.add(peer_key)
            stack_path = output_dir / f"{input_path.stem}_{stack_strategy}_stack{len(peers)}.fits"
            stack_info = build_peer_stack(peers, stack_path)
            manifest_inputs.extend(stack_info["members"])
            stack_candidates.append((stack_info.get("quality_proxy", {}).get("quality_score") or float("-inf"), stack_strategy, stack_path, stack_info))
        for _score, stack_strategy, stack_path, stack_info in sorted(stack_candidates, key=lambda item: item[0], reverse=True):
            local_args = build_local_args(stack_path, output_dir / f"stack_solve_{stack_strategy}")
            solved_payload, solved_outputs = run_solve_local(local_args)
            if solved_payload.get("result_status") == "solved":
                record_attempt(
                    "stacked_local_solve",
                    "success",
                    stack_path,
                    member_count=stack_info["member_count"],
                    peer_strategy=stack_strategy,
                    quality_proxy=stack_info.get("quality_proxy"),
                    source_count=solved_payload.get("source_count"),
                    output_dir=public_path((output_dir / f"stack_solve_{stack_strategy}").resolve()),
                )
                compact_visual_review, compact_visual_outputs = build_compact_visual_review(
                    input_path,
                    output_dir / f"stack_solve_{stack_strategy}",
                    solved_payload,
                    stack_path=stack_path,
                    review_label=f"Compact-field review after {stack_strategy} stack solve: {input_path.name}",
                )
                payload = {
                    "tool": "astrometry_net_workbench",
                    "mode": "solve-local-best-effort",
                    "input_path": public_path(input_path),
                    "result_status": "solved",
                    "final_strategy": f"stacked_local_solve:{stack_strategy}",
                    "fit_assessment": fit,
                    "preflight": preflight,
                    "stack_details": {**stack_info, "peer_strategy": stack_strategy},
                    "attempts": attempts,
                    "calibration": solved_payload.get("calibration"),
                    "downloaded_products": solved_payload.get("downloaded_products"),
                    "compact_visual_review": compact_visual_review,
                    "final_solve": solved_payload,
                    "manifest_input_paths": dedupe_strings(manifest_inputs),
                    "notes": [
                        "Compact imaging fields can solve more reliably after stacking nearby frames from the same sequence.",
                        "This path only falls back to stacking after the standard and aggressive single-frame local attempts miss.",
                        "A light visual-review quicklook is included so the stack-derived solution can be checked quickly before teaching or reusing it.",
                    ],
                }
                return payload, [output_dir, *solved_outputs, stack_path, *compact_visual_outputs]
            record_attempt(
                "stacked_local_solve",
                solved_payload.get("result_status") or "failed",
                stack_path,
                member_count=stack_info["member_count"],
                peer_strategy=stack_strategy,
                quality_proxy=stack_info.get("quality_proxy"),
                source_count=solved_payload.get("source_count"),
                failed_index_count=solved_payload.get("failed_index_loads", {}).get("count"),
            )
        if max(peer_counts_seen or [0]) < 3:
            record_attempt("stack-peers", "insufficient_peers", input_path, peer_count_found=max(peer_counts_seen or [0]))
    payload = {
        "tool": "astrometry_net_workbench",
        "mode": "solve-local-best-effort",
        "input_path": public_path(input_path),
        "result_status": "failed",
        "final_strategy": "no_successful_strategy",
        "fit_assessment": fit,
        "preflight": preflight,
        "attempts": attempts,
        "manifest_input_paths": dedupe_strings(manifest_inputs),
        "notes": [
            "Best-effort local mode tried the standard direct solve, an aggressive compact-field retry when appropriate, and any safe peer-stack recovery it had available.",
        ],
    }
    return payload, [output_dir]


def run_solve_local(args):
    input_path = Path(args.path).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = build_preflight(input_path, args)
    solve_field_bin = find_solve_field(args.solve_field_bin)
    if not solve_field_bin:
        raise SystemExit(
            "Local Astrometry.net solver not found. Install solve-field or pass --solve-field-bin explicitly."
        )
    index_dirs_checked = collect_local_index_dirs(args)
    index_dir_health = summarize_local_index_health(index_dirs_checked)
    if args.backend_config and not index_dirs_checked and not (args.index_file or []):
        index_dir_health = {
            "checked_dirs": [],
            "any_suspicious_small_files": None,
            "suspicious_small_file_count": None,
            "warning": "No usable index directories could be inferred from the supplied backend config or explicit --index-dir arguments.",
        }
    base_name = input_path.stem
    base_path = output_dir / base_name
    cmd = [solve_field_bin, str(input_path), "--dir", str(output_dir), "--out", base_name]
    if args.no_plots:
        cmd.append("--no-plots")
    if args.overwrite:
        cmd.append("--overwrite")
    if args.continue_run:
        cmd.append("--continue")
    if args.skip_solved:
        cmd.append("--skip-solved")
    explicit_index_dirs = []
    if args.backend_config:
        cmd.extend(["--backend-config", args.backend_config])
    backend_config_dir_texts = {
        str(item)
        for item in parse_backend_config_index_dirs(Path(args.backend_config).expanduser())
    } if args.backend_config else set()
    explicit_index_seen = set()
    for index_dir in args.index_dir or []:
        candidate_path = Path(index_dir).expanduser()
        resolved = str(candidate_path.resolve()) if candidate_path.exists() else str(candidate_path)
        if resolved in backend_config_dir_texts or resolved in explicit_index_seen:
            continue
        explicit_index_seen.add(resolved)
        explicit_index_dirs.append(resolved)
        cmd.extend(["--index-dir", resolved])
    for index_file in args.index_file or []:
        cmd.extend(["--index-file", str(Path(index_file).expanduser())])
    if args.cpulimit_sec is not None:
        cmd.extend(["--cpulimit", str(int(args.cpulimit_sec))])
    local_hints = preflight.get("suggested_local_solve_args") or {}
    solve_ra = args.center_ra if args.center_ra is not None else local_hints.get("ra")
    solve_dec = args.center_dec if args.center_dec is not None else local_hints.get("dec")
    solve_radius = args.radius_deg if args.radius_deg is not None else local_hints.get("radius")
    if solve_ra is not None:
        cmd.extend(["--ra", str(solve_ra)])
    if solve_dec is not None:
        cmd.extend(["--dec", str(solve_dec)])
    if solve_radius is not None:
        cmd.extend(["--radius", str(solve_radius)])
    scale_low = args.scale_lower if args.scale_lower is not None else local_hints.get("scale_low")
    scale_high = args.scale_upper if args.scale_upper is not None else local_hints.get("scale_high")
    scale_units = args.scale_units or local_hints.get("scale_units")
    if scale_low is not None:
        cmd.extend(["--scale-low", str(scale_low)])
    if scale_high is not None:
        cmd.extend(["--scale-high", str(scale_high)])
    if scale_units and (scale_low is not None or scale_high is not None):
        cmd.extend(["--scale-units", str(scale_units)])
    if args.downsample_factor is not None:
        cmd.extend(["--downsample", str(int(args.downsample_factor))])
    if args.parity in {0, 1}:
        cmd.extend(["--parity", "pos" if args.parity == 0 else "neg"])
    if args.use_sextractor:
        cmd.append("--use-source-extractor")
    if args.depth:
        cmd.extend(["--depth", str(args.depth)])
    if args.objs is not None:
        cmd.extend(["--objs", str(args.objs)])
    if args.nsigma is not None:
        cmd.extend(["--nsigma", str(args.nsigma)])
    if args.verify_wcs:
        cmd.extend(["--verify", args.verify_wcs])
    if args.no_verify:
        cmd.append("--no-verify")
    if args.crpix_center:
        cmd.append("--crpix-center")
    if args.tweak_order is not None:
        cmd.extend(["--tweak-order", str(args.tweak_order)])

    timed_out = False
    timeout_sec = int(args.wall_timeout_sec) if args.wall_timeout_sec is not None else None
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_sec)
        stdout_text = completed.stdout or ""
        stderr_text = completed.stderr or ""
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        if isinstance(stdout_text, bytes):
            stdout_text = stdout_text.decode("utf-8", errors="replace")
        if isinstance(stderr_text, bytes):
            stderr_text = stderr_text.decode("utf-8", errors="replace")
        returncode = None
    stdout_path = output_dir / "solve_field.stdout.txt"
    stderr_path = output_dir / "solve_field.stderr.txt"
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    failed_index_paths = sorted(set(re.findall(r'Failed to add index "([^"]+)"', stdout_text)))
    products = collect_local_products(base_path)
    solved_flag = None
    solved_path = Path(f"{base_path}{LOCAL_STANDARD_PRODUCTS['solved']}")
    if solved_path.exists():
        try:
            solved_flag = bool(solved_path.read_bytes()[:1] == b"\x01")
        except Exception:
            solved_flag = None
    input_shape = tuple(preflight.get("image_shape") or []) if preflight.get("image_shape") else None
    solve_stdout_details = parse_local_solve_stdout(stdout_text)
    calibration = {}
    for candidate in [Path(f"{base_path}.wcs"), Path(f"{base_path}.new")]:
        if candidate.exists():
            try:
                hdu_index, header, shape = _first_image_hdu(candidate)
                if header is None:
                    header = fits.getheader(candidate)
                candidate_shape = shape or input_shape
                existing = infer_existing_astrometric_solution(header, candidate_shape)
                calibration = {
                    "center": (existing or {}).get("center") or infer_center_from_header(header),
                    "scale": (existing or {}).get("scale") or infer_scale_from_header(header),
                }
                break
            except Exception:
                continue
    if Path(f"{base_path}.new").exists():
        quicklook = render_fits_qa_png(Path(f"{base_path}.new"), output_dir / "qa_wcs_quicklook.png", title=f"Local Astrometry solve: {input_path.name}")
        if quicklook:
            products["qa_wcs_quicklook"] = quicklook
    result_status = "solved" if solved_flag else "timed_out" if timed_out else "failed"
    payload = {
        "tool": "astrometry_net_workbench",
        "mode": "solve-local",
        "result_status": result_status,
        "input_path": public_path(input_path),
        "solve_field_bin": public_path(Path(solve_field_bin)),
        "index_dirs": [public_path(item) for item in index_dirs_checked],
        "index_files": [public_path(Path(item).expanduser().resolve()) for item in (args.index_file or []) if Path(item).expanduser().exists()],
        "command": cmd,
        "returncode": returncode,
        "timed_out": timed_out,
        "wall_timeout_sec": timeout_sec,
        "solved": solved_flag,
        "preflight": preflight,
        "calibration": calibration,
        "downloaded_products": products,
        "failed_index_loads": {
            "count": len(failed_index_paths),
            "paths": [public_path(Path(item)) for item in failed_index_paths],
        },
        "index_dir_health": index_dir_health,
        "stdout_log": public_path(stdout_path),
        "stderr_log": public_path(stderr_path),
        "notes": [
            "This path uses the official local solve-field workflow when Astrometry.net is installed on the machine.",
            "The official project documentation emphasizes that no answer is preferable to a false positive solve.",
        ],
    }
    if index_dir_health and index_dir_health.get("warning"):
        payload["notes"].append(index_dir_health["warning"])
    elif index_dir_health and index_dir_health.get("any_suspicious_small_files"):
        payload["notes"].append(
            f"Warning: the checked local index directories still contain {index_dir_health.get('suspicious_small_file_count')} suspiciously tiny FITS tiles."
        )
    elif index_dir_health:
        payload["notes"].append(
            "The checked local index directories did not contain suspiciously tiny FITS tiles."
        )
    payload.update(solve_stdout_details)
    scale_info = calibration.get("scale") or {}
    if scale_info.get("arcsec_per_pixel") is not None:
        payload["pixel_scale_arcsec_per_pixel"] = scale_info.get("arcsec_per_pixel")
    compact_field = (preflight.get("fit_assessment") or {}).get("classification") == "likely_compact_direct_imaging"
    if compact_field:
        payload["recommended_operational_route"] = "solve-local-best-effort"
        payload["notes"].append(
            "This input looks like a compact direct-imaging field. Treat plain solve-local as a stricter diagnostic; solve-local-best-effort is the recommended operational path."
        )
        if payload.get("result_status") != "solved" and payload.get("source_count") is not None:
            payload["notes"].append(
                f"This direct run only detected {payload.get('source_count')} sources. The best-effort route can retry the same frame more aggressively before it gives up or stacks peers."
            )
    return payload, [output_dir, stdout_path, stderr_path]


def main():
    args = parse_args()
    try:
        if args.command == "preflight":
            payload, extra_outputs = run_preflight(args)
        elif args.command == "verify-existing-wcs":
            payload, extra_outputs = run_verify_existing_wcs(args)
        elif args.command == "auth-check":
            payload, extra_outputs = run_auth_check(args)
        elif args.command == "stack-peers":
            payload, extra_outputs = run_stack_peers(args)
        elif args.command == "solve-web-best-effort":
            payload, extra_outputs = run_solve_web_best_effort(args)
        elif args.command == "solve-local-best-effort":
            payload, extra_outputs = run_solve_local_best_effort(args)
        elif args.command == "solve-web-url":
            payload, extra_outputs = run_solve_web_url(args)
        elif args.command == "solve-local":
            payload, extra_outputs = run_solve_local(args)
        else:
            payload, extra_outputs = run_solve_web(args)
    except requests.HTTPError as exc:
        return emit_blocked_payload(args, clean_known_stderr(f"Astrometry.net HTTP error: {exc}"), status="blocked")
    except SystemExit as exc:
        message = str(exc) or "Astrometry.net workbench command was blocked."
        return emit_blocked_payload(args, clean_known_stderr(message), status="blocked")
    except Exception as exc:
        return emit_blocked_payload(args, clean_known_stderr(str(exc)), status="blocked")

    payload = standardize_astrometry_payload(payload, args, extra_outputs)

    try:
        write_summary_payload(args.summary_json, payload)
        if args.report_md:
            write_report(Path(args.report_md), payload)
        if args.manifest_json:
            outputs = []
            if args.summary_json:
                outputs.append(Path(args.summary_json))
            if args.report_md:
                outputs.append(Path(args.report_md))
            outputs.extend(item for item in extra_outputs if isinstance(item, Path) and item.exists())
            manifest_inputs = [Path(args.path)] if hasattr(args, "path") else []
            for item in payload.get("manifest_input_paths", []):
                try:
                    manifest_inputs.append(Path(str(item).replace("~", str(Path.home()))).expanduser())
                except Exception:
                    continue
            manifest_extra = {"mode": args.command}
            if hasattr(args, "url"):
                manifest_extra["input_url"] = args.url
            write_manifest(
                args.manifest_json,
                inputs=manifest_inputs,
                outputs=outputs,
                parameters={k: v for k, v in vars(args).items() if k not in {"api_key"}},
                command="astrometry_net_workbench.py",
                notes=payload.get("notes", []),
                extra=manifest_extra,
            )
    except Exception as exc:
        return emit_blocked_payload(args, clean_known_stderr(f"Could not write requested astrometry output: {exc}"), status="blocked")
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
