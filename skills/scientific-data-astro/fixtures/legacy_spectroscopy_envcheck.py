#!/usr/bin/env python3
"""Preflight for legacy spectroscopy coursework on macOS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _internal.legacy_spectroscopy_common import detect_practice_assets, find_legacy_tools, path_risk_report, recommended_workspace_root
from _internal.provenance_utils import standard_qa_payload, standard_tool_payload, write_manifest
from _internal.public_contract import emit_payload
from _internal.runtime_common import clean_known_stderr, configure_runtime


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Practice root or a closely related legacy spectroscopy folder.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def detect_datanalysis_state() -> dict:
    executable = Path(sys.executable).resolve()
    text = str(executable)
    active = "/envs/datanalysis/" in text or executable.name == "python" and executable.parent.parent.name == "datanalysis"
    return {"active": active, "python": str(executable)}


def output_path_issue(path: str | None, label: str) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if candidate.exists() and candidate.is_dir():
        return f"{label} existe y es un directorio, no un archivo de salida: {candidate}"
    parent = candidate.parent
    if parent.exists() and not parent.is_dir():
        return f"El directorio padre de {label} existe y no es un directorio: {parent}"
    return None


def build_blocked_payload(args: argparse.Namespace, root: Path, message: str) -> dict:
    return standard_tool_payload(
        "legacy_spectroscopy_envcheck",
        status="blocked",
        notes=[message],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results={
            "practice_root": str(root),
            "blocking_findings": [message],
            "warning_findings": [],
        },
        qa=standard_qa_payload(status="blocked", findings=[message], metrics={"blocking_count": 1, "warning_count": 0}),
        include_environment=True,
    )


def emit_result(payload: dict, args: argparse.Namespace, root: Path, notes: list[str]) -> int:
    try:
        emit_payload(payload, args.summary_json)
    except OSError as exc:
        message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
        print(message, file=sys.stderr)
        return 2
    if args.manifest_json:
        try:
            write_manifest(
                args.manifest_json,
                inputs=[root],
                outputs=[args.summary_json] if args.summary_json else [],
                parameters={"tool": "legacy_spectroscopy_envcheck"},
                command=" ".join(sys.argv),
                notes=notes,
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def build_payload(args: argparse.Namespace) -> tuple[dict, Path, list[str]]:
    root = Path(args.root).expanduser().resolve()
    summary_issue = output_path_issue(args.summary_json, "summary_json")
    if summary_issue:
        return build_blocked_payload(args, root, summary_issue), root, [summary_issue]
    manifest_issue = output_path_issue(args.manifest_json, "manifest_json")
    if manifest_issue:
        return build_blocked_payload(args, root, manifest_issue), root, [manifest_issue]
    if not root.exists():
        message = f"No existe la ruta indicada: {root}"
        return build_blocked_payload(args, root, message), root, [message]
    if not root.is_dir():
        message = f"La ruta indicada no es un directorio de practica: {root}"
        return build_blocked_payload(args, root, message), root, [message]

    assets = detect_practice_assets(root)
    risk = path_risk_report(root)
    tools = find_legacy_tools()
    datanalysis = detect_datanalysis_state()

    iraf_ready = bool(tools["cl"] and tools["mkiraf"])
    primary_istarmod_root = root / "iSTARMOD"
    codex_istarmod_root = root / "CODEX" / "03_istarmod_work"
    istarmod_ready = bool(
        (
            primary_istarmod_root
            and (primary_istarmod_root / "iStarmod.py").exists()
            and (primary_istarmod_root / "lambdas.dat").exists()
        )
        or (
            codex_istarmod_root
            and (codex_istarmod_root / "iStarmod_automat_for_planets.py").exists()
            and (codex_istarmod_root / "lambdas.dat").exists()
        )
    )

    notes = []
    blocking_findings = []
    warning_findings = []
    if sys.platform != "darwin":
        blocking_findings.append("La ruta legacy IRAF/iSTARMOD esta declarada para macOS; esta plataforma no es macOS.")
    if risk["legacy_safe_workspace_needed"]:
        warning_findings.append("La ruta original contiene espacios o caracteres no ASCII; para IRAF conviene trabajar en una copia ASCII-safe.")
    else:
        notes.append("La ruta original ya es razonablemente segura para herramientas legacy.")
    if iraf_ready:
        notes.append("IRAF local parece disponible para una primera pasada reproducible con fxcor.")
    else:
        blocking_findings.append("Falta al menos uno de cl/mkiraf; la parte IRAF no esta lista todavia.")
    if tools["xgterm"] and tools["xquartz_app"]:
        notes.append("XQuartz/xgterm estan presentes; la parte interactiva legacy sigue siendo viable si hace falta.")
    if not datanalysis["active"]:
        warning_findings.append("El interprete actual no es datanalysis; para inventario FITS, correccion heliocentrica e informes conviene usarlo.")
    if assets["fits_count"] == 0:
        blocking_findings.append("No se detecto fits_p1 con FITS de practica; la ruta parece incompleta para esta workflow.")
    if not assets["calibration_csv"]:
        warning_findings.append("No se detecto FWHM_vsini_datafit.csv; la ruta de v sin i quedaria incompleta.")
    if not istarmod_ready:
        warning_findings.append("La carpeta iSTARMOD no parece lista o completa.")
    notes.extend(blocking_findings)
    notes.extend(warning_findings)

    status = "blocked" if blocking_findings else ("warning" if warning_findings else "ok")

    results = {
        "practice_root": str(root),
        "legacy_safe_workspace_needed": risk["legacy_safe_workspace_needed"],
        "path_risk": risk,
        "iraf_ready": iraf_ready,
        "istarmod_local_ready": istarmod_ready,
        "detected_practice_assets": assets,
        "legacy_tools": tools,
        "datanalysis_state": datanalysis,
        "recommended_workspace_root": recommended_workspace_root(root),
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
    }
    payload = standard_tool_payload(
        "legacy_spectroscopy_envcheck",
        status=status,
        notes=notes,
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results=results,
        qa=standard_qa_payload(
            status=status,
            findings=[*blocking_findings, *warning_findings],
            metrics={
                "fits_count": assets["fits_count"],
                "blocking_count": len(blocking_findings),
                "warning_count": len(warning_findings),
                "iraf_ready": int(iraf_ready),
                "istarmod_ready": int(istarmod_ready),
            },
        ),
    )
    return payload, root, notes


def main() -> int:
    args = parse_args()
    configure_runtime("legacy_spectroscopy_envcheck")
    payload, root, notes = build_payload(args)
    return emit_result(payload, args, root, notes)


if __name__ == "__main__":
    raise SystemExit(main())
