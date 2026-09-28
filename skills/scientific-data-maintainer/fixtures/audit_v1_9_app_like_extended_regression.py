#!/usr/bin/env python3
"""Lightweight app-like regression coverage for v1.9 Deuda R / G2."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import os
from typing import Any

from _internal.provenance_utils import FROZEN_ARTIFACT_TYPES
from _internal.run_bundle import REQUIRED_FILES


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_9_debt_R_app_like_extended"
INPUTS = TMP / "inputs"
RUNS = TMP / "runs"
SUMMARY = TMP / "app_like_extended_regression_summary.json"
REPORT = TMP / "app_like_extended_regression_report.md"
DOC = ROOT / "references" / "v1-9-app-like-extended-regression.md"

DATANALYSIS = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
PYTHON = DATANALYSIS if DATANALYSIS.exists() else Path(sys.executable)

VALID_APP_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}
LEGACY_STATUS_TO_APP = {
    "ok": "PASS",
    "pass": "PASS",
    "ready": "PASS",
    "success": "PASS",
    "warning": "WARNING",
    "blocked": "BLOCKED_CONTROLADO",
    "fail": "FAIL",
    "failed": "FAIL",
    "error": "FAIL",
}
SENSITIVE_REJECTIONS = {
    "stilts_workbench.py",
    "apt_workbench.py",
    "keynote_export.py",
    "external_astro_tools_preflight.py",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def write_notebook(path: Path) -> Path:
    payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Inherited notebook\n", "Received from a previous project handoff.\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["name = input('Operator name?')\n", "print(name)\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["from pathlib import Path\n", "Path('legacy_output.txt').write_text('side effect')\n"],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> Any:
    if not path.exists():
        return None
    if path.is_file():
        return sha256(path)
    records = []
    for item in sorted(child for child in path.rglob("*") if child.is_file()):
        records.append([str(item.relative_to(path)), sha256(item)])
    return records


def path_from_payload(raw: str | Path) -> Path:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        fail(f"No JSON object found in output: {text[:500]}")
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    require(isinstance(payload, dict), "First JSON value is not an object")
    return payload


def load_payload(completed: subprocess.CompletedProcess[str], summary_path: Path | None = None) -> dict[str, Any]:
    if summary_path and summary_path.is_file():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return first_json_object(completed.stdout)


def app_status(payload: dict[str, Any]) -> str:
    status = payload.get("app_status")
    if status:
        return str(status)
    return LEGACY_STATUS_TO_APP.get(str(payload.get("status", "")).lower(), "FAIL")


def assert_no_traceback(completed: subprocess.CompletedProcess[str], case_id: str) -> None:
    combined = f"{completed.stdout}\n{completed.stderr}"
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        fail(f"{case_id}: raw traceback leaked\n{combined}")


def validate_app_payload(
    payload: dict[str, Any],
    *,
    case_id: str,
    expected_statuses: set[str],
    require_artifact: bool = True,
    require_error: bool = False,
) -> list[str]:
    for key in ("contract_version", "tool", "status", "qa", "typed_artifacts", "app_hints", "next_actions", "original_modified"):
        require(key in payload, f"{case_id}: missing envelope field {key}")
    require(payload["contract_version"] == "1.8", f"{case_id}: unexpected contract_version")
    status = app_status(payload)
    require(status in VALID_APP_STATUSES, f"{case_id}: invalid app status {status}")
    require(status in expected_statuses, f"{case_id}: expected {expected_statuses}, got {status}")
    require(payload.get("original_modified") is False, f"{case_id}: original_modified must be false")
    require(isinstance(payload.get("next_actions"), list) and payload["next_actions"], f"{case_id}: missing next_actions")

    app_hints = payload.get("app_hints")
    require(isinstance(app_hints, dict), f"{case_id}: app_hints must be an object")
    for key in ("short_summary", "severity", "preview_artifact_types", "tags"):
        require(key in app_hints, f"{case_id}: missing app_hints.{key}")

    command = payload.get("command")
    require(isinstance(command, dict) and command.get("argv"), f"{case_id}: missing command.argv")

    typed_artifacts = payload.get("typed_artifacts")
    require(isinstance(typed_artifacts, list), f"{case_id}: typed_artifacts must be a list")
    existing_artifacts: list[str] = []
    for item in typed_artifacts:
        require(isinstance(item, dict), f"{case_id}: typed artifact is not an object")
        artifact_type = item.get("artifact_type")
        require(artifact_type in FROZEN_ARTIFACT_TYPES, f"{case_id}: unregistered artifact type {artifact_type!r}")
        raw_path = item.get("path")
        if isinstance(raw_path, str) and path_from_payload(raw_path).exists():
            existing_artifacts.append(str(path_from_payload(raw_path)))
    if require_artifact:
        require(existing_artifacts, f"{case_id}: no discoverable typed artifact exists")

    errors = payload.get("errors")
    require(isinstance(errors, list), f"{case_id}: errors must be a list")
    if require_error:
        require(errors, f"{case_id}: expected non-empty errors[]")
        for item in errors:
            require(isinstance(item, dict) and item.get("kind") and item.get("message"), f"{case_id}: malformed error item")
    return sorted(set(existing_artifacts))


def validate_run_bundle(run_dir: Path, case_id: str) -> None:
    for name in REQUIRED_FILES:
        candidate = run_dir / name
        require(candidate.exists(), f"{case_id}: missing run bundle file {name}")
    for directory in ("artifacts", "previews", "reports", "tables", "logs"):
        require((run_dir / directory).is_dir(), f"{case_id}: missing run bundle dir {directory}")
    next_steps = (run_dir / "next_steps.md").read_text(encoding="utf-8")
    require("# Next Steps" in next_steps, f"{case_id}: next_steps.md is not legible")


def assert_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "Deuda R",
        "G2",
        "profile_table.py",
        "document_intake_workbench.py",
        "inspect_data_container.py",
        "physical_qa.py",
        "scientific_workflow_router.py",
        "Backlog",
        "Deuda F",
    ]
    missing = [item for item in required if item not in text]
    require(not missing, f"app-like extended regression doc missing: {missing}")


def make_fixtures() -> dict[str, Path]:
    if TMP.exists():
        shutil.rmtree(TMP)
    INPUTS.mkdir(parents=True)
    RUNS.mkdir(parents=True)

    fixtures: dict[str, Path] = {}
    fixtures["professional_table"] = write_csv(
        INPUTS / "professional_table" / "service_metrics.csv",
        ["date", "team", "tickets", "resolution_hours", "cost_eur"],
        [
            ["2026-01-01", "support", 18, 4.2, 310.5],
            ["2026-01-02", "support", 21, 3.8, 328.0],
            ["2026-01-03", "ops", 9, 2.1, 140.0],
            ["2026-01-04", "ops", 12, 2.7, 171.0],
        ],
    )

    documents = INPUTS / "administrative_documents"
    documents.mkdir(parents=True)
    (documents / "policy_brief.md").write_text("# Policy brief\n\nNo private data. Pending signatures.\n", encoding="utf-8")
    (documents / "handoff_notes.txt").write_text("Checklist: invoice, consent form, delivery dates.\n", encoding="utf-8")
    (documents / "notice.pdf").write_bytes(b"%PDF-1.4\n% anonymized placeholder\n")
    fixtures["documents"] = documents

    package = INPUTS / "compressed_package" / "project_export.zip"
    package.parent.mkdir(parents=True)
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("README.txt", "Anonymized project export.\n")
        archive.writestr("tables/summary.csv", "month,value\n2026-01,10\n2026-02,12\n")
    fixtures["package"] = package

    corrupt_package = INPUTS / "corrupt_container" / "broken_export.zip"
    corrupt_package.parent.mkdir(parents=True)
    corrupt_package.write_bytes(b"not a zip container; intentionally corrupt for regression\n")
    fixtures["corrupt_package"] = corrupt_package

    fixtures["legacy_notebook"] = write_notebook(INPUTS / "legacy_notebook" / "handoff_analysis.ipynb")

    fixtures["time_series"] = write_csv(
        INPUTS / "time_series" / "monthly_sales_issues.csv",
        ["date", "value"],
        [
            ["2026-01-01", 100],
            ["2026-01-01", 105],
            ["not-a-date", 110],
            ["2026-04-01", 120],
            ["2026-05-01", 125],
            ["2026-06-01", 130],
            ["2026-07-01", 135],
            ["2026-08-01", 138],
            ["2026-09-01", 141],
            ["2026-10-01", 145],
            ["2026-11-01", 149],
            ["2026-12-01", 152],
            ["2027-01-01", 156],
            ["2027-02-01", 160],
        ],
    )

    rv_path = INPUTS / "astro_expert" / "manual_session.vels"
    rv_path.parent.mkdir(parents=True)
    rv_path.write_text(
        "# value_units = m/s\n"
        "2450000.0 10.2 0.5\n"
        "2450001.0 11.1 -1.0\n"
        "2450002.0 not-a-number 0.4\n"
        "2450003.0 9.8\n"
        "2450004.0 10.7 0.6\n",
        encoding="utf-8",
    )
    fixtures["rv_vels"] = rv_path

    fixtures["sensor_table"] = write_csv(
        INPUTS / "measurement_sensor" / "sensor_readings.csv",
        ["time", "wavelength", "flux", "uncertainty"],
        [
            ["2026-01-01T00:00:00", 6700.0, 10.0, 0.2],
            ["2026-01-01T00:00:00", 6700.0, -3.0, -0.1],
            ["2026-01-01T02:00:00", -5.0, "nan", 0.3],
            ["2026-01-01T01:00:00", 6702.0, "inf", 0.4],
        ],
    )
    return fixtures


def run_case(
    case_id: str,
    command: list[str],
    summary_path: Path,
    input_path: Path | None,
    *,
    family: str,
    expected_returncodes: set[int],
    expected_statuses: set[str],
    require_artifact: bool = True,
    require_error: bool = False,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    before = hash_path(input_path) if input_path else None
    completed = run(command)
    assert_no_traceback(completed, case_id)
    require(completed.returncode in expected_returncodes, f"{case_id}: unexpected return code {completed.returncode}: {completed.stderr}")
    payload = load_payload(completed, summary_path)
    artifacts = validate_app_payload(
        payload,
        case_id=case_id,
        expected_statuses=expected_statuses,
        require_artifact=require_artifact,
        require_error=require_error,
    )
    if run_dir is not None:
        validate_run_bundle(run_dir, case_id)
    after = hash_path(input_path) if input_path else None
    require(before == after, f"{case_id}: input was modified")
    return {
        "case": case_id,
        "family": family,
        "command": " ".join(command),
        "returncode": completed.returncode,
        "app_status": app_status(payload),
        "tool": payload.get("tool"),
        "artifact_count": len(artifacts),
        "summary_json": str(summary_path),
        "input_modified": False,
        "status": "PASS",
    }


def run_router_case(table: Path) -> dict[str, Any]:
    case_id = "router_general_table_exposure_guard"
    summary = RUNS / case_id / "summary.json"
    manifest = RUNS / case_id / "manifest.json"
    command = [
        str(PYTHON),
        str(SCRIPTS / "scientific_workflow_router.py"),
        "plan",
        str(table),
        "--task",
        "profile an anonymized professional service table",
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    before = hash_path(table)
    completed = run(command)
    assert_no_traceback(completed, case_id)
    require(completed.returncode == 0, f"{case_id}: router failed {completed.returncode}: {completed.stderr}")
    payload = load_payload(completed, summary)
    validate_app_payload(payload, case_id=case_id, expected_statuses={"PASS"}, require_artifact=True)
    recommended = payload.get("recommended_capabilities") or []
    labels = {item.get("label") for item in recommended if isinstance(item, dict)}
    require("profile_table.py" in labels, f"{case_id}: profile_table.py not recommended")

    rejected = payload.get("rejected_capabilities") or []
    rejected_by_label = {item.get("label"): item for item in rejected if isinstance(item, dict)}
    for label in SENSITIVE_REJECTIONS:
        item = rejected_by_label.get(label)
        require(item is not None, f"{case_id}: missing sensitive rejection for {label}")
        require(item.get("normal_user_action") is False, f"{case_id}: {label} is not clearly non-normal")
    require(before == hash_path(table), f"{case_id}: input was modified")
    return {
        "case": case_id,
        "family": "router/exposure",
        "command": " ".join(command),
        "returncode": completed.returncode,
        "app_status": app_status(payload),
        "tool": payload.get("tool"),
        "recommended": sorted(labels),
        "sensitive_rejections_checked": sorted(SENSITIVE_REJECTIONS),
        "summary_json": str(summary),
        "input_modified": False,
        "status": "PASS",
    }


def write_report(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# v1.9 Deuda R App-Like Extended Regression",
        "",
        "| Family | Case | Tool | App status | Artifacts | Input modified |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.get('family', 'unknown')}` | `{row['case']}` | `{row.get('tool', 'unknown')}` | `{row.get('app_status')}` | {row.get('artifact_count', 'n/a')} | {row.get('input_modified')} |"
        )
    lines.extend(
        [
            "",
            "## Backlog",
            "",
            "- Deuda F/G1 helper migration is intentionally not applied in this Deuda R pass.",
            "- Optional backend and GUI happy paths remain targeted or v2.0 work, not core app-like regression dependencies.",
            "- ScientificWorkbench end-to-end job history remains v2.0.",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    assert_doc()
    fixtures = make_fixtures()
    rows: list[dict[str, Any]] = []

    rows.append(run_router_case(fixtures["professional_table"]))

    profile_run = RUNS / "profile_table_run_bundle" / "run"
    rows.append(
        run_case(
            "profile_table_run_bundle",
            [str(PYTHON), str(SCRIPTS / "profile_table.py"), str(fixtures["professional_table"]), "--run-dir", str(profile_run)],
            profile_run / "summary.json",
            fixtures["professional_table"],
            family="tabla profesional",
            expected_returncodes={0},
            expected_statuses={"PASS", "WARNING"},
            run_dir=profile_run,
        )
    )

    doc_run = RUNS / "document_intake_run_bundle" / "run"
    rows.append(
        run_case(
            "document_intake_run_bundle",
            [str(PYTHON), str(SCRIPTS / "document_intake_workbench.py"), str(fixtures["documents"]), "--run-dir", str(doc_run)],
            doc_run / "summary.json",
            fixtures["documents"],
            family="documento administrativo",
            expected_returncodes={0},
            expected_statuses={"PASS", "WARNING"},
            run_dir=doc_run,
        )
    )

    notebook_summary = RUNS / "notebook_legacy_preflight" / "summary.json"
    notebook_manifest = RUNS / "notebook_legacy_preflight" / "manifest.json"
    rows.append(
        run_case(
            "notebook_legacy_preflight",
            [
                str(PYTHON),
                str(SCRIPTS / "notebook_workbench.py"),
                "preflight-execution",
                str(fixtures["legacy_notebook"]),
                "--summary-json",
                str(notebook_summary),
                "--manifest-json",
                str(notebook_manifest),
            ],
            notebook_summary,
            fixtures["legacy_notebook"],
            family="notebook heredado",
            expected_returncodes={0},
            expected_statuses={"WARNING", "BLOCKED_CONTROLADO"},
            require_error=True,
        )
    )

    container_run = RUNS / "inspect_container_zip_run_bundle" / "run"
    rows.append(
        run_case(
            "inspect_container_zip_run_bundle",
            [str(PYTHON), str(SCRIPTS / "inspect_data_container.py"), str(fixtures["package"]), "--run-dir", str(container_run)],
            container_run / "summary.json",
            fixtures["package"],
            family="contenedor/paquete",
            expected_returncodes={0},
            expected_statuses={"PASS", "WARNING"},
            run_dir=container_run,
        )
    )

    corrupt_run = RUNS / "inspect_container_corrupt_zip" / "run"
    rows.append(
        run_case(
            "inspect_container_corrupt_zip",
            [str(PYTHON), str(SCRIPTS / "inspect_data_container.py"), str(fixtures["corrupt_package"]), "--run-dir", str(corrupt_run)],
            corrupt_run / "summary.json",
            fixtures["corrupt_package"],
            family="contenedor corrupto",
            expected_returncodes={0, 2},
            expected_statuses={"WARNING", "BLOCKED_CONTROLADO", "FAIL"},
            run_dir=corrupt_run,
        )
    )

    timeseries_out = RUNS / "timeseries_ambiguous_dates" / "out"
    timeseries_summary = RUNS / "timeseries_ambiguous_dates" / "summary.json"
    timeseries_manifest = RUNS / "timeseries_ambiguous_dates" / "manifest.json"
    rows.append(
        run_case(
            "timeseries_ambiguous_dates",
            [
                str(PYTHON),
                str(SCRIPTS / "timeseries_forecasting_workbench.py"),
                "--output-dir",
                str(timeseries_out),
                "--data-path",
                str(fixtures["time_series"]),
                "--date-column",
                "date",
                "--value-column",
                "value",
                "--frequency",
                "MS",
                "--test-horizon",
                "2",
                "--summary-json",
                str(timeseries_summary),
                "--manifest-json",
                str(timeseries_manifest),
            ],
            timeseries_summary,
            fixtures["time_series"],
            family="serie temporal",
            expected_returncodes={0},
            expected_statuses={"WARNING"},
        )
    )

    physical_summary = RUNS / "physical_qa_sensor_warning" / "summary.json"
    rows.append(
        run_case(
            "physical_qa_sensor_warning",
            [str(PYTHON), str(SCRIPTS / "physical_qa.py"), str(fixtures["sensor_table"]), "--summary-json", str(physical_summary)],
            physical_summary,
            fixtures["sensor_table"],
            family="sensor/medicion",
            expected_returncodes={0},
            expected_statuses={"WARNING"},
        )
    )

    rv_summary = RUNS / "radial_velocity_expert_warning" / "summary.json"
    rv_manifest = RUNS / "radial_velocity_expert_warning" / "manifest.json"
    rows.append(
        run_case(
            "radial_velocity_expert_warning",
            [
                str(PYTHON),
                str(SCRIPTS / "radial_velocity_workbench.py"),
                "inspect",
                str(fixtures["rv_vels"]),
                "--summary-json",
                str(rv_summary),
                "--manifest-json",
                str(rv_manifest),
            ],
            rv_summary,
            fixtures["rv_vels"],
            family="ruta astro expert",
            expected_returncodes={0},
            expected_statuses={"WARNING"},
        )
    )

    optional_summary = RUNS / "external_optional_backend_absent" / "summary.json"
    rows.append(
        run_case(
            "external_optional_backend_absent",
            [
                str(PYTHON),
                str(SCRIPTS / "external_astro_tools_preflight.py"),
                "--require-stilts",
                "--stilts-command",
                str(INPUTS / "missing_backend" / "stilts-not-installed"),
                "--summary-json",
                str(optional_summary),
            ],
            optional_summary,
            None,
            family="backend opcional ausente",
            expected_returncodes={2},
            expected_statuses={"BLOCKED_CONTROLADO"},
            require_error=True,
        )
    )

    conflict_dir = RUNS / "env_doctor_output_conflict" / "summary_conflict"
    conflict_dir.mkdir(parents=True)
    rows.append(
        run_case(
            "env_doctor_output_conflict",
            [str(PYTHON), str(SCRIPTS / "env_doctor.py"), "--summary-json", str(conflict_dir)],
            conflict_dir,
            conflict_dir,
            family="output conflictivo",
            expected_returncodes={2},
            expected_statuses={"BLOCKED_CONTROLADO"},
            require_artifact=False,
            require_error=True,
        )
    )

    missing_summary = RUNS / "profile_table_missing_input" / "summary.json"
    rows.append(
        run_case(
            "profile_table_missing_input",
            [str(PYTHON), str(SCRIPTS / "profile_table.py"), str(INPUTS / "missing.csv"), "--summary-json", str(missing_summary)],
            missing_summary,
            None,
            family="entrada rota controlada",
            expected_returncodes={2},
            expected_statuses={"FAIL"},
            require_artifact=True,
            require_error=True,
        )
    )

    write_report(rows)
    output = {
        "status": "PASS",
        "check": "v1.9 Deuda R app-like extended regression",
        "case_count": len(rows),
        "cases": rows,
        "backlog": [
            "Deuda F/G1 helper migration intentionally not applied in this Deuda R pass.",
            "Optional backend and GUI happy paths remain targeted or v2.0 work.",
            "ScientificWorkbench end-to-end job history remains v2.0.",
        ],
        "report_md": str(REPORT),
    }
    SUMMARY.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
