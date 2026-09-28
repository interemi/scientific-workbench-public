#!/usr/bin/env python3
"""Focused regression for the v1.8 scientific workflow dry-run router."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_8_phase5_router"
FIXTURES = TMP / "fixtures"
RUNS = TMP / "runs"
REPORT = TMP / "phase5_router_regression_report.md"
SUMMARY = TMP / "phase5_router_regression.json"


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


def hash_path(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_file():
        return {path.name: sha256(path)}
    hashes: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            hashes[str(item.relative_to(path))] = sha256(item)
    return hashes


def reset_tmp() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    FIXTURES.mkdir(parents=True)
    RUNS.mkdir(parents=True)


def write_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "team", "hours", "cost_eur"])
        writer.writerow(["2026-01-01", "ops", "4.0", "120.50"])
        writer.writerow(["2026-01-02", "ops", "5.5", "165.00"])
        writer.writerow(["2026-01-03", "support", "3.0", "90.00"])


def make_fixtures() -> dict[str, Path]:
    csv_path = FIXTURES / "professional_metrics.csv"
    write_csv(csv_path)

    mixed = FIXTURES / "mixed project paquete"
    mixed.mkdir()
    write_csv(mixed / "client_metrics.csv")
    (mixed / "notes.txt").write_text("Project notes with no private data.\n", encoding="utf-8")
    (mixed / "brief.pdf").write_bytes(b"%PDF-1.4\n% minimal fake pdf for routing only\n")
    (mixed / "admin_fake.docx").write_text("fake docx payload for dry-run routing only\n", encoding="utf-8")
    with zipfile.ZipFile(mixed / "archive.zip", "w") as zf:
        zf.writestr("inside/readme.txt", "compressed sidecar\n")

    notebook = FIXTURES / "legacy_notebook.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": ["# Legacy notebook\n"]},
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": ["print('hello')\n"],
                    },
                ],
                "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    fake_fits = FIXTURES / "sensor_capture.fits"
    fake_fits.write_text("This looks like FITS by extension only.\n", encoding="utf-8")

    empty = FIXTURES / "empty_folder"
    empty.mkdir()

    return {
        "csv": csv_path,
        "mixed": mixed,
        "notebook": notebook,
        "fake_fits": fake_fits,
        "missing": FIXTURES / "missing.csv",
        "empty": empty,
    }


def run_router(case: str, args: list[str], input_path: Path | None) -> dict:
    run_dir = RUNS / case
    run_dir.mkdir(parents=True)
    summary_json = run_dir / "summary.json"
    manifest_json = run_dir / "manifest.json"
    before = hash_path(input_path) if input_path else {}
    cmd = [
        sys.executable,
        str(SCRIPTS / "scientific_workflow_router.py"),
        *args,
        "--summary-json",
        str(summary_json),
        "--manifest-json",
        str(manifest_json),
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    after = hash_path(input_path) if input_path else {}
    require(before == after, f"{case}: el router modifico el input")
    require(result.returncode == 0, f"{case}: returncode inesperado {result.returncode}: {result.stderr}")
    require("Traceback" not in result.stdout + result.stderr, f"{case}: traceback crudo en salida")
    payload = json.loads(result.stdout)
    require(summary_json.exists(), f"{case}: no se escribio summary_json")
    require(manifest_json.exists(), f"{case}: no se escribio manifest_json")
    require(json.loads(summary_json.read_text(encoding="utf-8"))["tool"] == "scientific_workflow_router", f"{case}: summary incorrecto")
    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    require("inputs" in manifest and "command" in manifest and "environment" in manifest, f"{case}: manifest incorrecto")
    return {
        "case": case,
        "command": " ".join(cmd),
        "payload": payload,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "summary_json": str(summary_json),
        "manifest_json": str(manifest_json),
    }


def app_status(payload: dict) -> str:
    return payload.get("app_status") or {"ok": "PASS", "warning": "WARNING", "blocked": "BLOCKED_CONTROLADO"}.get(
        payload.get("status"), "FAIL"
    )


def validate_payload(record: dict, expected_kind: str, accepted_statuses: set[str]) -> None:
    payload = record["payload"]
    case = record["case"]
    for key in (
        "contract_version",
        "tool",
        "status",
        "input_kind",
        "recommended_capabilities",
        "rejected_capabilities",
        "plan_steps",
        "required_backends",
        "safety_notes",
        "next_actions",
        "original_modified",
    ):
        require(key in payload, f"{case}: falta campo {key}")
    require(payload["contract_version"] == "1.8", f"{case}: contract_version no es 1.8")
    require(payload["tool"] == "scientific_workflow_router", f"{case}: tool inesperado")
    require(payload["input_kind"] == expected_kind, f"{case}: input_kind {payload['input_kind']} != {expected_kind}")
    require(app_status(payload) in accepted_statuses, f"{case}: status inesperado {app_status(payload)}")
    require(payload["original_modified"] is False, f"{case}: original_modified debe ser false")
    require(isinstance(payload["recommended_capabilities"], list), f"{case}: recommended no es lista")
    require(isinstance(payload["rejected_capabilities"], list), f"{case}: rejected no es lista")
    require(payload["plan_steps"], f"{case}: plan_steps vacio")
    require(payload["required_backends"], f"{case}: required_backends vacio")
    require(payload["safety_notes"], f"{case}: safety_notes vacio")
    require(payload["next_actions"], f"{case}: next_actions vacio")


def main() -> int:
    reset_tmp()
    fixtures = make_fixtures()
    cases = [
        (
            "csv_simple",
            ["inspect", str(fixtures["csv"]), "--task", "perfilar tabla profesional anonima"],
            fixtures["csv"],
            "table_csv",
            {"PASS"},
        ),
        (
            "mixed_folder",
            ["plan", str(fixtures["mixed"]), "--task", "diagnosticar paquete profesional mixto"],
            fixtures["mixed"],
            "mixed_folder",
            {"PASS", "WARNING"},
        ),
        (
            "legacy_notebook",
            [
                "explain",
                str(fixtures["notebook"]),
                "--task",
                "revisar notebook heredado antes de ejecutarlo",
                "--capability",
                "notebook_workbench.py execute-copy",
            ],
            fixtures["notebook"],
            "notebook_ipynb",
            {"PASS"},
        ),
        (
            "fake_fits",
            ["inspect", str(fixtures["fake_fits"]), "--task", "validar archivo que parece FITS"],
            fixtures["fake_fits"],
            "fits_like_unverified",
            {"WARNING"},
        ),
        (
            "missing_path",
            ["plan", str(fixtures["missing"]), "--task", "analizar ruta inexistente"],
            fixtures["missing"],
            "missing_path",
            {"BLOCKED_CONTROLADO"},
        ),
        (
            "empty_folder",
            ["inspect", str(fixtures["empty"]), "--task", "diagnosticar carpeta vacia"],
            fixtures["empty"],
            "empty_directory",
            {"BLOCKED_CONTROLADO"},
        ),
    ]

    records = []
    for case, args, input_path, expected_kind, accepted_statuses in cases:
        record = run_router(case, args, input_path)
        validate_payload(record, expected_kind, accepted_statuses)
        records.append(record)

    rows = []
    for record in records:
        payload = record["payload"]
        rows.append(
            {
                "case": record["case"],
                "status": app_status(payload),
                "input_kind": payload["input_kind"],
                "recommendations": [item["label"] for item in payload["recommended_capabilities"]],
                "summary_json": record["summary_json"],
                "manifest_json": record["manifest_json"],
            }
        )

    SUMMARY.write_text(json.dumps({"status": "PASS", "cases": rows}, indent=2), encoding="utf-8")
    lines = [
        "# v1.8 Phase 5 Router Regression",
        "",
        "Status: PASS",
        "",
        "| case | status | input_kind | recommendations |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['case']}` | `{row['status']}` | `{row['input_kind']}` | "
            f"{', '.join(f'`{item}`' for item in row['recommendations']) or '`none`'} |"
        )
    lines.extend(["", f"Machine summary: `{SUMMARY}`", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "report": str(REPORT), "summary": str(SUMMARY)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
