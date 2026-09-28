#!/usr/bin/env python3
"""Bridge Aperture Photometry Tool batch mode into reproducible skill outputs."""

from __future__ import annotations

import argparse
import csv
import io
import json
import shlex
import subprocess
from pathlib import Path

from _internal.provenance_utils import public_path, sanitize_payload, standard_qa_payload, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.tabular_io import read_table_any, write_table_any
from external_astro_tools_preflight import command_display, resolve_apt_command, resolve_apt_preferences


class InputValidationError(Exception):
    """Raised when an APT wrapper request is unsafe or incomplete."""

    def __init__(self, issues: list[dict]):
        super().__init__("; ".join(item["detail"] for item in issues))
        self.issues = issues


def tail(text: str, limit: int = 3000) -> str:
    return (text or "")[-limit:]


def ensure_parent(path: str | Path | None) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def resolved_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    return Path(path).expanduser().resolve(strict=False)


def paths_equal(left: str | Path | None, right: str | Path | None) -> bool:
    left_path = resolved_path(left)
    right_path = resolved_path(right)
    return bool(left_path and right_path and left_path == right_path)


def first_non_directory_ancestor(path: Path) -> Path | None:
    for parent in (path.parent, *path.parent.parents):
        if parent.exists():
            return parent if not parent.is_dir() else None
    return None


def issue(title: str, detail: str, *, path: str | Path | None = None, argument: str | None = None, severity: str = "high") -> dict:
    item = {"severity": severity, "title": title, "detail": detail}
    if path is not None:
        item["path"] = public_path(path)
    if argument:
        item["argument"] = argument
    return item


def validate_input_file(path: str | Path | None, label: str) -> list[dict]:
    if not path:
        return [issue("Missing input path", f"{label} is required.", argument=label)]
    candidate = Path(path).expanduser().resolve(strict=False)
    if not candidate.exists():
        return [issue("Input file does not exist", f"{label} does not exist: {public_path(candidate)}", path=candidate, argument=label)]
    if not candidate.is_file():
        return [issue("Input path is not a file", f"{label} must be a regular file: {public_path(candidate)}", path=candidate, argument=label)]
    return []


def validate_output_file(path: str | Path | None, label: str, *, protected_paths: list[str | Path | None] | None = None) -> list[dict]:
    if not path:
        return []
    candidate = Path(path).expanduser().resolve(strict=False)
    issues = []
    if candidate.exists() and candidate.is_dir():
        issues.append(issue("Output path is a directory", f"{label} must point to a file, not a directory: {public_path(candidate)}", path=candidate, argument=label))
    blocked_parent = first_non_directory_ancestor(candidate)
    if blocked_parent is not None:
        issues.append(
            issue(
                "Output parent is not a directory",
                f"{label} cannot be written because an ancestor is a file: {public_path(blocked_parent)}",
                path=candidate,
                argument=label,
            )
        )
    for protected in protected_paths or []:
        if protected and paths_equal(candidate, protected):
            issues.append(
                issue(
                    "Output would overwrite an input or companion artifact",
                    f"{label} points to the same path as a protected input/output: {public_path(candidate)}",
                    path=candidate,
                    argument=label,
                )
            )
    return issues


def validate_output_group(paths: list[tuple[str | Path | None, str]], *, protected_paths: list[str | Path | None] | None = None) -> list[dict]:
    issues = []
    seen: dict[Path, str] = {}
    for raw_path, label in paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve(strict=False)
        issues.extend(validate_output_file(path, label, protected_paths=protected_paths))
        if path in seen:
            issues.append(
                issue(
                    "Output paths collide",
                    f"{label} and {seen[path]} point to the same file: {public_path(path)}",
                    path=path,
                    argument=label,
                )
            )
        seen[path] = label
    return issues


def validate_log_dir(path: str | Path | None, *, protected_paths: list[str | Path | None] | None = None) -> list[dict]:
    if not path:
        return []
    candidate = Path(path).expanduser().resolve(strict=False)
    issues = []
    if candidate.exists() and not candidate.is_dir():
        issues.append(issue("Log path is not a directory", f"--log-dir must point to a directory: {public_path(candidate)}", path=candidate, argument="--log-dir"))
    blocked_parent = first_non_directory_ancestor(candidate)
    if blocked_parent is not None:
        issues.append(
            issue(
                "Log parent is not a directory",
                f"--log-dir cannot be created because an ancestor is a file: {public_path(blocked_parent)}",
                path=candidate,
                argument="--log-dir",
            )
        )
    for protected in protected_paths or []:
        if protected and paths_equal(candidate, protected):
            issues.append(issue("Log directory collides with protected path", f"--log-dir points to a protected path: {public_path(candidate)}", path=candidate, argument="--log-dir"))
    return issues


def validate_common_artifacts(args: argparse.Namespace) -> list[dict]:
    return validate_output_group(
        [
            (getattr(args, "summary_json", None), "--summary-json"),
            (getattr(args, "manifest_json", None), "--manifest-json"),
        ]
    )


def load_table_dependencies():
    from astropy.table import Table

    return Table


def write_log_bundle(log_dir: str | Path | None, command: list[str], stdout: str, stderr: str) -> dict:
    if not log_dir:
        return {}
    root = Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    command_path = root / "apt_command.sh"
    stdout_path = root / "apt_stdout.txt"
    stderr_path = root / "apt_stderr.txt"
    command_path.write_text(shlex.join(command) + "\n", encoding="utf-8")
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {
        "command_sh": command_path,
        "stdout_log": stdout_path,
        "stderr_log": stderr_path,
    }


def resolved_apt(args: argparse.Namespace) -> tuple[dict, dict]:
    command = resolve_apt_command(getattr(args, "apt_command", None))
    preferences = resolve_apt_preferences(getattr(args, "apt_preferences", None))
    return command, preferences


def cmd_preflight(args: argparse.Namespace) -> dict:
    validation_issues = validate_common_artifacts(args)
    if validation_issues:
        raise InputValidationError(validation_issues)
    command, preferences = resolved_apt(args)
    findings = []
    warnings = []
    if not command.get("found"):
        findings.append("No APT command was found. Provide --apt-command pointing at APT.csh/APT.bat.")
    if not preferences.get("found"):
        warnings.append("No APT preferences file was found. Batch mode should use a saved APT.pref configured in the GUI first.")
    status = "blocked" if findings else ("warning" if warnings else "ok")
    return build_tool_payload(
        "apt_workbench.preflight",
        status=status,
        notes=[
            "APT is optional and GUI-configured; batch mode is reproducible only when the saved preferences file is part of the manifest.",
            "For fully code-native aperture photometry, prefer aperture_photometry.py/photutils unless the task explicitly requires APT.",
        ],
        artifacts={"summary_json": args.summary_json},
        results={
            "apt": {"found": bool(command.get("found")), "source": command.get("source"), "command": command_display(command.get("command"))},
            "preferences": {
                "found": bool(preferences.get("found")),
                "source": preferences.get("source"),
                "path": public_path(preferences.get("path")),
            },
            "blocking_findings": findings,
            "warning_findings": warnings,
        },
        qa=standard_qa_payload(status=status, findings=findings + warnings, metrics={"blocking_count": len(findings), "warning_count": len(warnings)}),
        include_environment=True,
    )


def coerce_row_mapping(row: dict, x_col: str, y_col: str, id_col: str | None = None) -> dict:
    try:
        x = float(row[x_col])
        y = float(row[y_col])
    except KeyError as exc:
        raise ValueError(f"Missing source-list column: {exc.args[0]}") from exc
    except Exception as exc:
        raise ValueError(f"Source-list coordinates must be numeric in columns {x_col!r}/{y_col!r}.") from exc
    result = {"x": x, "y": y}
    if id_col:
        result["id"] = row.get(id_col, "")
    return result


def cmd_prepare_source_list(args: argparse.Namespace) -> dict:
    input_path = Path(args.input_table)
    output_path = Path(args.output_source_list)
    validation_issues = []
    validation_issues.extend(validate_input_file(input_path, "input_table"))
    validation_issues.extend(
        validate_output_group(
            [
                (output_path, "output_source_list"),
                (args.summary_json, "--summary-json"),
                (args.manifest_json, "--manifest-json"),
            ],
            protected_paths=[input_path],
        )
    )
    if validation_issues:
        raise InputValidationError(validation_issues)
    ensure_parent(output_path)
    text = input_path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t ;") if text.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        raise SystemExit("Input source table has no header row.")
    try:
        rows = [coerce_row_mapping(row, args.x_col, args.y_col, args.id_col) for row in reader]
    except ValueError as exc:
        raise InputValidationError([issue("Invalid source-list table", str(exc), path=input_path, argument="input_table")]) from exc
    output_lines = []
    for row in rows:
        if args.id_col:
            output_lines.append(f"{row['x']:.8f} {row['y']:.8f} {row['id']}".rstrip())
        else:
            output_lines.append(f"{row['x']:.8f} {row['y']:.8f}")
    output_path.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8")
    findings = []
    if not rows:
        findings.append("No source rows were written.")
    status = "warning" if findings else "ok"
    payload = build_tool_payload(
        "apt_workbench.prepare-source-list",
        status=status,
        notes=[
            "This writes a simple whitespace source list for APT; the APT preferences file must still declare whether coordinates are pixels or sky positions.",
            "Keep this derived list separate from the original catalog.",
        ],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json, "source_list": output_path},
        results={
            "input_table": public_path(input_path),
            "output_source_list": public_path(output_path),
            "row_count": len(rows),
            "x_col": args.x_col,
            "y_col": args.y_col,
            "id_col": args.id_col,
        },
        qa=standard_qa_payload(status=status, findings=findings, metrics={"row_count": len(rows)}),
        include_environment=True,
    )
    if args.manifest_json:
        outputs = [output_path]
        if args.summary_json:
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=outputs,
            parameters={"operation": "prepare-source-list", "x_col": args.x_col, "y_col": args.y_col, "id_col": args.id_col},
            command="apt_workbench.py prepare-source-list",
            notes=payload["notes"],
        )
    return payload


def blocked_run_batch(args: argparse.Namespace, findings: list[str], command: list[str] | None = None) -> dict:
    return build_tool_payload(
        "apt_workbench.run-batch",
        status="blocked",
        notes=[
            "APT batch mode requires both APT.csh/APT.bat and a saved APT.pref. Configure APT manually once, save preferences, then rerun this wrapper.",
            "The wrapper never edits the input FITS, source list, or preferences file.",
        ],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json, "output_table": args.output_table},
        results={"command": command_display(command) if command else None, "blocking_findings": findings},
        qa=standard_qa_payload(status="blocked", findings=findings, metrics={"blocking_count": len(findings)}),
        include_environment=True,
    )


def cmd_run_batch(args: argparse.Namespace) -> dict:
    command_info, pref_info = resolved_apt(args)
    findings = []
    if not command_info.get("found"):
        findings.append("No APT command was found. Provide --apt-command pointing at APT.csh/APT.bat.")
    if not pref_info.get("found"):
        findings.append("No APT preferences file was found. Use --apt-preferences or save ~/.AperturePhotometryTool/APT.pref first.")
    pref_path = Path(pref_info["path"])
    validation_issues = []
    validation_issues.extend(validate_input_file(args.image, "--image"))
    validation_issues.extend(validate_input_file(args.source_list, "--source-list"))
    if pref_info.get("exists") and not pref_info.get("is_file"):
        validation_issues.append(issue("APT preferences path is not a file", f"--apt-preferences must point to a saved APT.pref file: {public_path(pref_path)}", path=pref_path, argument="--apt-preferences"))
    protected_paths = [args.image, args.source_list, pref_path]
    validation_issues.extend(
        validate_output_group(
            [
                (args.output_table, "--output-table"),
                (args.summary_json, "--summary-json"),
                (args.manifest_json, "--manifest-json"),
            ],
            protected_paths=protected_paths,
        )
    )
    validation_issues.extend(validate_log_dir(args.log_dir, protected_paths=protected_paths + [args.output_table, args.summary_json, args.manifest_json]))
    command = [
        *(command_info.get("command") or []),
        "-i",
        str(Path(args.image)),
        "-s",
        str(Path(args.source_list)),
        "-p",
        str(pref_path),
        "-o",
        str(Path(args.output_table)),
    ]
    if args.zero_point is not None:
        command.extend(["-z", str(args.zero_point)])
    if args.verbosity is not None:
        command.extend(["-v", str(args.verbosity)])
    if validation_issues:
        raise InputValidationError(validation_issues)
    if findings:
        return blocked_run_batch(args, findings, command if command_info.get("command") else None)

    output_path = Path(args.output_table)
    ensure_parent(output_path)
    notes = [
        "APT batch mode is preference-driven; cite or archive the APT.pref used for the run.",
        "If results must be fully code-native and portable, rerun or compare with aperture_photometry.py/photutils.",
    ]
    if args.dry_run:
        return build_tool_payload(
            "apt_workbench.run-batch",
            status="ok",
            notes=[*notes, "Dry-run only: APT was not executed."],
            artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json, "output_table": output_path},
            results={"command": command_display(command), "dry_run": True, "returncode": None},
            qa=standard_qa_payload(status="not_applicable", findings=[], metrics={}),
            include_environment=True,
        )

    completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    log_artifacts = write_log_bundle(args.log_dir, command, completed.stdout, completed.stderr)
    missing_outputs = [] if output_path.exists() else [public_path(output_path)]
    run_findings = []
    if completed.returncode != 0:
        run_findings.append(f"APT exited with return code {completed.returncode}.")
    if missing_outputs:
        run_findings.append("Expected APT output table was not created: " + ", ".join(missing_outputs))
    status = "fail" if run_findings else "ok"
    artifacts = {
        "summary_json": args.summary_json,
        "manifest_json": args.manifest_json,
        "output_table": output_path,
        **log_artifacts,
    }
    payload = build_tool_payload(
        "apt_workbench.run-batch",
        status=status,
        notes=notes,
        artifacts=artifacts,
        results={
            "command": command_display(command),
            "returncode": completed.returncode,
            "stdout_tail": tail(completed.stdout),
            "stderr_tail": tail(completed.stderr),
            "dry_run": False,
            "output_table": {"path": public_path(output_path), "exists": output_path.exists()},
            "apt_preferences": public_path(pref_path),
        },
        qa=standard_qa_payload(
            status=status,
            findings=run_findings,
            metrics={"returncode": completed.returncode, "output_exists": int(output_path.exists())},
        ),
        include_environment=True,
    )
    if args.manifest_json:
        outputs = [output_path]
        if args.summary_json:
            outputs.append(Path(args.summary_json))
        outputs.extend(Path(path) for path in log_artifacts.values())
        write_manifest(
            args.manifest_json,
            inputs=[args.image, args.source_list, pref_path],
            outputs=outputs,
            parameters={
                "operation": "run-batch",
                "zero_point": args.zero_point,
                "verbosity": args.verbosity,
                "timeout_sec": args.timeout_sec,
            },
            command=command_display(command),
            notes=notes,
        )
    return payload


def cmd_parse_results(args: argparse.Namespace) -> dict:
    Table = load_table_dependencies()
    input_path = Path(args.input_table)
    output_path = Path(args.output_table)
    validation_issues = []
    validation_issues.extend(validate_input_file(input_path, "input_table"))
    validation_issues.extend(
        validate_output_group(
            [
                (output_path, "output_table"),
                (args.summary_json, "--summary-json"),
                (args.manifest_json, "--manifest-json"),
            ],
            protected_paths=[input_path],
        )
    )
    if validation_issues:
        raise InputValidationError(validation_issues)
    ensure_parent(output_path)
    format_attempts = []

    def read_candidate(format_name: str | None, label: str):
        candidate = read_table_any(Table, input_path, fmt=format_name)
        if len(getattr(candidate, "colnames", [])) == 0:
            raise ValueError(f"{label} produced a table with no columns")
        return candidate

    try:
        first_label = args.input_format or "auto"
        table = read_candidate(args.input_format, first_label)
        format_attempts.append({"format": first_label, "status": "ok"})
    except Exception as first_exc:
        table = None
        first_label = args.input_format or "auto"
        format_attempts.append({"format": first_label, "status": "error", "error": f"{first_exc.__class__.__name__}: {first_exc}"})
        fallback_formats = []
        if not args.input_format and input_path.suffix.lower() == ".tbl":
            fallback_formats = [
                "ascii.csv",
                "ascii.tab",
                "ascii.basic",
                "ascii.commented_header",
                "ascii.fast_csv",
                "ascii.fast_tab",
            ]
        last_exc = first_exc
        for format_name in fallback_formats:
            try:
                table = read_candidate(format_name, format_name)
                format_attempts.append({"format": format_name, "status": "ok"})
                break
            except Exception as exc:
                format_attempts.append({"format": format_name, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"})
                last_exc = exc
        if table is None:
            suggestions = [
                "Pass --input-format explicitly, for example ascii.csv, ascii.tab, ascii.basic, or ascii.commented_header.",
                "If this is a native APT table, check that the header row is present and contains APT-style column names.",
                "If this is just a CSV saved with .tbl extension, rerun with --input-format ascii.csv.",
            ]
            finding = f"Could not parse APT results table: {last_exc.__class__.__name__}: {last_exc}"
            payload = build_tool_payload(
                "apt_workbench.parse-results",
                status="blocked",
                notes=[
                    "APT result parsing could not identify the table format safely.",
                    "The wrapper blocks with a machine-readable payload instead of surfacing a raw Astropy traceback.",
                ],
                artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json, "output_table": output_path},
                results={
                    "input_table": public_path(input_path),
                    "output_table": public_path(output_path),
                    "input_format": args.input_format,
                    "format_attempts": format_attempts,
                    "suggestions": suggestions,
                    "blocking_findings": [finding],
                },
                qa=standard_qa_payload(status="blocked", findings=[finding], metrics={"format_attempt_count": len(format_attempts)}),
                include_environment=True,
            )
            return payload
    write_table_any(table, output_path)
    payload = build_tool_payload(
        "apt_workbench.parse-results",
        status="ok",
        notes=[
            "APT tables are parsed through the shared tabular readers and re-emitted as a clean analysis table copy.",
            "When .tbl auto-detection is ambiguous, this command tries a small set of common ASCII fallbacks before blocking.",
        ],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json, "output_table": output_path},
        results={
            "input_table": public_path(input_path),
            "output_table": public_path(output_path),
            "input_format": args.input_format,
            "format_attempts": format_attempts,
            "row_count": int(len(table)),
            "columns": list(table.colnames),
        },
        qa=standard_qa_payload(status="ok", findings=[], metrics={"row_count": int(len(table)), "column_count": len(table.colnames)}),
        include_environment=True,
    )
    if args.manifest_json:
        outputs = [output_path]
        if args.summary_json:
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=outputs,
            parameters={"operation": "parse-results", "input_format": args.input_format},
            command="apt_workbench.py parse-results",
            notes=payload["notes"],
        )
    return payload


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--summary-json", help="Optional standard-envelope JSON summary path.")


def add_apt_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--apt-command", help="Explicit APT.csh/APT.bat command.")
    parser.add_argument("--apt-preferences", help="Path to saved APT.pref.")


def add_artifact_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Check whether APT batch mode is plausibly available.")
    add_common(preflight)
    add_apt_common(preflight)
    preflight.set_defaults(func=cmd_preflight)

    prepare = subparsers.add_parser("prepare-source-list", help="Prepare a simple whitespace source list for APT.")
    add_common(prepare)
    add_artifact_common(prepare)
    prepare.add_argument("input_table")
    prepare.add_argument("output_source_list")
    prepare.add_argument("--x-col", required=True)
    prepare.add_argument("--y-col", required=True)
    prepare.add_argument("--id-col")
    prepare.set_defaults(func=cmd_prepare_source_list)

    batch = subparsers.add_parser("run-batch", help="Run APT in non-interactive batch mode on one image/source list.")
    add_common(batch)
    add_artifact_common(batch)
    add_apt_common(batch)
    batch.add_argument("--image", required=True, help="Input FITS image.")
    batch.add_argument("--source-list", required=True, help="APT source-list file or sourceListByAPT.")
    batch.add_argument("--output-table", required=True, help="APT output aperture-photometry table.")
    batch.add_argument("--zero-point", type=float, help="Optional APT calibrated image magnitude zero point.")
    batch.add_argument("--verbosity", type=int, choices=[0, 1], help="Optional APT verbosity level when supported.")
    batch.add_argument("--dry-run", action="store_true", help="Emit the APT command but do not execute it.")
    batch.add_argument("--timeout-sec", type=int, default=1800)
    batch.add_argument("--log-dir", help="Optional directory for command/stdout/stderr logs.")
    batch.set_defaults(func=cmd_run_batch)

    parse = subparsers.add_parser("parse-results", help="Parse an APT output table and convert it to a clean table.")
    add_common(parse)
    add_artifact_common(parse)
    parse.add_argument("input_table")
    parse.add_argument("output_table")
    parse.add_argument("--input-format", help="Optional Astropy table format override.")
    parse.set_defaults(func=cmd_parse_results)

    return parser


def tool_id(args: argparse.Namespace) -> str:
    return f"apt_workbench.{getattr(args, 'command', 'unknown') or 'unknown'}"


def common_artifacts(args: argparse.Namespace) -> dict:
    artifacts = {"summary_json": getattr(args, "summary_json", None), "manifest_json": getattr(args, "manifest_json", None)}
    for attr in ("output_source_list", "output_table", "log_dir"):
        if hasattr(args, attr):
            artifacts[attr] = getattr(args, attr)
    return artifacts


def blocked_validation_payload(args: argparse.Namespace, issues: list[dict]) -> dict:
    return build_tool_payload(
        tool_id(args),
        status="blocked",
        notes=["APT wrapper request was blocked before writing outputs or running an optional backend."],
        artifacts=common_artifacts(args),
        results={"operation": getattr(args, "command", None), "blocking_findings": issues},
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"blocking_count": len(issues)}),
        include_environment=True,
    )


def failure_payload(args: argparse.Namespace, error: Exception) -> dict:
    finding = issue("APT wrapper failed", f"{error.__class__.__name__}: {error}")
    return build_tool_payload(
        tool_id(args),
        status="fail",
        notes=["APT wrapper failed before producing a trustworthy result."],
        artifacts=common_artifacts(args),
        results={"operation": getattr(args, "command", None), "error_type": error.__class__.__name__, "error": str(error)},
        qa=standard_qa_payload(status="fail", findings=[finding], metrics={"finding_count": 1}),
        include_environment=True,
    )


def payload_mentions_summary_problem(payload: dict) -> bool:
    for finding in payload.get("qa", {}).get("findings", []):
        if isinstance(finding, dict) and finding.get("argument") == "--summary-json":
            return True
    return False


def print_payload(payload: dict) -> None:
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))


def emit_payload_cleanly(payload: dict, args: argparse.Namespace) -> None:
    summary_json = getattr(args, "summary_json", None)
    if summary_json and not payload_mentions_summary_problem(payload):
        try:
            emit_payload(payload, summary_json)
            return
        except Exception as exc:
            emitted = dict(payload)
            findings = list(emitted.get("qa", {}).get("findings", []))
            findings.append(issue("Could not write summary JSON", f"{exc.__class__.__name__}: {exc}", path=summary_json, argument="--summary-json"))
            emitted["qa"] = standard_qa_payload(status="fail", findings=findings, metrics={"finding_count": len(findings)})
            emitted["status"] = "fail"
            print_payload(emitted)
            return
    print_payload(payload)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except InputValidationError as exc:
        payload = blocked_validation_payload(args, exc.issues)
    except Exception as exc:
        payload = failure_payload(args, exc)
    emit_payload_cleanly(payload, args)
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
