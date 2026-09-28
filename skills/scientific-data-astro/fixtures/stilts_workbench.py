#!/usr/bin/env python3
"""Run reproducible STILTS catalog operations through a small public wrapper."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import public_path, standard_qa_payload, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.runtime_common import clean_known_stderr
from external_astro_tools_preflight import command_display, resolve_stilts_command


def tail(text: str, limit: int = 3000) -> str:
    return (text or "")[-limit:]


def ensure_parent(path: str | Path | None) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def path_signature(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {
        "exists": True,
        "is_file": path.is_file(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def validate_output_targets(outputs: list[Path]) -> str | None:
    for output in outputs:
        if output.exists() and output.is_dir():
            return f"Output path is a directory, not a file target: {output}"
        parent = output.parent
        if parent.exists() and not parent.is_dir():
            return f"Output parent exists and is not a directory: {parent}"
    return None


def validate_optional_artifact_path(path: str | Path | None, label: str, *, directory: bool = False) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if directory:
        if candidate.exists() and not candidate.is_dir():
            return f"{label} exists and is not a directory: {candidate}"
        parent = candidate.parent
    else:
        if candidate.exists() and candidate.is_dir():
            return f"{label} exists and is a directory, not a file target: {candidate}"
        parent = candidate.parent
    if parent.exists() and not parent.is_dir():
        return f"{label} parent exists and is not a directory: {parent}"
    return None


def write_log_bundle(log_dir: str | Path | None, command: list[str], stdout: str, stderr: str) -> dict:
    if not log_dir:
        return {}
    root = Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    command_path = root / "stilts_command.sh"
    stdout_path = root / "stilts_stdout.txt"
    stderr_path = root / "stilts_stderr.txt"
    command_path.write_text(shlex.join(command) + "\n", encoding="utf-8")
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {
        "command_sh": command_path,
        "stdout_log": stdout_path,
        "stderr_log": stderr_path,
    }


def resolved_stilts(args: argparse.Namespace) -> dict:
    return resolve_stilts_command(
        stilts_command=getattr(args, "stilts_command", None),
        stilts_jar=getattr(args, "stilts_jar", None),
        topcat_command=getattr(args, "topcat_command", None),
        topcat_jar=getattr(args, "topcat_jar", None),
    )


def blocked_payload(args: argparse.Namespace, operation: str, finding: str, command: list[str] | None = None) -> dict:
    return build_tool_payload(
        f"stilts_workbench.{operation}",
        status="blocked",
        notes=[
            "STILTS is optional. Use catalog_workbench.py for compact Python crossmatches, or install STILTS/TOPCAT for large catalog and VO workflows.",
            "The TOPCAT GUI is not automated by this wrapper; reproducible work should go through STILTS commands.",
        ],
        artifacts={"summary_json": args.summary_json, "manifest_json": getattr(args, "manifest_json", None)},
        results={
            "operation": operation,
            "command": command_display(command) if command else None,
            "blocking_findings": [finding],
            "native_alternative": {
                "capability_id": "catalog_workbench.crossmatch-sky",
                "label": "catalog_workbench.py crossmatch-sky",
                "applies_to": ["compact_sky_crossmatch", "small_or_medium_catalogs"],
            },
        },
        qa=standard_qa_payload(status="blocked", findings=[finding], metrics={"blocking_count": 1}),
        include_environment=True,
    )


def run_stilts(args: argparse.Namespace, operation: str, stilts_args: list[str], outputs: list[Path] | None = None) -> dict:
    resolved = resolved_stilts(args)
    command = [*(resolved.get("command") or []), *stilts_args]
    if not resolved.get("found"):
        return blocked_payload(
            args,
            operation,
            "Optional backend unavailable: STILTS. Provide --stilts-command, --stilts-jar, or a TOPCAT installation usable in -stilts mode.",
            command=None,
        )

    outputs = outputs or []
    if args.timeout_sec <= 0:
        return blocked_payload(args, operation, "--timeout-sec must be a positive integer.", command=command)
    path_error = validate_output_targets(outputs)
    if path_error:
        return blocked_payload(args, operation, path_error, command=command)
    path_error = validate_optional_artifact_path(getattr(args, "manifest_json", None), "manifest_json")
    if path_error:
        return blocked_payload(args, operation, path_error, command=command)
    path_error = validate_optional_artifact_path(getattr(args, "log_dir", None), "log_dir", directory=True)
    if path_error:
        return blocked_payload(args, operation, path_error, command=command)
    for output in outputs:
        try:
            ensure_parent(output)
        except OSError as exc:
            message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
            return blocked_payload(args, operation, f"Could not create output parent: {message}", command=command)

    artifacts = {
        "summary_json": args.summary_json,
        "manifest_json": getattr(args, "manifest_json", None),
        "outputs": outputs,
    }
    notes = [
        "This wrapper records the exact STILTS command so catalog operations can be cited or rerun.",
        "Prefer explicit RA/Dec columns and formats for scientific reporting; do not rely on ambiguous auto-detection when precision matters.",
    ]
    if getattr(args, "dry_run", False):
        payload = build_tool_payload(
            f"stilts_workbench.{operation}",
            status="ok",
            notes=[*notes, "Dry-run only: STILTS was not executed."],
            artifacts=artifacts,
            results={
                "operation": operation,
                "backend_source": resolved.get("source"),
                "command": command_display(command),
                "returncode": None,
                "dry_run": True,
            },
            qa=standard_qa_payload(status="not_applicable", findings=[], metrics={}),
            include_environment=True,
        )
        return payload

    before_outputs = {path: path_signature(path) for path in outputs}
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        run_findings = []
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        run_findings = [f"STILTS timed out after {args.timeout_sec} seconds."]
    except OSError as exc:
        returncode = None
        stdout = ""
        stderr = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        run_findings = [f"STILTS could not be launched: {stderr}"]

    log_artifacts = {}
    try:
        log_artifacts = write_log_bundle(getattr(args, "log_dir", None), command, stdout, stderr)
    except OSError as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        run_findings.append(f"Could not write STILTS log bundle: {message}")
    artifacts.update(log_artifacts)
    missing_outputs = [public_path(path) for path in outputs if not path.exists()]
    unchanged_outputs = [
        public_path(path)
        for path in outputs
        if before_outputs[path].get("exists") and path.exists() and path_signature(path) == before_outputs[path]
    ]
    findings = [*run_findings]
    if returncode not in (0, None) and returncode != 124:
        findings.append(f"STILTS exited with return code {returncode}.")
    if missing_outputs:
        findings.append("Expected output paths were not created: " + ", ".join(missing_outputs))
    if unchanged_outputs:
        findings.append("Expected output paths were not updated by STILTS: " + ", ".join(unchanged_outputs))
    status = "fail" if findings else "ok"
    result = {
        "operation": operation,
        "backend_source": resolved.get("source"),
        "command": command_display(command),
        "returncode": returncode,
        "stdout_tail": tail(stdout),
        "stderr_tail": tail(stderr),
        "dry_run": False,
        "outputs": [
            {
                "path": public_path(path),
                "exists": path.exists(),
                "existed_before": before_outputs[path].get("exists", False),
                "updated": path.exists() and path_signature(path) != before_outputs[path],
            }
            for path in outputs
        ],
    }
    payload = build_tool_payload(
        f"stilts_workbench.{operation}",
        status=status,
        notes=notes,
        artifacts=artifacts,
        results=result,
        qa=standard_qa_payload(
            status=status,
            findings=findings,
            metrics={
                "returncode": returncode,
                "missing_outputs": len(missing_outputs),
                "unchanged_outputs": len(unchanged_outputs),
            },
        ),
        include_environment=True,
    )
    if getattr(args, "manifest_json", None):
        manifest_outputs = [*outputs]
        if args.summary_json:
            manifest_outputs.append(Path(args.summary_json))
        manifest_outputs.extend(Path(path) for path in log_artifacts.values())
        try:
            write_manifest(
                args.manifest_json,
                inputs=getattr(args, "manifest_inputs", []),
                outputs=manifest_outputs,
                parameters=getattr(args, "manifest_parameters", {}),
                command=command_display(command),
                notes=notes,
            )
        except OSError as exc:
            message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
            payload["status"] = "fail"
            payload["qa"] = standard_qa_payload(status="fail", findings=[*findings, f"Could not write manifest: {message}"], metrics=payload["qa"]["metrics"])
    return payload


def cmd_preflight(args: argparse.Namespace) -> dict:
    resolved = resolved_stilts(args)
    findings = []
    if not resolved.get("found"):
        findings.append("Optional backend unavailable: STILTS. Provide --stilts-command, --stilts-jar, or TOPCAT -stilts mode.")
    status = "blocked" if findings else "ok"
    return build_tool_payload(
        "stilts_workbench.preflight",
        status=status,
        notes=["STILTS is the reproducible backend; TOPCAT GUI use should remain manual and documented."],
        artifacts={"summary_json": args.summary_json},
        results={
            "found": bool(resolved.get("found")),
            "source": resolved.get("source"),
            "command": command_display(resolved.get("command")),
            "blocking_findings": findings,
            "native_alternative": {
                "capability_id": "catalog_workbench.crossmatch-sky",
                "label": "catalog_workbench.py crossmatch-sky",
                "applies_to": ["compact_sky_crossmatch", "small_or_medium_catalogs"],
            },
        },
        qa=standard_qa_payload(status=status, findings=findings, metrics={"blocking_count": len(findings)}),
        include_environment=True,
    )


def cmd_convert(args: argparse.Namespace) -> dict:
    stilts_args = ["tcopy", f"in={args.input}", f"out={args.output}"]
    if args.ifmt:
        stilts_args.append(f"ifmt={args.ifmt}")
    if args.ofmt:
        stilts_args.append(f"ofmt={args.ofmt}")
    args.manifest_inputs = [args.input]
    args.manifest_parameters = {"operation": "convert", "ifmt": args.ifmt, "ofmt": args.ofmt}
    return run_stilts(args, "convert", stilts_args, outputs=[Path(args.output)])


def cmd_filter(args: argparse.Namespace) -> dict:
    stilts_args = ["tpipe", f"in={args.input}", f"out={args.output}"]
    if args.ifmt:
        stilts_args.append(f"ifmt={args.ifmt}")
    if args.ofmt:
        stilts_args.append(f"ofmt={args.ofmt}")
    for command in args.cmd:
        stilts_args.append(f"cmd={command}")
    args.manifest_inputs = [args.input]
    args.manifest_parameters = {"operation": "filter", "ifmt": args.ifmt, "ofmt": args.ofmt, "cmd": args.cmd}
    return run_stilts(args, "filter", stilts_args, outputs=[Path(args.output)])


def cmd_crossmatch_sky(args: argparse.Namespace) -> dict:
    if args.radius_arcsec <= 0:
        return blocked_payload(args, "crossmatch-sky", "--radius-arcsec must be positive.")
    stilts_args = [
        "tskymatch2",
        f"in1={args.left}",
        f"in2={args.right}",
        f"ra1={args.left_ra}",
        f"dec1={args.left_dec}",
        f"ra2={args.right_ra}",
        f"dec2={args.right_dec}",
        f"error={args.radius_arcsec}",
        f"join={args.join}",
        f"find={args.find}",
        f"out={args.output}",
    ]
    if args.ifmt1:
        stilts_args.append(f"ifmt1={args.ifmt1}")
    if args.ifmt2:
        stilts_args.append(f"ifmt2={args.ifmt2}")
    if args.ofmt:
        stilts_args.append(f"ofmt={args.ofmt}")
    args.manifest_inputs = [args.left, args.right]
    args.manifest_parameters = {
        "operation": "crossmatch-sky",
        "left_ra": args.left_ra,
        "left_dec": args.left_dec,
        "right_ra": args.right_ra,
        "right_dec": args.right_dec,
        "radius_arcsec": args.radius_arcsec,
        "join": args.join,
        "find": args.find,
        "ifmt1": args.ifmt1,
        "ifmt2": args.ifmt2,
        "ofmt": args.ofmt,
    }
    return run_stilts(args, "crossmatch-sky", stilts_args, outputs=[Path(args.output)])


def cmd_votlint(args: argparse.Namespace) -> dict:
    if args.maxrepeat < 0:
        return blocked_payload(args, "votlint", "--maxrepeat must be zero or a positive integer.")
    stilts_args = [
        "votlint",
        f"validate={str(args.validate).lower()}",
        f"ucd={str(args.ucd).lower()}",
        f"unit={args.unit}",
        f"maxrepeat={args.maxrepeat}",
        f"out={args.report}",
        args.input,
    ]
    args.manifest_inputs = [args.input]
    args.manifest_parameters = {
        "operation": "votlint",
        "validate": args.validate,
        "ucd": args.ucd,
        "unit": args.unit,
        "maxrepeat": args.maxrepeat,
    }
    return run_stilts(args, "votlint", stilts_args, outputs=[Path(args.report)])


def add_backend_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stilts-command", help="Explicit stilts command or wrapper.")
    parser.add_argument("--stilts-jar", help="Path to stilts.jar; executed via java -jar.")
    parser.add_argument("--topcat-command", help="Explicit TOPCAT command usable with -stilts.")
    parser.add_argument("--topcat-jar", help="Path to TOPCAT jar; used with -stilts if no standalone STILTS is found.")
    parser.add_argument("--dry-run", action="store_true", help="Only emit the STILTS command; do not execute it.")
    parser.add_argument("--timeout-sec", type=int, default=600, help="Execution timeout for real STILTS runs.")
    parser.add_argument("--summary-json", help="Optional standard-envelope JSON summary path.")


def add_run_artifact_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    parser.add_argument("--log-dir", help="Optional directory for command/stdout/stderr logs.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Check whether a usable STILTS backend is available.")
    add_backend_args(preflight)
    preflight.set_defaults(func=cmd_preflight)

    convert = subparsers.add_parser("convert", help="Convert between catalog/table formats with STILTS tcopy.")
    add_backend_args(convert)
    add_run_artifact_args(convert)
    convert.add_argument("input")
    convert.add_argument("output")
    convert.add_argument("--ifmt", help="Explicit STILTS input format, e.g. csv, votable, fits.")
    convert.add_argument("--ofmt", help="Explicit STILTS output format, e.g. csv, votable, fits.")
    convert.set_defaults(func=cmd_convert)

    filt = subparsers.add_parser("filter", help="Run one or more STILTS tpipe cmd operations.")
    add_backend_args(filt)
    add_run_artifact_args(filt)
    filt.add_argument("input")
    filt.add_argument("output")
    filt.add_argument("--cmd", action="append", required=True, help="STILTS tpipe command, repeatable. Example: 'keepcols ra dec mag'")
    filt.add_argument("--ifmt", help="Explicit STILTS input format.")
    filt.add_argument("--ofmt", help="Explicit STILTS output format.")
    filt.set_defaults(func=cmd_filter)

    cross = subparsers.add_parser("crossmatch-sky", help="Crossmatch two tables on sky position with STILTS tskymatch2.")
    add_backend_args(cross)
    add_run_artifact_args(cross)
    cross.add_argument("left")
    cross.add_argument("right")
    cross.add_argument("output")
    cross.add_argument("--left-ra", required=True)
    cross.add_argument("--left-dec", required=True)
    cross.add_argument("--right-ra", required=True)
    cross.add_argument("--right-dec", required=True)
    cross.add_argument("--radius-arcsec", type=float, default=1.0)
    cross.add_argument("--join", default="1and2", choices=["1and2", "1or2", "all1", "all2", "1not2", "2not1", "1xor2"])
    cross.add_argument("--find", default="best", choices=["all", "best", "best1", "best2"])
    cross.add_argument("--ifmt1", help="Explicit STILTS format for the left table.")
    cross.add_argument("--ifmt2", help="Explicit STILTS format for the right table.")
    cross.add_argument("--ofmt", help="Explicit STILTS output format.")
    cross.set_defaults(func=cmd_crossmatch_sky)

    lint = subparsers.add_parser("votlint", help="Validate a VOTable with STILTS votlint.")
    add_backend_args(lint)
    add_run_artifact_args(lint)
    lint.add_argument("input")
    lint.add_argument("report")
    lint.add_argument("--validate", action=argparse.BooleanOptionalAction, default=True)
    lint.add_argument("--ucd", action=argparse.BooleanOptionalAction, default=True)
    lint.add_argument("--unit", default="null", choices=["true", "false", "null"])
    lint.add_argument("--maxrepeat", type=int, default=4)
    lint.set_defaults(func=cmd_votlint)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = args.func(args)
    try:
        emit_payload(payload, args.summary_json)
    except OSError as exc:
        message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
        print(message, file=sys.stderr)
        return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
