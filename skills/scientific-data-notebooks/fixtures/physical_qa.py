#!/usr/bin/env python3
"""Light physical and metadata QA for FITS, spectra, and table-like files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload
from _internal.tabular_io import read_table_any


NULL_STRINGS = {"", "nan", "none", "null", "na", "n/a", "--", "..."}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input FITS or table path.")
    parser.add_argument("--summary-json", help="Optional JSON output.")
    return parser.parse_args()


def emit_collision_only(input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing physical-QA outputs that overlap the input dataset."
    payload = build_tool_payload(
        "physical_qa",
        status="blocked",
        notes=[message, "No summary was written and the input was not modified."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "input": public_path(input_path),
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def add_issue(issues: list[dict], severity: str, message: str, **extra) -> None:
    issue = {"severity": severity, "message": message}
    for key, value in extra.items():
        if value is not None:
            issue[key] = value
    issues.append(issue)


def to_plain(value):
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def safe_float(value):
    value = to_plain(value)
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
        return None
    try:
        return float(value)
    except Exception:
        return None


def numeric_profile(column) -> dict:
    import numpy as np

    values = []
    total = 0
    missing = 0
    invalid = 0
    for raw in column:
        total += 1
        try:
            if np.ma.is_masked(raw):
                missing += 1
                continue
        except Exception:
            pass
        value = to_plain(raw)
        if value is None:
            missing += 1
            continue
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
            missing += 1
            continue
        try:
            values.append(float(value))
        except Exception:
            invalid += 1
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    return {
        "total": int(total),
        "missing": int(missing),
        "invalid": int(invalid),
        "non_finite": int(arr.size - finite.size),
        "values": arr,
        "finite": finite,
        "finite_count": int(finite.size),
    }


def is_ra_name(token: str) -> bool:
    return token in {"ra", "radeg", "raj2000", "raj", "alpha", "rightascension"}


def is_dec_name(token: str) -> bool:
    return token in {"dec", "decdeg", "dej2000", "dej", "delta", "declination"}


def is_airmass_name(token: str) -> bool:
    return token in {"airmass", "secz", "seczd", "secantz"}


def is_flux_name(token: str) -> bool:
    return (
        "flux" in token
        or token in {"counts", "count", "adu", "intensity", "sourceintensity", "signal"}
        or token.endswith("counts")
    )


def is_error_name(token: str) -> bool:
    return (
        "error" in token
        or "sigma" in token
        or "uncert" in token
        or token.endswith("err")
        or token.endswith("errs")
    )


def is_wavelength_name(token: str) -> bool:
    return token in {"wave", "wavelength", "lambda", "lam", "wl"} or "wavelength" in token


def is_time_name(token: str) -> bool:
    if token in {"time", "obsdate", "dateobs", "mjd", "jd", "bjd", "hjd", "epoch"}:
        return True
    return token.endswith("time") or token.endswith("date")


def is_numeric_time_name(token: str) -> bool:
    return token in {"mjd", "jd", "bjd", "hjd"}


def is_relevant_physical_column(token: str) -> bool:
    return (
        is_ra_name(token)
        or is_dec_name(token)
        or is_airmass_name(token)
        or is_flux_name(token)
        or is_error_name(token)
        or is_wavelength_name(token)
        or is_time_name(token)
    )


def parse_time_column(column_name: str, token: str, column, issues: list[dict]) -> list[float]:
    from astropy.time import Time

    values = []
    invalid = 0
    for raw in column:
        value = to_plain(raw)
        if value is None:
            continue
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        text = str(value).strip()
        if text.lower() in NULL_STRINGS:
            continue
        try:
            if token in {"mjd", "bjd", "hjd"}:
                values.append(float(value))
            elif token == "jd":
                values.append(float(value))
            else:
                values.append(float(Time(text).mjd))
        except Exception:
            invalid += 1
    if invalid:
        add_issue(
            issues,
            "info",
            f"Column '{column_name}' has {invalid} time values that could not be parsed; time-order checks ignore them",
            column=column_name,
        )
    return values


def check_numeric_column(name: str, token: str, profile: dict, issues: list[dict]) -> None:
    import numpy as np

    finite = profile["finite"]
    total = profile["total"]
    invalid = profile["invalid"]
    non_finite = profile.get("non_finite", 0)

    if not total:
        return
    if is_time_name(token) and not is_numeric_time_name(token):
        # ISO-like time columns are parsed by parse_time_column(); treating them as
        # numeric first creates false warnings for perfectly valid timestamps.
        return
    if invalid and is_relevant_physical_column(token):
        add_issue(
            issues,
            "warning",
            f"Column '{name}' contains non-numeric values; physical range checks used only finite numeric rows",
            column=name,
            invalid_count=invalid,
        )
    if non_finite and is_relevant_physical_column(token):
        add_issue(
            issues,
            "warning",
            f"Column '{name}' contains non-finite numeric values; physical range checks used only finite numeric rows",
            column=name,
            non_finite_count=non_finite,
        )
    if is_relevant_physical_column(token) and finite.size == 0:
        add_issue(
            issues,
            "warning",
            f"Column '{name}' looks physically relevant but has no finite numeric values",
            column=name,
        )
        return

    if is_ra_name(token) and finite.size:
        if np.nanmin(finite) < -1.0 or np.nanmax(finite) > 360.5:
            add_issue(issues, "warning", "RA values appear outside [0, 360] degrees", column=name)
    if is_dec_name(token) and finite.size:
        if np.nanmin(finite) < -90.5 or np.nanmax(finite) > 90.5:
            add_issue(issues, "warning", "Dec values appear outside [-90, 90] degrees", column=name)
    if is_airmass_name(token) and finite.size:
        if np.nanmin(finite) < 1.0 or np.nanmax(finite) > 5.0:
            add_issue(
                issues,
                "warning",
                f"Column '{name}' has airmass values outside the reasonable [1, 5] range",
                column=name,
            )
    if is_flux_name(token) and finite.size and np.nanmin(finite) < 0:
        add_issue(
            issues,
            "warning",
            f"Column '{name}' contains negative flux/count values; this can be valid after background subtraction, but review the sign convention",
            column=name,
        )
    if is_error_name(token) and finite.size and np.nanmin(finite) < 0:
        add_issue(
            issues,
            "warning",
            f"Column '{name}' contains negative uncertainty/error values",
            column=name,
        )
    if is_wavelength_name(token) and finite.size:
        if np.nanmin(finite) <= 0:
            add_issue(issues, "warning", f"Column '{name}' contains non-positive wavelength values", column=name)
        if finite.size >= 2:
            diffs = np.diff(finite)
            if np.any(diffs == 0):
                add_issue(issues, "warning", f"Column '{name}' contains duplicate wavelength values", column=name)
            if np.any(diffs < 0):
                add_issue(
                    issues,
                    "warning",
                    f"Column '{name}' is not strictly increasing; review spectral wavelength order",
                    column=name,
                )


def table_checks(path: Path) -> tuple[list[dict], dict]:
    import numpy as np
    from astropy.table import Table

    issues: list[dict] = []
    table = read_table_any(Table, path)
    normalized = {name: normalize_name(name) for name in table.colnames}
    metrics = {
        "row_count": int(len(table)),
        "column_count": int(len(table.colnames)),
        "checked_columns": [],
        "spectrum_like": False,
    }

    for name in table.colnames:
        token = normalized[name]
        if not is_relevant_physical_column(token):
            continue
        metrics["checked_columns"].append(name)
        profile = numeric_profile(table[name])
        check_numeric_column(name, token, profile, issues)

        if getattr(table[name], "unit", None) is None:
            add_issue(issues, "info", f"Column '{name}' has no unit metadata", column=name)

        if is_time_name(token):
            times = parse_time_column(name, token, table[name], issues)
            finite_times = [value for value in times if np.isfinite(value)]
            if len(finite_times) >= 2:
                if len(set(finite_times)) < len(finite_times):
                    add_issue(issues, "warning", f"Column '{name}' contains duplicate timestamps", column=name)
                if any(b < a for a, b in zip(finite_times, finite_times[1:])):
                    add_issue(issues, "warning", f"Column '{name}' is not monotonic in observation order", column=name)

    wavelength_columns = [name for name, token in normalized.items() if is_wavelength_name(token)]
    flux_columns = [name for name, token in normalized.items() if is_flux_name(token)]
    if wavelength_columns and flux_columns:
        metrics["spectrum_like"] = True
        flux_profile = numeric_profile(table[flux_columns[0]])
        finite_fraction = (
            flux_profile["finite_count"] / flux_profile["total"] if flux_profile["total"] else 0.0
        )
        if flux_profile["total"] and finite_fraction < 0.8:
            add_issue(
                issues,
                "warning",
                f"Spectrum-like flux column '{flux_columns[0]}' has low finite fraction ({finite_fraction:.3f})",
                column=flux_columns[0],
            )

    return issues, metrics


def check_fits_time(header, key: str, issues: list[dict]) -> None:
    from astropy.time import Time

    if key not in header:
        return
    value = header.get(key)
    try:
        if key == "MJD-OBS":
            Time(float(value), format="mjd")
        else:
            Time(value)
    except Exception:
        add_issue(issues, "warning", f"Could not parse FITS header {key}", header_key=key)


def fits_checks(path: Path) -> tuple[list[dict], dict]:
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    issues: list[dict] = []
    metrics = {"hdu_count": 0, "data_hdu_count": 0, "checked_data_hdus": 0}
    with fits.open(path) as hdus:
        metrics["hdu_count"] = len(hdus)
        header = hdus[0].header

        exptime = header.get("EXPTIME")
        exptime_float = safe_float(exptime)
        if exptime is None:
            add_issue(issues, "warning", "Missing FITS header EXPTIME", header_key="EXPTIME")
        elif exptime_float is None:
            add_issue(issues, "warning", "FITS header EXPTIME is not numeric", header_key="EXPTIME")
        elif exptime_float <= 0:
            add_issue(issues, "warning", "FITS header EXPTIME is non-positive", header_key="EXPTIME")

        airmass = header.get("AIRMASS")
        if airmass is not None:
            airmass_float = safe_float(airmass)
            if airmass_float is None:
                add_issue(issues, "warning", "FITS header AIRMASS is not numeric", header_key="AIRMASS")
            elif airmass_float < 1.0 or airmass_float > 5.0:
                add_issue(
                    issues,
                    "warning",
                    "FITS header AIRMASS is outside the reasonable [1, 5] range",
                    header_key="AIRMASS",
                )

        check_fits_time(header, "DATE-OBS", issues)
        check_fits_time(header, "MJD-OBS", issues)

        if "CTYPE1" in header or "CTYPE2" in header:
            try:
                wcs = WCS(header)
                if not getattr(wcs, "has_celestial", False):
                    add_issue(issues, "info", "WCS keywords are present but not celestial")
            except Exception:
                add_issue(issues, "warning", "WCS keywords are present but parsing failed")

        for idx, hdu in enumerate(hdus):
            data = hdu.data
            if data is None:
                continue
            metrics["data_hdu_count"] += 1
            arr = np.asarray(data)
            if arr.size == 0:
                add_issue(issues, "warning", f"HDU {idx} contains an empty data array", hdu=idx)
                continue
            if not np.issubdtype(arr.dtype, np.number):
                add_issue(issues, "info", f"HDU {idx} data are not numeric; finite-fraction check skipped", hdu=idx)
                continue
            metrics["checked_data_hdus"] += 1
            finite_fraction = float(np.isfinite(arr).sum() / arr.size)
            if finite_fraction < 0.5:
                add_issue(issues, "warning", f"HDU {idx} has low finite pixel fraction: {finite_fraction:.3f}", hdu=idx)
            negative_fraction = float((arr[np.isfinite(arr)] < 0).sum() / np.isfinite(arr).sum()) if np.isfinite(arr).any() else 0.0
            if negative_fraction > 0.25:
                add_issue(
                    issues,
                    "info",
                    f"HDU {idx} has many negative pixels ({negative_fraction:.3f}); this can be valid after background subtraction",
                    hdu=idx,
                )

    if metrics["data_hdu_count"] == 0:
        add_issue(issues, "info", "No FITS data arrays found; only header-level checks were possible")
    return issues, metrics


def blocked_payload(input_path: Path, kind: str, message: str, summary_json: str | None) -> dict:
    issue = {"severity": "error", "message": message}
    summary = {
        "path": str(input_path.resolve()) if input_path.exists() else str(input_path),
        "kind": kind,
        "issue_count": 1,
        "issues": [issue],
        "metrics": {},
    }
    return build_tool_payload(
        "physical_qa",
        status="blocked",
        notes=[
            "Light physical sanity checks only: this does not replace domain-specific reduction QA or scientific interpretation.",
            "The input could not be read far enough to run QA checks.",
        ],
        artifacts={"summary_json": summary_json},
        results=summary,
        qa={"status": "blocked", "findings": [issue], "metrics": {"issue_count": 1, "warning_count": 0}},
        legacy=summary,
    )


def summary_json_parent_issue(summary_json: str | None) -> str | None:
    if not summary_json:
        return None
    parent = Path(summary_json).expanduser().parent
    if parent.exists() and not parent.is_dir():
        return f"summary-json parent is not a directory: {parent}"
    return None


def emit_blocked(input_path: Path, kind: str, message: str, summary_json: str | None) -> int:
    payload = blocked_payload(input_path, kind, message, summary_json)
    emit_payload(payload, summary_json)
    return 2


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser()
    collisions = find_output_input_collisions(
        [("input", input_path)],
        [("--summary-json", args.summary_json)],
    )
    if collisions:
        return emit_collision_only(input_path, collisions)
    summary_issue = summary_json_parent_issue(args.summary_json)
    if summary_issue:
        print(summary_issue)
        return 2
    if not input_path.exists():
        return emit_blocked(input_path, "unknown", f"File not found: {input_path}", args.summary_json)

    suffix = input_path.suffix.lower()
    kind = "fits" if suffix in {".fits", ".fit", ".fts", ".fz"} else "table"
    try:
        if kind == "fits":
            issues, metrics = fits_checks(input_path)
        else:
            issues, metrics = table_checks(input_path)
    except Exception as exc:
        return emit_blocked(input_path, kind, f"Could not read {kind} input: {exc.__class__.__name__}: {exc}", args.summary_json)

    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    summary = {
        "path": str(input_path.resolve()),
        "kind": kind,
        "issue_count": len(issues),
        "issues": issues,
        "metrics": metrics,
    }
    payload = build_tool_payload(
        "physical_qa",
        status="warning" if warning_count else "ok",
        notes=[
            "Light physical sanity checks only: this does not replace domain-specific reduction QA or scientific interpretation.",
            "Checks are deliberately conservative: FITS headers/data, coordinate bounds, flux/count signs, uncertainties, airmass, time order, and spectrum-like wavelength sanity.",
        ],
        artifacts={"summary_json": args.summary_json},
        results=summary,
        qa={
            "status": "warning" if warning_count else "ok",
            "findings": issues,
            "metrics": {"issue_count": len(issues), "warning_count": warning_count, **metrics},
        },
        legacy=summary,
    )
    emit_payload(payload, args.summary_json)
    if args.summary_json:
        print(f"Saved summary: {Path(args.summary_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
