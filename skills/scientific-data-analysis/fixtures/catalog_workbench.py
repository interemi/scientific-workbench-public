#!/usr/bin/env python3
"""Perform TopCat-like filtering, joins, and sky cross-matches on tabular data."""

import argparse
import json
import math
import sys
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.tabular_io import read_table_any, write_table_any


def load_dependencies():
    import numpy as np
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.table import Table, join

    return np, u, SkyCoord, Table, join


def read_table(Table, path):
    return read_table_any(Table, path)


def write_table(table, path):
    write_table_any(table, path)


def numeric_degree_column(np, table, name, *, role):
    if name not in table.colnames:
        available = ", ".join(str(item) for item in table.colnames[:12])
        if len(table.colnames) > 12:
            available += ", ..."
        raise ValueError(f"{role} coordinate column '{name}' was not found. Available columns: {available or '(none)'}.")
    column = table[name]
    if hasattr(column, "filled"):
        column = column.filled(np.nan)
    try:
        values = np.asarray(column, dtype=float)
    except Exception as exc:
        raise ValueError(f"{role} coordinate column '{name}' could not be coerced to numeric degree values.") from exc
    if values.ndim != 1:
        values = values.reshape(-1)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{role} coordinate column '{name}' contains non-finite values and cannot be used as sky coordinates.")
    return values


def validate_coordinate_ranges(np, ra_values, dec_values, *, role):
    findings = []
    if np.any((ra_values < 0.0) | (ra_values >= 360.0)):
        findings.append(f"{role} RA values must be in [0, 360) degrees.")
    if np.any((dec_values < -90.0) | (dec_values > 90.0)):
        findings.append(f"{role} Dec values must be in [-90, 90] degrees.")
    if findings:
        raise ValueError(" ".join(findings))


def validate_output_parent(path, *, label):
    parent = Path(path).expanduser().parent
    if parent.exists() and not parent.is_dir():
        return f"{label} parent is not a directory: {parent}"
    return None


def crossmatch_artifacts(args, *, output_written=False):
    return {
        "summary_json": args.summary_json,
        "output_table": args.output if output_written else None,
        "manifest_json": args.manifest_json,
    }


def emit_crossmatch_payload(args, *, status, notes, results, findings=None, metrics=None, output_written=False):
    qa_status = "ok" if status == "ok" else status
    payload = build_tool_payload(
        "catalog_workbench.crossmatch-sky",
        status=status,
        notes=notes,
        artifacts=crossmatch_artifacts(args, output_written=output_written),
        results=results,
        qa={"status": qa_status, "findings": findings or [], "metrics": metrics or {}},
        legacy=results,
    )
    if args.summary_json:
        emit_payload(payload, args.summary_json)
    else:
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
        print(rendered)
    return payload


def block_crossmatch(args, message, *, status="blocked", results=None, metrics=None):
    print(message, file=sys.stderr)
    emit_crossmatch_payload(
        args,
        status=status,
        notes=["Sky cross-match did not run to completion because the input contract was not satisfied."],
        results={
            "operation": "crossmatch-sky",
            "left": public_path(args.left),
            "right": public_path(args.right),
            "output": public_path(args.output),
            "radius_arcsec": args.radius_arcsec,
            "message": message,
            **(results or {}),
        },
        findings=[message],
        metrics=metrics or {},
        output_written=False,
    )
    return 2


def cmd_filter(args):
    _, _, _, Table, _ = load_dependencies()
    table = read_table(Table, args.input)
    expr = args.expression
    namespace = {name: table[name] for name in table.colnames}
    mask = eval(expr, {"__builtins__": {}}, namespace)
    result = table[mask]
    print(f"Rows before: {len(table)}")
    print(f"Rows after: {len(result)}")
    write_table(result, args.output)
    summary = {
        "operation": "filter",
        "input": public_path(args.input),
        "output": public_path(args.output),
        "rows_before": int(len(table)),
        "rows_after": int(len(result)),
        "expression": expr,
    }
    if args.summary_json:
        payload = build_tool_payload(
            "catalog_workbench.filter",
            status="ok",
            notes=["This filter uses a Python-like boolean expression over column names."],
            artifacts={"summary_json": args.summary_json, "output_table": args.output, "manifest_json": args.manifest_json},
            results=summary,
            qa={"status": "ok", "findings": [], "metrics": {"rows_after": int(len(result))}},
            legacy=summary,
        )
        emit_payload(payload, args.summary_json)
    if args.manifest_json:
        write_manifest(args.manifest_json, inputs=[args.input], outputs=[args.output, args.summary_json] if args.summary_json else [args.output], parameters={"operation": "filter", "expression": expr}, command="catalog_workbench.py filter")
    print(f"Saved filtered table: {Path(args.output).resolve()}")


def cmd_join_key(args):
    _, _, _, Table, join = load_dependencies()
    left = read_table(Table, args.left)
    right = read_table(Table, args.right)
    if args.left_key != args.right_key:
        right = right.copy()
        right.rename_column(args.right_key, args.left_key)
    result = join(left, right, keys=args.left_key, join_type=args.how, table_names=["left", "right"], uniq_col_name="{table_name}_{col_name}")
    print(f"Output rows: {len(result)}")
    write_table(result, args.output)
    summary = {
        "operation": "join-key",
        "left": public_path(args.left),
        "right": public_path(args.right),
        "output": public_path(args.output),
        "rows_output": int(len(result)),
        "left_key": args.left_key,
        "right_key": args.right_key,
        "join_type": args.how,
    }
    if args.summary_json:
        payload = build_tool_payload(
            "catalog_workbench.join-key",
            status="ok",
            notes=["This join reuses the shared tabular readers so FITS tables and common flat formats can be combined with the same CLI."],
            artifacts={"summary_json": args.summary_json, "output_table": args.output, "manifest_json": args.manifest_json},
            results=summary,
            qa={"status": "ok", "findings": [], "metrics": {"rows_output": int(len(result))}},
            legacy=summary,
        )
        emit_payload(payload, args.summary_json)
    if args.manifest_json:
        write_manifest(args.manifest_json, inputs=[args.left, args.right], outputs=[args.output, args.summary_json] if args.summary_json else [args.output], parameters={"operation": "join-key", "left_key": args.left_key, "right_key": args.right_key, "join_type": args.how}, command="catalog_workbench.py join-key")
    print(f"Saved join: {Path(args.output).resolve()}")


def cmd_crossmatch_sky(args):
    path_issues = []
    for label, value in [("output", args.output), ("summary-json", args.summary_json), ("manifest-json", args.manifest_json)]:
        if not value:
            continue
        issue = validate_output_parent(value, label=label)
        if issue:
            path_issues.append(issue)
    if path_issues:
        return block_crossmatch(args, " ".join(path_issues), status="fail")

    try:
        radius_arcsec = float(args.radius_arcsec)
    except (TypeError, ValueError):
        return block_crossmatch(args, f"Search radius must be a numeric arcsec value, got {args.radius_arcsec!r}.")
    if not math.isfinite(radius_arcsec) or radius_arcsec <= 0:
        return block_crossmatch(args, f"Search radius must be finite and positive, got {args.radius_arcsec!r}.")

    try:
        np, u, SkyCoord, Table, _ = load_dependencies()
    except Exception as exc:
        return block_crossmatch(args, f"Required astronomy dependencies are unavailable: {exc}")

    try:
        left = read_table(Table, args.left)
        right = read_table(Table, args.right)
    except Exception as exc:
        return block_crossmatch(args, f"Could not read input tables: {exc}")
    if len(left) == 0 or len(right) == 0:
        return block_crossmatch(args, f"Both input tables need at least one row; got left={len(left)}, right={len(right)}.")

    try:
        left_ra = numeric_degree_column(np, left, args.left_ra, role="left RA")
        left_dec = numeric_degree_column(np, left, args.left_dec, role="left Dec")
        right_ra = numeric_degree_column(np, right, args.right_ra, role="right RA")
        right_dec = numeric_degree_column(np, right, args.right_dec, role="right Dec")
        validate_coordinate_ranges(np, left_ra, left_dec, role="left")
        validate_coordinate_ranges(np, right_ra, right_dec, role="right")
    except ValueError as exc:
        return block_crossmatch(
            args,
            str(exc),
            metrics={"left_rows": int(len(left)), "right_rows": int(len(right))},
        )

    c1 = SkyCoord(ra=left_ra * u.deg, dec=left_dec * u.deg)
    c2 = SkyCoord(ra=right_ra * u.deg, dec=right_dec * u.deg)
    idx, sep2d, _ = c1.match_to_catalog_sky(c2)
    mask = sep2d <= radius_arcsec * u.arcsec
    matched_left = left[mask]
    matched_right = right[idx[mask]]
    matched = matched_left.copy()
    for name in matched_right.colnames:
        new_name = name if name not in matched.colnames else f"right_{name}"
        matched[new_name] = matched_right[name]
    matched["match_sep_arcsec"] = sep2d[mask].to_value(u.arcsec)
    print(f"Matched rows: {len(matched)}")
    try:
        write_table(matched, args.output)
    except Exception as exc:
        return block_crossmatch(args, f"Could not write cross-match output: {exc}", status="fail")

    sep_arcsec = sep2d[mask].to_value(u.arcsec)
    matched_rows = int(len(matched))
    warning_findings = []
    if matched_rows == 0:
        warning_findings.append("No rows matched within the requested sky radius; output table is intentionally empty.")
    if radius_arcsec > 3600:
        warning_findings.append("Search radius is larger than 1 degree; verify this was intentional.")
    if matched_rows:
        right_indices = idx[mask]
        if len(set(int(item) for item in right_indices)) < matched_rows:
            warning_findings.append("Multiple left rows matched the same nearest right-row candidate.")
    status = "warning" if warning_findings else "ok"
    summary = {
        "operation": "crossmatch-sky",
        "left": public_path(args.left),
        "right": public_path(args.right),
        "output": public_path(args.output),
        "left_rows": int(len(left)),
        "right_rows": int(len(right)),
        "matched_rows": matched_rows,
        "unmatched_left_rows": int(len(left) - matched_rows),
        "radius_arcsec": radius_arcsec,
        "left_ra": args.left_ra,
        "left_dec": args.left_dec,
        "right_ra": args.right_ra,
        "right_dec": args.right_dec,
    }
    metrics = {
        "left_rows": int(len(left)),
        "right_rows": int(len(right)),
        "matched_rows": matched_rows,
        "radius_arcsec": radius_arcsec,
    }
    if matched_rows:
        metrics["median_sep_arcsec"] = float(np.median(sep_arcsec))
        metrics["max_sep_arcsec"] = float(np.max(sep_arcsec))
    emit_crossmatch_payload(
        args,
        status=status,
        notes=["This cross-match uses nearest-neighbour sky matching with a single radius cut, similar to a compact TOPCAT-style pass."],
        results=summary,
        findings=warning_findings,
        metrics=metrics,
        output_written=True,
    )
    if args.manifest_json:
        write_manifest(args.manifest_json, inputs=[args.left, args.right], outputs=[args.output, args.summary_json] if args.summary_json else [args.output], parameters={"operation": "crossmatch-sky", "radius_arcsec": radius_arcsec}, command="catalog_workbench.py crossmatch-sky")
    print(f"Saved sky cross-match: {Path(args.output).resolve()}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--summary-json", help="Optional summary JSON using the standard top-level envelope.")
    common.add_argument("--manifest-json", help="Optional provenance manifest path.")

    p_filter = subparsers.add_parser("filter", parents=[common], help="Filter a table with a Python-like boolean expression.")
    p_filter.add_argument("input")
    p_filter.add_argument("output")
    p_filter.add_argument("--expression", required=True, help="Example: (flux > 10) & (flag == 0)")
    p_filter.set_defaults(func=cmd_filter)

    p_join = subparsers.add_parser("join-key", parents=[common], help="Join two tables by key.")
    p_join.add_argument("left")
    p_join.add_argument("right")
    p_join.add_argument("output")
    p_join.add_argument("--left-key", required=True)
    p_join.add_argument("--right-key", required=True)
    p_join.add_argument("--how", default="inner", choices=["inner", "left", "right", "outer"])
    p_join.set_defaults(func=cmd_join_key)

    p_cross = subparsers.add_parser("crossmatch-sky", parents=[common], help="Cross-match two catalogs on the sky.")
    p_cross.add_argument("left")
    p_cross.add_argument("right")
    p_cross.add_argument("output")
    p_cross.add_argument("--left-ra", required=True)
    p_cross.add_argument("--left-dec", required=True)
    p_cross.add_argument("--right-ra", required=True)
    p_cross.add_argument("--right-dec", required=True)
    p_cross.add_argument("--radius-arcsec", type=float, default=1.0)
    p_cross.set_defaults(func=cmd_crossmatch_sky)

    return parser


def emit_collision_only(args, collisions: list[dict[str, str]]) -> int:
    message = "Refusing catalog outputs that overlap protected input tables."
    payload = build_tool_payload(
        f"catalog_workbench.{args.command}",
        status="blocked",
        notes=[message, "No output table, summary, or manifest was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "operation": args.command,
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


def preflight_output_safety(args) -> int | None:
    if args.command == "filter":
        inputs = [("input", args.input)]
    else:
        inputs = [("left", args.left), ("right", args.right)]
    outputs = [
        ("output", args.output),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
    ]
    collisions = find_output_input_collisions(inputs, outputs)
    return emit_collision_only(args, collisions) if collisions else None


def main():
    parser = build_parser()
    args = parser.parse_args()
    collision_status = preflight_output_safety(args)
    if collision_status is not None:
        return collision_status
    result = args.func(args)
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
