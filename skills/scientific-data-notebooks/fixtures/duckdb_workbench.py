#!/usr/bin/env python3
"""Query heterogeneous tabular files with DuckDB and safe fallbacks."""

import argparse
import csv
import json
import math
import re
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, suppress_fd_output


COMPRESSION_SUFFIXES = {".gz", ".bz2", ".xz"}
DUCKDB_RESERVED_ALIASES = {
    "all",
    "and",
    "as",
    "by",
    "create",
    "delete",
    "from",
    "group",
    "insert",
    "join",
    "limit",
    "order",
    "select",
    "table",
    "update",
    "view",
    "where",
}


def reject_unknown_long_option_assignments(parser):
    known_options = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    positional_only = False
    for token in sys.argv[1:]:
        if token == "--":
            positional_only = True
            continue
        if positional_only or not token.startswith("--") or "=" not in token:
            continue
        option = token.split("=", 1)[0]
        if option not in known_options:
            parser.error(f"unrecognized arguments: {token}")


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "DuckDB source aliases are always available as source0, source1, source2, ...\n"
            "The first input is source0, the second is source1, and so on.\n"
            "Safe stem-based aliases may also be added when they do not collide."
        ),
    )
    parser.add_argument("inputs", nargs="+", help="Input tables or datasets to expose inside DuckDB.")
    parser.add_argument("--sql", help="SQL query to run. Defaults to a preview query on the first source.")
    parser.add_argument("--preview-rows", type=int, default=10, help="Rows to print when previewing results.")
    parser.add_argument("--output", help="Optional output file (.csv, .json, .parquet).")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    reject_unknown_long_option_assignments(parser)
    return parser.parse_args()


def resolve_summary_path(args):
    return Path(args.summary_json) if args.summary_json else None


def paths_refer_to_same_file(left: Path, right: Path) -> bool:
    """Compare existing aliases/hardlinks and not-yet-created paths canonically."""
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)


def find_input_output_collision(args) -> str | None:
    """Return a controlled blocker when any requested output aliases an input."""
    inputs = [Path(item) for item in getattr(args, "inputs", [])]
    outputs = (
        ("--output", getattr(args, "output", None)),
        ("--summary-json", getattr(args, "summary_json", None)),
        ("--manifest-json", getattr(args, "manifest_json", None)),
    )
    for label, raw_output in outputs:
        if not raw_output:
            continue
        output_path = Path(raw_output)
        for input_path in inputs:
            if paths_refer_to_same_file(output_path, input_path):
                return (
                    f"Refusing to overwrite an input: {label} resolves to the same file as "
                    f"{public_path(input_path)}."
                )
    return None


def validate_output_target(raw_path: str | None, label: str) -> None:
    if not raw_path:
        return
    path = Path(raw_path)
    if path.exists() and path.is_dir():
        raise ValueError(f"{label} must point to a file, not a directory.")
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise ValueError(f"{label} parent is not a directory: {parent}")


def validate_args(args):
    if args.preview_rows <= 0:
        raise ValueError("--preview-rows must be positive.")
    validate_output_target(args.output, "--output")
    validate_output_target(args.summary_json, "--summary-json")
    validate_output_target(args.manifest_json, "--manifest-json")


def clean_duckdb_message(message: str) -> str:
    cleaned = clean_known_stderr(message) or message
    table_match = re.search(r"Table with name ([A-Za-z0-9_]+) does not exist", cleaned)
    if table_match:
        cleaned += " Hint: DuckDB inputs are always exposed as source0, source1, source2, ..."
    if "syntax error" in cleaned.lower() and re.search(r"\bfrom\s+table\b", cleaned, flags=re.IGNORECASE):
        cleaned += " Hint: 'table' is a reserved word and not exposed as a stem alias; use source0."
    return cleaned


def emit_blocked(
    args,
    message: str,
    *,
    paths=None,
    bindings=None,
    aliases=None,
    write_summary: bool = True,
) -> int:
    # Defensive backstop: a blocked route must never serialize over an input,
    # even if a future caller forgets to run the main preflight first.
    if find_input_output_collision(args):
        write_summary = False
    summary_path = resolve_summary_path(args) if write_summary else None
    input_paths = list(paths) if paths is not None else [Path(item) for item in getattr(args, "inputs", [])]
    payload = standard_tool_payload(
        "duckdb_workbench",
        status="blocked",
        notes=[
            "DuckDB workbench did not run the requested query to completion.",
            "Use positional aliases source0, source1, source2, ... when stem-based aliases are ambiguous or absent.",
        ],
        artifacts={"summary_json": public_path(summary_path) if summary_path else None},
        results={
            "blocked_reason": message,
            "inputs": [public_path(path) for path in input_paths],
            "bindings": bindings or [],
            "aliases": aliases or {},
            "sql": getattr(args, "sql", None),
        },
        qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": 1}},
        inputs=input_paths,
        legacy={"blocked_reason": message},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if summary_path:
        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered, encoding="utf-8")
            print(f"Saved summary: {public_path(summary_path)}")
        except OSError:
            pass
    return 2


def effective_suffix(path):
    suffixes = [item.lower() for item in Path(path).suffixes]
    if not suffixes:
        return ""
    if suffixes[-1] in COMPRESSION_SUFFIXES and len(suffixes) >= 2:
        return suffixes[-2]
    return suffixes[-1]


def safe_alias(name):
    alias = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    if not alias:
        alias = "source"
    if alias[0].isdigit():
        alias = f"src_{alias}"
    return alias


def quote_identifier(alias: str) -> str:
    return '"' + alias.replace('"', '""') + '"'


def is_safe_named_alias(alias: str) -> bool:
    return bool(alias) and alias not in DUCKDB_RESERVED_ALIASES and not alias.startswith("source")


def json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, (str, int, bool)):
        return value
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
    try:
        if value != value:
            return None
    except Exception:
        pass
    return str(value)


def json_safe_records(records):
    return [{str(key): json_safe_value(value) for key, value in record.items()} for record in records]


def load_with_pandas(path):
    with suppress_fd_output(True):
        import pandas as pd

    warnings.filterwarnings("ignore", message=r"Pandas requires version '.*' or newer of 'numexpr'.*", category=Warning)
    warnings.filterwarnings("ignore", message=r"Pandas requires version '.*' or newer of 'bottleneck'.*", category=Warning)

    suffix = effective_suffix(path)
    if suffix in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
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
    return pd.read_csv(path, sep=None, engine="python")


def validate_delimited_rows(path: Path, delimiter: str) -> None:
    """Reject malformed or width-inconsistent rows before DuckDB can skip/recover them."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Delimited input is empty: {public_path(path)}") from exc
        expected_width = len(header)
        if expected_width == 0:
            raise ValueError(f"Delimited input has no columns: {public_path(path)}")
        for row_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(
                    f"Malformed delimited row {row_number}: expected {expected_width} fields, got {len(row)}."
                )


def register_source(connection, path, alias):
    path = Path(path)
    suffix = effective_suffix(path)
    resolved = str(path.resolve())
    public_resolved = public_path(path)
    sql_path = resolved.replace("'", "''")
    info = {"alias": alias, "path": public_resolved, "suffix": suffix, "backend": "duckdb"}
    if suffix == ".csv":
        validate_delimited_rows(path, ",")
        connection.execute(f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS SELECT * FROM read_csv_auto('{sql_path}', delim=',', ignore_errors=false)")
    elif suffix == ".tsv":
        validate_delimited_rows(path, "\t")
        connection.execute(f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS SELECT * FROM read_csv_auto('{sql_path}', delim='\t', ignore_errors=false)")
    elif suffix in {".json", ".jsonl", ".ndjson"}:
        connection.execute(f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS SELECT * FROM read_json_auto('{sql_path}')")
    elif suffix == ".parquet":
        connection.execute(f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS SELECT * FROM read_parquet('{sql_path}')")
    else:
        dataframe = load_with_pandas(path)
        connection.register(alias, dataframe)
        info["backend"] = "pandas"
        info["rows_loaded"] = int(len(dataframe))
    return info


def write_output(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = effective_suffix(path)
    if suffix == ".csv":
        frame.to_csv(path, index=False)
    elif suffix == ".json":
        path.write_text(frame.to_json(orient="records", indent=2) + "\n")
    elif suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {path.suffix}")


def apply_query_output_artifact_type(payload: dict, output_path: str | Path | None) -> dict:
    """Refine the generic `output` artifact using the concrete DuckDB format."""
    if not output_path:
        return payload
    artifact_type = {
        ".csv": "table_csv",
        ".json": "metadata_json",
    }.get(effective_suffix(output_path))
    if not artifact_type:
        return payload
    expected_path = public_path(output_path)
    for field in ("typed_artifacts", "outputs"):
        for item in payload.get(field, []) or []:
            if isinstance(item, dict) and item.get("path") == expected_path:
                item["artifact_type"] = artifact_type
    app_hints = payload.get("app_hints")
    if isinstance(app_hints, dict):
        app_hints["preview_artifact_types"] = sorted(
            {
                item.get("artifact_type")
                for item in payload.get("typed_artifacts", []) or []
                if isinstance(item, dict) and item.get("artifact_type")
            }
        )
    return payload


def main() -> int:
    args = parse_args()
    collision = find_input_output_collision(args)
    if collision:
        return emit_blocked(args, collision, write_summary=False)
    ensure_datanalysis_runtime("duckdb_workbench", strict=False)
    try:
        validate_args(args)
    except ValueError as exc:
        return emit_blocked(args, str(exc))
    try:
        import duckdb
    except ImportError as exc:
        return emit_blocked(
            args,
            "DuckDB is not installed. Install requirements-full.txt or add duckdb to the current environment "
            "if you want SQL over mixed files.",
        )

    paths = [Path(item) for item in args.inputs]
    for path in paths:
        if not path.exists():
            return emit_blocked(args, f"File not found: {path}", paths=paths)

    connection = duckdb.connect()
    bindings = []
    alias_map = {}
    for index, path in enumerate(paths):
        primary_alias = f"source{index}"
        try:
            info = register_source(connection, path, primary_alias)
        except Exception as exc:
            return emit_blocked(
                args,
                f"Could not register input {public_path(path)}: {clean_duckdb_message(str(exc))}",
                paths=paths,
                bindings=bindings,
                aliases=alias_map,
            )
        bindings.append(info)
        alias_map[primary_alias] = public_path(path)
        named_alias = safe_alias(path.stem)
        if named_alias not in alias_map and is_safe_named_alias(named_alias):
            connection.execute(f"CREATE OR REPLACE VIEW {quote_identifier(named_alias)} AS SELECT * FROM {quote_identifier(primary_alias)}")
            alias_map[named_alias] = public_path(path)

    sql = (args.sql or f"SELECT * FROM source0 LIMIT {args.preview_rows}").strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    try:
        result = connection.execute(sql).fetchdf()
        preview_records = json_safe_records(result.head(args.preview_rows).to_dict(orient="records"))
        result_count = int(connection.execute(f"SELECT COUNT(*) AS n FROM ({sql}) AS result_view").fetchone()[0])
    except Exception as exc:
        return emit_blocked(args, clean_duckdb_message(str(exc)), paths=paths, bindings=bindings, aliases=alias_map)

    result_summary = {
        "inputs": bindings,
        "aliases": alias_map,
        "sql": sql,
        "result_rows": result_count,
        "result_columns": list(result.columns),
        "preview": preview_records,
    }
    notes = [
        "DuckDB always exposes positional aliases source0, source1, source2, and so on.",
        "Additional stem-based aliases are best-effort conveniences and may not exist when they would collide.",
    ]

    print("DuckDB sources:")
    for binding in bindings:
        print(f"- {binding['alias']} ({binding['backend']}): {binding['path']}")
    print("Alias reminder: use source0, source1, source2, ... in SQL when in doubt.")
    print(f"SQL: {sql}")
    print(f"Rows: {result_count}")
    print("Preview:")
    for row in preview_records:
        print(json.dumps(row, ensure_ascii=True))

    outputs = []
    if args.output:
        try:
            write_output(result, args.output)
        except Exception as exc:
            return emit_blocked(args, str(exc), paths=paths, bindings=bindings, aliases=alias_map)
        outputs.append(public_path(args.output))
        print(f"Saved query output: {public_path(args.output)}")
    qa_findings = []
    if not args.output:
        qa_findings.append("Query result was returned as a preview only; pass --output to save a table artifact.")
    summary = standard_tool_payload(
        "duckdb_workbench",
        status="warning" if qa_findings else "ok",
        notes=notes,
        artifacts={
            "output": public_path(args.output) if args.output else None,
            "summary_json": public_path(args.summary_json) if args.summary_json else None,
            "manifest_json": public_path(args.manifest_json) if args.manifest_json else None,
        },
        results=result_summary,
        qa={
            "status": "warning" if qa_findings else "ok",
            "findings": qa_findings,
            "metrics": {"result_rows": result_count, "output_saved": bool(args.output)},
        },
        inputs=paths,
        legacy=result_summary,
    )
    apply_query_output_artifact_type(summary, args.output)
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
        outputs.append(public_path(args.summary_json))
        print(f"Saved summary: {public_path(args.summary_json)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=paths,
            outputs=outputs,
            parameters={"sql": sql, "aliases": alias_map},
            command="duckdb_workbench.py",
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
