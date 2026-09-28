#!/usr/bin/env python3
"""Optional local validation for real STILTS/TOPCAT and APT backends."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import public_path, standard_qa_payload
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.runtime_common import clean_known_stderr
from maintainer_path_safety import PathSafetyError, ensure_safe_paths, operand


ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRIPTS = ROOT / "scripts"
ASTRO_SCRIPTS = ROOT.parent / "scientific-data-astro" / "scripts"
SCRIPTS = ASTRO_SCRIPTS if (ASTRO_SCRIPTS / "external_astro_tools_preflight.py").is_file() else LOCAL_SCRIPTS


def _explicit_command_path(value: str | None) -> Path | None:
    """Resolve explicit executable paths without treating a PATH token as a file."""

    if not value:
        return None
    discovered = shutil.which(value)
    if discovered:
        return Path(discovered)
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or os.sep in value or (os.altsep and os.altsep in value) or candidate.exists():
        return candidate
    return None


def ensure_external_validation_paths(args: argparse.Namespace) -> None:
    """Fail closed before synthetic artifacts can overlap backend inputs."""

    input_paths = [
        operand("--stilts-command", _explicit_command_path(args.stilts_command)),
        operand("--stilts-jar", args.stilts_jar, tree=bool(args.stilts_jar and Path(args.stilts_jar).expanduser().is_dir())),
        operand("--topcat-command", _explicit_command_path(args.topcat_command)),
        operand("--topcat-jar", args.topcat_jar, tree=bool(args.topcat_jar and Path(args.topcat_jar).expanduser().is_dir())),
        operand("--java-command", _explicit_command_path(args.java_command)),
        operand("--apt-command", _explicit_command_path(args.apt_command)),
        operand(
            "--apt-preferences",
            args.apt_preferences,
            tree=bool(args.apt_preferences and Path(args.apt_preferences).expanduser().is_dir()),
        ),
    ]
    output_dir = Path(args.output_dir).expanduser()
    planned_names = [
        "external_astro_preflight.json",
        "stilts_left.csv",
        "stilts_right.csv",
        "stilts_matched.csv",
        "stilts_crossmatch_summary.json",
        "stilts_crossmatch_manifest.json",
        "apt_sources.csv",
        "apt_sources.lst",
        "apt_synthetic_image.fits",
        "apt_source_list_summary.json",
        "apt_source_list_manifest.json",
        "APT.tbl",
        "apt_batch_summary.json",
        "apt_batch_manifest.json",
    ]
    output_paths = [
        operand("--output-dir", output_dir, tree=True),
        operand("--summary-json", args.summary_json),
        *(operand(f"generated artifact {name}", output_dir / name) for name in planned_names),
        operand("generated STILTS log directory", output_dir / "stilts_logs", tree=True),
        operand("generated APT log directory", output_dir / "apt_logs", tree=True),
    ]
    ensure_safe_paths(inputs=input_paths, outputs=output_paths)


def run_command(command: list[str], timeout_sec: int) -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            env=env,
        )
        return {
            "command": [public_path(item) for item in command],
            "returncode": completed.returncode,
            "stdout_tail": (completed.stdout or "")[-3000:],
            "stderr_tail": (completed.stderr or "")[-3000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": [public_path(item) for item in command],
            "returncode": 124,
            "stdout_tail": (exc.stdout or "")[-3000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }
    except OSError as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or exc.__class__.__name__
        return {
            "command": [public_path(item) for item in command],
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": message,
            "timed_out": False,
            "launch_error": True,
        }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def remove_generated_artifacts(paths: list[Path]) -> str | None:
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except OSError as exc:
            return clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
    return None


def build_blocked_payload(args: argparse.Namespace, message: str, output_dir: Path | None = None) -> dict:
    return build_tool_payload(
        "external_astro_tools_local_validation",
        status="blocked",
        notes=["Local backend validation was blocked before trustworthy validation artifacts could be produced."],
        artifacts={},
        results={
            "tool_selection": args.tool,
            "include_apt_batch": args.include_apt_batch,
            "blocking_findings": [message],
            "validations": [],
        },
        qa=standard_qa_payload(
            status="blocked",
            findings=[message],
            metrics={
                "validation_count": 0,
                "pass_count": 0,
                "fail_count": 0,
                "blocked_required_count": 1,
                "blocked_controlado_count": 0,
            },
        ),
        include_environment=True,
    )


def add_backend_flags(command: list[str], args: argparse.Namespace, family: str) -> list[str]:
    pairs = []
    if family == "stilts":
        pairs = [
            ("--stilts-command", args.stilts_command),
            ("--stilts-jar", args.stilts_jar),
            ("--topcat-command", args.topcat_command),
            ("--topcat-jar", args.topcat_jar),
        ]
    elif family == "apt":
        pairs = [
            ("--apt-command", args.apt_command),
            ("--apt-preferences", args.apt_preferences),
        ]
    for flag, value in pairs:
        if value:
            command.extend([flag, value])
    return command


def write_catalog_fixtures(root: Path) -> tuple[Path, Path]:
    left = root / "stilts_left.csv"
    right = root / "stilts_right.csv"
    left.write_text("id,ra,dec,mag\nA,10.000000,20.000000,15.1\nB,11.0,21.0,18.5\n", encoding="utf-8")
    right.write_text("id,ra,dec,color\nX,10.000050,20.000040,0.7\nY,30.0,40.0,1.2\n", encoding="utf-8")
    return left, right


def write_apt_fixtures(root: Path) -> tuple[Path, Path, Path]:
    sources = root / "apt_sources.csv"
    sources.write_text("id,x,y\nA,12,18\nB,30,45\n", encoding="utf-8")
    image = root / "apt_synthetic_image.fits"
    try:
        from astropy.io import fits
        import numpy as np

        data = np.zeros((64, 64), dtype="float32")
        data[18, 12] = 1000.0
        data[45, 30] = 700.0
        fits.PrimaryHDU(data=data).writeto(image, overwrite=True)
    except Exception:
        image.write_text("Synthetic FITS placeholder for APT dry-run validation only.\n", encoding="utf-8")
    source_list = root / "apt_sources.lst"
    return sources, source_list, image


def run_preflight(args: argparse.Namespace, output_dir: Path) -> tuple[dict, dict]:
    summary = output_dir / "external_astro_preflight.json"
    cleanup_error = remove_generated_artifacts([summary])
    if cleanup_error:
        return {
            "command": [],
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": cleanup_error,
            "timed_out": False,
        }, {}
    command = [
        sys.executable,
        str(SCRIPTS / "external_astro_tools_preflight.py"),
        "--probe",
        "--summary-json",
        str(summary),
    ]
    if args.java_command:
        command.extend(["--java-command", args.java_command])
    add_backend_flags(command, args, "stilts")
    add_backend_flags(command, args, "apt")
    if args.require_stilts:
        command.append("--require-stilts")
    if args.require_apt:
        command.append("--require-apt")
    run = run_command(command, args.timeout_sec)
    payload = read_json(summary) if summary.exists() else {}
    return run, payload


def validate_stilts(args: argparse.Namespace, output_dir: Path, capabilities: dict) -> dict:
    if not capabilities.get("stilts_ready"):
        status = "blocked" if args.require_stilts else "BLOCKED_CONTROLADO"
        return {
            "id": "stilts_real_crossmatch",
            "status": status,
            "finding": "STILTS is not locally ready; install/configure it or keep using catalog_workbench.py for Python-native catalog work.",
        }

    left, right = write_catalog_fixtures(output_dir)
    matched = output_dir / "stilts_matched.csv"
    summary = output_dir / "stilts_crossmatch_summary.json"
    manifest = output_dir / "stilts_crossmatch_manifest.json"
    cleanup_error = remove_generated_artifacts([matched, summary, manifest, output_dir / "stilts_logs"])
    if cleanup_error:
        return {
            "id": "stilts_real_crossmatch",
            "status": "FAIL",
            "finding": f"Could not clear stale STILTS validation artifacts: {cleanup_error}",
            "stderr_tail": cleanup_error,
        }
    command = [
        sys.executable,
        str(SCRIPTS / "stilts_workbench.py"),
        "crossmatch-sky",
        str(left),
        str(right),
        str(matched),
        "--left-ra",
        "ra",
        "--left-dec",
        "dec",
        "--right-ra",
        "ra",
        "--right-dec",
        "dec",
        "--radius-arcsec",
        "1.0",
        "--ofmt",
        "csv",
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
        "--log-dir",
        str(output_dir / "stilts_logs"),
    ]
    add_backend_flags(command, args, "stilts")
    run = run_command(command, args.timeout_sec)
    payload = read_json(summary) if summary.exists() else {}
    ok = run["returncode"] == 0 and payload.get("status") == "ok" and matched.exists() and manifest.exists()
    return {
        "id": "stilts_real_crossmatch",
        "status": "PASS" if ok else "FAIL",
        "command": run["command"],
        "summary_json": public_path(summary) if summary.exists() else None,
        "manifest_json": public_path(manifest) if manifest.exists() else None,
        "output_table": public_path(matched) if matched.exists() else None,
        "returncode": run["returncode"],
        "finding": None if ok else "Real STILTS crossmatch fixture did not complete cleanly.",
        "stderr_tail": run["stderr_tail"],
    }


def validate_apt(args: argparse.Namespace, output_dir: Path, capabilities: dict) -> dict:
    sources, source_list, image = write_apt_fixtures(output_dir)
    prep_summary = output_dir / "apt_source_list_summary.json"
    prep_manifest = output_dir / "apt_source_list_manifest.json"
    cleanup_error = remove_generated_artifacts([source_list, prep_summary, prep_manifest])
    if cleanup_error:
        return {
            "id": "apt_source_list",
            "status": "FAIL",
            "finding": f"Could not clear stale APT source-list artifacts: {cleanup_error}",
            "stderr_tail": cleanup_error,
        }
    prep_command = [
        sys.executable,
        str(SCRIPTS / "apt_workbench.py"),
        "prepare-source-list",
        str(sources),
        str(source_list),
        "--x-col",
        "x",
        "--y-col",
        "y",
        "--id-col",
        "id",
        "--summary-json",
        str(prep_summary),
        "--manifest-json",
        str(prep_manifest),
    ]
    prep_run = run_command(prep_command, args.timeout_sec)
    prep_payload = read_json(prep_summary) if prep_summary.exists() else {}
    if prep_run["returncode"] != 0 or prep_payload.get("status") not in {"ok", "warning"}:
        return {
            "id": "apt_source_list",
            "status": "FAIL",
            "finding": "APT source-list preparation failed before backend validation.",
            "command": prep_run["command"],
            "stderr_tail": prep_run["stderr_tail"],
        }

    if not capabilities.get("apt_batch_ready"):
        status = "blocked" if args.require_apt else "BLOCKED_CONTROLADO"
        return {
            "id": "apt_batch_validation",
            "status": status,
            "source_list": public_path(source_list),
            "finding": "APT batch is not locally ready; configure APT, save APT.pref, and rerun this validation when APT is explicitly needed.",
        }

    output_table = output_dir / "APT.tbl"
    batch_summary = output_dir / "apt_batch_summary.json"
    batch_manifest = output_dir / "apt_batch_manifest.json"
    cleanup_error = remove_generated_artifacts([output_table, batch_summary, batch_manifest, output_dir / "apt_logs"])
    if cleanup_error:
        return {
            "id": "apt_batch_validation",
            "status": "FAIL",
            "finding": f"Could not clear stale APT batch artifacts: {cleanup_error}",
            "stderr_tail": cleanup_error,
        }
    batch_command = [
        sys.executable,
        str(SCRIPTS / "apt_workbench.py"),
        "run-batch",
        "--image",
        str(image),
        "--source-list",
        str(source_list),
        "--output-table",
        str(output_table),
        "--summary-json",
        str(batch_summary),
        "--manifest-json",
        str(batch_manifest),
        "--log-dir",
        str(output_dir / "apt_logs"),
    ]
    add_backend_flags(batch_command, args, "apt")
    if not args.include_apt_batch:
        batch_command.append("--dry-run")
    batch_run = run_command(batch_command, args.timeout_sec)
    batch_payload = read_json(batch_summary) if batch_summary.exists() else {}
    if args.include_apt_batch:
        ok = batch_run["returncode"] == 0 and batch_payload.get("status") == "ok" and output_table.exists()
        mode = "real_batch"
    else:
        ok = batch_run["returncode"] == 0 and batch_payload.get("status") == "ok"
        mode = "dry_run"
    return {
        "id": "apt_batch_validation",
        "status": "PASS" if ok else "FAIL",
        "mode": mode,
        "source_list": public_path(source_list),
        "image": public_path(image),
        "summary_json": public_path(batch_summary) if batch_summary.exists() else None,
        "manifest_json": public_path(batch_manifest) if batch_manifest.exists() else None,
        "output_table": public_path(output_table) if output_table.exists() else None,
        "returncode": batch_run["returncode"],
        "finding": None if ok else "APT batch validation did not complete cleanly.",
        "stdout_tail": batch_run["stdout_tail"] if not ok else "",
        "stderr_tail": batch_run["stderr_tail"],
    }


def build_payload(args: argparse.Namespace) -> dict:
    ensure_external_validation_paths(args)
    output_dir = Path(args.output_dir)
    if args.timeout_sec <= 0:
        return build_blocked_payload(args, "--timeout-sec must be a positive integer.", output_dir=output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        return build_blocked_payload(args, f"Output directory path exists and is not a directory: {output_dir}", output_dir=output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        return build_blocked_payload(args, f"Could not create output directory: {message}", output_dir=output_dir)
    preflight_run, preflight_payload = run_preflight(args, output_dir)
    capabilities = ((preflight_payload.get("results") or {}).get("capabilities") or {})
    validations = [
        {
            "id": "external_astro_preflight_probe",
            "status": "PASS" if preflight_run["returncode"] in {0, 2} and preflight_payload else "FAIL",
            "summary_json": public_path(output_dir / "external_astro_preflight.json"),
            "returncode": preflight_run["returncode"],
            "finding": None if preflight_payload else "External astronomy preflight did not emit JSON.",
        }
    ]
    if args.tool in {"all", "stilts"}:
        validations.append(validate_stilts(args, output_dir, capabilities))
    if args.tool in {"all", "apt"}:
        validations.append(validate_apt(args, output_dir, capabilities))

    failed = [item for item in validations if item["status"] == "FAIL"]
    blocked_required = [item for item in validations if item["status"] == "blocked"]
    controlled = [item for item in validations if item["status"] == "BLOCKED_CONTROLADO"]
    findings = [item.get("finding") for item in validations if item.get("finding")]
    status = "fail" if failed else ("blocked" if blocked_required else ("warning" if controlled or preflight_payload.get("status") == "warning" else "ok"))
    payload = build_tool_payload(
        "external_astro_tools_local_validation",
        status=status,
        notes=[
            "This maintainer validation uses tiny synthetic inputs and only exercises real STILTS/APT backends when they are locally configured.",
            "Missing STILTS or APT is a controlled optional-backend result unless --require-stilts or --require-apt is used.",
            "APT defaults to dry-run validation; pass --include-apt-batch only when the saved APT.pref is intentionally ready for a real batch run.",
        ],
        artifacts={
            "output_dir": output_dir,
            "summary_json": args.summary_json,
            "preflight_json": output_dir / "external_astro_preflight.json",
        },
        results={
            "tool_selection": args.tool,
            "include_apt_batch": args.include_apt_batch,
            "capabilities": capabilities,
            "validations": validations,
        },
        qa=standard_qa_payload(
            status=status,
            findings=findings,
            metrics={
                "validation_count": len(validations),
                "pass_count": sum(1 for item in validations if item["status"] == "PASS"),
                "fail_count": len(failed),
                "blocked_required_count": len(blocked_required),
                "blocked_controlado_count": len(controlled),
            },
        ),
        include_environment=True,
    )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=["all", "stilts", "apt"], default="all", help="Backend family to validate.")
    parser.add_argument("--output-dir", default="external_astro_local_validation", help="Directory for synthetic fixtures and validation artifacts.")
    parser.add_argument("--summary-json", help="Optional standard-envelope JSON summary path.")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--require-stilts", action="store_true", help="Treat missing STILTS as blocked instead of controlled optional absence.")
    parser.add_argument("--require-apt", action="store_true", help="Treat missing APT batch readiness as blocked instead of controlled optional absence.")
    parser.add_argument("--include-apt-batch", action="store_true", help="Run a real APT batch fixture instead of the default dry-run command validation.")
    parser.add_argument("--stilts-command", help="Explicit stilts command or wrapper.")
    parser.add_argument("--stilts-jar", help="Path to stilts.jar; executed via java -jar.")
    parser.add_argument("--topcat-command", help="Explicit TOPCAT command usable with -stilts.")
    parser.add_argument("--topcat-jar", help="Path to TOPCAT jar; used with -stilts if no standalone STILTS is found.")
    parser.add_argument("--java-command", help="Explicit java command for preflight validation.")
    parser.add_argument("--apt-command", help="Explicit APT.csh/APT.bat command.")
    parser.add_argument("--apt-preferences", help="Path to saved APT.pref.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_payload(args)
    except PathSafetyError as exc:
        payload = build_blocked_payload(args, str(exc), output_dir=Path(args.output_dir).expanduser())
        # The requested summary itself may be the protected input.  A safety
        # failure is therefore emitted to stdout only.
        emit_payload(payload, None)
        return 2
    try:
        emit_payload(payload, args.summary_json)
    except OSError as exc:
        message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
        print(message, file=sys.stderr)
        return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
