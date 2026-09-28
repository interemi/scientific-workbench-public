#!/usr/bin/env python3
"""Profile tabular data files used in scientific or general analysis."""

import argparse
import json
import math
import os
import re
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import public_path, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.run_bundle import add_run_bundle_argument, apply_run_bundle_defaults, finalize_existing_run_bundle
from _internal.runtime_common import suppress_fd_output
from _internal.tabular_io import read_table_any


ASTRONOMY_EXTENSIONS = {".ecsv", ".fits", ".fit", ".fts", ".vot", ".votable", ".xml"}
CSV_EXTENSIONS = {".csv", ".tsv"}
TEXT_EXTENSIONS = {".txt", ".dat", ".ascii"}
JSON_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".xlsb", ".ods"}
COLUMNAR_EXTENSIONS = {".parquet", ".feather", ".arrow", ".ipc"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to the table-like file.")
    parser.add_argument(
        "--format",
        help="Explicit format string for astropy.table.Table.read when needed.",
    )
    parser.add_argument(
        "--prefer",
        choices=["auto", "astropy", "pandas"],
        default="auto",
        help="Preferred backend. Default: auto.",
    )
    parser.add_argument(
        "--hdu",
        help="Optional FITS HDU for table reads.",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=5,
        help="Number of preview rows to print.",
    )
    parser.add_argument(
        "--max-columns",
        type=int,
        default=20,
        help="Maximum number of columns to print detailed summaries for.",
    )
    parser.add_argument(
        "--summary-json",
        help="Optional output path for machine-readable JSON summary.",
    )
    parser.add_argument("--lazy", action="store_true", help="Prefer out-of-core profiling when possible.")
    parser.add_argument("--lazy-threshold-mb", type=int, default=64, help="Auto-switch to lazy profiling above this size.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    add_run_bundle_argument(parser)
    return parser.parse_args()


def load_dependencies():
    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit("Missing numpy. Install numpy before using this script.") from exc

    try:
        warnings.filterwarnings(
            "ignore",
            message=r"Pandas requires version .* of 'numexpr'.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r"Pandas requires version .* of 'bottleneck'.*",
            category=UserWarning,
        )
        with suppress_fd_output(True):
            import pandas as pd
    except ImportError:
        pd = None

    try:
        from astropy.table import Table
    except ImportError:
        Table = None

    try:
        import dask.dataframe as dd
    except Exception:
        dd = None

    return np, pd, Table, dd


def choose_separator(path):
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "\t"
    if suffix == ".csv":
        return ","
    return None


def maybe_number(value):
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        if value != value:
            return None
    except Exception:
        pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return json_safe_value(value.item())
        except Exception:
            pass
    return str(value)


def json_safe_record(record: dict) -> dict:
    return {str(key): json_safe_value(value) for key, value in record.items()}


def json_safe_records(records: list[dict]) -> list[dict]:
    return [json_safe_record(record) for record in records]


def sanitize_json_numbers(value):
    """Recursively replace non-standard JSON numbers while preserving QA counts."""
    if isinstance(value, dict):
        return {str(key): sanitize_json_numbers(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_numbers(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def paths_refer_to_same_file(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)


def numeric_stats(np, values):
    array = np.asarray(values)
    if array.size == 0:
        return None
    try:
        finite = array[np.isfinite(array)].astype(float, copy=False)
    except Exception:
        return None
    if finite.size == 0:
        return None
    return {
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "median": float(np.median(finite)),
        "std": float(np.std(finite)),
    }


def load_with_pandas(pd, path):
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix in {".xlsx", ".xlsm", ".xls", ".ods"}:
        return pd.read_excel(path)
    if suffix == ".xlsb":
        last_error = None
        for engine in ("calamine", "pyxlsb"):
            try:
                return pd.read_excel(path, engine=engine)
            except Exception as exc:
                last_error = exc
        raise last_error
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".feather", ".arrow", ".ipc"}:
        return pd.read_feather(path)
    sep = choose_separator(path)
    if sep is not None:
        return pd.read_csv(path, sep=sep)
    return pd.read_csv(path, sep=None, engine="python")


def load_with_astropy(Table, path, fmt=None, hdu=None):
    return read_table_any(Table, path, fmt=fmt, hdu=hdu)


def load_with_dask(dd, path):
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return dd.read_csv(path, sep="\t" if suffix == ".tsv" else ",", assume_missing=True)
    if suffix in {".jsonl", ".ndjson"}:
        return dd.read_json(path, blocksize="16MB")
    if suffix == ".parquet":
        return dd.read_parquet(path)
    raise ValueError(f"Unsupported lazy format: {suffix}")


def load_table(path, fmt, prefer, hdu, pd, Table, dd, lazy=False, lazy_threshold_mb=64):
    suffix = path.suffix.lower()
    use_lazy = False
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
        use_lazy = lazy or (dd is not None and size_mb >= lazy_threshold_mb and suffix in CSV_EXTENSIONS | JSON_EXTENSIONS | COLUMNAR_EXTENSIONS)
    except Exception:
        size_mb = None

    if use_lazy and dd is not None:
        try:
            return "dask", load_with_dask(dd, path)
        except Exception:
            pass

    if prefer == "pandas":
        if pd is None:
            raise SystemExit("Pandas is not installed, so the pandas backend is unavailable.")
        return "pandas", load_with_pandas(pd, path)

    if prefer == "astropy":
        if Table is None:
            raise SystemExit("Astropy is not installed, so the astropy backend is unavailable.")
        return "astropy", load_with_astropy(Table, path, fmt=fmt, hdu=hdu)

    if suffix in CSV_EXTENSIONS | JSON_EXTENSIONS | SPREADSHEET_EXTENSIONS | COLUMNAR_EXTENSIONS and pd is not None:
        try:
            return "pandas", load_with_pandas(pd, path)
        except Exception:
            pass

    if (suffix in ASTRONOMY_EXTENSIONS or suffix in TEXT_EXTENSIONS or suffix in JSON_EXTENSIONS | SPREADSHEET_EXTENSIONS | COLUMNAR_EXTENSIONS) and Table is not None:
        try:
            if suffix in {".fits", ".fit", ".fts"} and hdu is None:
                try:
                    return "astropy", load_with_astropy(Table, path, fmt=fmt, hdu=1)
                except Exception:
                    pass
            return "astropy", load_with_astropy(Table, path, fmt=fmt, hdu=hdu)
        except Exception:
            pass

    if pd is not None:
        try:
            return "pandas", load_with_pandas(pd, path)
        except Exception:
            pass

    if Table is not None:
        try:
            return "astropy", load_with_astropy(Table, path, fmt=fmt, hdu=hdu)
        except Exception:
            pass

    raise SystemExit(
        "Could not read the table with the available backends. "
        "Try --prefer astropy, --prefer pandas, or an explicit --format."
    )


def summarize_dask(df, head, max_columns):
    import numpy as np
    import pandas as pd

    preview = json_safe_records(df.head(head).to_dict(orient="records"))
    row_count = int(df.shape[0].compute())
    summary = {
        "backend": "dask",
        "rows": row_count,
        "columns": int(len(df.columns)),
        "column_summaries": [],
        "preview": preview,
    }
    for name in list(df.columns)[:max_columns]:
        series = df[name]
        entry = {"name": str(name), "dtype": str(series.dtype), "nulls": int(series.isna().sum().compute())}
        if pd.api.types.is_numeric_dtype(series.dtype):
            infinite_mask = (series == np.inf) | (series == -np.inf)
            entry["infinite_count"] = int(infinite_mask.sum().compute())
            finite_series = series.mask(infinite_mask)
            finite_count = int(finite_series.count().compute())
            if finite_count:
                stats = {
                    "min": json_safe_value(float(finite_series.min().compute())),
                    "max": json_safe_value(float(finite_series.max().compute())),
                    "mean": json_safe_value(float(finite_series.mean().compute())),
                    "median": json_safe_value(float(finite_series.quantile(0.5).compute())),
                    "std": json_safe_value(float(finite_series.std(ddof=0).compute())),
                }
                entry["stats"] = stats
            else:
                entry["sample_values"] = []
        else:
            entry["sample_values"] = [str(item) for item in series.dropna().head(5).tolist()]
        summary["column_summaries"].append(entry)
    return summary


def summarize_pandas(np, df, head, max_columns):
    summary = {
        "backend": "pandas",
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_summaries": [],
        "preview": json_safe_records(df.head(head).to_dict(orient="records")),
    }
    for name in list(df.columns)[:max_columns]:
        series = df[name]
        entry = {
            "name": str(name),
            "dtype": str(series.dtype),
            "nulls": int(series.isna().sum()),
        }
        stats = numeric_stats(np, series.dropna().to_numpy())
        if stats:
            entry["stats"] = stats
            numeric = np.asarray(series.dropna().to_numpy())
            try:
                entry["infinite_count"] = int(np.isinf(numeric).sum())
            except Exception:
                entry["infinite_count"] = 0
        else:
            unique_values = [json_safe_value(value) for value in series.dropna().unique().tolist()[:5]]
            entry["sample_values"] = unique_values
        summary["column_summaries"].append(entry)
    return summary


def summarize_astropy(np, table, head, max_columns):
    summary = {
        "backend": "astropy",
        "rows": int(len(table)),
        "columns": int(len(table.colnames)),
        "column_summaries": [],
        "preview_text": table[:head].pformat(max_width=120),
    }
    for name in table.colnames[:max_columns]:
        column = table[name]
        entry = {
            "name": str(name),
            "dtype": str(column.dtype),
            "nulls": int(getattr(column, "mask", []).sum()) if hasattr(column, "mask") else 0,
        }
        if getattr(column, "unit", None) is not None:
            entry["unit"] = str(column.unit)
        stats = numeric_stats(np, column)
        if stats:
            entry["stats"] = stats
            try:
                entry["infinite_count"] = int(np.isinf(column).sum())
            except Exception:
                entry["infinite_count"] = 0
        else:
            entry["sample_values"] = [json_safe_value(value) for value in column[:5]]
        summary["column_summaries"].append(entry)
    return summary


def profile_quality_findings(summary):
    hard_errors = []
    warnings_found = []
    metrics = {
        "empty_or_unnamed_column_count": 0,
        "suspected_duplicate_column_count": 0,
        "all_null_column_count": 0,
        "infinite_value_count": 0,
    }
    if summary.get("rows") == 0:
        warnings_found.append("The table has zero data rows; check whether the header or file format was interpreted correctly.")

    column_names = [entry.get("name", "") for entry in summary.get("column_summaries", [])]
    column_name_set = set(column_names)
    for name in column_names:
        rendered = str(name)
        if "\n" in rendered or "\r" in rendered:
            hard_errors.append(f"Suspicious column name contains a line break: {rendered!r}. The input may be malformed.")
        if not rendered.strip() or rendered.lower().startswith("unnamed:"):
            metrics["empty_or_unnamed_column_count"] += 1
        match = re.match(r"^(.+)\.\d+$", rendered)
        if match and match.group(1) in column_name_set:
            metrics["suspected_duplicate_column_count"] += 1

    for entry in summary.get("column_summaries", []):
        nulls = int(entry.get("nulls", 0) or 0)
        if summary.get("rows") and nulls == summary.get("rows"):
            metrics["all_null_column_count"] += 1
        metrics["infinite_value_count"] += int(entry.get("infinite_count", 0) or 0)

    if metrics["empty_or_unnamed_column_count"]:
        warnings_found.append(
            f"{metrics['empty_or_unnamed_column_count']} columns are empty or unnamed; the file may need header cleanup."
        )
    if metrics["suspected_duplicate_column_count"]:
        warnings_found.append(
            f"{metrics['suspected_duplicate_column_count']} columns look like pandas-renamed duplicates; verify the original header."
        )
    if metrics["all_null_column_count"]:
        warnings_found.append(f"{metrics['all_null_column_count']} columns are entirely null in the profiled table.")
    if metrics["infinite_value_count"]:
        warnings_found.append(f"{metrics['infinite_value_count']} infinite numeric values were detected.")
    return hard_errors, warnings_found, metrics


def print_summary(path, summary, head):
    print(f"Table file: {path}")
    print(f"Backend: {summary['backend']}")
    print(f"Rows: {summary['rows']}")
    print(f"Columns: {summary['columns']}")
    print("")
    print("Column summaries:")
    for entry in summary["column_summaries"]:
        line = f"- {entry['name']}: dtype={entry['dtype']}, nulls={entry['nulls']}"
        if "unit" in entry:
            line += f", unit={entry['unit']}"
        if "stats" in entry:
            stats = entry["stats"]
            line += (
                f", min={stats['min']:.6g}, median={stats['median']:.6g}, "
                f"max={stats['max']:.6g}, std={stats['std']:.6g}"
            )
        elif "sample_values" in entry:
            line += ", sample=" + ", ".join(str(value) for value in entry["sample_values"])
        print(line)

    print("")
    print(f"Preview (first {head} rows):")
    if summary["backend"] in {"pandas", "dask"}:
        for row in summary["preview"]:
            print(json.dumps(row, ensure_ascii=True))
    else:
        for line in summary["preview_text"]:
            print(line)


def build_failure_payload(args, message, partial_summary=None):
    return build_tool_payload(
        "profile_table",
        status="fail",
        notes=["The table could not be profiled safely; inspect the error before using any partial output."],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results={"error": message, "partial_summary": partial_summary or {}},
        qa={
            "status": "fail",
            "findings": [message],
            "metrics": {},
        },
        legacy={"error": message, "partial_summary": partial_summary or {}},
    )


def emit_failure(args, message, partial_summary=None):
    payload = sanitize_json_numbers(build_failure_payload(args, message, partial_summary=partial_summary))
    if args.summary_json:
        try:
            emit_payload(payload, args.summary_json)
        except Exception as exc:
            print(json.dumps(payload, indent=2, ensure_ascii=True), file=sys.stdout)
            print(f"Could not write failure payload: {exc}", file=sys.stderr)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True), file=sys.stdout)
    layout = getattr(args, "_run_bundle_layout", None)
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=2)
    print(message, file=sys.stderr)
    return 2


def emit_collision_only(args, path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing to overwrite or overlap the input table with table-profile outputs."
    original_summary = args.summary_json
    original_manifest = args.manifest_json
    args.summary_json = None
    args.manifest_json = None
    payload = sanitize_json_numbers(build_failure_payload(args, message))
    payload["status"] = "blocked"
    payload["app_status"] = "BLOCKED_CONTROLADO"
    payload["artifacts"] = {}
    payload["typed_artifacts"] = []
    payload["results"].update(
        {
            "error_type": "output_input_collision",
            "input": public_path(path),
            "collisions": collisions,
            "requested_summary_json": public_path(original_summary) if original_summary else None,
            "requested_manifest_json": public_path(original_manifest) if original_manifest else None,
        }
    )
    payload["qa"]["status"] = "blocked"
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 2


def main():
    args = parse_args()
    path = Path(args.path).expanduser()
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    outputs: list[tuple[str, Path | str | None]] = [
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
        ("--run-dir", run_dir),
    ]
    if run_dir is not None:
        outputs.extend(
            (f"derived:{name}", run_dir / name)
            for name in ("summary.json", "manifest.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md")
        )
    collisions = find_output_input_collisions([("path", path)], outputs)
    if collisions:
        return emit_collision_only(args, path, collisions)
    layout = apply_run_bundle_defaults(args)
    try:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"Expected a table-like file, got a directory: {path}")

        np, pd, Table, dd = load_dependencies()
        backend, table = load_table(
            path=path,
            fmt=args.format,
            prefer=args.prefer,
            hdu=args.hdu,
            pd=pd,
            Table=Table,
            dd=dd,
            lazy=args.lazy,
            lazy_threshold_mb=args.lazy_threshold_mb,
        )

        if backend == "pandas":
            summary = summarize_pandas(np, table, args.head, args.max_columns)
        elif backend == "dask":
            summary = summarize_dask(table, args.head, args.max_columns)
        else:
            summary = summarize_astropy(np, table, args.head, args.max_columns)
    except SystemExit as exc:
        message = str(exc) if str(exc) else "profile_table stopped before producing a table profile."
        return emit_failure(args, message)
    except Exception as exc:
        return emit_failure(args, str(exc))

    summary["path"] = public_path(path)
    hard_errors, warnings_found, quality_metrics = profile_quality_findings(summary)
    summary["quality_warnings"] = warnings_found
    summary["quality_metrics"] = quality_metrics
    if hard_errors:
        return emit_failure(args, "; ".join(hard_errors), partial_summary=summary)

    print_summary(public_path(path), summary, args.head)

    notes = [
        "This profiler is intended as a first-pass inventory for tabular inputs before cleaning, modeling, or cross-domain joins.",
    ]
    if backend == "dask":
        notes.append("Lazy/out-of-core profiling was used for this run.")
    if warnings_found:
        notes.append("Profile completed with table-quality warnings; inspect qa.findings before cleaning or modeling.")
    payload = sanitize_json_numbers(build_tool_payload(
        "profile_table",
        status="warning" if warnings_found else "ok",
        notes=notes,
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results=summary,
        qa={
            "status": "warning" if warnings_found else "ok",
            "findings": warnings_found,
            "metrics": {
                "rows": summary["rows"],
                "columns": summary["columns"],
                "backend": summary["backend"],
                **quality_metrics,
            },
        },
        legacy=summary,
    ))
    json.dumps(payload, allow_nan=False)
    if args.summary_json:
        emit_payload(payload, args.summary_json)
        print("")
        print(f"Saved JSON summary: {public_path(args.summary_json)}")
    if args.manifest_json:
        outputs = [args.summary_json] if args.summary_json else []
        write_manifest(args.manifest_json, inputs=[path], outputs=outputs, parameters={"backend": backend, "lazy": args.lazy})
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
