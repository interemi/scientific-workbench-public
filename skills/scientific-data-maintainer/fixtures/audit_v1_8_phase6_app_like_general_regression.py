#!/usr/bin/env python3
"""v1.8 app-like regression for general ScientificWorkbench-style families."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import os
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_8_phase6_app_like_general"
INPUTS = TMP / "inputs"
RUNS = TMP / "runs"
REPORT = TMP / "phase6_app_like_general_report.md"
SUMMARY = TMP / "phase6_app_like_general_summary.json"
PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_file():
        return {path.name: sha256(path)}
    hashes: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            hashes[str(item.relative_to(path))] = sha256(item)
    return hashes


def clean_tmp() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    INPUTS.mkdir(parents=True)
    RUNS.mkdir(parents=True)


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def write_notebook(path: Path) -> None:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Legacy handoff notebook\n", "Small anonymized notebook for app-like inspection.\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["import pandas as pd\n", "pd.DataFrame({'x': [1, 2], 'y': [3, 4]})\n"],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_fixtures() -> dict[str, Path]:
    fixtures: dict[str, Path] = {}

    professional = INPUTS / "professional_tables" / "service_metrics.csv"
    write_csv(
        professional,
        ["date", "department", "tickets", "resolution_hours", "cost_eur"],
        [
            ["2026-01-01", "support", 18, 4.2, 310.5],
            ["2026-01-02", "support", 21, 3.8, 328.0],
            ["2026-01-03", "ops", 9, 2.1, 140.0],
            ["2026-01-04", "ops", 12, 2.7, 171.0],
        ],
    )
    fixtures["professional_tables"] = professional

    docs = INPUTS / "administrative_documents"
    docs.mkdir(parents=True)
    (docs / "policy_brief.md").write_text("# Policy brief\n\nNo private data. Pending signatures.\n", encoding="utf-8")
    (docs / "handoff_notes.txt").write_text("Checklist: invoice, consent form, delivery dates.\n", encoding="utf-8")
    (docs / "scanned_notice.pdf").write_bytes(b"%PDF-1.4\n% anonymized placeholder for routing\n")
    fixtures["administrative_documents"] = docs

    notebook = INPUTS / "legacy_notebooks" / "handoff_analysis.ipynb"
    notebook.parent.mkdir(parents=True)
    write_notebook(notebook)
    fixtures["legacy_notebooks"] = notebook

    package_dir = INPUTS / "compressed_packages"
    package_dir.mkdir(parents=True)
    package_zip = package_dir / "project_export.zip"
    with zipfile.ZipFile(package_zip, "w") as zf:
        zf.writestr("tables/summary.csv", "month,value\n2026-01,10\n2026-02,12\n")
        zf.writestr("notes/readme.txt", "Anonymized project export.\n")
    fixtures["compressed_packages"] = package_zip

    series = INPUTS / "time_series" / "monthly_energy.csv"
    monthly_rows = []
    for idx in range(14):
        year = 2025 + idx // 12
        month = idx % 12 + 1
        monthly_rows.append([f"{year}-{month:02d}-01", 213 + idx * 3 + (idx % 3) * 7])
    write_csv(
        series,
        ["date", "kwh"],
        monthly_rows,
    )
    fixtures["time_series"] = series

    sensor = INPUTS / "measurement_sensor" / "environment_sensor.csv"
    write_csv(
        sensor,
        ["timestamp", "temperature_c", "humidity_pct", "signal", "uncertainty"],
        [
            ["2026-02-01T00:00:00", 21.1, 42.0, 100.0, 0.2],
            ["2026-02-01T01:00:00", 21.3, 43.0, 101.0, 0.2],
            ["2026-02-01T02:00:00", "NaN", 44.0, 99.0, 0.2],
            ["2026-02-01T03:00:00", 999.0, 44.5, "Inf", 0.2],
        ],
    )
    fixtures["measurement_sensor"] = sensor

    personal = INPUTS / "personal_mixed_folder"
    personal.mkdir(parents=True)
    write_csv(
        personal / "budget.csv",
        ["date", "category", "amount_eur"],
        [["2026-03-01", "groceries", 54.2], ["2026-03-02", "transport", 12.8]],
    )
    (personal / "trip_notes.md").write_text("# Weekend plan\n\nTickets, budget, packing list.\n", encoding="utf-8")
    (personal / "receipt.txt").write_text("Anonymized receipt text.\n", encoding="utf-8")
    with zipfile.ZipFile(personal / "attachments.zip", "w") as zf:
        zf.writestr("attachment.txt", "small personal sidecar\n")
    fixtures["personal_mixed_folder"] = personal

    return fixtures


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def app_status(payload: dict[str, Any]) -> str:
    return payload.get("app_status") or {"ok": "PASS", "warning": "WARNING", "blocked": "BLOCKED_CONTROLADO", "fail": "FAIL"}.get(
        str(payload.get("status", "")).lower(), "FAIL"
    )


def path_from_payload(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def discover_artifacts(summary_path: Path, payload: dict[str, Any], run_dir: Path | None) -> list[str]:
    discovered: list[str] = []
    if summary_path.exists():
        discovered.append(str(summary_path))
    for item in payload.get("typed_artifacts", []) or []:
        raw_path = item.get("path") if isinstance(item, dict) else None
        if not raw_path:
            continue
        candidate = path_from_payload(str(raw_path))
        if candidate.exists():
            discovered.append(str(candidate))
    if run_dir and run_dir.exists():
        for name in ("manifest.json", "summary.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md"):
            candidate = run_dir / name
            if candidate.exists():
                discovered.append(str(candidate))
    return sorted(set(discovered))


def validate_envelope(payload: dict[str, Any], case: str) -> None:
    for key in ("contract_version", "tool", "status", "qa", "next_actions", "original_modified"):
        require(key in payload, f"{case}: falta campo envelope {key}")
    require(payload["contract_version"] == "1.8", f"{case}: contract_version inesperado")
    require(payload["original_modified"] is False, f"{case}: original_modified debe ser false")
    require(isinstance(payload.get("next_actions"), list) and payload["next_actions"], f"{case}: next_actions vacio")
    require(app_status(payload) in {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}, f"{case}: app_status invalido")


def run_router(case: str, fixture: Path, task: str, expected_first: str) -> dict[str, Any]:
    run_dir = RUNS / case / "router"
    run_dir.mkdir(parents=True)
    summary_json = run_dir / "summary.json"
    manifest_json = run_dir / "manifest.json"
    cmd = [
        str(PYTHON),
        str(SCRIPTS / "scientific_workflow_router.py"),
        "plan",
        str(fixture),
        "--task",
        task,
        "--summary-json",
        str(summary_json),
        "--manifest-json",
        str(manifest_json),
    ]
    result = run_command(cmd)
    require(result.returncode == 0, f"{case}: router fallo {result.returncode}: {result.stderr}")
    require("Traceback" not in result.stdout + result.stderr, f"{case}: router emitio traceback")
    payload = json.loads(result.stdout)
    validate_envelope(payload, f"{case}/router")
    require(payload["recommended_capabilities"], f"{case}: router sin recomendaciones")
    first = payload["recommended_capabilities"][0]["label"]
    require(first == expected_first, f"{case}: primera recomendacion {first!r} != {expected_first!r}")
    return {
        "command": " ".join(cmd),
        "summary_json": str(summary_json),
        "manifest_json": str(manifest_json),
        "payload": payload,
        "first_recommendation": first,
    }


def capability_command(case: str, fixture: Path) -> tuple[list[str], Path, Path | None, str]:
    run_root = RUNS / case / "capability"
    run_root.mkdir(parents=True)
    if case == "professional_tables":
        run_dir = run_root / "run"
        return (
            [str(PYTHON), str(SCRIPTS / "profile_table.py"), str(fixture), "--run-dir", str(run_dir)],
            run_dir / "summary.json",
            run_dir,
            "Perfila una tabla profesional y deja summary/manifest/next_steps para decidir limpieza o analisis.",
        )
    if case == "administrative_documents":
        run_dir = run_root / "run"
        return (
            [str(PYTHON), str(SCRIPTS / "document_intake_workbench.py"), str(fixture), "--run-dir", str(run_dir)],
            run_dir / "summary.json",
            run_dir,
            "Resume un paquete administrativo, inventaria documentos y avisa de placeholders/formato.",
        )
    if case == "legacy_notebooks":
        summary = run_root / "summary.json"
        manifest = run_root / "manifest.json"
        return (
            [str(PYTHON), str(SCRIPTS / "notebook_workbench.py"), "inspect", str(fixture), "--summary-json", str(summary), "--manifest-json", str(manifest)],
            summary,
            None,
            "Inspecciona el notebook heredado antes de ejecutar copias y conserva el original intacto.",
        )
    if case == "compressed_packages":
        run_dir = run_root / "run"
        return (
            [str(PYTHON), str(SCRIPTS / "inspect_data_container.py"), str(fixture), "--run-dir", str(run_dir)],
            run_dir / "summary.json",
            run_dir,
            "Lista el contenido del ZIP sin extraerlo a ciegas y detecta riesgos de contenedor.",
        )
    if case == "time_series":
        summary = run_root / "summary.json"
        manifest = run_root / "manifest.json"
        output_dir = run_root / "forecast"
        return (
            [
                str(PYTHON),
                str(SCRIPTS / "timeseries_forecasting_workbench.py"),
                "--output-dir",
                str(output_dir),
                "--data-path",
                str(fixture),
                "--date-column",
                "date",
                "--value-column",
                "kwh",
                "--test-horizon",
                "4",
                "--summary-json",
                str(summary),
                "--manifest-json",
                str(manifest),
            ],
            summary,
            None,
            "Crea scaffold reproducible de forecasting con notebook y manifest para continuar el analisis.",
        )
    if case == "measurement_sensor":
        summary = run_root / "summary.json"
        return (
            [str(PYTHON), str(SCRIPTS / "physical_qa.py"), str(fixture), "--summary-json", str(summary)],
            summary,
            None,
            "Detecta valores no finitos y rangos sospechosos antes de modelar o reportar mediciones.",
        )
    if case == "personal_mixed_folder":
        run_dir = run_root / "run"
        return (
            [str(PYTHON), str(SCRIPTS / "cross_domain_data_workbench.py"), str(fixture), "--run-dir", str(run_dir)],
            run_dir / "summary.json",
            run_dir,
            "Convierte una carpeta personal mixta en inventario/report para decidir el siguiente paso.",
        )
    raise KeyError(case)


def run_capability(case: str, fixture: Path) -> dict[str, Any]:
    cmd, summary_json, run_dir, usefulness = capability_command(case, fixture)
    before = hash_tree(fixture)
    result = run_command(cmd)
    after = hash_tree(fixture)
    require(before == after, f"{case}: la capability modifico el input")
    require("Traceback" not in result.stdout + result.stderr, f"{case}: traceback crudo")
    require(summary_json.exists(), f"{case}: no existe summary_json")
    payload = load_json(summary_json)
    validate_envelope(payload, f"{case}/capability")
    discovered = discover_artifacts(summary_json, payload, run_dir)
    require(discovered, f"{case}: no se descubrieron artefactos")
    accepted_returncodes = {0}
    if app_status(payload) in {"WARNING", "BLOCKED_CONTROLADO", "FAIL"}:
        accepted_returncodes.add(2)
    require(result.returncode in accepted_returncodes, f"{case}: returncode {result.returncode} no concuerda con {app_status(payload)}")
    return {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "summary_json": str(summary_json),
        "run_dir": str(run_dir) if run_dir else None,
        "payload": payload,
        "app_status": app_status(payload),
        "artifact_count": len(discovered),
        "artifacts": discovered[:12],
        "usefulness": usefulness,
    }


def classify_result(capability: dict[str, Any]) -> str:
    status = capability["app_status"]
    if status == "PASS":
        return "PASS"
    if status == "WARNING":
        return "WARNING"
    if status == "BLOCKED_CONTROLADO":
        return "BLOCKED_CONTROLADO"
    return "FAIL"


def main() -> int:
    clean_tmp()
    fixtures = make_fixtures()
    cases = [
        {
            "case": "professional_tables",
            "family": "tablas profesionales",
            "task": "perfilar tabla profesional anonima y decidir limpieza",
            "expected_first": "profile_table.py",
        },
        {
            "case": "administrative_documents",
            "family": "documentos administrativos",
            "task": "hacer intake de documentos administrativos anonimizados",
            "expected_first": "document_intake_workbench.py",
        },
        {
            "case": "legacy_notebooks",
            "family": "notebooks heredados",
            "task": "revisar notebook heredado antes de ejecutarlo",
            "expected_first": "coursework_notebook_fidelity_check.py",
        },
        {
            "case": "compressed_packages",
            "family": "contenedores/paquetes comprimidos",
            "task": "inspeccionar paquete comprimido antes de extraer",
            "expected_first": "inspect_data_container.py",
        },
        {
            "case": "time_series",
            "family": "series temporales",
            "task": "serie temporal forecasting mensual de consumo energetico",
            "expected_first": "timeseries_forecasting_workbench.py",
        },
        {
            "case": "measurement_sensor",
            "family": "medicion/sensor",
            "task": "QA de sensor con NaN Inf rangos sospechosos e incertidumbre",
            "expected_first": "physical_qa.py",
        },
        {
            "case": "personal_mixed_folder",
            "family": "carpeta mixta personal",
            "task": "diagnosticar carpeta mixta personal con presupuesto notas y adjuntos",
            "expected_first": "cross_domain_data_workbench.py",
        },
    ]

    rows = []
    for item in cases:
        case = item["case"]
        fixture = fixtures[case]
        router = run_router(case, fixture, item["task"], item["expected_first"])
        capability = run_capability(case, fixture)
        rows.append(
            {
                "case": case,
                "family": item["family"],
                "fixture": str(fixture),
                "router_command": router["command"],
                "capability_command": capability["command"],
                "state": classify_result(capability),
                "router_first": router["first_recommendation"],
                "capability_app_status": capability["app_status"],
                "summary_json": capability["summary_json"],
                "artifact_count": capability["artifact_count"],
                "artifacts": capability["artifacts"],
                "helpful_for_real_person": capability["app_status"] in {"PASS", "WARNING", "BLOCKED_CONTROLADO"}
                and bool(capability["payload"].get("next_actions")),
                "diagnostic": capability["usefulness"],
            }
        )

    overall = "PASS" if all(row["state"] in {"PASS", "WARNING", "BLOCKED_CONTROLADO"} for row in rows) else "FAIL"
    SUMMARY.write_text(json.dumps({"status": overall, "rows": rows}, indent=2), encoding="utf-8")

    lines = [
        "# v1.8 Phase 6 App-Like General Regression",
        "",
        f"Status: {overall}",
        "",
        "| familia | estado | router principal | artefactos | utilidad real |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        helpful = "si" if row["helpful_for_real_person"] else "no"
        lines.append(
            f"| {row['family']} | `{row['state']}` | `{row['router_first']}` | {row['artifact_count']} | {helpful}: {row['diagnostic']} |"
        )
    lines.extend(["", f"Machine summary: `{SUMMARY}`", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": overall, "report": str(REPORT), "summary": str(SUMMARY)}, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
