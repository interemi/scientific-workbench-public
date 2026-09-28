#!/usr/bin/env python3
"""Profile and summarize mixed operational tabular datasets with optional SQL exploration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from _internal.path_safety import canonical_path, output_overlaps_input
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from _internal.run_bundle import (
    REQUIRED_DIRS,
    REQUIRED_FILES,
    add_run_bundle_argument,
    apply_run_bundle_defaults,
    finalize_existing_run_bundle,
)
from _internal.runtime_common import clean_known_stderr, configure_runtime


TABLE_EXTS = {
    ".csv",
    ".tsv",
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
    ".txt",
    ".dat",
}


def empty_sql_summary(executed=False, runtime=None, error=None):
    return {
        "executed": bool(executed),
        "success": False if error else None,
        "result_rows": None,
        "result_columns": [],
        "output": None,
        "runtime": runtime,
        "error": error,
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
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("inputs", nargs="+", help="Table files or directories containing operational datasets.")
    parser.add_argument("--sql", help="Optional DuckDB SQL query across all discovered files.")
    parser.add_argument("--query-output", help="Optional output file for SQL results (.csv, .json, .parquet).")
    parser.add_argument("--head", type=int, default=5, help="Preview rows per file for profiling.")
    parser.add_argument("--max-files", type=int, default=24, help="Maximum number of tabular files to include.")
    parser.add_argument("--output-dir", help="Directory for profiles, report, and optional query results.")
    parser.add_argument("--summary-json", help="Optional summary JSON.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    add_run_bundle_argument(parser)
    reject_unknown_long_option_assignments(parser)
    args = parser.parse_args()
    if not args.output_dir and not args.run_dir:
        parser.error("--output-dir is required unless --run-dir is supplied.")
    return args


def discover_tables(inputs: list[str], limit: int) -> list[Path]:
    found = []
    seen = set()
    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file():
            effective = path.suffix.lower()
            if effective in TABLE_EXTS:
                resolved = str(path.resolve())
                if resolved not in seen:
                    found.append(path.resolve())
                    seen.add(resolved)
            continue
        if not path.is_dir():
            continue
        for item in sorted(path.rglob("*")):
            if not item.is_file():
                continue
            if item.suffix.lower() not in TABLE_EXTS:
                continue
            resolved = str(item.resolve())
            if resolved in seen:
                continue
            found.append(item.resolve())
            seen.add(resolved)
            if len(found) >= limit:
                return found
    return found[:limit]


def output_path_overlaps_input(output_path: str | Path, inputs: list[str]) -> Path | None:
    for raw in inputs:
        if output_overlaps_input(output_path, raw):
            return canonical_path(raw)
    return None


def existing_owned_run_artifacts(run_dir: str | Path | None) -> list[Path]:
    if not run_dir:
        return []
    root = Path(run_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    collisions = [root / name for name in REQUIRED_FILES if (root / name).exists()]
    for name in REQUIRED_DIRS:
        candidate = root / name
        if not candidate.exists():
            continue
        if not candidate.is_dir():
            collisions.append(candidate)
            continue
        try:
            if any(candidate.iterdir()):
                collisions.append(candidate)
        except OSError:
            collisions.append(candidate)
    return sorted(set(collisions), key=lambda item: str(item))


def existing_owned_output_artifacts(output_dir: str | Path | None, query_output: str | Path | None = None) -> list[Path]:
    collisions = []
    if output_dir:
        root = Path(output_dir).expanduser()
        for name in ("inventory.csv", "report.md", "duckdb_summary.json", "query_result.csv"):
            candidate = root / name
            if candidate.exists():
                collisions.append(candidate)
        profiles = root / "profiles"
        if profiles.exists():
            try:
                if not profiles.is_dir() or any(profiles.iterdir()):
                    collisions.append(profiles)
            except OSError:
                collisions.append(profiles)
    if query_output and Path(query_output).expanduser().exists():
        collisions.append(Path(query_output).expanduser())
    return sorted(set(collisions), key=lambda item: str(item))


def unsupported_or_missing_inputs(inputs: list[str]) -> list[dict]:
    issues = []
    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            issues.append({"path": public_path(path), "reason": "missing"})
        elif path.is_file() and path.suffix.lower() not in TABLE_EXTS:
            issues.append({"path": public_path(path), "reason": f"unsupported_suffix:{path.suffix.lower() or '<none>'}"})
        elif not path.is_file() and not path.is_dir():
            issues.append({"path": public_path(path), "reason": "not_file_or_directory"})
    return issues


def run_json_command(cmd: list[str]) -> tuple[dict | None, dict]:
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    payload = None
    if completed.returncode == 0 and cmd:
        for item in reversed(cmd):
            if item.endswith(".json") and Path(item).exists():
                try:
                    payload = json.loads(Path(item).read_text(encoding="utf-8"))
                    break
                except Exception:
                    payload = None
    return payload, {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": clean_known_stderr(completed.stderr[-4000:]),
    }


def run_script_with_optional_datanalysis(script: Path, script_args: list[str]) -> tuple[dict | None, dict]:
    primary_cmd = [sys.executable, str(script), *script_args]
    payload, runtime = run_json_command(primary_cmd)
    datanalysis_wrapper = script.parent / "datanalysis_env.py"
    if runtime["returncode"] == 0 or not datanalysis_wrapper.exists():
        return payload, runtime
    fallback_cmd = [sys.executable, str(datanalysis_wrapper), "run-script", str(script), *script_args]
    fallback_payload, fallback_runtime = run_json_command(fallback_cmd)
    if fallback_runtime["returncode"] == 0:
        fallback_runtime["fallback_from"] = runtime
        return fallback_payload, fallback_runtime
    return payload, runtime


def summarize_profile(path: Path, profile: dict | None, runtime: dict) -> dict:
    if profile is None:
        return {
            "path": public_path(path),
            "name": path.name,
            "suffix": path.suffix.lower(),
            "profile_ok": False,
            "backend": None,
            "rows": None,
            "columns": None,
            "null_hotspots": [],
            "key_columns": [],
            "profile_status": "fail",
            "profile_findings": ["Profile command did not produce a readable payload."],
            "profile_quality_metrics": {},
            "runtime": runtime,
        }
    profile_qa = profile.get("qa") or {}
    null_hotspots = sorted(
        [
            {"name": item["name"], "nulls": item.get("nulls", 0), "dtype": item.get("dtype")}
            for item in profile.get("column_summaries", [])
        ],
        key=lambda entry: entry["nulls"],
        reverse=True,
    )[:5]
    key_columns = [item["name"] for item in profile.get("column_summaries", [])[:8]]
    return {
        "path": public_path(path),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "profile_ok": True,
        "backend": profile.get("backend"),
        "rows": profile.get("rows"),
        "columns": profile.get("columns"),
        "null_hotspots": null_hotspots,
        "key_columns": key_columns,
        "profile_status": profile.get("status"),
        "profile_findings": list(profile_qa.get("findings", [])),
        "profile_quality_metrics": dict(profile_qa.get("metrics", {})),
        "runtime": runtime,
    }


def write_inventory_csv(path: Path, rows: list[dict]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "suffix", "backend", "rows", "columns", "profile_ok", "path", "key_columns", "null_hotspots"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row["name"],
                    "suffix": row["suffix"],
                    "backend": row["backend"],
                    "rows": row["rows"],
                    "columns": row["columns"],
                    "profile_ok": row["profile_ok"],
                    "path": row["path"],
                    "key_columns": ",".join(row["key_columns"]),
                    "null_hotspots": "; ".join(f"{item['name']}({item['nulls']})" for item in row["null_hotspots"]),
                }
            )


def write_report(path: Path, summary: dict) -> None:
    lines = [
        "# Cross-Domain Data Workbench",
        "",
        f"- Files profiled: `{summary['file_count']}`",
        f"- Extensions seen: `{', '.join(summary['extensions_seen'])}`",
        f"- Total estimated rows: `{summary['total_rows']}`",
        f"- SQL executed: `{summary['sql']['executed']}`",
        "",
        "## Inventory",
        "",
    ]
    for item in summary["files"]:
        lines.extend(
            [
                f"- `{item['name']}` [{item['suffix']}] -> rows `{item['rows']}`, cols `{item['columns']}`, backend `{item['backend']}`",
                f"  key columns: `{', '.join(item['key_columns']) or 'none'}`",
            ]
        )
        if item["null_hotspots"]:
            lines.append(
                "  null hotspots: "
                + ", ".join(f"`{entry['name']}`={entry['nulls']}" for entry in item["null_hotspots"])
            )
        if item.get("profile_findings"):
            lines.append(
                "  profile warnings: "
                + "; ".join(f"`{finding}`" for finding in item["profile_findings"])
            )
    if summary["sql"]["executed"]:
        lines.extend(
            [
                "",
                "## SQL",
                "",
                f"- Query success: `{summary['sql'].get('success')}`",
                f"- Query rows: `{summary['sql']['result_rows']}`",
                f"- Query columns: `{', '.join(summary['sql']['result_columns'])}`",
                f"- Query output: `{summary['sql']['output']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This workflow is aimed at operations, business, education, QA, and general tabular analysis outside science-specific FITS work.",
            "- It reuses the same profiling and optional DuckDB stack as the rest of the skill, so portability stays aligned with the existing environment model.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_failure_payload(args, message, input_issues=None):
    return build_tool_payload(
        "cross_domain_data_workbench",
        status="fail",
        notes=["The workbench could not build a reliable bundle; inspect the error before using partial outputs."],
        artifacts={
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
            "output_dir": args.output_dir,
        },
        results={
            "error": message,
            "input_issues": input_issues or [],
            "sql": empty_sql_summary(),
        },
        qa={
            "status": "fail",
            "findings": [message],
            "metrics": {"file_count": 0, "total_rows": 0, "sql_executed": bool(args.sql)},
        },
        legacy={"error": message, "input_issues": input_issues or []},
    )


def emit_failure(args, message, input_issues=None):
    payload = build_failure_payload(args, message, input_issues=input_issues)
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        try:
            summary_path = Path(args.summary_json)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered, encoding="utf-8")
        except Exception as exc:
            print(f"Could not write failure summary: {clean_known_stderr(str(exc)) or exc}", file=sys.stderr)
    layout = getattr(args, "_run_bundle_layout", None)
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=2)
    print(message, file=sys.stderr)
    return 2


def emit_blocked(args, message, *, error_type: str | None = None):
    payload = build_tool_payload(
        "cross_domain_data_workbench",
        status="blocked",
        notes=[message, "No input tables were modified."],
        artifacts=(
            {}
            if error_type == "output_input_collision"
            else {"summary_json": None, "manifest_json": None, "output_dir": args.output_dir}
        ),
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "sql": empty_sql_summary(),
        },
        qa={"status": "blocked", "findings": [message], "metrics": {"file_count": 0, "blocking_count": 1}},
        legacy={"blocked_reason": message},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", end="")
    return 2


def main():
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    effective_output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else (run_dir / "artifacts" if run_dir else None)
    )
    requested_outputs: list[tuple[str, Path | str | None]] = [
        ("--output-dir", args.output_dir),
        ("--run-dir", run_dir),
        ("--query-output", args.query_output),
        ("--summary-json", args.summary_json or (run_dir / "summary.json" if run_dir else None)),
        ("--manifest-json", args.manifest_json or (run_dir / "manifest.json" if run_dir else None)),
    ]
    if effective_output_dir is not None:
        requested_outputs.extend(
            [
                ("derived:query_result.csv", effective_output_dir / "query_result.csv"),
                ("derived:duckdb_summary.json", effective_output_dir / "duckdb_summary.json"),
                ("derived:inventory.csv", effective_output_dir / "inventory.csv"),
                ("derived:report.md", effective_output_dir / "report.md"),
            ]
        )
    if run_dir is not None:
        requested_outputs.extend(
            (f"derived:{name}", run_dir / name)
            for name in ("stdout.txt", "stderr.txt", "command.txt", "next_steps.md")
        )
    for label, requested_path in requested_outputs:
        if not requested_path:
            continue
        overlapping_input = output_path_overlaps_input(requested_path, args.inputs)
        if overlapping_input is not None:
            args.summary_json = None
            args.manifest_json = None
            return emit_blocked(
                args,
                f"Refusing {label} because it overlaps input {public_path(overlapping_input)}; "
                "choose a separate derived-output location.",
                error_type="output_input_collision",
            )
    run_collisions = existing_owned_run_artifacts(args.run_dir)
    if run_collisions:
        return emit_blocked(
            args,
            "Refusing to reuse a run bundle that already contains owned artifacts: "
            + ", ".join(public_path(item) for item in run_collisions[:8])
            + ". Choose a new --run-dir.",
        )
    output_collisions = existing_owned_output_artifacts(args.output_dir, args.query_output)
    if output_collisions:
        return emit_blocked(
            args,
            "Refusing to overwrite existing workbench artifacts: "
            + ", ".join(public_path(item) for item in output_collisions[:8])
            + ". Choose a clean --output-dir/--query-output.",
        )
    layout = apply_run_bundle_defaults(args, output_attr="output_dir")
    configure_runtime("cross_domain_data_workbench")
    script_dir = Path(__file__).resolve().parent
    profile_script = script_dir / "profile_table.py"
    duckdb_script = script_dir / "duckdb_workbench.py"

    input_issues = unsupported_or_missing_inputs(args.inputs)
    table_paths = discover_tables(args.inputs, args.max_files)
    if not table_paths:
        return emit_failure(args, "No supported tabular files were found in the provided inputs.", input_issues=input_issues)

    output_dir = Path(args.output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        return emit_failure(args, f"Output path exists and is not a directory: {output_dir}", input_issues=input_issues)
    profiles_dir = output_dir / "profiles"
    try:
        profiles_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return emit_failure(args, f"Could not create output directory: {clean_known_stderr(str(exc)) or exc}", input_issues=input_issues)

    files = []
    outputs = []
    for index, path in enumerate(table_paths, start=1):
        summary_json = profiles_dir / f"{index:02d}_{path.stem}.json"
        payload, runtime = run_script_with_optional_datanalysis(
            profile_script,
            [
                str(path),
                "--head",
                str(args.head),
                "--summary-json",
                str(summary_json),
            ],
        )
        files.append(summarize_profile(path, payload, runtime))
        if summary_json.exists():
            outputs.append(summary_json)

    sql_summary = empty_sql_summary(executed=False)
    if args.sql:
        query_output = Path(args.query_output) if args.query_output else output_dir / "query_result.csv"
        query_summary = output_dir / "duckdb_summary.json"
        payload, runtime = run_script_with_optional_datanalysis(
            duckdb_script,
            [
                *[str(path) for path in table_paths],
                "--sql",
                args.sql,
                "--output",
                str(query_output),
                "--summary-json",
                str(query_summary),
            ],
        )
        sql_error = None
        if runtime.get("returncode") != 0:
            sql_error = clean_known_stderr(runtime.get("stderr") or runtime.get("stdout") or "SQL execution failed.")
        sql_summary = {
            "executed": True,
            "success": bool(payload is not None and runtime.get("returncode") == 0),
            "result_rows": None if payload is None else payload.get("result_rows"),
            "result_columns": [] if payload is None else payload.get("result_columns", []),
            "output": public_path(query_output) if query_output.exists() else None,
            "runtime": runtime,
            "error": sql_error,
        }
        if query_summary.exists():
            outputs.append(query_summary)
        if query_output.exists():
            outputs.append(query_output)

    extensions = Counter(item["suffix"] for item in files)
    total_rows = sum(item["rows"] or 0 for item in files if item["rows"] is not None)
    legacy_summary = {
        "tool": "cross_domain_data_workbench",
        "environment": environment_summary(),
        "file_count": len(files),
        "extensions_seen": sorted(extensions),
        "extension_counts": dict(extensions),
        "total_rows": int(total_rows),
        "files": files,
        "sql": sql_summary,
        "input_issues": input_issues,
        "notes": [
            "This workflow is science-adjacent rather than science-only: it targets mixed operational tables, spreadsheets, JSONL feeds, and columnar datasets.",
            "DuckDB remains optional; if no SQL is supplied, the workflow stays lightweight and profile-first.",
        ],
    }
    inventory_csv = output_dir / "inventory.csv"
    report_md = output_dir / "report.md"
    write_inventory_csv(inventory_csv, files)
    write_report(report_md, legacy_summary)
    outputs.extend([inventory_csv, report_md])
    qa_findings = []
    if any(not item["profile_ok"] for item in files):
        qa_findings.append("At least one discovered table could not be profiled successfully.")
    for item in files:
        for finding in item.get("profile_findings", []):
            qa_findings.append(f"Profile warning in {item['name']}: {finding}")
    if input_issues:
        qa_findings.append("Some requested inputs were missing or unsupported and were not included in the bundle.")
    if args.sql and not sql_summary.get("success"):
        qa_findings.append("The requested SQL pass did not complete successfully; inspect results.sql.runtime.")
    payload = build_tool_payload(
        "cross_domain_data_workbench",
        status="warning" if qa_findings else "ok",
        notes=legacy_summary["notes"],
        artifacts={
            "inventory_csv": inventory_csv,
            "report_md": report_md,
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
        },
        results=legacy_summary,
        qa={
            "status": "warning" if qa_findings else "ok",
            "findings": qa_findings,
            "metrics": {"file_count": len(files), "total_rows": int(total_rows), "sql_executed": bool(args.sql)},
        },
        legacy=legacy_summary,
    )

    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
        outputs.append(summary_path)

    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=table_paths,
            outputs=outputs,
            parameters={
                "sql": args.sql,
                "max_files": args.max_files,
                "head": args.head,
            },
            command="cross_domain_data_workbench.py",
            notes=legacy_summary["notes"],
            extra={"summary": legacy_summary},
        )
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=0)


if __name__ == "__main__":
    raise SystemExit(main())
