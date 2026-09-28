#!/usr/bin/env python3
"""Helpers for Systemic-style radial-velocity files and normalized RV summaries."""

from __future__ import annotations

import math
import re
from pathlib import Path
from statistics import median

from _internal.provenance_utils import public_path


COMMENT_RE = re.compile(r"^#\s*(?P<key>[^=]+?)\s*=\s*(?P<value>.+?)\s*$")
SYS_KEY_MAP = {
    "Name": "name",
    "Mass": "mass_solar",
    "HD": "hd",
    "HIP": "hip",
    "Teff": "teff_k",
    "RA": "ra_deg",
    "Dec": "dec_deg",
}


def _coerce_scalar(value: str):
    text = value.strip()
    if not text or text.upper() == "NA":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def _normalize_key(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return cleaned.strip("_") or "value"


def _safe_median(values: list[float]) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return None
    return float(median(finite))


def _range_payload(values: list[float]) -> dict:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"min": None, "max": None, "median": None}
    return {
        "min": float(min(finite)),
        "max": float(max(finite)),
        "median": _safe_median(finite),
    }


def _resolve_reference(base_dir: Path, reference: str) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def parse_systemic_sys(path: str | Path) -> dict:
    sys_path = Path(path).resolve()
    raw_metadata = {}
    star_metadata = {
        "name": None,
        "mass_solar": None,
        "hd": None,
        "hip": None,
        "teff_k": None,
        "ra_deg": None,
        "dec_deg": None,
    }
    rv_files = []
    for line in sys_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in stripped:
            key, value = stripped.split("\t", 1)
        else:
            parts = stripped.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts
        key = key.strip()
        value = value.strip()
        if key == "RV[]":
            rv_files.append(value)
            continue
        raw_metadata[key] = _coerce_scalar(value)
        normalized = SYS_KEY_MAP.get(key)
        if normalized:
            star_metadata[normalized] = _coerce_scalar(value)
    return {
        "path": public_path(sys_path),
        "filename": sys_path.name,
        "star_metadata": star_metadata,
        "raw_metadata": raw_metadata,
        "rv_files": rv_files,
    }


def parse_systemic_vels(path: str | Path) -> dict:
    vels_path = Path(path).resolve()
    metadata = {}
    jd_values = []
    rv_values = []
    error_values = []
    data_rows = 0
    malformed_rows = 0
    nonfinite_value_rows = 0
    invalid_error_rows = 0
    nonpositive_error_rows = 0
    missing_error_rows = 0
    for line in vels_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            match = COMMENT_RE.match(stripped)
            if match:
                key = _normalize_key(match.group("key"))
                metadata[key] = match.group("value").strip()
            continue
        parts = stripped.split()
        if len(parts) < 2:
            malformed_rows += 1
            continue
        data_rows += 1
        try:
            jd = float(parts[0])
            rv = float(parts[1])
        except ValueError:
            malformed_rows += 1
            continue
        if not (math.isfinite(jd) and math.isfinite(rv)):
            nonfinite_value_rows += 1
            continue
        jd_values.append(jd)
        rv_values.append(rv)
        if len(parts) < 3:
            missing_error_rows += 1
            continue
        try:
            err = float(parts[2])
        except ValueError:
            invalid_error_rows += 1
            continue
        if not math.isfinite(err):
            invalid_error_rows += 1
            continue
        if err <= 0:
            nonpositive_error_rows += 1
            continue
        error_values.append(err)
    jd_range = _range_payload(jd_values)
    rv_range = _range_payload(rv_values)
    error_range = _range_payload(error_values)
    jd_span_days = None
    if jd_values:
        jd_span_days = float(max(jd_values) - min(jd_values))
    return {
        "path": public_path(vels_path),
        "filename": vels_path.name,
        "dataset_label": vels_path.stem,
        "metadata": metadata,
        "data_row_count": data_rows,
        "sample_count": len(jd_values),
        "malformed_rows": malformed_rows,
        "nonfinite_value_rows": nonfinite_value_rows,
        "invalid_error_rows": invalid_error_rows,
        "nonpositive_error_rows": nonpositive_error_rows,
        "missing_error_rows": missing_error_rows,
        "value_units": metadata.get("value_units"),
        "jd_range": jd_range,
        "jd_span_days": jd_span_days,
        "rv_range": rv_range,
        "error_range": error_range,
    }


def inspect_systemic_system(path: str | Path) -> dict:
    sys_payload = parse_systemic_sys(path)
    sys_path = Path(path).resolve()
    datasets = []
    jd_mins = []
    jd_maxs = []
    total_samples = 0
    for reference in sys_payload["rv_files"]:
        resolved = _resolve_reference(sys_path.parent, reference)
        entry = {
            "reference": reference,
            "resolved_path": public_path(resolved),
            "exists": resolved.exists(),
        }
        if resolved.exists():
            dataset = parse_systemic_vels(resolved)
            entry.update(dataset)
            sample_count = dataset.get("sample_count") or 0
            total_samples += sample_count
            jd_range = dataset.get("jd_range") or {}
            if jd_range.get("min") is not None:
                jd_mins.append(float(jd_range["min"]))
            if jd_range.get("max") is not None:
                jd_maxs.append(float(jd_range["max"]))
        datasets.append(entry)
    combined_span_days = None
    if jd_mins and jd_maxs:
        combined_span_days = float(max(jd_maxs) - min(jd_mins))
    return {
        "mode": "system",
        "system_file": sys_payload["path"],
        "filename": sys_payload["filename"],
        "system_name": sys_payload["star_metadata"].get("name") or sys_path.stem,
        "star_metadata": sys_payload["star_metadata"],
        "raw_metadata": sys_payload["raw_metadata"],
        "rv_dataset_count": len(datasets),
        "rv_sample_count_total": total_samples,
        "time_span_days": combined_span_days,
        "rv_datasets": datasets,
    }


def inspect_systemic_directory(path: str | Path) -> dict:
    root = Path(path).resolve()
    system_files = sorted(root.rglob("*.sys"))
    vels_files = sorted(root.rglob("*.vels"))
    systems = [inspect_systemic_system(item) for item in system_files]
    referenced = set()
    for system in systems:
        for dataset in system.get("rv_datasets", []):
            resolved_path = dataset.get("resolved_path")
            if resolved_path:
                referenced.add(resolved_path)
    standalone = []
    for dataset_path in vels_files:
        rendered = public_path(dataset_path.resolve())
        if rendered in referenced:
            continue
        standalone.append(parse_systemic_vels(dataset_path))
    return {
        "mode": "directory",
        "path": public_path(root),
        "system_count": len(systems),
        "standalone_dataset_count": len(standalone),
        "systems": systems,
        "standalone_datasets": standalone,
    }


def inspect_systemic_input(path: str | Path) -> dict:
    candidate = Path(path).resolve()
    if candidate.is_dir():
        return inspect_systemic_directory(candidate)
    suffix = candidate.suffix.lower()
    if suffix == ".sys":
        return inspect_systemic_system(candidate)
    if suffix == ".vels":
        payload = parse_systemic_vels(candidate)
        payload["mode"] = "dataset"
        return payload
    raise ValueError(f"Unsupported Systemic radial-velocity input: {candidate}")
