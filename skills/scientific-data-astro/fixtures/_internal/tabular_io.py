#!/usr/bin/env python3
"""Shared readers and writers for scientific-data-analysis table-like formats."""

import json
import os
import re
from pathlib import Path

from _internal.runtime_common import suppress_fd_output

os.environ.setdefault("ARROW_USER_SIMD_LEVEL", "NONE")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

COMPRESSION_SUFFIXES = {".gz", ".bz2", ".xz"}
PANDAS_RECORD_EXTS = {".json", ".jsonl", ".ndjson", ".geojson", ".xlsx", ".xlsm", ".xls", ".xlsb", ".ods", ".parquet", ".feather", ".arrow", ".ipc"}


def _split_multi_space(line):
    return [part for part in re.split(r"\s{2,}", line.strip()) if part]


def _split_apt_fields(line):
    fields = _split_multi_space(line)
    if len(fields) <= 1:
        fields = line.strip().split()
    return fields


def _coerce_column(values):
    try:
        ints = [int(value) for value in values]
        return ints
    except Exception:
        pass
    try:
        floats = [float(value) for value in values]
        return floats
    except Exception:
        pass
    return values


def _effective_suffix(path):
    suffixes = [item.lower() for item in Path(path).suffixes]
    if not suffixes:
        return ""
    if suffixes[-1] in COMPRESSION_SUFFIXES and len(suffixes) >= 2:
        return suffixes[-2]
    return suffixes[-1]


def _load_pandas():
    try:
        with suppress_fd_output(True):
            import pandas as pd
    except ImportError:
        return None
    return pd


def _table_from_records(Table, records):
    if not records:
        return Table()
    names = []
    seen = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Expected a list of objects for record-style JSON input.")
        for key in row:
            if key not in seen:
                names.append(key)
                seen.add(key)
    rows = [[row.get(name) for name in names] for row in records]
    return Table(rows=rows, names=names)


def _read_json_table(Table, path):
    payload = json.loads(Path(path).read_text(errors="replace"))
    if isinstance(payload, list):
        return _table_from_records(Table, payload)
    if isinstance(payload, dict):
        if payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list):
            records = []
            for feature in payload["features"]:
                properties = dict(feature.get("properties") or {})
                geometry = feature.get("geometry") or {}
                properties["geometry_type"] = geometry.get("type")
                coordinates = geometry.get("coordinates")
                if isinstance(coordinates, list):
                    properties["geometry_coordinates"] = json.dumps(coordinates, ensure_ascii=True)
                records.append(properties)
            return _table_from_records(Table, records)
        for key in ["data", "rows", "records", "items", "table"]:
            value = payload.get(key)
            if isinstance(value, list):
                return _table_from_records(Table, value)
        if payload and all(isinstance(value, list) for value in payload.values()):
            return Table(payload)
    raise ValueError("Unsupported JSON table layout.")


def _read_jsonl_table(Table, path):
    records = []
    for raw in Path(path).read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return _table_from_records(Table, records)


def _table_from_pandas(Table, dataframe):
    return Table.from_pandas(dataframe)


def _read_with_pandas(Table, path, suffix):
    pd = _load_pandas()
    if pd is None:
        raise ImportError("pandas is required for this format.")
    if suffix in {".xlsx", ".xlsm", ".xls", ".ods"}:
        dataframe = pd.read_excel(path)
    elif suffix == ".xlsb":
        last_error = None
        for engine in ("calamine", "pyxlsb"):
            try:
                dataframe = pd.read_excel(path, engine=engine)
                break
            except Exception as exc:
                last_error = exc
        else:
            raise last_error
    elif suffix == ".parquet":
        dataframe = pd.read_parquet(path)
    elif suffix in {".feather", ".arrow", ".ipc"}:
        dataframe = pd.read_feather(path)
    else:
        raise ValueError(f"Unsupported pandas-driven format: {suffix}")
    return _table_from_pandas(Table, dataframe)


def read_apt_tbl(Table, path):
    lines = Path(path).read_text(errors="replace").splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if "Number" in line and ("Image" in line or "SourceIntensity" in line):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("APT-style header not found.")

    names = _split_apt_fields(lines[header_idx])
    if len(names) <= 1:
        raise ValueError("APT-style header did not split into usable columns.")
    rows = []
    for raw in lines[header_idx + 1 :]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = _split_apt_fields(line)
        if len(parts) < len(names):
            continue
        if len(parts) > len(names):
            parts = parts[: len(names) - 1] + [" ".join(parts[len(names) - 1 :])]
        rows.append(parts)
    if not rows:
        raise ValueError("No data rows found in APT table.")

    columns = list(zip(*rows))
    coerced = [_coerce_column(list(column)) for column in columns]
    return Table({name: column for name, column in zip(names, coerced)})


def read_table_any(Table, path, fmt=None, hdu=None):
    path = Path(path)
    suffix = _effective_suffix(path)
    kwargs = {}
    if fmt:
        kwargs["format"] = fmt
    if hdu is not None:
        kwargs["hdu"] = hdu

    if suffix == ".tbl":
        try:
            return read_apt_tbl(Table, path)
        except Exception:
            pass

    if suffix in {".fits", ".fit", ".fts"} and hdu is None:
        try:
            return Table.read(path, hdu=1, **kwargs)
        except Exception:
            pass

    if suffix == ".json":
        return _read_json_table(Table, path)

    if suffix in {".jsonl", ".ndjson"}:
        return _read_jsonl_table(Table, path)

    if suffix in PANDAS_RECORD_EXTS:
        return _read_with_pandas(Table, path, suffix)

    if suffix in {".txt", ".text", ".dat", ".ascii"}:
        for format_name in ["ascii.basic", "ascii.no_header", "ascii.tab"]:
            try:
                return Table.read(path, format=format_name)
            except Exception:
                continue

    return Table.read(path, **kwargs)


def write_table_any(table, path):
    path = Path(path)
    suffix = _effective_suffix(path)
    if suffix == ".csv":
        table.write(path, format="ascii.csv", overwrite=True)
        return
    if suffix == ".ecsv":
        table.write(path, format="ascii.ecsv", overwrite=True)
        return
    if suffix in {".tsv", ".tab"}:
        table.write(path, format="ascii.tab", overwrite=True)
        return
    if suffix in {".jsonl", ".ndjson"}:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for row in table:
                serializable = {name: row[name].item() if hasattr(row[name], "item") else row[name] for name in table.colnames}
                fh.write(json.dumps(serializable, ensure_ascii=True) + "\n")
        return
    if suffix in {".xlsx", ".xlsb", ".parquet", ".feather", ".arrow", ".ipc"}:
        pd = _load_pandas()
        if pd is None:
            raise RuntimeError(f"Writing {suffix} requires pandas.")
        dataframe = table.to_pandas()
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".xlsx":
            dataframe.to_excel(path, index=False)
        elif suffix == ".xlsb":
            from pyxlsbwriter import XlsbWriter

            rows = [list(dataframe.columns)]
            rows.extend(dataframe.where(dataframe.notna(), None).values.tolist())
            with XlsbWriter(str(path)) as writer:
                writer.add_sheet("Sheet1")
                writer.write_sheet(rows)
        elif suffix == ".parquet":
            dataframe.to_parquet(path, index=False)
        else:
            dataframe.to_feather(path)
        return
    table.write(path, overwrite=True)
