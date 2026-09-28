#!/usr/bin/env python3
"""Export a presentation copy to PDF through Keynote on macOS.

This is a GUI fallback for environments where LibreOffice is unavailable. It is
intentionally copy-oriented: export the derived PDF without mutating the source deck.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _internal.path_safety import output_overlaps_input
from _internal.public_contract import build_preflight_payload, build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, write_manifest
from _internal.runtime_common import clean_known_stderr, find_executable


SUPPORTED_INPUT_SUFFIXES = {".key", ".pptm", ".pptx"}
KEYNOTE_PROBE_TIMEOUT_SECONDS = 10
KEYNOTE_EXPORT_TIMEOUT_SECONDS = 300


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("presentation_path", help="Input presentation copy (.pptx, .pptm, or .key).")
    parser.add_argument("pdf_path", help="Target PDF path.")
    parser.add_argument("--preflight-only", action="store_true", help="Only report capability status without exporting.")
    parser.add_argument(
        "--require-confirmation",
        action="store_true",
        help="Block before opening Keynote unless --confirmation-id records an external approval.",
    )
    parser.add_argument("--confirmation-id", help="Opaque identifier for the reviewed external confirmation.")
    parser.add_argument("--log-txt", help="Optional native execution log.")
    parser.add_argument("--summary-json", help="Optional summary JSON.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def keynote_available():
    osascript = find_executable(["osascript"])
    if sys.platform != "darwin" or not osascript:
        return False
    try:
        probe = subprocess.run(
            [osascript, "-e", 'id of application "Keynote"'],
            text=True,
            capture_output=True,
            check=False,
            timeout=KEYNOTE_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def build_capability_report():
    osascript = find_executable(["osascript"])
    capabilities = {
        "platform": sys.platform,
        "osascript": bool(osascript),
        "keynote_app": keynote_available(),
    }
    blocking_findings = []
    warning_findings = []
    if sys.platform != "darwin":
        blocking_findings.append("Keynote export is only available on macOS.")
    if not osascript:
        blocking_findings.append("osascript is not available on this machine.")
    elif not capabilities["keynote_app"]:
        blocking_findings.append("Keynote.app is not installed or not discoverable by AppleScript.")
    status = "blocked" if blocking_findings else "ok"
    recommendation = (
        "Run this export on a macOS machine with Keynote installed, or use a copy-based LibreOffice/PDF fallback when fidelity permits."
        if blocking_findings
        else "Keynote export is ready."
    )
    return {
        "status": status,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
        "recommendation": recommendation,
        "capabilities": capabilities,
    }


def _blocked_qa(title: str, detail: str) -> dict:
    return {
        "status": "blocked",
        "findings": [{"severity": "high", "title": title, "detail": detail}],
        "metrics": {"blocking_count": 1},
    }


def _apply_v2_gui_contract(payload: dict) -> dict:
    payload["contract_version"] = "2.0"
    payload["job_metadata"] = {
        "safe_to_retry": True,
        "supports_cancel": True,
        "recommended_exposure": "optional",
    }
    payload["safety"] = {
        "input_policy": "copied_input_only",
        "output_policy": "separate_run_directory",
        "secrets_redacted": True,
        "requires_confirmation": True,
    }
    payload["provenance"]["skill_contract_version"] = "v2.0"
    payload["provenance"]["originals_policy"] = "copied_inputs_only"
    return payload


def confirmation_record(*, enforced: bool, confirmation_id: str | None) -> dict:
    return {
        "required": True,
        "enforced_by_backend": bool(enforced),
        "recorded": bool(confirmation_id),
        "confirmation_id": confirmation_id or None,
    }


def canonical_path(pathlike: str | Path) -> Path:
    return Path(pathlike).expanduser().resolve(strict=False)


def path_collides_with_deck(output_path: Path, input_path: Path) -> bool:
    expanded_input = input_path.expanduser()
    if output_overlaps_input(output_path, expanded_input):
        return True
    if not expanded_input.is_dir() and expanded_input.suffix.lower() != ".key":
        return False
    return False


def deck_output_collisions(args, input_path: Path, output_path: Path) -> list[dict[str, str]]:
    collisions = []
    for flag, pathlike in (
        ("pdf_path", output_path),
        ("--log-txt", args.log_txt),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
    ):
        if pathlike and path_collides_with_deck(Path(pathlike), input_path):
            collisions.append(
                {
                    "flag": flag,
                    "path": public_path(canonical_path(pathlike)),
                }
            )
    return collisions


def _emit_deck_collision_only(
    args,
    input_path: Path,
    output_path: Path,
    collisions: list[dict[str, str]],
) -> int:
    rendered = ", ".join(item["flag"] for item in collisions)
    message = f"Refusing output paths that resolve to or inside the input deck: {rendered}."
    payload = build_tool_payload(
        "keynote_export",
        status="blocked",
        notes=[message, "No output files were written and the input deck was not modified."],
        artifacts={
            "summary_json": None,
            "output_pdf": None,
            "manifest_json": None,
            "log_txt": None,
        },
        results={
            "input": public_path(input_path),
            "output": public_path(output_path),
            "blocked_reason": message,
            "collisions": collisions,
            "confirmation": confirmation_record(
                enforced=args.require_confirmation,
                confirmation_id=args.confirmation_id,
            ),
        },
        qa=_blocked_qa("Input/output collision", message),
        legacy={
            "input": public_path(input_path),
            "output": None,
            "used_gui_path": False,
            "native_error": message,
        },
        inputs=[input_path],
    )
    _apply_v2_gui_contract(payload)
    payload["next_actions"] = ["Choose output paths outside the copied input deck and retry."]
    emit_payload(payload, None)
    return 2


def write_execution_log(
    path: str | Path | None,
    *,
    phase: str,
    status: str,
    input_path: Path,
    output_path: Path,
    stdout: str = "",
    stderr: str = "",
    detail: str = "",
) -> None:
    if not path:
        return
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "tool=keynote_export",
        f"phase={phase}",
        f"status={status}",
        f"input={public_path(input_path)}",
        f"output={public_path(output_path)}",
    ]
    if detail:
        lines.extend(["detail:", clean_known_stderr(detail) or detail])
    if stdout:
        lines.extend(["stdout:", clean_known_stderr(stdout) or stdout])
    if stderr:
        lines.extend(["stderr:", clean_known_stderr(stderr) or stderr])
    log_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _emit_blocked(
    args,
    input_path: Path,
    output_path: Path,
    message: str,
    *,
    title: str = "Keynote export blocked",
    capability_report: dict | None = None,
) -> int:
    cleaned = clean_known_stderr(message) or message
    report = capability_report or build_capability_report()
    try:
        write_execution_log(
            args.log_txt,
            phase="preflight" if args.preflight_only else "export",
            status="BLOCKED_CONTROLADO",
            input_path=input_path,
            output_path=output_path,
            detail=cleaned,
        )
    except OSError:
        pass
    payload = build_tool_payload(
        "keynote_export",
        status="blocked",
        notes=["Keynote export was blocked before a trustworthy PDF could be produced."],
        artifacts={"summary_json": args.summary_json, "log_txt": args.log_txt},
        results={
            "input": public_path(input_path),
            "output": public_path(output_path),
            "native_error": cleaned,
            "confirmation": confirmation_record(
                enforced=args.require_confirmation,
                confirmation_id=args.confirmation_id,
            ),
            **report,
        },
        qa=_blocked_qa(title, cleaned),
        legacy={
            "input": public_path(input_path),
            "output": None,
            "used_gui_path": False,
            "native_error": cleaned,
        },
        inputs=[input_path],
    )
    _apply_v2_gui_contract(payload)
    payload["next_actions"] = [
        "Review the preflight or native Keynote error before retrying.",
        "Use presentation inspection or a copy-based LibreOffice/PDF fallback when exact Keynote rendering is not required.",
    ]
    emit_payload(payload, args.summary_json)
    return 2


def validate_export_request(input_path: Path, output_path: Path) -> str | None:
    suffix = input_path.suffix.lower()
    if not input_path.exists():
        return f"Input presentation does not exist: {input_path}"
    if suffix not in SUPPORTED_INPUT_SUFFIXES:
        expected = ", ".join(sorted(SUPPORTED_INPUT_SUFFIXES))
        return f"Unsupported presentation suffix for Keynote export: {suffix or '<none>'}. Expected one of: {expected}"
    if suffix != ".key" and not input_path.is_file():
        return f"Input presentation is not a regular file: {input_path}"
    if suffix == ".key" and not (input_path.is_file() or input_path.is_dir()):
        return f"Input Keynote document is neither a file nor a package directory: {input_path}"
    if output_path.suffix.lower() != ".pdf":
        return f"Target output must be a .pdf path: {output_path}"
    parent = output_path.parent
    if parent.exists() and not parent.is_dir():
        return f"Output parent exists and is not a directory: {parent}"
    if output_path.exists() and output_path.is_dir():
        return f"Output path exists and is a directory, not a PDF file path: {output_path}"
    if output_path.exists():
        return f"Target PDF already exists; choose a fresh run output path: {output_path}"
    return None


def export_with_keynote(presentation_path: Path, pdf_path: Path) -> subprocess.CompletedProcess[str]:
    script = """
on run argv
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv
    set inputFile to POSIX file inputPath
    set outputFile to POSIX file outputPath
    set documentOpened to false
    tell application "Keynote"
        activate
        try
            set theDoc to open inputFile
            set documentOpened to true
            export theDoc to outputFile as PDF
            close theDoc saving no
            set documentOpened to false
        on error errorMessage number errorNumber
            if documentOpened then
                try
                    close theDoc saving no
                end try
            end if
            error errorMessage number errorNumber
        end try
    end tell
end run
""".strip()
    cmd = [
        "osascript",
        "-e",
        script,
        str(presentation_path.resolve()),
        str(pdf_path.resolve()),
    ]
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        timeout=KEYNOTE_EXPORT_TIMEOUT_SECONDS,
    )


def discard_partial_pdf(path: Path) -> None:
    """Best-effort removal of an output created by a failed GUI export."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        # The controlled error payload remains the primary result. A cleanup
        # failure must not leak a raw traceback from an already-failed export.
        pass


def main():
    args = parse_args()
    input_path = Path(args.presentation_path)
    output_path = Path(args.pdf_path)
    collisions = deck_output_collisions(args, input_path, output_path)
    if collisions:
        raise SystemExit(_emit_deck_collision_only(args, input_path, output_path, collisions))
    capability_report = build_capability_report()
    if args.preflight_only:
        try:
            write_execution_log(
                args.log_txt,
                phase="preflight",
                status="PASS" if capability_report["status"] == "ok" else "BLOCKED_CONTROLADO",
                input_path=input_path,
                output_path=output_path,
                detail=capability_report["recommendation"],
            )
        except OSError as exc:
            raise SystemExit(
                _emit_blocked(
                    args,
                    input_path,
                    output_path,
                    f"Could not write requested preflight log: {exc.__class__.__name__}: {exc}",
                    title="Preflight log unavailable",
                    capability_report=capability_report,
                )
            ) from None
        payload = build_preflight_payload(
            "keynote_export",
            status=capability_report["status"],
            capabilities=capability_report["capabilities"],
            recommendation=capability_report["recommendation"],
            blocking_findings=capability_report["blocking_findings"],
            warning_findings=capability_report["warning_findings"],
            notes=["This preflight checks whether the Keynote GUI export path is usable on the current machine."],
            artifacts={"summary_json": args.summary_json, "log_txt": args.log_txt},
            results={
                "input": public_path(input_path),
                "output": public_path(output_path),
                "confirmation": confirmation_record(enforced=False, confirmation_id=None),
            },
            inputs=[input_path],
        )
        _apply_v2_gui_contract(payload)
        payload["next_actions"] = (
            ["Confirm the copied-deck GUI export in ScientificWorkbench before opening Keynote."]
            if capability_report["status"] == "ok"
            else [
                "Resolve the listed macOS, AppleScript, or Keynote prerequisite.",
                "Use presentation inspection or a copy-based LibreOffice/PDF fallback when exact Keynote rendering is not required.",
            ]
        )
        emit_payload(payload, args.summary_json)
        return
    if capability_report["status"] == "blocked":
        message = capability_report["blocking_findings"][0] if capability_report["blocking_findings"] else "Keynote export is unavailable."
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                message,
                title="Keynote dependency unavailable",
                capability_report=capability_report,
            )
        )
    if args.require_confirmation and not args.confirmation_id:
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                "--confirmation-id is required when --require-confirmation is set.",
                title="Keynote GUI confirmation required",
                capability_report=capability_report,
            )
        )
    request_error = validate_export_request(input_path, output_path)
    if request_error:
        raise SystemExit(_emit_blocked(args, input_path, output_path, request_error, capability_report=capability_report))
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        raise SystemExit(_emit_blocked(args, input_path, output_path, message, title="Output directory unavailable", capability_report=capability_report)) from None
    try:
        result = export_with_keynote(input_path, output_path)
    except subprocess.TimeoutExpired:
        discard_partial_pdf(output_path)
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                f"Keynote export exceeded the {KEYNOTE_EXPORT_TIMEOUT_SECONDS}-second safety timeout.",
                title="Keynote export timed out",
                capability_report=capability_report,
            )
        ) from None
    except Exception as exc:
        discard_partial_pdf(output_path)
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        raise SystemExit(_emit_blocked(args, input_path, output_path, message, title="Keynote launch failed", capability_report=capability_report)) from None
    if result.returncode != 0:
        discard_partial_pdf(output_path)
        message = result.stderr or result.stdout or "Keynote export failed."
        raise SystemExit(_emit_blocked(args, input_path, output_path, message, title="Keynote native export failed", capability_report=capability_report))
    if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size == 0:
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                "Keynote reported success, but the target PDF was not created as a non-empty file.",
                title="Missing export artifact",
                capability_report=capability_report,
            )
        )
    try:
        write_execution_log(
            args.log_txt,
            phase="export",
            status="PASS",
            input_path=input_path,
            output_path=output_path,
            stdout=result.stdout,
            stderr=result.stderr,
            detail="Keynote produced a non-empty PDF and closed the copied deck without saving.",
        )
    except OSError as exc:
        if output_path.exists():
            output_path.unlink()
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                f"Could not write requested execution log: {exc.__class__.__name__}: {exc}",
                title="Execution log unavailable",
                capability_report=capability_report,
            )
        ) from None
    payload = build_tool_payload(
        "keynote_export",
        status="ok",
        notes=["This is a copy-based GUI fallback for environments where LibreOffice export is not the right route."],
        artifacts={
            "summary_json": args.summary_json,
            "output_pdf": output_path,
            "manifest_json": args.manifest_json,
            "log_txt": args.log_txt,
        },
        results={
            "input": public_path(input_path),
            "output": public_path(output_path),
            "confirmation": confirmation_record(
                enforced=args.require_confirmation,
                confirmation_id=args.confirmation_id,
            ),
            **capability_report,
        },
        qa={"status": "ok", "findings": [], "metrics": {"used_gui_path": True}},
        legacy={"input": public_path(input_path), "output": public_path(output_path)},
        inputs=[input_path],
    )
    _apply_v2_gui_contract(payload)
    payload["next_actions"] = [
        "Review the exported PDF visually before delivery.",
        "Keep the PDF, log, summary, and manifest together as the Keynote export run.",
    ]
    print(public_path(output_path))
    if args.summary_json:
        emit_payload(payload, args.summary_json)
    if args.manifest_json:
        manifest_outputs = [output_path]
        if args.summary_json:
            manifest_outputs.append(args.summary_json)
        if args.log_txt:
            manifest_outputs.append(args.log_txt)
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=manifest_outputs,
            parameters={
                "tool": "keynote_export",
                "confirmation": confirmation_record(
                    enforced=args.require_confirmation,
                    confirmation_id=args.confirmation_id,
                ),
            },
            command="keynote_export.py",
            notes=payload["notes"],
        )


if __name__ == "__main__":
    main()
