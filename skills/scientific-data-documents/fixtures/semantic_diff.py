#!/usr/bin/env python3
"""Compare tables or documents semantically and summarize the differences."""

import argparse
import csv
import difflib
import json
import math
import sys
from pathlib import Path

from _internal.path_safety import paths_alias
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload
from document_semantics import detect_and_extract
from _internal.provenance_utils import write_manifest
from _internal.tabular_io import read_table_any


TABLE_SUFFIXES = {
    ".csv",
    ".tsv",
    ".ecsv",
    ".tbl",
    ".dat",
    ".json",
    ".jsonl",
    ".ndjson",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".xlsb",
    ".ods",
    ".parquet",
    ".feather",
    ".arrow",
    ".ipc",
    ".fits",
    ".fit",
    ".fts",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", help="Baseline file.")
    parser.add_argument("candidate", help="Candidate file.")
    parser.add_argument("--summary-json", help="Optional summary JSON using the standard top-level envelope.")
    parser.add_argument("--output-json", help="Optional JSON output path.")
    parser.add_argument("--output-md", help="Optional Markdown output path.")
    parser.add_argument("--manifest-json", help="Optional manifest output path.")
    return parser.parse_args()


def table_like(path):
    return Path(path).suffix.lower() in TABLE_SUFFIXES


def effective_suffix(path):
    suffixes = [suffix.lower() for suffix in Path(path).suffixes]
    if not suffixes:
        return ""
    if suffixes[-1] in {".gz", ".bz2", ".xz"} and len(suffixes) >= 2:
        return suffixes[-2]
    return suffixes[-1]


def normalize_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    return str(value)


def rows_from_astropy_table(table):
    names = list(table.colnames)
    rows = []
    for row in table:
        rows.append({name: normalize_value(row[name]) for name in names})
    return names, rows, "astropy"


def table_from_records(records):
    names = []
    seen = set()
    rows = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Expected record-style objects for JSON table comparison.")
        for key in record:
            rendered_key = str(key)
            if rendered_key not in seen:
                names.append(rendered_key)
                seen.add(rendered_key)
        rows.append({str(key): normalize_value(value) for key, value in record.items()})
    return names, rows


def read_delimited_table(path, delimiter):
    with Path(path).open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("Delimited table has no header row.")
        names = [name if name is not None else "" for name in reader.fieldnames]
        if any(not name.strip() for name in names):
            raise ValueError("Delimited table has empty column names.")
        rows = []
        for row in reader:
            rows.append({name: normalize_value(row.get(name)) for name in names})
    return names, rows, "csv"


def read_json_records(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    if isinstance(payload, list):
        names, rows = table_from_records(payload)
        return names, rows, "json"
    if isinstance(payload, dict):
        for key in ("data", "rows", "records", "items", "table"):
            value = payload.get(key)
            if isinstance(value, list):
                names, rows = table_from_records(value)
                return names, rows, "json"
        if payload and all(isinstance(value, list) for value in payload.values()):
            names = [str(key) for key in payload]
            row_count = max((len(value) for value in payload.values()), default=0)
            rows = []
            for index in range(row_count):
                rows.append(
                    {
                        name: normalize_value(payload[name][index] if index < len(payload[name]) else None)
                        for name in names
                    }
                )
            return names, rows, "json"
    raise ValueError("Unsupported JSON table layout.")


def read_jsonl_records(path):
    records = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line:
            records.append(json.loads(line))
    names, rows = table_from_records(records)
    return names, rows, "jsonl"


def read_table_portable(path):
    suffix = effective_suffix(path)
    if suffix == ".csv":
        return read_delimited_table(path, ",")
    if suffix in {".tsv", ".tab"}:
        return read_delimited_table(path, "\t")
    if suffix == ".json":
        return read_json_records(path)
    if suffix in {".jsonl", ".ndjson"}:
        return read_jsonl_records(path)
    if suffix in {".xlsx", ".xlsm", ".xls", ".xlsb", ".ods", ".parquet", ".feather", ".arrow", ".ipc"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(f"Reading {suffix} tables requires pandas or astropy.") from exc
        if suffix in {".xlsx", ".xlsm", ".xls", ".ods"}:
            frame = pd.read_excel(path)
        elif suffix == ".xlsb":
            frame = pd.read_excel(path, engine="pyxlsb")
        elif suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_feather(path)
        names = [str(name) for name in frame.columns]
        rows = [
            {name: normalize_value(value) for name, value in row.items()}
            for row in frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
        ]
        return names, rows, "pandas"
    raise RuntimeError(
        f"Portable table comparison for '{suffix or '<no suffix>'}' requires astropy or a CSV/TSV/JSON/Pandas-readable table."
    )


def read_table_records(path):
    try:
        from astropy.table import Table
    except ImportError:
        return read_table_portable(path)
    table = read_table_any(Table, path)
    return rows_from_astropy_table(table)


def compare_tables(baseline, candidate):
    left_names, left_rows, left_backend = read_table_records(baseline)
    right_names, right_rows, right_backend = read_table_records(candidate)
    common = [name for name in left_names if name in right_names]
    changes = []
    change_count = 0
    max_reported_changes = 1000
    if common:
        for row_index in range(min(len(left_rows), len(right_rows))):
            for name in common:
                left_value = left_rows[row_index].get(name)
                right_value = right_rows[row_index].get(name)
                if left_value != right_value:
                    change_count += 1
                    if len(changes) < max_reported_changes:
                        changes.append(
                            {
                                "row": row_index,
                                "column": name,
                                "baseline": str(left_value),
                                "candidate": str(right_value),
                            }
                        )
    warnings = []
    if len(left_rows) != len(right_rows):
        warnings.append(f"Row count changed from {len(left_rows)} to {len(right_rows)}.")
    if not common:
        warnings.append("No common columns were found; cell-level comparison was skipped.")
    if change_count > len(changes):
        warnings.append(
            f"All cells were compared, but only the first {len(changes)} of {change_count} changes are included in the report."
        )
    return {
        "comparison_type": "table",
        "baseline_rows": int(len(left_rows)),
        "candidate_rows": int(len(right_rows)),
        "baseline_columns": left_names,
        "candidate_columns": right_names,
        "columns_added": [name for name in right_names if name not in left_names],
        "columns_removed": [name for name in left_names if name not in right_names],
        "cell_changes": changes,
        "cell_change_count": change_count,
        "reported_cell_change_count": len(changes),
        "comparison_complete": True,
        "inspected_rows": int(min(len(left_rows), len(right_rows))),
        "inspected_columns": common,
        "reader_backends": {"baseline": left_backend, "candidate": right_backend},
        "warnings": warnings,
    }


def compare_documents(baseline, candidate):
    left = detect_and_extract(Path(baseline), 12000)
    right = detect_and_extract(Path(candidate), 12000)
    left_text = (left.get("text_excerpt") or "").splitlines()
    right_text = (right.get("text_excerpt") or "").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            left_text,
            right_text,
            fromfile=Path(baseline).name,
            tofile=Path(candidate).name,
            lineterm="",
        )
    )
    metadata_keys = ["method", "package_type", "pages", "slide_count", "sheet_count", "member_count"]
    metadata_diff = {}
    for key in metadata_keys:
        if left.get(key) != right.get(key):
            metadata_diff[key] = {"baseline": left.get(key), "candidate": right.get(key)}
    return {
        "comparison_type": "document",
        "metadata_diff": metadata_diff,
        "diff_excerpt": diff_lines[:120],
        "baseline_excerpt": left.get("text_excerpt", "")[:1000],
        "candidate_excerpt": right.get("text_excerpt", "")[:1000],
    }


def write_markdown(path, summary):
    lines = ["# Semantic Diff", ""]
    lines.append(f"- Type: `{summary['comparison_type']}`")
    if summary["comparison_type"] == "table":
        lines.append(f"- Rows: `{summary['baseline_rows']}` -> `{summary['candidate_rows']}`")
        lines.append(f"- Columns added: `{', '.join(summary['columns_added']) or 'none'}`")
        lines.append(f"- Columns removed: `{', '.join(summary['columns_removed']) or 'none'}`")
        if summary["cell_changes"]:
            lines.extend(["", "## Sample cell changes"])
            for item in summary["cell_changes"][:20]:
                lines.append(
                    f"- row {item['row']} col `{item['column']}`: `{item['baseline']}` -> `{item['candidate']}`"
                )
    else:
        lines.extend(["", "## Metadata differences"])
        for key, value in summary["metadata_diff"].items():
            lines.append(f"- `{key}`: `{value['baseline']}` -> `{value['candidate']}`")
        if summary["diff_excerpt"]:
            lines.extend(["", "## Text diff excerpt", "```diff"])
            lines.extend(summary["diff_excerpt"][:80])
            lines.append("```")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")


def write_json_payload(path, payload):
    output_path = Path(path)
    if output_path.exists() and output_path.is_dir():
        raise IsADirectoryError(f"JSON output points to a directory: {public_path(output_path)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    output_path.write_text(rendered, encoding="utf-8")


def build_failure_payload(args, message):
    summary_json_path = Path(args.summary_json) if args.summary_json else None
    return build_tool_payload(
        "semantic_diff",
        status="fail",
        notes=["semantic_diff could not complete; inspect the error before using any partial outputs."],
        artifacts={
            "summary_json": str(summary_json_path) if summary_json_path else None,
            "diff_json": args.output_json,
            "report_md": args.output_md,
            "manifest_json": args.manifest_json,
        },
        results={"error": message},
        qa={
            "status": "fail",
            "findings": [message],
            "metrics": {"comparison_type": "unknown"},
        },
        legacy={"comparison_type": "error", "error": message},
    )


def canonical_path(pathlike) -> Path:
    return Path(pathlike).expanduser().resolve(strict=False)


def input_output_collisions(args, baseline: Path, candidate: Path) -> list[dict[str, str]]:
    inputs = {
        "baseline": canonical_path(baseline),
        "candidate": canonical_path(candidate),
    }
    collisions = []
    requested_outputs = [
        ("--output-json", args.output_json),
        ("--summary-json", args.summary_json),
        ("--output-md", args.output_md),
        ("--manifest-json", args.manifest_json),
    ]
    for flag, pathlike in requested_outputs:
        if not pathlike:
            continue
        resolved_output = canonical_path(pathlike)
        for input_label, resolved_input in inputs.items():
            if paths_alias(pathlike, resolved_input):
                collisions.append(
                    {
                        "flag": flag,
                        "input": input_label,
                        "path": public_path(resolved_input),
                    }
                )
    active_outputs = [(flag, pathlike) for flag, pathlike in requested_outputs if pathlike]
    for index, (left_flag, left_path) in enumerate(active_outputs):
        for right_flag, right_path in active_outputs[index + 1 :]:
            if paths_alias(left_path, right_path):
                collisions.append(
                    {
                        "flag": left_flag,
                        "input": right_flag,
                        "path": public_path(canonical_path(left_path)),
                        "collision_kind": "output_output_alias",
                    }
                )
    return collisions


def emit_input_collision_only(args, baseline: Path, candidate: Path, collisions: list[dict[str, str]]) -> int:
    rendered = ", ".join(f"{item['flag']}={item['input']}" for item in collisions)
    message = f"Refusing output paths that resolve to semantic-diff inputs: {rendered}."
    payload = build_tool_payload(
        "semantic_diff",
        status="blocked",
        notes=[message, "No output files were written."],
        artifacts={
            "summary_json": None,
            "diff_json": None,
            "report_md": None,
            "manifest_json": None,
        },
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"comparison_type": "blocked", "error": message},
        inputs=[baseline, candidate],
    )
    emit_payload(payload, None)
    return 2


def emit_failure(args, message):
    payload = build_failure_payload(args, message)
    summary_json_path = Path(args.summary_json) if args.summary_json else None
    try:
        emit_payload(payload, summary_json_path)
    except Exception as exc:
        print(json.dumps(payload, indent=2, ensure_ascii=True), file=sys.stdout)
        print(f"Could not write failure payload: {exc}", file=sys.stderr)
    if args.output_json:
        output_json_path = Path(args.output_json)
        if summary_json_path is None or output_json_path.resolve(strict=False) != summary_json_path.resolve(strict=False):
            try:
                write_json_payload(output_json_path, payload)
            except Exception as exc:
                print(f"Could not write --output-json failure payload: {exc}", file=sys.stderr)
    print(message, file=sys.stderr)
    return 2


def main():
    args = parse_args()
    baseline = Path(args.baseline)
    candidate = Path(args.candidate)
    collisions = input_output_collisions(args, baseline, candidate)
    if collisions:
        return emit_input_collision_only(args, baseline, candidate, collisions)
    try:
        if not baseline.exists():
            raise FileNotFoundError(f"File not found: {baseline}")
        if not candidate.exists():
            raise FileNotFoundError(f"File not found: {candidate}")
        if baseline.is_dir() or candidate.is_dir():
            raise IsADirectoryError("semantic_diff expects two files, not directories.")

        baseline_table = table_like(baseline)
        candidate_table = table_like(candidate)
        if baseline_table and candidate_table:
            summary = compare_tables(baseline, candidate)
        elif baseline_table != candidate_table:
            raise ValueError("Input types differ: compare two table-like files or two document-like files.")
        else:
            summary = compare_documents(baseline, candidate)
    except Exception as exc:
        return emit_failure(args, str(exc))

    summary_json_path = Path(args.summary_json) if args.summary_json else None
    notes = [
        "Use this diff as a semantic QA pass before handoff, not as a substitute for domain-specific validation.",
    ]
    findings = []
    if summary["comparison_type"] == "table":
        findings.extend(summary.get("warnings", []))
    if summary["comparison_type"] == "table" and not summary.get("cell_changes") and not summary.get("columns_added") and not summary.get("columns_removed"):
        notes.append("No cell differences were detected in the complete common-row/common-column comparison.")
    if summary["comparison_type"] == "document" and not summary.get("metadata_diff") and not summary.get("diff_excerpt"):
        findings.append("No visible semantic differences were detected in the extracted excerpt.")
    payload = build_tool_payload(
        "semantic_diff",
        status="warning" if findings else "ok",
        notes=notes,
        artifacts={
            "summary_json": str(summary_json_path) if summary_json_path else None,
            "diff_json": args.output_json,
            "report_md": args.output_md,
            "manifest_json": args.manifest_json,
        },
        results=summary,
        qa={
            "status": "warning" if findings else "ok",
            "findings": findings,
            "metrics": {
                "comparison_type": summary["comparison_type"],
                "cell_change_count": summary.get("cell_change_count", len(summary.get("cell_changes", []))),
                "metadata_diff_count": len(summary.get("metadata_diff", {})),
                "warning_count": len(summary.get("warnings", [])),
            },
        },
        legacy=summary,
    )
    print(json.dumps(sanitize_payload(summary), indent=2, ensure_ascii=True, allow_nan=False))
    outputs = []
    if args.output_json:
        try:
            write_json_payload(args.output_json, payload)
        except Exception as exc:
            return emit_failure(args, f"Could not write --output-json: {exc}")
        outputs.append(str(Path(args.output_json).resolve()))
        print(f"Saved JSON diff: {public_path(args.output_json)}")
    if summary_json_path:
        try:
            emit_payload(payload, summary_json_path)
        except Exception as exc:
            return emit_failure(args, f"Could not write --summary-json: {exc}")
        outputs.append(str(Path(summary_json_path).resolve()))
        print(f"Saved summary: {public_path(summary_json_path)}")
    if args.output_md:
        write_markdown(args.output_md, summary)
        outputs.append(str(Path(args.output_md).resolve()))
        print(f"Saved Markdown diff: {Path(args.output_md).resolve()}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[baseline, candidate],
            outputs=outputs,
            parameters={"comparison_type": summary["comparison_type"]},
            command="semantic_diff.py",
        )
        print(f"Saved manifest: {Path(args.manifest_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
