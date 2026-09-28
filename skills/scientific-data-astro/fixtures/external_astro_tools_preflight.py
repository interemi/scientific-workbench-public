#!/usr/bin/env python3
"""Preflight external astronomy tools such as Java, STILTS/TOPCAT, and APT."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import public_path, standard_qa_payload
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.runtime_common import clean_known_stderr, find_executable


DEFAULT_APT_PREF = Path.home() / ".AperturePhotometryTool" / "APT.pref"
DEFAULT_APT_APP_JAR = Path("/Applications/Aperture Photometry Tool.app/Contents/Resources/Java/APT.jar")


def split_command(spec: str | None) -> list[str] | None:
    if not spec:
        return None
    direct = Path(str(spec)).expanduser()
    if direct.exists():
        return [str(direct.resolve())]
    parts = shlex.split(str(spec))
    if not parts:
        return None
    first = Path(parts[0]).expanduser()
    if first.exists():
        parts[0] = str(first.resolve())
        return parts
    resolved = shutil.which(parts[0])
    if resolved:
        parts[0] = resolved
        return parts
    return parts


def command_launchable(command: list[str] | None) -> bool:
    if not command:
        return False
    first = command[0]
    path = Path(first)
    if path.exists():
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(first) is not None


def command_display(command: list[str] | None) -> str | None:
    if not command:
        return None
    return shlex.join([public_path(item) for item in command])


def resolve_java_command(java_command: str | None = None) -> dict:
    explicit = split_command(java_command or os.environ.get("JAVA_COMMAND"))
    if explicit:
        return {"found": command_launchable(explicit), "source": "explicit", "command": explicit}
    java = find_executable(["java"])
    return {"found": bool(java), "source": "PATH" if java else None, "command": [java] if java else None}


def resolve_topcat_command(topcat_command: str | None = None, topcat_jar: str | None = None, java_command: str | None = None) -> dict:
    explicit = split_command(topcat_command or os.environ.get("TOPCAT_COMMAND"))
    if explicit:
        return {"found": command_launchable(explicit), "source": "explicit", "command": explicit}
    jar = topcat_jar or os.environ.get("TOPCAT_JAR")
    if jar:
        jar_path = Path(jar).expanduser()
        java = resolve_java_command(java_command)
        if jar_path.exists() and java["found"]:
            return {"found": True, "source": "topcat_jar", "command": [*java["command"], "-jar", str(jar_path.resolve())]}
    topcat = find_executable(["topcat"])
    return {"found": bool(topcat), "source": "PATH" if topcat else None, "command": [topcat] if topcat else None}


def resolve_stilts_command(
    stilts_command: str | None = None,
    stilts_jar: str | None = None,
    topcat_command: str | None = None,
    topcat_jar: str | None = None,
    java_command: str | None = None,
) -> dict:
    explicit = split_command(stilts_command or os.environ.get("STILTS_COMMAND"))
    if explicit:
        return {"found": command_launchable(explicit), "source": "explicit", "command": explicit}
    stilts = find_executable(["stilts"])
    if stilts:
        return {"found": True, "source": "PATH", "command": [stilts]}
    jar = stilts_jar or os.environ.get("STILTS_JAR")
    if jar:
        jar_path = Path(jar).expanduser()
        java = resolve_java_command(java_command)
        if jar_path.exists() and java["found"]:
            return {"found": True, "source": "stilts_jar", "command": [*java["command"], "-jar", str(jar_path.resolve())]}
    topcat = resolve_topcat_command(topcat_command=topcat_command, topcat_jar=topcat_jar, java_command=java_command)
    if topcat["found"]:
        return {"found": True, "source": "topcat_stilts_mode", "command": [*topcat["command"], "-stilts"]}
    return {"found": False, "source": None, "command": None}


def resolve_apt_command(apt_command: str | None = None) -> dict:
    explicit = split_command(apt_command or os.environ.get("APT_COMMAND"))
    if explicit:
        return {"found": command_launchable(explicit), "source": "explicit", "command": explicit}
    apt = find_executable(["APT.csh", "APT.bat", "AperturePhotometryTool"])
    if apt:
        return {"found": True, "source": "PATH", "command": [apt]}
    java = resolve_java_command()
    if DEFAULT_APT_APP_JAR.exists() and java["found"]:
        return {
            "found": True,
            "source": "apt_app_jar",
            "command": [*java["command"], "-jar", str(DEFAULT_APT_APP_JAR)],
        }
    return {"found": False, "source": None, "command": None}


def resolve_apt_preferences(path: str | None = None) -> dict:
    candidate = Path(path or os.environ.get("APT_PREFERENCES") or DEFAULT_APT_PREF).expanduser()
    return {
        "found": candidate.is_file(),
        "exists": candidate.exists(),
        "is_file": candidate.is_file(),
        "path": candidate,
        "source": "explicit" if path or os.environ.get("APT_PREFERENCES") else "default",
    }


def probe(command: list[str] | None, args: list[str], timeout_sec: int = 20) -> dict:
    if not command:
        return {"attempted": False, "returncode": None, "stdout": "", "stderr": ""}
    try:
        completed = subprocess.run([*command, *args], capture_output=True, text=True, timeout=timeout_sec, check=False)
        return {
            "attempted": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-1200:],
            "stderr": completed.stderr[-1200:],
        }
    except OSError as exc:
        return {
            "attempted": True,
            "returncode": None,
            "stdout": "",
            "stderr": clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or exc.__class__.__name__,
            "launch_error": True,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "attempted": True,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-1200:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-1200:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }


def build_report(args: argparse.Namespace) -> dict:
    java = resolve_java_command(getattr(args, "java_command", None))
    topcat = resolve_topcat_command(
        getattr(args, "topcat_command", None),
        getattr(args, "topcat_jar", None),
        getattr(args, "java_command", None),
    )
    stilts = resolve_stilts_command(
        getattr(args, "stilts_command", None),
        getattr(args, "stilts_jar", None),
        getattr(args, "topcat_command", None),
        getattr(args, "topcat_jar", None),
        getattr(args, "java_command", None),
    )
    apt = resolve_apt_command(getattr(args, "apt_command", None))
    apt_pref = resolve_apt_preferences(getattr(args, "apt_preferences", None))

    probes = {}
    if getattr(args, "probe", False):
        probes["java"] = probe(java["command"] if java["found"] else None, ["-version"])
        probes["stilts"] = probe(stilts["command"] if stilts["found"] else None, [])
        probes["apt"] = probe(apt["command"] if apt["found"] else None, ["-h"])

    blocking = []
    warnings = []
    if getattr(args, "require_stilts", False) and not stilts["found"]:
        blocking.append("Optional backend unavailable: STILTS is required for the requested workflow, but no stilts command, STILTS_JAR, or TOPCAT STILTS mode was found.")
    if getattr(args, "require_apt", False) and not apt["found"]:
        blocking.append("APT is required for this workflow but no APT.csh/APT.bat command was found.")
    if getattr(args, "require_apt", False) and not apt_pref["found"]:
        blocking.append("APT batch mode is required but no APT preferences file was found; configure APT in GUI and save APT.pref first.")
    if (stilts["found"] or topcat["found"] or apt["found"]) and not java["found"]:
        blocking.append("Java is required by TOPCAT/STILTS/APT but no java executable was found.")
    if getattr(args, "probe", False):
        for label, required in (("java", stilts["found"] or topcat["found"] or apt["found"]), ("stilts", getattr(args, "require_stilts", False)), ("apt", getattr(args, "require_apt", False))):
            result = probes.get(label) or {}
            if not result.get("attempted"):
                continue
            failed = result.get("launch_error") or result.get("timed_out") or result.get("returncode") not in (0, None)
            if not failed:
                continue
            detail = result.get("stderr") or result.get("stdout") or "probe failed"
            message = f"{label} probe failed: {detail}"
            if required:
                blocking.append(message)
            else:
                warnings.append(message)

    if not stilts["found"]:
        warnings.append("STILTS is not available; use catalog_workbench.py for small/medium Python crossmatches or install STILTS for large/VO workflows.")
    if not apt["found"]:
        warnings.append("APT batch command is not available; use aperture_photometry.py/photutils unless APT is explicitly required.")
    if apt["found"] and not apt_pref["found"]:
        warnings.append("APT was found, but batch mode depends on a saved APT.pref preferences file.")
    if apt_pref["exists"] and not apt_pref["is_file"]:
        message = "APT preferences path exists but is not a regular file."
        if getattr(args, "require_apt", False):
            blocking.append(message)
        else:
            warnings.append(message)

    capabilities = {
        "java_ready": bool(java["found"]),
        "topcat_ready": bool(topcat["found"]),
        "stilts_ready": bool(stilts["found"] and java["found"]),
        "apt_command_ready": bool(apt["found"] and java["found"]),
        "apt_batch_ready": bool(apt["found"] and java["found"] and apt_pref["found"]),
    }
    results = {
        "capabilities": capabilities,
        "java": {**java, "command": command_display(java["command"])},
        "topcat": {**topcat, "command": command_display(topcat["command"])},
        "stilts": {**stilts, "command": command_display(stilts["command"])},
        "apt": {**apt, "command": command_display(apt["command"])},
        "apt_preferences": {
            "found": apt_pref["found"],
            "exists": apt_pref["exists"],
            "is_file": apt_pref["is_file"],
            "path": public_path(apt_pref["path"]),
            "source": apt_pref["source"],
        },
        "probes": probes,
        "blocking_findings": blocking,
        "warning_findings": warnings,
        "native_alternatives": {
            "stilts": {
                "capability_id": "catalog_workbench.crossmatch-sky",
                "label": "catalog_workbench.py crossmatch-sky",
                "applies_to": ["compact_sky_crossmatch", "small_or_medium_catalogs"],
            },
            "apt": {
                "capability_id": "aperture_photometry",
                "label": "Python/photutils aperture photometry",
                "applies_to": ["portable_aperture_photometry"],
            },
        },
    }
    status = "blocked" if blocking else ("warning" if warnings else "ok")
    return build_tool_payload(
        "external_astro_tools_preflight",
        status=status,
        notes=[
            "TOPCAT/STILTS/APT are treated as optional external backends, not as required core dependencies.",
            "Prefer STILTS over TOPCAT GUI for reproducible catalog commands.",
            "APT batch mode is only reproducible when the saved preferences file is part of the run provenance.",
        ],
        artifacts={"summary_json": getattr(args, "summary_json", None)},
        results=results,
        qa=standard_qa_payload(
            status=status,
            findings=blocking if blocking else warnings,
            metrics={"blocking_count": len(blocking), "warning_count": len(warnings)},
        ),
        include_environment=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-command", help="Explicit java command if PATH discovery is not enough.")
    parser.add_argument("--stilts-command", help="Explicit stilts command or wrapper.")
    parser.add_argument("--stilts-jar", help="Path to stilts.jar.")
    parser.add_argument("--topcat-command", help="Explicit topcat command.")
    parser.add_argument("--topcat-jar", help="Path to topcat-full.jar or topcat-extra.jar.")
    parser.add_argument("--apt-command", help="Explicit APT.csh/APT.bat command.")
    parser.add_argument("--apt-preferences", help="Path to APT.pref.")
    parser.add_argument("--require-stilts", action="store_true", help="Return blocked if STILTS is unavailable.")
    parser.add_argument("--require-apt", action="store_true", help="Return blocked if APT batch mode is unavailable.")
    parser.add_argument("--probe", action="store_true", help="Run short help/version probes for detected commands.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_report(args)
    try:
        emit_payload(payload, args.summary_json)
    except OSError as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        print(f"Could not write summary JSON: {message}", file=sys.stderr)
        return 2
    return 2 if payload["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
