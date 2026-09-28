#!/usr/bin/env python3
"""Inspect, copy, and run narrow iSTARMOD coursework trees safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import public_path, standard_qa_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


PREPARE_MANIFEST = ".istarmod_prepare.json"
RVVALUES_NAME = "rvvalues.dat"
INSPECT_TOOL = "istarmod_workbench.inspect-tree"
PREPARE_TOOL = "istarmod_workbench.prepare-copy"


class InputValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-tree", help="Inspect a legacy iSTARMOD tree.")
    inspect_parser.add_argument("path")
    inspect_parser.add_argument("--summary-json")
    inspect_parser.add_argument("--manifest-json")

    copy_parser = subparsers.add_parser("prepare-copy", help="Create a clean copy of the tree for non-destructive runs.")
    copy_parser.add_argument("path")
    copy_parser.add_argument("--output-dir", required=True)
    copy_parser.add_argument("--summary-json")
    copy_parser.add_argument("--manifest-json")

    run_parser = subparsers.add_parser("run-sm", help="Run one .sm file inside a prepared copy or other safe tree.")
    run_parser.add_argument("path")
    run_parser.add_argument("--sm-file", help="Optional .sm file. Default: first .sm found in the tree.")
    run_parser.add_argument("--python-bin", help="Optional explicit Python interpreter for the run.")
    run_parser.add_argument("--cache-policy", choices=["archive", "wipe", "keep"], default="archive")
    run_parser.add_argument("--kinematics-mode", choices=["auto", "free", "fixed"], default="auto")
    run_parser.add_argument("--fixed-rv", type=float, help="Required with --kinematics-mode fixed. Seeds rvvalues.dat in the copied tree.")
    run_parser.add_argument("--summary-json")
    run_parser.add_argument("--manifest-json")
    return parser.parse_args()


def embedded_python(root: Path) -> Path | None:
    for candidate in [root / "starmod" / "bin" / "python3.11", root / "starmod" / "bin" / "python3", root / "starmod" / "bin" / "python"]:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def embedded_python_candidates(root: Path) -> list[dict]:
    candidates = []
    for candidate in [root / "starmod" / "bin" / "python3.11", root / "starmod" / "bin" / "python3", root / "starmod" / "bin" / "python"]:
        candidates.append(
            {
                "path": str(candidate),
                "exists": candidate.exists(),
                "is_symlink": candidate.is_symlink(),
                "executable": os.access(candidate, os.X_OK) if candidate.exists() else False,
            }
        )
    return candidates


def list_sm_files(root: Path) -> list[Path]:
    return sorted(item for item in root.glob("*.sm") if item.is_file())


def inspect_tree(root: Path) -> dict:
    sm_files = list_sm_files(root)
    lambdas = root / "lambdas.dat"
    embedded = embedded_python(root)
    logs_dir = root / "logs"
    res_dir = root / "p_est_frias" / "RES"
    old_outputs = []
    for pattern in ["syn*.fits", "sub*.fits", "*.pdf", "*.png", "*.dat"]:
        old_outputs.extend(
            item
            for item in root.glob(pattern)
            if item.name not in {"lambdas.dat", RVVALUES_NAME, PREPARE_MANIFEST}
        )
    if res_dir.exists():
        old_outputs.extend(res_dir.rglob("*"))
    rvvalues_files = sorted(root.rglob(RVVALUES_NAME))
    return {
        "tree_root": str(root),
        "sm_files": [str(item) for item in sm_files],
        "sm_count": len(sm_files),
        "lambdas_dat": str(lambdas) if lambdas.exists() else None,
        "embedded_python": str(embedded) if embedded else None,
        "embedded_python_candidates": embedded_python_candidates(root),
        "has_iStarmod_py": (root / "iStarmod.py").exists(),
        "has_unittestreadFITS": (root / "unittestreadFITS.py").exists(),
        "logs_dir": str(logs_dir) if logs_dir.exists() else None,
        "res_dir": str(res_dir) if res_dir.exists() else None,
        "old_output_count": len([item for item in old_outputs if item.is_file()]),
        "old_output_examples": [str(item) for item in old_outputs if item.is_file()][:12],
        "rvvalues_files": [str(item) for item in rvvalues_files],
        "rvvalues_count": len(rvvalues_files),
    }


def output_file_issue(path: str | Path | None, label: str) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.exists() and candidate.is_dir():
        return f"{label} apunta a un directorio, no a un archivo: {public_path(candidate)}"
    probe = candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"{label} no puede escribirse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def inspect_blocked_payload(args, issues: list[str]) -> dict:
    return standard_tool_payload(
        INSPECT_TOOL,
        status="blocked",
        notes=[
            "Validacion de entrada fallida antes de inspeccionar el arbol iSTARMOD.",
            "La inspeccion se bloquea para evitar diagnosticos sobre rutas ambiguas o salidas parciales.",
        ],
        artifacts={"summary_json": args.summary_json},
        results={"input_path": args.path, "input_validation_issues": issues},
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"issue_count": len(issues)}),
    )


def emit_inspect_payload(payload: dict, args, *, root: Path | None = None, notes: list[str] | None = None) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
    print(rendered)
    summary_path = Path(args.summary_json).expanduser() if args.summary_json else None
    if summary_path:
        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            outputs = [summary_path] if summary_path else []
            write_manifest(
                args.manifest_json,
                inputs=[root] if root else [],
                outputs=outputs,
                parameters={"tool": INSPECT_TOOL},
                command=" ".join(sys.argv),
                notes=notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def inspect_findings(info: dict) -> list[str]:
    findings = []
    if not info["sm_count"]:
        findings.append("no_sm_files_found")
    if info["sm_count"] and not info["lambdas_dat"]:
        findings.append("missing_lambdas_dat")
    if info["sm_count"] and not info["has_iStarmod_py"]:
        findings.append("missing_iStarmod_py")
    if info["old_output_count"]:
        findings.append("stale_outputs_present")
    if info["rvvalues_count"]:
        findings.append("rvvalues_cache_present")
    if any(Path(candidate["path"]).parent.exists() for candidate in info["embedded_python_candidates"]) and not info["embedded_python"]:
        findings.append("embedded_venv_without_reusable_python")
    return findings


def copy_ignore_reason(relative_path: Path) -> str | None:
    parts = set(relative_path.parts)
    if "__pycache__" in parts or relative_path.suffix == ".pyc":
        return "python_cache"
    if "venv" in parts or "starmod" in parts:
        return "embedded_runtime"
    if relative_path.parts[:2] == ("p_est_frias", "RES"):
        return "residual_outputs"
    if relative_path.parts[:1] == ("logs",):
        return "logs"
    if relative_path.name.startswith("syn") and relative_path.suffix.lower() == ".fits":
        return "synthetic_output_fits"
    if relative_path.name.startswith("sub") and relative_path.suffix.lower() == ".fits":
        return "subtraction_output_fits"
    if relative_path.name.lower() == RVVALUES_NAME:
        return "rvvalues_cache"
    if len(relative_path.parts) == 1 and relative_path.suffix.lower() in {".pdf", ".png"}:
        return "root_stale_output"
    if len(relative_path.parts) == 1 and relative_path.suffix.lower() == ".dat" and relative_path.name != "lambdas.dat":
        return "root_stale_output"
    return None


def should_ignore(relative_path: Path) -> bool:
    return copy_ignore_reason(relative_path) is not None


def parse_sm_metadata(sm_path: Path) -> dict:
    text = sm_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    inline_comment_lines = []
    assignments = {}
    requested_line = None
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if "#" in stripped and not stripped.startswith("#"):
            inline_comment_lines.append(line_no)
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$", line)
        if match:
            assignments[match.group(1).upper()] = match.group(2).strip()
        if requested_line is None:
            number_match = re.search(r"\b(39[0-9]{2}\.\d+|42[0-9]{2}\.\d+|58[0-9]{2}\.\d+|65[0-9]{2}\.\d+|67[0-9]{2}\.\d+|84[0-9]{2}\.\d+|85[0-9]{2}\.\d+)\b", line)
            if number_match:
                requested_line = float(number_match.group(1))
    configured_rv = None
    for key in ["RV", "VRAD", "VEL", "VELRAD", "PRIMARY_RV"]:
        value = assignments.get(key)
        if value:
            number_match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
            if number_match:
                configured_rv = float(number_match.group(0))
                break
    return {
        "path": str(sm_path),
        "assignments": assignments,
        "sec_path_present": "SEC_PATH" in assignments,
        "aperture_present": any(key.startswith("APERTURE") or key == "APERTURE" for key in assignments),
        "requested_line": requested_line,
        "configured_rv_kms": configured_rv,
        "inline_comment_lines": inline_comment_lines,
    }


def validate_sm(root: Path, sm_path: Path) -> tuple[dict, list[str]]:
    metadata = parse_sm_metadata(sm_path)
    findings = []
    sec_path = metadata["assignments"].get("SEC_PATH")
    if not metadata["sec_path_present"]:
        findings.append("Falta SEC_PATH en el .sm.")
    elif not (root / sec_path).expanduser().exists():
        findings.append(f"SEC_PATH apunta a una ruta no encontrada dentro de la copia: {sec_path}")
    if not metadata["aperture_present"]:
        findings.append("No se detecta APERTURE en el .sm.")
    if metadata["inline_comment_lines"]:
        findings.append("Hay comentarios inline en el .sm; revisa que iSTARMOD no los interprete como parte del valor.")
    requested_line = metadata.get("requested_line")
    lambdas_path = root / "lambdas.dat"
    if requested_line is not None and lambdas_path.exists():
        lambda_text = lambdas_path.read_text(encoding="utf-8", errors="replace")
        if f"{requested_line:.1f}" not in lambda_text and f"{requested_line:.2f}" not in lambda_text:
            findings.append(f"La linea {requested_line:.2f} no aparece de forma obvia en lambdas.dat.")
    elif requested_line is not None and not lambdas_path.exists():
        findings.append("No existe lambdas.dat para validar la linea pedida por el .sm.")
    return metadata, findings


def find_rvvalues_files(root: Path) -> list[Path]:
    return sorted(item for item in root.rglob(RVVALUES_NAME) if item.is_file())


def parse_rvvalues_numeric(path: Path) -> float | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def handle_rvvalues_cache(root: Path, logs_dir: Path, policy: str, notes: list[str]) -> list[str]:
    archived = []
    rvvalues_files = find_rvvalues_files(root)
    if not rvvalues_files:
        return archived
    archive_dir = logs_dir / "rvvalues_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for source in rvvalues_files:
        if policy == "keep":
            notes.append(f"Se mantiene cache existente: {source.name}.")
            continue
        if policy == "wipe":
            source.unlink()
            notes.append(f"Se elimino {source.name} antes del rerun para evitar contaminacion por cache.")
            continue
        target = archive_dir / f"{source.stem}_{len(archived)+1}{source.suffix}.bak"
        shutil.move(str(source), str(target))
        archived.append(str(target))
    if archived:
        notes.append("Se archivaron ficheros rvvalues.dat antes de ejecutar iSTARMOD.")
    return archived


def seed_fixed_rv(root: Path, fixed_rv: float, notes: list[str]) -> str:
    target = root / RVVALUES_NAME
    target.write_text(f"{fixed_rv:.6f}\n", encoding="utf-8")
    notes.append(f"Se sembró {RVVALUES_NAME} con una RV fija de {fixed_rv:.3f} km/s.")
    return str(target)


def output_dir_issue(output_dir: Path, source_root: Path) -> str | None:
    if output_dir == source_root:
        return f"--output-dir no puede ser el mismo directorio que la fuente: {public_path(output_dir)}"
    if source_root in output_dir.parents:
        return f"--output-dir no puede estar dentro del arbol fuente: {public_path(output_dir)}"
    if output_dir.exists():
        if output_dir.is_symlink():
            return f"--output-dir existe como symlink; elige una ruta nueva y explicita: {public_path(output_dir)}"
        if not output_dir.is_dir():
            return f"--output-dir existe pero no es un directorio: {public_path(output_dir)}"
        try:
            has_contents = any(output_dir.iterdir())
        except OSError as exc:
            return f"No se pudo inspeccionar --output-dir: {public_path(output_dir)}: {exc}"
        if has_contents:
            return f"--output-dir ya existe y no esta vacio; no se sobrescribe sin una limpieza explicita: {public_path(output_dir)}"
        return None
    probe = output_dir.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"--output-dir no puede crearse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def prepare_blocked_payload(args, issues: list[str]) -> dict:
    return standard_tool_payload(
        PREPARE_TOOL,
        status="blocked",
        notes=[
            "Validacion de entrada fallida antes de preparar la copia iSTARMOD.",
            "La copia se bloquea para evitar borrar fuentes, salidas existentes o escribir artefactos parciales.",
        ],
        artifacts={"output_dir": args.output_dir, "summary_json": args.summary_json},
        results={"input_path": args.path, "input_validation_issues": issues},
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"issue_count": len(issues)}),
    )


def emit_prepare_payload(payload: dict, args, *, source_root: Path | None = None, output_dir: Path | None = None, notes: list[str] | None = None) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
    print(rendered)
    summary_path = Path(args.summary_json).expanduser() if args.summary_json else None
    if summary_path:
        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            outputs = []
            if output_dir:
                outputs.append(output_dir)
            if summary_path:
                outputs.append(summary_path)
            write_manifest(
                args.manifest_json,
                inputs=[source_root] if source_root else [],
                outputs=outputs,
                parameters={"tool": PREPARE_TOOL},
                command=" ".join(sys.argv),
                notes=notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def skipped_by_reason(skipped_items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in skipped_items:
        reason = item["reason"]
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def prepare_findings(source_info: dict, skipped_items: list[dict]) -> list[str]:
    findings = []
    reasons = skipped_by_reason(skipped_items)
    if not source_info["sm_count"]:
        findings.append("no_sm_files_copied")
    if source_info["sm_count"] and not source_info["lambdas_dat"]:
        findings.append("missing_lambdas_dat")
    if source_info["sm_count"] and not source_info["has_iStarmod_py"]:
        findings.append("missing_iStarmod_py")
    if any(reason in reasons for reason in ["logs", "residual_outputs", "synthetic_output_fits", "subtraction_output_fits", "root_stale_output"]):
        findings.append("stale_outputs_omitted")
    if "rvvalues_cache" in reasons:
        findings.append("rvvalues_cache_omitted")
    return sorted(set(findings))


def cmd_inspect(args):
    configure_runtime("istarmod_workbench_inspect")
    root = Path(args.path).expanduser().resolve()
    preflight_issues = []
    if not root.exists():
        preflight_issues.append(f"No existe la ruta indicada: {public_path(root)}")
    elif not root.is_dir():
        preflight_issues.append(f"La ruta indicada no es un directorio iSTARMOD: {public_path(root)}")
    for issue in [output_file_issue(args.summary_json, "summary JSON"), output_file_issue(args.manifest_json, "manifest JSON")]:
        if issue:
            preflight_issues.append(issue)
    if preflight_issues:
        raise InputValidationError(preflight_issues)
    info = inspect_tree(root)
    notes = []
    if info["embedded_python"]:
        notes.append("Se detecto un interprete embebido de iSTARMOD.")
    elif (root / "starmod" / "bin").exists():
        notes.append("El arbol trae un venv de iSTARMOD, pero no se detecto un interprete reutilizable en esta maquina.")
    if info["old_output_count"]:
        notes.append("El arbol contiene outputs antiguos; conviene preparar una copia limpia antes de correr nada.")
    if info["rvvalues_count"]:
        notes.append("Se detecto rvvalues.dat; conviene aislarlo o archivarlo antes de reruns por objeto o linea.")
    if not info["sm_count"]:
        notes.append("No se encontraron .sm en la raiz del arbol.")
    if info["sm_count"] and not info["lambdas_dat"]:
        notes.append("No se encontro lambdas.dat junto al arbol; valida manualmente que el .sm apunta a lineas existentes.")
    if info["sm_count"] and not info["has_iStarmod_py"]:
        notes.append("No se encontro iStarmod.py; la inspeccion sirve para inventario, pero el arbol no parece ejecutable tal cual.")
    findings = inspect_findings(info)
    status = "warning" if findings else "ok"
    payload = standard_tool_payload(
        INSPECT_TOOL,
        status=status,
        notes=notes or ["Arbol iSTARMOD inspeccionado."],
        artifacts={},
        results=info,
        qa=standard_qa_payload(
            status=status,
            findings=findings,
            metrics={
                "sm_count": info["sm_count"],
                "old_output_count": info["old_output_count"],
                "rvvalues_count": info["rvvalues_count"],
            },
        ),
    )
    return emit_inspect_payload(payload, args, root=root, notes=notes)


def cmd_prepare_copy(args):
    configure_runtime("istarmod_workbench_prepare")
    source_root = Path(args.path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    preflight_issues = []
    if not source_root.exists():
        preflight_issues.append(f"No existe la ruta indicada: {public_path(source_root)}")
    elif not source_root.is_dir():
        preflight_issues.append(f"La ruta indicada no es un directorio iSTARMOD: {public_path(source_root)}")
    if source_root.exists() and source_root.is_dir():
        issue = output_dir_issue(output_dir, source_root)
        if issue:
            preflight_issues.append(issue)
    for issue in [output_file_issue(args.summary_json, "summary JSON"), output_file_issue(args.manifest_json, "manifest JSON")]:
        if issue:
            preflight_issues.append(issue)
    if preflight_issues:
        raise InputValidationError(preflight_issues)
    output_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []
    skipped_items = []
    for source in source_root.rglob("*"):
        relative = source.relative_to(source_root)
        reason = copy_ignore_reason(relative)
        if reason:
            skipped_items.append({"relative_path": str(relative), "reason": reason})
            continue
        if source.is_symlink():
            skipped_items.append({"relative_path": str(relative), "reason": "symlink_skipped"})
            continue
        target = output_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_files.append(target)

    source_info = inspect_tree(source_root)
    findings = prepare_findings(source_info, skipped_items)
    status = "warning" if findings else "ok"
    manifest = {
        "source_root": str(source_root),
        "copied_root": str(output_dir),
        "source_embedded_python": str(embedded_python(source_root)) if embedded_python(source_root) else None,
        "skipped_items": skipped_items,
    }
    (output_dir / PREPARE_MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    notes = ["Copia iSTARMOD preparada sin tocar el arbol original."]
    if manifest["source_embedded_python"]:
        notes.append("Se guardo la referencia al interprete embebido original por si conviene reutilizarlo en la copia.")
    if skipped_items:
        notes.append("Se omitieron caches, runtimes embebidos o salidas antiguas para dejar una copia limpia.")
    if not source_info["sm_count"]:
        notes.append("No se copiaron .sm; la copia queda como inventario incompleto y debe revisarse antes de ejecutar.")
    payload = standard_tool_payload(
        PREPARE_TOOL,
        status=status,
        notes=notes,
        artifacts={"copied_root": str(output_dir), "prepare_manifest": str(output_dir / PREPARE_MANIFEST)},
        results={
            "copied_file_count": len(copied_files),
            "source_root": str(source_root),
            "skipped_count": len(skipped_items),
            "skipped_by_reason": skipped_by_reason(skipped_items),
            "source_sm_count": source_info["sm_count"],
            "source_old_output_count": source_info["old_output_count"],
            "source_rvvalues_count": source_info["rvvalues_count"],
        },
        qa=standard_qa_payload(
            status=status,
            findings=findings,
            metrics={
                "copied_file_count": len(copied_files),
                "skipped_count": len(skipped_items),
                "source_sm_count": source_info["sm_count"],
            },
        ),
    )
    return emit_prepare_payload(payload, args, source_root=source_root, output_dir=output_dir, notes=notes)


def choose_python(root: Path, explicit: str | None) -> tuple[Path, list[str]]:
    notes = []
    if explicit:
        return Path(explicit).expanduser().resolve(), notes
    local_embedded = embedded_python(root)
    if local_embedded:
        notes.append("Se usa el interprete embebido copiado dentro del arbol.")
        return local_embedded, notes
    prepare_manifest_path = root / PREPARE_MANIFEST
    if prepare_manifest_path.exists():
        payload = json.loads(prepare_manifest_path.read_text(encoding="utf-8"))
        external_embedded = payload.get("source_embedded_python")
        if external_embedded and Path(external_embedded).exists():
            notes.append("Se reutiliza el interprete embebido original guardado en el prepare manifest.")
            return Path(external_embedded).resolve(), notes
    return Path(sys.executable).resolve(), notes


def snapshot_tree(root: Path) -> dict[str, float]:
    result = {}
    for item in root.rglob("*"):
        if item.is_file():
            result[str(item.relative_to(root))] = item.stat().st_mtime
    return result


def choose_sm(root: Path, requested: str | None) -> Path:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            raise SystemExit(f"No existe el .sm solicitado: {candidate}")
        return candidate.resolve()
    sm_files = list_sm_files(root)
    if not sm_files:
        raise SystemExit("No se encontro ningun .sm en la raiz del arbol.")
    return sm_files[0]


def build_runner(root: Path, sm_path: Path) -> Path:
    runner = root / "_codex_run_selected_sm.py"
    content = (
        "import numpy as np\n"
        "if not hasattr(np, 'trapz') and hasattr(np, 'trapezoid'):\n"
        "    np.trapz = np.trapezoid\n"
        "from iStarmod_automat_for_planets import *\n"
        "from iStarmod_process_activity_files import *\n"
        "import time\n"
        "start_time = time.time()\n"
        f"starmod({sm_path.name!r})\n"
        "print(f'--- {time.time() - start_time:.2f} seconds ---')\n"
    )
    runner.write_text(content, encoding="utf-8")
    return runner


def cmd_run_sm(args):
    configure_runtime("istarmod_workbench_run")
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"No existe la ruta indicada: {root}")
    sm_path = choose_sm(root, args.sm_file)
    sm_metadata, sm_findings = validate_sm(root, sm_path)
    python_bin, notes = choose_python(root, args.python_bin)
    runner = build_runner(root, sm_path)
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{sm_path.stem}_run.log"
    if args.kinematics_mode == "fixed" and args.fixed_rv is None:
        raise SystemExit("--fixed-rv es obligatorio cuando --kinematics-mode fixed.")
    archived_cache = handle_rvvalues_cache(root, logs_dir, args.cache_policy, notes)
    seeded_rvvalues = None
    if args.kinematics_mode == "fixed":
        seeded_rvvalues = seed_fixed_rv(root, float(args.fixed_rv), notes)
    elif args.kinematics_mode == "free":
        notes.append("Modo free: se evita reutilizar cache previa y se deja que iSTARMOD resuelva la cinemática de nuevo.")
    if sm_findings:
        notes.append("El .sm trae advertencias de validacion; revisa el resumen antes de adoptar el resultado.")

    before = snapshot_tree(root)
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    env["PYTHONUNBUFFERED"] = "1"
    completed = subprocess.run(
        [str(python_bin), str(runner)],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    log_path.write_text(
        "[stdout]\n"
        + completed.stdout
        + "\n\n[stderr]\n"
        + completed.stderr,
        encoding="utf-8",
    )
    after = snapshot_tree(root)
    changed = sorted(relative for relative, mtime in after.items() if relative not in before or mtime > before[relative])
    artifact_files = [str(root / item) for item in changed if Path(item).suffix.lower() in {".fits", ".png", ".pdf", ".dat", ".txt", ".log"}]
    rvvalues_after = find_rvvalues_files(root)
    rvvalues_numeric = parse_rvvalues_numeric(rvvalues_after[0]) if rvvalues_after else None
    configured_rv = sm_metadata.get("configured_rv_kms")
    cache_warning = None
    if configured_rv is not None and rvvalues_numeric is not None and abs(rvvalues_numeric - configured_rv) > 1.5:
        cache_warning = (
            f"La RV final en {RVVALUES_NAME} ({rvvalues_numeric:.3f} km/s) difiere de la RV configurada en el .sm ({configured_rv:.3f} km/s)."
        )
        notes.append(cache_warning)
    if completed.returncode == 0:
        notes.append("iSTARMOD se ejecuto en copia sin tocar el arbol original.")
        status = "ok"
    else:
        notes.append("iSTARMOD fallo; revisa el log capturado y los artefactos generados en la copia.")
        status = "warning"

    payload = standard_tool_payload(
        "istarmod_workbench.run-sm",
        status=status,
        notes=notes,
        artifacts={
            "runner": str(runner),
            "log_path": str(log_path),
            "artifact_files": artifact_files,
            "archived_cache_files": archived_cache,
            "seeded_rvvalues": seeded_rvvalues,
        },
        results={
            "tree_root": str(root),
            "sm_file": str(sm_path),
            "python_bin": str(python_bin),
            "returncode": completed.returncode,
            "changed_files": changed,
            "sm_validation": {"metadata": sm_metadata, "findings": sm_findings},
            "cache_policy": args.cache_policy,
            "kinematics_mode": args.kinematics_mode,
            "configured_rv_kms": configured_rv,
            "rvvalues_after": [str(item) for item in rvvalues_after],
            "rvvalues_numeric_kms": rvvalues_numeric,
            "cache_warning": cache_warning,
        },
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        Path(args.summary_json).write_text(rendered + "\n", encoding="utf-8")
    if args.manifest_json:
        outputs = [log_path, *[root / item for item in changed]]
        outputs.extend(Path(item) for item in archived_cache)
        if seeded_rvvalues:
            outputs.append(Path(seeded_rvvalues))
        write_manifest(
            args.manifest_json,
            inputs=[root, sm_path],
            outputs=outputs,
            parameters={
                "tool": "istarmod_workbench.run-sm",
                "python_bin": str(python_bin),
                "cache_policy": args.cache_policy,
                "kinematics_mode": args.kinematics_mode,
                "fixed_rv": args.fixed_rv,
            },
            command=" ".join(sys.argv),
            notes=notes,
        )


def main():
    args = parse_args()
    if args.command == "inspect-tree":
        try:
            return cmd_inspect(args)
        except InputValidationError as exc:
            return emit_inspect_payload(inspect_blocked_payload(args, exc.issues), args)
    elif args.command == "prepare-copy":
        try:
            return cmd_prepare_copy(args)
        except InputValidationError as exc:
            return emit_prepare_payload(prepare_blocked_payload(args, exc.issues), args)
    elif args.command == "run-sm":
        cmd_run_sm(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
