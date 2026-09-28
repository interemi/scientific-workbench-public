#!/usr/bin/env python3
"""Locate and use the dedicated datanalysis environment for heavy workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from _internal.astro_cli_output_safety import preflight_astro_cli
from _internal.provenance_utils import app_ready_fields, public_path, sanitize_payload
from _internal.runtime_common import configure_runtime, find_executable


ENV_NAME = "datanalysis"
ENV_PYTHON_OVERRIDE = "DATAANALYSIS_PYTHON"
ENV_ROOT_OVERRIDE = "DATAANALYSIS_ENV_ROOT"
SKILL_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT_YML = SKILL_ROOT / "environment.yml"


def parse_args(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "python":
        return argparse.Namespace(command="python", python_args=argv[1:])
    if argv and argv[0] == "doctor":
        return argparse.Namespace(command="doctor", doctor_args=argv[1:])

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show whether datanalysis exists and the next recommended action.")
    status.add_argument("--summary-json")

    locate = subparsers.add_parser("locate", help="Locate the datanalysis environment.")
    locate.add_argument("--summary-json")

    recovery = subparsers.add_parser("recovery", help="Show the most likely recovery commands for recreating datanalysis.")
    recovery.add_argument("--summary-json")

    quickstart = subparsers.add_parser("quickstart", help="Show the recommended create-and-verify commands for datanalysis.")
    quickstart.add_argument("--summary-json")

    python_cmd = subparsers.add_parser("python", help="Run Python inside datanalysis.")
    python_cmd.add_argument("python_args", nargs=argparse.REMAINDER)

    run_script = subparsers.add_parser("run-script", help="Run a script path inside datanalysis. Prefer run-tool for skill-owned scripts.")
    run_script.add_argument("script")
    run_script.add_argument("script_args", nargs=argparse.REMAINDER)

    run_tool = subparsers.add_parser("run-tool", help="Run a skill script by tool name inside datanalysis.")
    run_tool.add_argument("tool_name")
    run_tool.add_argument("tool_args", nargs=argparse.REMAINDER)

    doctor = subparsers.add_parser("doctor", help="Run env_doctor.py inside datanalysis.")
    doctor.add_argument("doctor_args", nargs=argparse.REMAINDER)

    health = subparsers.add_parser("healthcheck", help="Run the datanalysis healthcheck helper.")
    health.add_argument("--summary-json")
    health.add_argument("--manifest-json")

    return parser.parse_args(argv)


def candidate_conda_roots() -> list[Path]:
    roots = []
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        prefix_path = Path(conda_prefix).resolve()
        if prefix_path.name == ENV_NAME and prefix_path.parent.name == "envs":
            roots.append(prefix_path.parent.parent)
        else:
            roots.append(prefix_path)
    conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe:
        roots.append(Path(conda_exe).resolve().parent.parent)
    conda_bin = find_executable(["conda"])
    if conda_bin:
        roots.append(Path(conda_bin).resolve().parent.parent)
    roots.extend(
        [
            Path.home() / "anaconda3",
            Path.home() / "opt" / "anaconda3",
            Path("/opt/anaconda3"),
            Path.home() / "miniconda3",
            Path.home() / "mambaforge",
        ]
    )
    environments_txt = Path.home() / ".conda" / "environments.txt"
    if environments_txt.exists():
        try:
            for raw_line in environments_txt.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                env_path = Path(line).expanduser()
                if env_path.name == ENV_NAME:
                    roots.append(env_path.parent.parent if env_path.parent.name == "envs" else env_path.parent)
                elif env_path.name == "envs":
                    roots.append(env_path.parent)
                elif env_path.is_dir():
                    roots.append(env_path)
        except OSError:
            pass
    deduped = []
    seen = set()
    for root in roots:
        resolved = str(root)
        if resolved not in seen:
            deduped.append(root)
            seen.add(resolved)
    return deduped


def override_candidate() -> dict | None:
    python_override = os.environ.get(ENV_PYTHON_OVERRIDE)
    if python_override:
        python_path = Path(python_override).expanduser().resolve()
        if python_path.exists():
            env_root = python_path.parent.parent if python_path.parent.name in {"bin", "Scripts"} else python_path.parent
            return {"kind": "override-python", "root": env_root.parent, "env_root": env_root, "python": python_path}
    root_override = os.environ.get(ENV_ROOT_OVERRIDE)
    if root_override:
        env_root = Path(root_override).expanduser().resolve()
        if env_root.exists():
            python_candidates = [env_root / "bin" / "python", env_root / "python.exe"]
            for python_path in python_candidates:
                if python_path.exists():
                    return {"kind": "override-root", "root": env_root.parent, "env_root": env_root, "python": python_path}
    current_python = Path(sys.executable).resolve()
    parts = current_python.parts
    if ENV_NAME in parts:
        for index, part in enumerate(parts):
            if part == ENV_NAME:
                env_root = Path(*parts[: index + 1])
                break
        else:
            env_root = current_python.parent
        return {"kind": "current-python", "root": env_root.parent, "env_root": env_root, "python": current_python}
    return None


def is_usable_python(python_path: Path) -> bool:
    if not python_path.exists() or not python_path.is_file():
        return False
    try:
        completed = subprocess.run(
            [str(python_path), "-c", "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def add_candidate(raw_candidates: list[dict], invalid_candidates: list[dict], candidate: dict) -> None:
    python_path = Path(candidate["python"])
    if is_usable_python(python_path):
        raw_candidates.append(candidate)
        return
    invalid_candidates.append(
        {
            "kind": candidate.get("kind"),
            "python": python_path,
            "reason": "exists_but_is_not_a_usable_python3_interpreter",
        }
    )


def locate_env_real() -> dict:
    candidates = []
    invalid_candidates = []
    overridden = override_candidate()
    if overridden is not None:
        add_candidate(candidates, invalid_candidates, overridden)
    checked = candidate_conda_roots()
    for root in checked:
        env_root = root / "envs" / ENV_NAME
        python_bin = env_root / "bin" / "python"
        if python_bin.exists():
            add_candidate(
                candidates,
                invalid_candidates,
                {"kind": "conda-env", "root": root, "env_root": env_root, "python": python_bin},
            )
        win_python = env_root / "python.exe"
        if win_python.exists():
            add_candidate(
                candidates,
                invalid_candidates,
                {"kind": "conda-env", "root": root, "env_root": env_root, "python": win_python},
            )
    return {
        "env_name": ENV_NAME,
        "found": bool(candidates),
        "selected": candidates[0] if candidates else None,
        "candidates_checked": [{"root": root, "env_root": root / "envs" / ENV_NAME} for root in checked],
        "invalid_candidates": invalid_candidates,
    }


def build_recovery_hint(payload: dict) -> str | None:
    if payload["found"]:
        return None
    for item in payload["candidates_checked"]:
        root = Path(item["root"])
        if not root.exists():
            continue
        conda_bin = root / "bin" / "conda"
        env_root = Path(item["env_root"])
        if conda_bin.exists():
            return (
                f"Base Conda install found at {public_path(root)} but {public_path(env_root)} is missing. "
                f"Try: {public_path(conda_bin)} env create -f {public_path(ENVIRONMENT_YML)} "
                f"or {public_path(conda_bin)} create -n {ENV_NAME} python=3.11 pip"
            )
        return (
            f"Base Python/Conda-style root found at {public_path(root)} but {public_path(env_root)} is missing. "
            f"Create the environment from {public_path(ENVIRONMENT_YML)} or point the skill at the correct interpreter with "
            f"{ENV_PYTHON_OVERRIDE} or {ENV_ROOT_OVERRIDE}."
        )
    return (
        f"No obvious Conda base was found. Create the environment from {public_path(ENVIRONMENT_YML)} "
        f"or set {ENV_PYTHON_OVERRIDE} / {ENV_ROOT_OVERRIDE} explicitly."
    )


def build_recovery_plan(payload: dict) -> dict:
    commands = []
    base_root = None
    conda_bin = None
    recommended_create_command = None
    recommended_verify_command = None
    for item in payload["candidates_checked"]:
        root = Path(item["root"])
        if not root.exists():
            continue
        base_root = root
        candidate_conda = root / "bin" / "conda"
        if candidate_conda.exists():
            conda_bin = candidate_conda
            recommended_create_command = f"{public_path(candidate_conda)} env create -f {public_path(ENVIRONMENT_YML)}"
            recommended_verify_command = (
                f"{public_path(candidate_conda)} run -n {ENV_NAME} python {public_path(Path(__file__).resolve())} "
                "doctor --summary-json datanalysis_doctor.json"
            )
            commands = [
                recommended_create_command,
                f"{public_path(candidate_conda)} create -n {ENV_NAME} python=3.11 pip",
                recommended_verify_command,
            ]
            break
        commands = [
            f"Create the environment from {public_path(ENVIRONMENT_YML)} in the detected base install.",
            f"Or point the skill at the correct interpreter with {ENV_PYTHON_OVERRIDE} / {ENV_ROOT_OVERRIDE}.",
        ]
        break
    if not commands:
        commands = [
            f"Create the environment from {public_path(ENVIRONMENT_YML)}.",
            f"Or point the skill at the correct interpreter with {ENV_PYTHON_OVERRIDE} / {ENV_ROOT_OVERRIDE}.",
        ]
    return {
        "env_name": ENV_NAME,
        "base_root": public_path(base_root) if base_root else None,
        "conda_bin": public_path(conda_bin) if conda_bin else None,
        "environment_yml": public_path(ENVIRONMENT_YML),
        "recommended_create_command": recommended_create_command,
        "recommended_verify_command": recommended_verify_command,
        "commands": commands,
        "note": "Use these commands after a Conda or Anaconda reinstall when the base install exists but the datanalysis environment does not.",
    }


def locate_env() -> dict:
    payload = locate_env_real()
    found = payload["selected"]
    warnings = [
        {
            "kind": item.get("kind"),
            "python": public_path(item.get("python")),
            "reason": item.get("reason"),
        }
        for item in payload.get("invalid_candidates", [])
    ]
    return {
        "env_name": ENV_NAME,
        "found": payload["found"],
        "selected": None
        if found is None
        else {
            "kind": found["kind"],
            "root": public_path(found["root"]),
            "env_root": public_path(found["env_root"]),
            "python": public_path(found["python"]),
        },
        "candidates_checked": [
            {"root": public_path(item["root"]), "env_root": public_path(item["env_root"])}
            for item in payload["candidates_checked"]
        ],
        "warnings": warnings,
        "recovery_hint": build_recovery_hint(payload),
        "recovery_plan": build_recovery_plan(payload),
    }


def build_status_payload() -> dict:
    locate_payload = locate_env()
    selected = locate_payload.get("selected") or {}
    found = bool(locate_payload["found"])
    legacy_warnings = locate_payload.get("warnings", [])
    if locate_payload["found"]:
        next_step = f"python {public_path(Path(__file__).resolve())} doctor --summary-json datanalysis_doctor.json"
    else:
        recovery = locate_payload.get("recovery_plan") or {}
        next_step = recovery.get("recommended_create_command") or "python scripts/datanalysis_env.py recovery"
    payload = {
        "tool": "datanalysis_env.status",
        "status": "ok" if found else "blocked",
        "env_name": ENV_NAME,
        "found": found,
        "selected_python": selected.get("python"),
        "selected_env_root": selected.get("env_root"),
        "next_step": next_step,
        "recovery_hint": locate_payload.get("recovery_hint"),
        "warnings": legacy_warnings,
    }
    notes = [
        "Dedicated datanalysis environment status for heavy notebook, FITS, and scientific workflows.",
    ]
    warning_findings = [
        f"{item.get('kind') or 'candidate'}: {item.get('reason') or 'warning'}"
        for item in legacy_warnings
    ]
    findings = warning_findings if found else [locate_payload.get("recovery_hint") or "datanalysis environment was not found."]
    app_fields = app_ready_fields(
        "datanalysis_env.status",
        "ok" if found else "blocked",
        notes=notes,
        artifacts={},
        qa={
            "status": "warning" if found and legacy_warnings else "ok" if found else "blocked",
            "findings": findings,
            "metrics": {"found": found, "invalid_candidate_count": len(legacy_warnings)},
        },
    )
    payload.update(app_fields)
    payload["warnings"] = legacy_warnings
    payload.setdefault("app_warnings", app_fields.get("warnings", []))
    return payload


def write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"Could not write JSON summary to {public_path(target)}: {exc.__class__.__name__}: {exc}"
        ) from None


def ensure_env_python() -> str:
    payload = locate_env_real()
    if not payload["found"]:
        recovery_hint = build_recovery_hint(payload)
        recovery_command = f"python {public_path(Path(__file__).resolve())} recovery"
        raise SystemExit(
            "Could not locate the 'datanalysis' environment. "
            "Try setting DATAANALYSIS_PYTHON or DATAANALYSIS_ENV_ROOT, "
            f"or create it from the skill environment definition. Run `{recovery_command}` for exact commands. "
            + (recovery_hint or "")
        )
    return str(Path(payload["selected"]["python"]).resolve())


def resolve_tool_script(tool_name: str) -> Path:
    body_dir = Path(__file__).resolve().parent
    skill_root = body_dir.parent if body_dir.name in {"fixtures", "scripts"} else body_dir
    public_scripts_dir = skill_root / "scripts"
    scripts_dir = public_scripts_dir if public_scripts_dir.is_dir() else body_dir
    candidate = scripts_dir / tool_name
    if candidate.exists():
        return candidate
    if not tool_name.endswith(".py"):
        candidate_py = scripts_dir / f"{tool_name}.py"
        if candidate_py.exists():
            return candidate_py
    available = sorted(path.name for path in scripts_dir.glob("*.py"))
    preview = ", ".join(available[:12])
    suffix = "" if len(available) <= 12 else ", ..."
    raise SystemExit(
        f"Could not resolve tool '{tool_name}' inside {public_path(scripts_dir)}. "
        f"Available examples: {preview}{suffix}"
    )


def resolve_public_script(script: str | Path) -> Path:
    """Route a skill-owned fixture body through its public safety wrapper."""
    candidate = Path(script).expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return candidate
    if resolved.parent.name != "fixtures":
        return candidate
    wrapper = resolved.parent.parent / "scripts" / resolved.name
    return wrapper if wrapper.is_file() else candidate


def run_command(cmd: list[str]) -> int:
    configure_runtime("datanalysis_env")
    completed = subprocess.run(cmd)
    return completed.returncode


def main():
    args = parse_args()
    if args.command == "status":
        payload = build_status_payload()
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
        print(rendered)
        if args.summary_json:
            write_json(args.summary_json, payload)
        raise SystemExit(0 if payload["found"] else 1)
    if args.command == "locate":
        payload = locate_env()
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
        print(rendered)
        if args.summary_json:
            write_json(args.summary_json, payload)
        raise SystemExit(0 if payload["found"] else 1)
    if args.command == "recovery":
        payload = build_recovery_plan(locate_env_real())
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
        print(rendered)
        if args.summary_json:
            write_json(args.summary_json, payload)
        raise SystemExit(0)
    if args.command == "quickstart":
        payload = build_recovery_plan(locate_env_real())
        quickstart = {
            "env_name": payload["env_name"],
            "recommended_create_command": payload["recommended_create_command"],
            "recommended_verify_command": payload["recommended_verify_command"],
            "note": "Run the create command first, then the verify command.",
        }
        rendered = json.dumps(quickstart, indent=2, ensure_ascii=True)
        print(rendered)
        if args.summary_json:
            write_json(args.summary_json, quickstart)
        raise SystemExit(0)

    if args.command == "run-script":
        safe_script = resolve_public_script(args.script)
        safety_returncode = preflight_astro_cli(safe_script, args.script_args)
        if safety_returncode is not None:
            raise SystemExit(safety_returncode)
    if args.command == "run-tool":
        tool_script = resolve_tool_script(args.tool_name)
        safety_returncode = preflight_astro_cli(tool_script, args.tool_args)
        if safety_returncode is not None:
            raise SystemExit(safety_returncode)

    env_python = ensure_env_python()
    if args.command == "python":
        raise SystemExit(run_command([env_python, *args.python_args]))
    if args.command == "run-script":
        raise SystemExit(run_command([env_python, str(safe_script), *args.script_args]))
    if args.command == "run-tool":
        raise SystemExit(run_command([env_python, str(tool_script), *args.tool_args]))
    if args.command == "doctor":
        tool_script = resolve_tool_script("env_doctor.py")
        raise SystemExit(run_command([env_python, str(tool_script), *args.doctor_args]))

    healthcheck_script = Path(__file__).with_name("datanalysis_healthcheck.py")
    cmd = [env_python, str(healthcheck_script)]
    if args.summary_json:
        cmd.extend(["--summary-json", args.summary_json])
    if args.manifest_json:
        cmd.extend(["--manifest-json", args.manifest_json])
    raise SystemExit(run_command(cmd))


if __name__ == "__main__":
    main()
