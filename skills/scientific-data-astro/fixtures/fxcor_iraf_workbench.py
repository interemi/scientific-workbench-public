#!/usr/bin/env python3
"""Prepare, run, and merge narrow IRAF/fxcor coursework sessions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _internal.legacy_spectroscopy_common import (
    copy_selected_files,
    default_fxcor_cases,
    detect_practice_assets,
    find_legacy_tools,
    parse_fxcor_txt,
    path_risk_report,
    recommended_workspace_root,
)
from _internal.provenance_utils import public_path, standard_qa_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


MANUAL_OVERRIDE_FIELDS = [
    "case_id",
    "aperture",
    "include",
    "override_shift_pix",
    "override_fwhm_kms",
    "override_tdr",
    "override_vrel_kms",
    "override_verr_kms",
    "notes",
]

PREPARE_TOOL = "fxcor_iraf_workbench.prepare-session"
RUN_TOOL = "fxcor_iraf_workbench.run-auto"


def output_file_issue(path: str | Path | None, label: str) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.exists() and candidate.is_dir():
        return f"{label} apunta a un directorio, no a un archivo: {public_path(candidate)}"
    parent = candidate.parent
    probe = parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"{label} no puede escribirse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def output_dir_issue(output_dir: Path, practice_root: Path) -> str | None:
    if output_dir.exists() and not output_dir.is_dir():
        return f"--output-dir existe pero no es un directorio: {public_path(output_dir)}"
    probe = output_dir.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"--output-dir no puede crearse porque un componente padre no es directorio: {public_path(probe)}"
    try:
        output_dir.relative_to(practice_root)
    except ValueError:
        return None
    return "El workspace derivado no debe crearse dentro de la practica original; elige una ruta externa ASCII-safe."


def blocked_prepare_payload(practice_root: Path | None, output_dir: Path | None, findings: list[str]) -> dict:
    artifacts = {}
    if output_dir is not None:
        artifacts["workspace_root"] = str(output_dir)
    results = {"blocking_findings": findings, "warning_findings": []}
    if practice_root is not None:
        results["practice_root"] = str(practice_root)
    return standard_tool_payload(
        PREPARE_TOOL,
        status="blocked",
        notes=findings,
        artifacts=artifacts,
        results=results,
        qa=standard_qa_payload(status="blocked", findings=findings, metrics={"blocking_count": len(findings), "warning_count": 0}),
    )


def blocked_run_payload(workspace_root: Path | None, findings: list[str]) -> dict:
    artifacts = {}
    results = {"blocking_findings": findings, "warning_findings": []}
    if workspace_root is not None:
        artifacts["workspace_root"] = str(workspace_root)
        results["workspace_root"] = str(workspace_root)
    return standard_tool_payload(
        RUN_TOOL,
        status="blocked",
        notes=findings,
        artifacts=artifacts,
        results=results,
        qa=standard_qa_payload(status="blocked", findings=findings, metrics={"blocking_count": len(findings), "warning_count": 0}),
    )


def emit_prepare_payload(payload: dict, args, *, manifest_inputs=None, manifest_outputs=None, manifest_notes=None) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        try:
            summary_path = Path(args.summary_json)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            write_manifest(
                args.manifest_json,
                inputs=manifest_inputs or [],
                outputs=manifest_outputs or [],
                parameters={"tool": PREPARE_TOOL},
                command=" ".join(sys.argv),
                notes=manifest_notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def emit_run_payload(payload: dict, args, *, manifest_inputs=None, manifest_outputs=None, manifest_notes=None, selected_ids=None) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        try:
            summary_path = Path(args.summary_json)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            write_manifest(
                args.manifest_json,
                inputs=manifest_inputs or [],
                outputs=manifest_outputs or [],
                parameters={"tool": RUN_TOOL, "case_ids": sorted(selected_ids or [])},
                command=" ".join(sys.argv),
                notes=manifest_notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-session", help="Create a safe derived workspace and editable fxcor config.")
    prepare.add_argument("practice_root")
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--summary-json")
    prepare.add_argument("--manifest-json")

    run_auto = subparsers.add_parser("run-auto", help="Generate CL scripts, run fxcor, and parse txtonly outputs.")
    run_auto.add_argument("workspace")
    run_auto.add_argument("--case-id", action="append", default=[], help="Only run the selected case id. Repeat as needed.")
    run_auto.add_argument("--summary-json")
    run_auto.add_argument("--manifest-json")

    merge = subparsers.add_parser("merge-overrides", help="Merge automatic fxcor rows with manual overrides.")
    merge.add_argument("workspace")
    merge.add_argument("--manual-csv", help="Optional override CSV. Default: workspace/manual_overrides.csv")
    merge.add_argument("--summary-json")
    merge.add_argument("--manifest-json")

    return parser.parse_args()


def load_workspace_config(path: str | Path) -> tuple[Path, dict]:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        config_path = candidate
        workspace_root = candidate.parent
    else:
        workspace_root = candidate
        config_path = workspace_root / "fxcor_cases.json"
    if not config_path.exists():
        raise SystemExit(f"No se encontro la configuracion esperada: {config_path}")
    return workspace_root, json.loads(config_path.read_text(encoding="utf-8"))


def load_workspace_config_safe(path: str | Path) -> tuple[Path, dict | None, list[str]]:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        config_path = candidate
        workspace_root = candidate.parent
    else:
        workspace_root = candidate
        config_path = workspace_root / "fxcor_cases.json"
    findings = []
    if not workspace_root.exists():
        findings.append(f"No existe el workspace indicado: {public_path(workspace_root)}")
        return workspace_root, None, findings
    if not workspace_root.is_dir():
        findings.append(f"El workspace indicado no es un directorio: {public_path(workspace_root)}")
        return workspace_root, None, findings
    if not config_path.exists():
        findings.append(f"No se encontro la configuracion esperada: {public_path(config_path)}")
        return workspace_root, None, findings
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(f"fxcor_cases.json no es JSON valido: {exc.msg} en linea {exc.lineno}, columna {exc.colno}.")
        return workspace_root, None, findings
    if not isinstance(config, dict):
        findings.append("fxcor_cases.json debe contener un objeto JSON.")
        return workspace_root, None, findings
    return workspace_root, config, []


def write_csv_template(path: Path, cases: list[dict]) -> None:
    rows = []
    for case in cases:
        for aperture in case.get("apertures", []):
            rows.append(
                {
                    "case_id": case["case_id"],
                    "aperture": aperture,
                    "include": "auto",
                    "override_shift_pix": "",
                    "override_fwhm_kms": "",
                    "override_tdr": "",
                    "override_vrel_kms": "",
                    "override_verr_kms": "",
                    "notes": "",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANUAL_OVERRIDE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def maybe_prepare_login_cl(workspace_root: Path, practice_root: Path, notes: list[str]) -> Path | None:
    target = workspace_root / "login.cl"
    if target.exists():
        return target
    source = practice_root / "CODEX" / "01_iraf_safe" / "login.cl"
    if source.exists():
        shutil.copy2(source, target)
        notes.append("Se copio login.cl desde CODEX/01_iraf_safe para no depender de la ruta original.")
        return target
    tools = find_legacy_tools()
    mkiraf_bin = tools.get("mkiraf")
    if not mkiraf_bin:
        notes.append("No se pudo preparar login.cl automaticamente porque mkiraf no esta disponible.")
        return None
    for seed in ("xgterm\n", "\n"):
        try:
            completed = subprocess.run(
                [mkiraf_bin],
                cwd=workspace_root,
                input=seed,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
        except Exception as exc:
            notes.append(f"mkiraf no pudo ejecutarse automaticamente: {exc}")
            return None
        if completed.returncode == 0 and target.exists():
            notes.append("mkiraf genero login.cl dentro del workspace derivado.")
            return target
    notes.append("mkiraf se intento pero no llego a dejar login.cl listo en el workspace.")
    return None


def ensure_local_iraf_home(workspace_root: Path, notes: list[str]) -> Path:
    iraf_home = workspace_root / ".iraf"
    for path in (iraf_home, iraf_home / "uparm", iraf_home / "cache", iraf_home / "imdir"):
        path.mkdir(parents=True, exist_ok=True)
    root_login = workspace_root / "login.cl"
    iraf_login = iraf_home / "login.cl"
    if root_login.exists():
        shutil.copy2(root_login, iraf_login)
    elif not iraf_login.exists():
        notes.append("No habia login.cl disponible para preparar un HOME local de IRAF.")
    return iraf_home


def seed_fxcor_parameter_file(iraf_home: Path, cl_bin: str, notes: list[str]) -> Path | None:
    """Seed IRAF's user fxcor parameter file from the installed package.

    Community IRAF can segfault when ``rvfxcor.par`` is absent even though
    ``cl`` exits with status zero. The package-owned parameter file is a
    reproducible local source and is copied only into the derived workspace.
    """
    target = iraf_home / "uparm" / "rvfxcor.par"
    if target.is_file():
        return target

    resolved_cl = Path(cl_bin).expanduser().resolve()
    candidates: list[Path] = []
    configured_root = os.environ.get("iraf") or os.environ.get("IRAF")
    if configured_root:
        candidates.append(Path(configured_root).expanduser() / "noao" / "rv" / "fxcor.par")
    candidates.extend(parent / "noao" / "rv" / "fxcor.par" for parent in resolved_cl.parents)

    for source in candidates:
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            notes.append("Se inicializo rvfxcor.par desde la instalacion local de IRAF dentro del workspace derivado.")
            return target

    notes.append("No se encontro el parametro base fxcor.par de la instalacion IRAF; la ejecucion puede bloquearse de forma controlada.")
    return None


def native_cl_failure(stdout: str, stderr: str) -> str | None:
    markers = ("segmentation violation", "fatal error", "error:")
    for line in (stdout + "\n" + stderr).splitlines():
        normalized = line.strip().lower()
        if any(marker in normalized for marker in markers):
            return line.strip()[:500]
    return None


def serialize_case(case: dict) -> dict:
    rendered = dict(case)
    rendered["apertures"] = list(rendered.get("apertures", []))
    return rendered


def cmd_prepare_session(args):
    configure_runtime("fxcor_iraf_workbench_prepare")
    practice_root = Path(args.practice_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    preflight_findings = []
    if sys.platform != "darwin":
        preflight_findings.append("La ruta IRAF/fxcor legacy esta declarada para macOS; esta plataforma no es macOS.")
    summary_issue = output_file_issue(args.summary_json, "summary JSON")
    if summary_issue:
        preflight_findings.append(summary_issue)
    manifest_issue = output_file_issue(args.manifest_json, "manifest JSON")
    if manifest_issue:
        preflight_findings.append(manifest_issue)
    if not practice_root.exists():
        preflight_findings.append(f"No existe la practica indicada: {public_path(practice_root)}")
    elif not practice_root.is_dir():
        preflight_findings.append(f"La practica indicada no es un directorio: {public_path(practice_root)}")
    else:
        dir_issue = output_dir_issue(output_dir, practice_root)
        if dir_issue:
            preflight_findings.append(dir_issue)
    if preflight_findings:
        payload = blocked_prepare_payload(practice_root, output_dir, preflight_findings)
        return emit_prepare_payload(payload, args)

    fits_dir = practice_root / "fits_p1"
    if not fits_dir.exists() or not fits_dir.is_dir():
        payload = blocked_prepare_payload(practice_root, output_dir, [f"No se encontro fits_p1 dentro de {public_path(practice_root)}"])
        return emit_prepare_payload(payload, args)

    output_preexisting = output_dir.exists() and any(output_dir.iterdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    logs_dir = output_dir / "logs"
    parsed_dir = output_dir / "parsed"
    scripts_dir = output_dir / "scripts"
    for path in (data_dir, logs_dir, parsed_dir, scripts_dir, output_dir / "uparm"):
        path.mkdir(parents=True, exist_ok=True)

    available_fits = {item.name for item in fits_dir.glob("*.fits")}
    cases = default_fxcor_cases(available_fits)
    if not cases:
        payload = blocked_prepare_payload(
            practice_root,
            output_dir,
            ["No se pudieron inferir casos legacy razonables a partir de los FITS disponibles."],
        )
        return emit_prepare_payload(payload, args)
    selected = []
    seen = set()
    for case in cases:
        for name in (case["object"], case["template"]):
            if name not in seen:
                selected.append(fits_dir / name)
                seen.add(name)
    copied = copy_selected_files(selected, data_dir)

    notes = []
    warning_findings = []
    risk = path_risk_report(practice_root)
    if risk["legacy_safe_workspace_needed"]:
        warning_findings.append("La practica original contiene espacios o caracteres no ASCII; conviene ejecutar IRAF solo desde la copia derivada.")
        notes.append("La practica original es arriesgada para IRAF; este workspace derivado queda como carril seguro.")
    output_risk = path_risk_report(output_dir)
    if output_risk["legacy_safe_workspace_needed"]:
        warning_findings.append("El --output-dir contiene espacios o caracteres no ASCII; puede no ser seguro para una sesion IRAF/fxcor.")
    if output_preexisting:
        warning_findings.append("El --output-dir ya contenia archivos antes de preparar la sesion; revisa que no mezcle outputs previos.")
    all_cases = default_fxcor_cases()
    if len(cases) < len(all_cases):
        warning_findings.append(f"Solo se pudieron inferir {len(cases)} de {len(all_cases)} casos fxcor conocidos por falta de FITS esperados.")
    login_path = maybe_prepare_login_cl(output_dir, practice_root, notes)
    ensure_local_iraf_home(output_dir, notes)
    if login_path is None:
        warning_findings.append("No se pudo preparar login.cl; la copia queda inventariada pero no lista para correr IRAF sin intervencion.")
    manual_csv = output_dir / "manual_overrides.csv"
    write_csv_template(manual_csv, cases)

    config = {
        "tool": "fxcor_iraf_workbench",
        "practice_root": str(practice_root),
        "workspace_root": str(output_dir),
        "recommended_workspace_root": recommended_workspace_root(practice_root),
        "data_dir": "data",
        "logs_dir": "logs",
        "parsed_dir": "parsed",
        "scripts_dir": "scripts",
        "cases": [serialize_case(item) for item in cases],
    }
    config_path = output_dir / "fxcor_cases.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    status = "warning" if warning_findings else "ok"
    payload = standard_tool_payload(
        PREPARE_TOOL,
        status=status,
        notes=notes or ["Workspace derivado preparado para fxcor sin tocar la practica original."],
        artifacts={
            "workspace_root": str(output_dir),
            "config_json": str(config_path),
            "manual_overrides_csv": str(manual_csv),
            "copied_fits": [str(item) for item in copied],
        },
        results={
            "practice_assets": detect_practice_assets(practice_root),
            "case_count": len(cases),
            "cases": [serialize_case(item) for item in cases],
            "blocking_findings": [],
            "warning_findings": warning_findings,
            "path_risk": {"practice_root": risk, "workspace_root": output_risk},
        },
        qa=standard_qa_payload(
            status=status,
            findings=warning_findings,
            metrics={"case_count": len(cases), "copied_fits_count": len(copied), "warning_count": len(warning_findings), "blocking_count": 0},
        ),
    )
    return emit_prepare_payload(payload, args, manifest_inputs=[practice_root] + selected, manifest_outputs=[output_dir, config_path, manual_csv, *copied], manifest_notes=notes)


def cl_lines_for_case(case: dict) -> list[str]:
    line = [
        "fxcor",
        f"objects={case['object']}",
        f"templates={case['template']}",
        'apertures="{}"'.format(",".join(str(item) for item in case.get("apertures", []))),
        f'output="../logs/{case["case_id"]}"',
        "interactive=no",
        "autowrite=yes",
        "verbose=txtonly",
    ]
    if case.get("mode") == "sb2_rv":
        line.append(f"window={case.get('window', 275)}")
    elif case.get("window") is not None:
        line.append(f"window={case['window']}")
    if case.get("wincenter") is not None:
        line.append(f"wincenter={case['wincenter']}")
    if case.get("osample"):
        line.append(f'osample="{case["osample"]}"')
    if case.get("rsample"):
        line.append(f'rsample="{case["rsample"]}"')
    return ["noao", "rv", "unlearn fxcor", " ".join(line), "logout"]


def write_case_script(path: Path, case: dict) -> None:
    path.write_text("\n".join(cl_lines_for_case(case)) + "\n", encoding="utf-8")


def parse_case_output(case: dict, txt_path: Path) -> list[dict]:
    rows = []
    for row in parse_fxcor_txt(txt_path):
        rows.append(
            {
                "case_id": case["case_id"],
                "case_label": case.get("label"),
                "mode": case.get("mode"),
                "object_name": row.object_name,
                "image_name": row.image_name,
                "template_image": row.template_image,
                "template_vhelio_kms": row.template_vhelio_kms,
                "aperture": row.aperture,
                "shift_pix": row.shift_pix,
                "height": row.height,
                "fwhm_kms": row.fwhm_kms,
                "fwhm_pix": row.fwhm_pix,
                "tdr": row.tdr,
                "vrel_kms": row.vrel_kms,
                "verr_kms": row.verr_kms,
                "veldisp_kms_per_pix": row.veldisp_kms_per_pix,
                "txtonly_path": str(txt_path),
            }
        )
    return rows


def csv_path_for_case(parsed_dir: Path, case: dict) -> Path:
    return parsed_dir / f"{case['case_id']}_auto.csv"


def write_case_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "case_id",
        "case_label",
        "mode",
        "object_name",
        "image_name",
        "template_image",
        "template_vhelio_kms",
        "aperture",
        "shift_pix",
        "height",
        "fwhm_kms",
        "fwhm_pix",
        "tdr",
        "vrel_kms",
        "verr_kms",
        "veldisp_kms_per_pix",
        "txtonly_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_cl_case(workspace_root: Path, case: dict) -> dict:
    tools = find_legacy_tools()
    cl_bin = tools.get("cl")
    script_path = workspace_root / "scripts" / f"{case['case_id']}.cl"
    if not cl_bin:
        return {
            "status": "blocked",
            "notes": ["No se encontro el ejecutable cl de IRAF."],
            "blocking_findings": ["No se encontro el ejecutable cl de IRAF."],
            "rows": [],
            "script_path": str(script_path),
            "txtonly_path": None,
            "parsed_csv": None,
        }
    notes = []
    iraf_home = ensure_local_iraf_home(workspace_root, notes)
    seed_fxcor_parameter_file(iraf_home, cl_bin, notes)
    write_case_script(script_path, case)
    output_base = workspace_root / "logs" / case["case_id"]
    for candidate in (
        output_base.with_suffix(".txt"),
        output_base.with_suffix(".log"),
        output_base.with_suffix(".gki"),
        workspace_root / "parsed" / f"{case['case_id']}_auto.csv",
    ):
        if candidate.exists():
            candidate.unlink()
    env = os.environ.copy()
    env["HOME"] = str(workspace_root)
    env.setdefault("TERM", "xterm")
    with script_path.open("r", encoding="utf-8") as handle:
        completed = subprocess.run(
            [cl_bin],
            cwd=workspace_root / "data",
            stdin=handle,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    txt_path = workspace_root / "logs" / f"{case['case_id']}.txt"
    log_path = workspace_root / "logs" / f"{case['case_id']}.cl_stdout.log"
    log_path.write_text(
        f"IRAF_HOME={iraf_home}\n"
        f"EXEC_CWD={workspace_root / 'data'}\n\n"
        "STDOUT\n"
        + completed.stdout
        + "\n\nSTDERR\n"
        + completed.stderr,
        encoding="utf-8",
    )
    native_failure = native_cl_failure(completed.stdout, completed.stderr)
    blocking_findings = []
    if txt_path.exists():
        rows = parse_case_output(case, txt_path)
        if native_failure:
            csv_path = None
            finding = f"IRAF/cl reporto un error nativo en {case['case_id']}: {native_failure}"
            notes.append(finding)
            blocking_findings.append(finding)
            status = "blocked"
        elif not rows:
            csv_path = None
            finding = f"La salida txtonly de {case['case_id']} no contiene filas fxcor utilizables."
            notes.append(finding)
            blocking_findings.append(finding)
            status = "blocked"
        else:
            csv_path = csv_path_for_case(workspace_root / "parsed", case)
            write_case_csv(csv_path, rows)
            notes.append(f"Se parseo {txt_path.name} y se guardo {csv_path.name}.")
            if completed.returncode == 0:
                status = "ok"
            else:
                notes.append(f"cl devolvio codigo {completed.returncode} aunque genero la salida txtonly para {case['case_id']}.")
                status = "warning"
    else:
        rows = []
        csv_path = None
        finding = f"No aparecio la salida txtonly esperada para {case['case_id']}."
        notes.append(finding)
        blocking_findings.append(finding)
        if native_failure:
            native_finding = f"IRAF/cl reporto un error nativo en {case['case_id']}: {native_failure}"
            notes.append(native_finding)
            blocking_findings.append(native_finding)
        status = "blocked"
    return {
        "status": status,
        "notes": notes,
        "blocking_findings": blocking_findings,
        "returncode": completed.returncode,
        "stdout_log": str(log_path),
        "txtonly_path": str(txt_path) if txt_path.exists() else None,
        "parsed_csv": str(csv_path) if csv_path else None,
        "rows": rows,
        "script_path": str(script_path),
    }


def cmd_run_auto(args):
    configure_runtime("fxcor_iraf_workbench_run")
    workspace_candidate = Path(args.workspace).expanduser().resolve()
    preflight_findings = []
    if sys.platform != "darwin":
        preflight_findings.append("La ruta IRAF/fxcor legacy esta declarada para macOS; esta plataforma no es macOS.")
    summary_issue = output_file_issue(args.summary_json, "summary JSON")
    if summary_issue:
        preflight_findings.append(summary_issue)
    manifest_issue = output_file_issue(args.manifest_json, "manifest JSON")
    if manifest_issue:
        preflight_findings.append(manifest_issue)
    if preflight_findings:
        payload = blocked_run_payload(workspace_candidate if workspace_candidate.exists() else None, preflight_findings)
        return emit_run_payload(payload, args, selected_ids=set(args.case_id or []))

    workspace_root, config, load_findings = load_workspace_config_safe(args.workspace)
    if load_findings:
        payload = blocked_run_payload(workspace_root, load_findings)
        return emit_run_payload(payload, args, selected_ids=set(args.case_id or []))
    assert config is not None
    selected_ids = set(args.case_id or [])
    configured_cases = config.get("cases", [])
    if not isinstance(configured_cases, list):
        payload = blocked_run_payload(workspace_root, ["fxcor_cases.json debe incluir una lista 'cases'."])
        return emit_run_payload(payload, args, selected_ids=selected_ids)
    configured_ids = {str(item.get("case_id")) for item in configured_cases if isinstance(item, dict) and item.get("case_id")}
    missing_ids = sorted(selected_ids - configured_ids)
    if missing_ids:
        payload = blocked_run_payload(workspace_root, [f"No hay casos configurados para --case-id: {', '.join(missing_ids)}"])
        return emit_run_payload(payload, args, selected_ids=selected_ids)
    cases = [item for item in configured_cases if isinstance(item, dict) and (not selected_ids or item.get("case_id") in selected_ids)]
    if not cases:
        payload = blocked_run_payload(workspace_root, ["No hay casos seleccionados para ejecutar."])
        return emit_run_payload(payload, args, selected_ids=selected_ids)

    notes = []
    runs = []
    warning_findings = []
    workspace_risk = path_risk_report(workspace_root)
    if workspace_risk["legacy_safe_workspace_needed"]:
        warning_findings.append("El workspace contiene espacios o caracteres no ASCII; IRAF/fxcor puede fallar fuera de esta prueba.")
    overall_status = "ok"
    for case in cases:
        outcome = run_cl_case(workspace_root, case)
        if outcome["status"] != "ok" and overall_status == "ok":
            overall_status = outcome["status"]
        if outcome["status"] == "blocked":
            overall_status = "blocked"
        runs.append({"case": case, "outcome": outcome})
        notes.extend(outcome["notes"])
    if warning_findings and overall_status == "ok":
        overall_status = "warning"
    case_warning_findings = [note for note in notes if note.startswith("cl devolvio codigo")]
    warning_findings.extend(case_warning_findings)
    case_blocking_findings = [
        finding
        for item in runs
        for finding in item["outcome"].get("blocking_findings", [])
    ]

    payload = standard_tool_payload(
        RUN_TOOL,
        status=overall_status,
        notes=notes or ["fxcor ejecutado sobre la copia derivada."],
        artifacts={
            "workspace_root": str(workspace_root),
            "case_scripts": [item["outcome"].get("script_path") for item in runs if item["outcome"].get("script_path")],
            "txtonly_outputs": [item["outcome"].get("txtonly_path") for item in runs if item["outcome"].get("txtonly_path")],
            "parsed_csvs": [item["outcome"].get("parsed_csv") for item in runs if item["outcome"].get("parsed_csv")],
        },
        results={
            "case_runs": runs,
            "blocking_findings": case_blocking_findings,
            "warning_findings": warning_findings,
            "path_risk": {"workspace_root": workspace_risk},
        },
        qa=standard_qa_payload(
            status=overall_status,
            findings=[*warning_findings, *case_blocking_findings],
            metrics={
                "case_count": len(cases),
                "ok_case_count": sum(1 for item in runs if item["outcome"]["status"] == "ok"),
                "warning_case_count": sum(1 for item in runs if item["outcome"]["status"] == "warning"),
                "blocked_case_count": sum(1 for item in runs if item["outcome"]["status"] == "blocked"),
                "parsed_csv_count": sum(1 for item in runs if item["outcome"].get("parsed_csv")),
                "warning_count": len(warning_findings),
            },
        ),
    )
    outputs = [workspace_root / "logs", workspace_root / "parsed", workspace_root / "scripts"]
    return emit_run_payload(payload, args, manifest_inputs=[workspace_root / "fxcor_cases.json"], manifest_outputs=outputs, manifest_notes=notes, selected_ids=selected_ids)


def load_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def apply_manual_overrides(auto_rows: list[dict], override_rows: list[dict]) -> tuple[list[dict], list[str]]:
    keyed = {(row["case_id"], str(row["aperture"])): row for row in override_rows}
    merged = []
    notes = []
    for row in auto_rows:
        key = (row["case_id"], str(row["aperture"]))
        override = keyed.get(key)
        if override is None:
            record = dict(row)
            record["row_source"] = "auto"
            record["manual_note"] = ""
            merged.append(record)
            continue
        include_value = str(override.get("include", "auto")).strip().lower()
        if include_value in {"no", "false", "0", "drop", "exclude"}:
            notes.append(f"Fila {row['case_id']} / orden {row['aperture']} excluida por override manual.")
            continue
        record = dict(row)
        manual_used = False
        for source_field, target_field in [
            ("override_shift_pix", "shift_pix"),
            ("override_fwhm_kms", "fwhm_kms"),
            ("override_tdr", "tdr"),
            ("override_vrel_kms", "vrel_kms"),
            ("override_verr_kms", "verr_kms"),
        ]:
            value = str(override.get(source_field, "")).strip()
            if value:
                record[target_field] = value
                manual_used = True
        record["row_source"] = "manual" if manual_used or include_value == "manual" else "auto"
        record["manual_note"] = override.get("notes", "")
        merged.append(record)
    return merged, notes


def cmd_merge_overrides(args):
    configure_runtime("fxcor_iraf_workbench_merge")
    workspace_root, _ = load_workspace_config(args.workspace)
    manual_csv = Path(args.manual_csv).expanduser().resolve() if args.manual_csv else workspace_root / "manual_overrides.csv"
    if not manual_csv.exists():
        raise SystemExit(f"No se encontro el CSV de overrides: {manual_csv}")

    auto_csvs = sorted((workspace_root / "parsed").glob("*_auto.csv"))
    if not auto_csvs:
        raise SystemExit("No hay CSVs automaticos en parsed/ para fusionar.")
    auto_rows = []
    for csv_path in auto_csvs:
        auto_rows.extend(load_csv_rows(csv_path))
    merged_rows, notes = apply_manual_overrides(auto_rows, load_csv_rows(manual_csv))

    merged_csv = workspace_root / "parsed" / "merged_overrides.csv"
    if merged_rows:
        fieldnames = list(merged_rows[0].keys())
        with merged_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged_rows)

    payload = standard_tool_payload(
        "fxcor_iraf_workbench.merge-overrides",
        status="ok",
        notes=notes or ["Overrides manuales fusionados con prioridad por fila."],
        artifacts={"merged_csv": str(merged_csv), "manual_csv": str(manual_csv)},
        results={"row_count": len(merged_rows)},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered + "\n", encoding="utf-8")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[manual_csv, *auto_csvs],
            outputs=[merged_csv],
            parameters={"tool": "fxcor_iraf_workbench.merge-overrides"},
            command=" ".join(sys.argv),
            notes=notes,
        )


def main():
    args = parse_args()
    if args.command == "prepare-session":
        return cmd_prepare_session(args)
    elif args.command == "run-auto":
        return cmd_run_auto(args)
    elif args.command == "merge-overrides":
        cmd_merge_overrides(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
