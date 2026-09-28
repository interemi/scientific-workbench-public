#!/usr/bin/env python3
"""v1.7 phase 4 regression for professional and personal real-world packages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "sda_v1_7_phase4_professional_personal_packages"


def fail(message: str) -> None:
    raise AssertionError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated anonymized packages, command logs, and reports.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_to_temp(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def copytree_to_temp(source: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"expected JSON output missing: {path}")
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda token: fail(f"non-strict JSON constant emitted: {token}"),
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_docx(path: Path, title: str, paragraphs: list[str]) -> Path | None:
    try:
        from docx import Document
    except ImportError:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading(title, level=1)
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(path)
    return path


def write_notebook(path: Path, title: str, code: str) -> Path:
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# {title}\n", "Synthetic anonymized v1.7 package fixture.\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def run_command(case_dir: Path, command: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    case_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        cwd=SKILL_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    (case_dir / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")
    (case_dir / "command.json").write_text(json.dumps(command, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (case_dir / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (case_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    (case_dir / "returncode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    combined = proc.stdout + "\n" + proc.stderr
    if "Traceback (most recent call last)" in combined:
        fail(f"traceback leaked for command: {' '.join(command)}")
    return proc


def status_label(proc: subprocess.CompletedProcess[str], payload: dict[str, Any] | None) -> str:
    if payload and payload.get("status") == "blocked":
        return "BLOCKED_CONTROLADO"
    if proc.returncode != 0:
        if payload and payload.get("status") in {"blocked", "fail"}:
            return "BLOCKED_CONTROLADO"
        return "FAIL"
    if payload and payload.get("status") == "warning":
        return "WARNING"
    return "PASS"


def require_returncode(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        fail(f"{label} failed: {proc.stderr or proc.stdout}")


def is_sandbox_blocked(payload: dict[str, Any]) -> bool:
    run = payload.get("results", {}).get("run", {})
    assessment = run.get("assessment", {}) if isinstance(run, dict) else {}
    return payload.get("status") == "blocked" and assessment.get("status") == "sandbox_blocked"


def require_payload_status(payload: dict[str, Any], expected: set[str], label: str) -> None:
    status = payload.get("status")
    qa_status = (payload.get("qa") or {}).get("status")
    sandbox_blocked = is_sandbox_blocked(payload)
    if status not in expected and not ({"ok", "warning"} & expected and sandbox_blocked):
        fail(f"{label}: expected status in {sorted(expected)}, got {status}")
    if sandbox_blocked and qa_status == "warning":
        return
    if qa_status and qa_status != status:
        fail(f"{label}: qa.status {qa_status} did not match status {status}")


def make_sqlite(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE tasks(task_id TEXT, owner TEXT, state TEXT, hours REAL)")
        for row in rows:
            conn.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                (row["task_id"], row["owner"], row["state"], float(row["hours"])),
            )
        conn.commit()
    return path


def make_npz(path: Path) -> Path | None:
    try:
        import numpy as np
    except ImportError:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        room_temperature_c=np.array([19.2, 19.4, 20.1, 21.3, 20.8], dtype=float),
        humidity_pct=np.array([42.0, 43.5, 45.0, 48.0, 47.2], dtype=float),
    )
    return path


def create_fixtures(source_root: Path) -> dict[str, Any]:
    professional = source_root / "professional"
    personal = source_root / "personal"

    ops_rows = [
        {"ticket_id": "T-001", "team": "support", "priority": "P2", "resolution_hours": "5.2", "sla_breached": "false", "impact_eur": "1200"},
        {"ticket_id": "T-002", "team": "billing", "priority": "P1", "resolution_hours": "46.0", "sla_breached": "true", "impact_eur": "inf"},
        {"ticket_id": "T-003", "team": "data", "priority": "P2", "resolution_hours": "18.5", "sla_breached": "false", "impact_eur": "430"},
        {"ticket_id": "T-004", "team": "support", "priority": "P3", "resolution_hours": "2.7", "sla_breached": "false", "impact_eur": "0"},
    ]
    capacity_rows = [
        {"team": "billing", "weekly_capacity_hours": "120"},
        {"team": "data", "weekly_capacity_hours": "80"},
        {"team": "support", "weekly_capacity_hours": "220"},
    ]
    budget_rows = [
        {"date": "2026-05-01", "category": "groceries", "planned_eur": "320", "actual_eur": "342.20"},
        {"date": "2026-05-02", "category": "transport", "planned_eur": "90", "actual_eur": "75.00"},
        {"date": "2026-05-03", "category": "home", "planned_eur": "180", "actual_eur": "210.35"},
        {"date": "2026-05-04", "category": "savings", "planned_eur": "400", "actual_eur": "400.00"},
    ]
    daily_orders = [
        {"date": f"2026-04-{day:02d}", "orders": str(94 + day + (day % 5) * 3)}
        for day in range(1, 31)
    ]
    weekly_energy = [
        {"date": f"2026-{month:02d}-01", "kwh": str(260 + month * 9 + (month % 3) * 12)}
        for month in range(1, 13)
    ]
    professional_sensor = [
        {"time": "2026-05-20T09:00:00", "signal": "102.4", "signal_error": "0.8", "background_counts": "11.2"},
        {"time": "2026-05-20T09:01:00", "signal": "inf", "signal_error": "0.9", "background_counts": "11.1"},
        {"time": "2026-05-20T09:02:00", "signal": "-4.0", "signal_error": "-0.3", "background_counts": "11.3"},
        {"time": "not-a-time", "signal": "103.1", "signal_error": "0.7", "background_counts": "11.0"},
    ]
    personal_sensor = [
        {"time": "2026-05-20T22:00:00", "counts": "31.2", "error": "0.5", "room": "living"},
        {"time": "2026-05-20T23:00:00", "counts": "29.8", "error": "0.4", "room": "living"},
        {"time": "2026-05-20T21:00:00", "counts": "33.1", "error": "0.5", "room": "living"},
        {"time": "2026-05-21T00:00:00", "counts": "-1.0", "error": "0.4", "room": "living"},
    ]

    paths: dict[str, Any] = {}
    paths["professional_table_dir"] = professional / "tables"
    paths["personal_table_dir"] = personal / "tables"
    paths["ops_tickets"] = write_csv(paths["professional_table_dir"] / "support_tickets_anon.csv", list(ops_rows[0]), ops_rows)
    paths["team_capacity"] = write_csv(paths["professional_table_dir"] / "team_capacity.csv", list(capacity_rows[0]), capacity_rows)
    paths["budget_table"] = write_csv(paths["personal_table_dir"] / "household_budget_anon.csv", list(budget_rows[0]), budget_rows)

    paths["professional_docs"] = professional / "documents"
    paths["personal_docs"] = personal / "documents"
    write_text(
        paths["professional_docs"] / "vendor_handoff.md",
        "# Vendor handoff\n\nAnonymous support migration packet. Next step: confirm the P1 billing incident and clean the infinite finance placeholder.\n",
    )
    write_text(
        paths["professional_docs"] / "release_note.txt",
        "Release note: anonymized internal service package. Verify table freshness before executive summary.\n",
    )
    write_docx(
        paths["professional_docs"] / "ops_summary.docx",
        "Anonymous operations summary",
        ["No private customer data is present.", "One finance placeholder should be cleaned before reporting."],
    )
    write_text(
        paths["personal_docs"] / "home_project_plan.md",
        "# Home project plan\n\nAnonymous renovation checklist. Next step: separate receipts from decisions and dates.\n",
    )
    write_text(
        paths["personal_docs"] / "travel_admin_note.txt",
        "Travel admin note. Names removed. Check booking deadlines and reimbursement status.\n",
    )
    write_docx(
        paths["personal_docs"] / "family_admin_summary.docx",
        "Anonymous personal admin summary",
        ["Contains no real names.", "Next step is to sort open actions by due date."],
    )

    paths["professional_notebook"] = write_notebook(
        professional / "notebooks" / "ops_review_legacy.ipynb",
        "Operations KPI Review",
        "import pandas as pd\n"
        "df = pd.read_csv('support_tickets_anon.csv')\n"
        "print(df.groupby('team')['resolution_hours'].mean().round(2).to_dict())\n",
    )
    paths["personal_notebook"] = write_notebook(
        personal / "notebooks" / "budget_review_legacy.ipynb",
        "Household Budget Review",
        "import pandas as pd\n"
        "df = pd.read_csv('household_budget_anon.csv')\n"
        "df['variance_eur'] = df['actual_eur'] - df['planned_eur']\n"
        "print(df[['category', 'variance_eur']].to_dict('records'))\n",
    )

    paths["professional_container_dir"] = professional / "container_source"
    paths["personal_container_dir"] = personal / "container_source"
    (paths["professional_container_dir"] / "tables").mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["ops_tickets"], paths["professional_container_dir"] / "tables" / "support_tickets_anon.csv")
    shutil.copy2(paths["team_capacity"], paths["professional_container_dir"] / "tables" / "team_capacity.csv")
    write_text(paths["professional_container_dir"] / "README.txt", "Anonymous professional package for v1.7 phase 4.\n")
    make_sqlite(
        paths["professional_container_dir"] / "tasks.sqlite",
        [
            {"task_id": "A-1", "owner": "ops", "state": "open", "hours": "3.5"},
            {"task_id": "A-2", "owner": "data", "state": "done", "hours": "1.2"},
        ],
    )
    (paths["personal_container_dir"] / "budget").mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["budget_table"], paths["personal_container_dir"] / "budget" / "household_budget_anon.csv")
    write_text(paths["personal_container_dir"] / "README.txt", "Anonymous personal archive for v1.7 phase 4.\n")
    npz = make_npz(paths["personal_container_dir"] / "home_sensor_snapshot.npz")
    if npz is not None:
        paths["personal_npz"] = npz
    paths["professional_zip"] = professional / "containers" / "ops_package_anon.zip"
    paths["professional_zip"].parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(paths["professional_zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(paths["professional_container_dir"].rglob("*")):
            if item.is_file():
                archive.write(item, arcname=str(item.relative_to(paths["professional_container_dir"])))
    paths["personal_zip"] = personal / "containers" / "home_admin_archive_anon.zip"
    paths["personal_zip"].parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(paths["personal_zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(paths["personal_container_dir"].rglob("*")):
            if item.is_file():
                archive.write(item, arcname=str(item.relative_to(paths["personal_container_dir"])))

    paths["daily_orders"] = write_csv(professional / "timeseries" / "daily_orders_anon.csv", list(daily_orders[0]), daily_orders)
    paths["weekly_energy"] = write_csv(personal / "timeseries" / "weekly_energy_anon.csv", list(weekly_energy[0]), weekly_energy)
    paths["professional_sensor"] = write_csv(professional / "measurement" / "sensor_roi_counts.csv", list(professional_sensor[0]), professional_sensor)
    paths["personal_sensor"] = write_csv(personal / "measurement" / "home_room_sensor.csv", list(personal_sensor[0]), personal_sensor)
    return paths


def case_table_professional(output_dir: Path, source_dir: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / "tables_professional"
    input_dir = copytree_to_temp(source_dir, case_dir / "input_copy" / "ops_tables")
    before = {path: sha256(path) for path in sorted(input_dir.rglob("*")) if path.is_file()}
    out_dir = case_dir / "out"
    summary = case_dir / "summary.json"
    manifest = case_dir / "manifest.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "cross_domain_data_workbench.py"),
        str(input_dir),
        "--head",
        "4",
        "--output-dir",
        str(out_dir),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, "cross_domain_data_workbench professional tables")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, "professional tables")
    if not (out_dir / "inventory.csv").exists() or not (out_dir / "report.md").exists():
        fail("professional tables did not produce inventory/report")
    if {path: sha256(path) for path in sorted(input_dir.rglob("*")) if path.is_file()} != before:
        fail("professional table inputs were modified")
    return case_row(
        "tablas",
        "profesional",
        "cross_domain_data_workbench.py",
        input_dir,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        "Inventario y perfil de tablas de operaciones; permite decidir limpiar el valor infinito antes del informe.",
        out_dir / "report.md",
    )


def case_table_personal(output_dir: Path, source: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / "tables_personal"
    input_file = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_file)
    summary = case_dir / "summary.json"
    manifest = case_dir / "manifest.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "profile_table.py"),
        str(input_file),
        "--head",
        "4",
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, "profile_table personal table")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, "personal table")
    if sha256(input_file) != before:
        fail("personal table input was modified")
    return case_row(
        "tablas",
        "personal",
        "profile_table.py",
        input_file,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        "Perfil de presupuesto familiar; permite ver categorias y columnas numericas antes de calcular desviaciones.",
        summary,
    )


def case_document(output_dir: Path, context: str, source_dir: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / f"documents_{context}"
    input_dir = copytree_to_temp(source_dir, case_dir / "input_copy" / f"{context}_documents")
    before = {path: sha256(path) for path in sorted(input_dir.rglob("*")) if path.is_file()}
    out_dir = case_dir / "out"
    summary = case_dir / "summary.json"
    manifest = case_dir / "manifest.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "document_intake_workbench.py"),
        str(input_dir),
        "--output-dir",
        str(out_dir),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, f"document_intake {context}")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, f"documents {context}")
    if not (out_dir / "inventory.csv").exists() or not (out_dir / "report.md").exists():
        fail(f"{context} documents did not produce inventory/report")
    if {path: sha256(path) for path in sorted(input_dir.rglob("*")) if path.is_file()} != before:
        fail(f"{context} document inputs were modified")
    diagnostic = (
        "Intake de documentos de handoff; permite decidir que nota convertir en siguiente accion."
        if context == "professional"
        else "Intake de documentos personales; permite separar recibos/notas de decisiones pendientes."
    )
    return case_row(
        "documentos",
        "profesional" if context == "professional" else "personal",
        "document_intake_workbench.py",
        input_dir,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        diagnostic,
        out_dir / "report.md",
    )


def case_notebook(output_dir: Path, context: str, notebook: Path, staged_csv: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / f"notebooks_{context}"
    input_notebook = copy_to_temp(notebook, case_dir / "input_copy" / notebook.name)
    input_csv = copy_to_temp(staged_csv, case_dir / "input_copy" / staged_csv.name)
    before = {input_notebook: sha256(input_notebook), input_csv: sha256(input_csv)}
    summary = case_dir / "summary.json"
    manifest = case_dir / "manifest.json"
    out_dir = case_dir / "executed_copy"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "notebook_workbench.py"),
        "execute-copy",
        str(input_notebook),
        "--output-dir",
        str(out_dir),
        "--kernel-name",
        "python3",
        "--timeout-sec",
        "120",
        "--stage-extra",
        str(input_csv),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command, timeout=240)
    require_returncode(proc, f"notebook_workbench {context}")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, f"notebook {context}")
    if {input_notebook: sha256(input_notebook), input_csv: sha256(input_csv)} != before:
        fail(f"{context} notebook inputs were modified")
    if not list(out_dir.glob("*.ipynb")):
        fail(f"{context} notebook did not write executed copy")
    diagnostic = (
        "Ejecuta una copia de notebook heredado de KPIs; permite confiar en el calculo sin tocar el original."
        if context == "professional"
        else "Ejecuta una copia de notebook personal de presupuesto; permite revisar desviaciones sin modificar el original."
    )
    return case_row(
        "notebooks",
        "profesional" if context == "professional" else "personal",
        "notebook_workbench.py execute-copy",
        input_notebook,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        diagnostic,
        out_dir,
    )


def case_container(output_dir: Path, context: str, source: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / f"containers_{context}"
    input_file = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_file)
    summary = case_dir / "summary.json"
    output_json = case_dir / "container_inventory.json"
    manifest = case_dir / "manifest.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "inspect_data_container.py"),
        str(input_file),
        "--summary-json",
        str(summary),
        "--output-json",
        str(output_json),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, f"inspect_data_container {context}")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, f"container {context}")
    if sha256(input_file) != before:
        fail(f"{context} container input was modified")
    diagnostic = (
        "Inventario seguro de ZIP profesional; permite decidir si extraerlo y que subarchivos revisar."
        if context == "professional"
        else "Inventario seguro de archivo personal; permite decidir si contiene tablas/sensores utiles antes de extraer."
    )
    return case_row(
        "contenedores",
        "profesional" if context == "professional" else "personal",
        "inspect_data_container.py",
        input_file,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        diagnostic,
        output_json,
    )


def case_timeseries(output_dir: Path, context: str, source: Path, date_col: str, value_col: str, freq: str, horizon: int) -> dict[str, Any]:
    case_dir = output_dir / "cases" / f"timeseries_{context}"
    input_file = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_file)
    out_dir = case_dir / "forecast_package"
    summary = case_dir / "summary.json"
    manifest = case_dir / "manifest.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "timeseries_forecasting_workbench.py"),
        "--output-dir",
        str(out_dir),
        "--title",
        "Professional demand forecast" if context == "professional" else "Personal energy forecast",
        "--language",
        "bilingual",
        "--runtime-profile",
        "local",
        "--data-path",
        str(input_file),
        "--date-column",
        date_col,
        "--value-column",
        value_col,
        "--frequency",
        freq,
        "--test-horizon",
        str(horizon),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, f"timeseries_forecasting_workbench {context}")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, f"timeseries {context}")
    if sha256(input_file) != before:
        fail(f"{context} time series input was modified")
    if not list(out_dir.glob("*.ipynb")):
        fail(f"{context} time series did not scaffold notebook")
    diagnostic = (
        "Scaffold de forecast de demanda; permite decidir ejecutar notebook y revisar holdout."
        if context == "professional"
        else "Scaffold de consumo energetico; permite planear prediccion domestica sin hard-codear rutas."
    )
    return case_row(
        "series temporales",
        "profesional" if context == "professional" else "personal",
        "timeseries_forecasting_workbench.py",
        input_file,
        command,
        status_label(proc, payload),
        "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        diagnostic,
        out_dir,
    )


def case_measurement(output_dir: Path, context: str, source: Path) -> dict[str, Any]:
    case_dir = output_dir / "cases" / f"measurement_{context}"
    input_file = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_file)
    summary = case_dir / "summary.json"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "physical_qa.py"),
        str(input_file),
        "--summary-json",
        str(summary),
    ]
    proc = run_command(case_dir, command)
    require_returncode(proc, f"physical_qa {context}")
    payload = read_json(summary)
    require_payload_status(payload, {"ok", "warning"}, f"measurement {context}")
    if sha256(input_file) != before:
        fail(f"{context} measurement input was modified")
    findings = payload.get("qa", {}).get("findings", [])
    diagnostic = (
        "QA de sensor profesional: detecta no-finitos, signo raro y errores negativos antes de usar la serie."
        if context == "professional"
        else "QA de sensor personal: detecta orden temporal/signo sospechoso antes de interpretar consumo o ambiente."
    )
    return case_row(
        "medicion/sensor",
        "profesional" if context == "professional" else "personal",
        "physical_qa.py",
        input_file,
        command,
        status_label(proc, payload),
        "; ".join(str(item) for item in findings) or "none",
        diagnostic,
        summary,
    )


def case_row(
    family: str,
    context: str,
    capability: str,
    input_path: Path,
    command: list[str],
    status: str,
    warning_error: str,
    diagnostic: str,
    artifact: Path,
) -> dict[str, Any]:
    return {
        "family": family,
        "context": context,
        "capability": capability,
        "input": str(input_path),
        "command": " ".join(command),
        "status": status,
        "warning_error": warning_error,
        "diagnostic": diagnostic,
        "modifies_originals": "NO: command ran on a copied temporary package and copied input hashes were checked",
        "useful_for_real_person": "YES: " + diagnostic,
        "artifact": str(artifact),
    }


def write_report(output_dir: Path, cases: list[dict[str, Any]]) -> Path:
    report = output_dir / "phase4_professional_personal_packages_report.md"
    lines = [
        "# AUDITORIA v1.7 - Fase 4: paquetes profesionales y personales",
        "",
        "## Alcance",
        "",
        "Se crearon paquetes no academicos, sinteticos y anonimizados para seis familias. Cada familia cubre un caso profesional y uno personal.",
        "",
        "## Resultados",
        "",
        "| Familia | Contexto | Capability | Input | Comando | Estado | Warning/error | Diagnostico | Modifica originales | Artefacto |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        clean = {key: str(value).replace("|", "\\|") for key, value in case.items()}
        lines.append(
            "| {family} | {context} | {capability} | `{input}` | `{command}` | {status} | {warning_error} | {diagnostic} | {modifies_originals} | `{artifact}` |".format(
                **clean
            )
        )
    lines.extend(
        [
            "",
            "## Decision real-world",
            "",
            "Las salidas son utiles como primer paso de decision: limpiar datos, revisar documentos, ejecutar copia de notebook, inspeccionar contenedores antes de extraer, preparar forecast reproducible o bloquear interpretaciones de sensores sospechosos.",
            "",
            "No se crearon capabilities nuevas ni se sincronizo la skill instalada.",
        ]
    )
    report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report


def run_phase(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = create_fixtures(output_dir / "generated_packages")
    cases = [
        case_table_professional(output_dir, fixtures["professional_table_dir"]),
        case_table_personal(output_dir, fixtures["budget_table"]),
        case_document(output_dir, "professional", fixtures["professional_docs"]),
        case_document(output_dir, "personal", fixtures["personal_docs"]),
        case_notebook(output_dir, "professional", fixtures["professional_notebook"], fixtures["ops_tickets"]),
        case_notebook(output_dir, "personal", fixtures["personal_notebook"], fixtures["budget_table"]),
        case_container(output_dir, "professional", fixtures["professional_zip"]),
        case_container(output_dir, "personal", fixtures["personal_zip"]),
        case_timeseries(output_dir, "professional", fixtures["daily_orders"], "date", "orders", "D", 7),
        case_timeseries(output_dir, "personal", fixtures["weekly_energy"], "date", "kwh", "MS", 3),
        case_measurement(output_dir, "professional", fixtures["professional_sensor"]),
        case_measurement(output_dir, "personal", fixtures["personal_sensor"]),
    ]
    report = write_report(output_dir, cases)
    counts = {status: sum(1 for case in cases if case["status"] == status) for status in sorted({case["status"] for case in cases})}
    families = sorted({case["family"] for case in cases})
    missing_family_contexts = []
    for family in families:
        contexts = {case["context"] for case in cases if case["family"] == family}
        for context in ("profesional", "personal"):
            if context not in contexts:
                missing_family_contexts.append({"family": family, "missing_context": context})
    if missing_family_contexts:
        fail(f"missing required family/context coverage: {missing_family_contexts}")
    summary = {
        "phase": "v1.7 phase 4",
        "status": "ok",
        "case_count": len(cases),
        "family_count": len(families),
        "case_status_counts": counts,
        "output_dir": str(output_dir),
        "report_md": str(report),
        "cases": cases,
        "sync_installed": False,
    }
    (output_dir / "phase4_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    summary = run_phase(Path(args.output_dir))
    print(
        json.dumps(
            {
                "phase": summary["phase"],
                "status": summary["status"],
                "case_count": summary["case_count"],
                "family_count": summary["family_count"],
                "case_status_counts": summary["case_status_counts"],
                "report_md": summary["report_md"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
