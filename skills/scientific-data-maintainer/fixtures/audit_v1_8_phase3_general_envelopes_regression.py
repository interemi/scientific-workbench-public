#!/usr/bin/env python3
"""Exercise v1.8 app-ready envelopes for high-value general routes."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp" / "v1_8_phase3_general_envelopes"
RUNS = TMP / "runs"
FIXTURES = TMP / "fixtures"
DATANALYSIS_PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
PYTHON = str(DATANALYSIS_PYTHON if DATANALYSIS_PYTHON.exists() else sys.executable)

APP_STATUS_BY_LEGACY = {
    "ok": "PASS",
    "pass": "PASS",
    "success": "PASS",
    "ready": "PASS",
    "warning": "WARNING",
    "blocked": "BLOCKED_CONTROLADO",
    "fail": "FAIL",
    "failed": "FAIL",
    "error": "FAIL",
}
ARTIFACT_TYPES = {
    "summary_json",
    "manifest_json",
    "report_md",
    "preview_png",
    "table_csv",
    "notebook_ipynb",
    "log_txt",
    "qa_report",
    "handoff_bundle",
    "unknown",
}


@dataclass
class Case:
    target: str
    case_type: str
    command: list[str]
    summary_json: Path
    expected_app_statuses: set[str]
    input_paths: list[Path] = field(default_factory=list)
    artifact_required: bool = True
    notes: str = ""


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_raw(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_notebook(path: Path, cells: list[dict]) -> Path:
    payload = {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def code_cell(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(True)}


def markdown_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_fixtures() -> dict[str, Path]:
    if RUNS.exists():
        shutil.rmtree(RUNS)
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    RUNS.mkdir(parents=True)
    FIXTURES.mkdir(parents=True)

    fixtures: dict[str, Path] = {}
    fixtures["table_happy"] = write_csv(
        FIXTURES / "tables" / "support_happy.csv",
        [
            {"ticket_id": 1001, "team": "ops", "hours": 1.5, "priority": "low"},
            {"ticket_id": 1002, "team": "data", "hours": 3.0, "priority": "high"},
            {"ticket_id": 1003, "team": "ops", "hours": 2.25, "priority": "medium"},
        ],
    )
    fixtures["table_duplicate_header"] = write_raw(
        FIXTURES / "tables" / "duplicate_header.csv",
        "id,value,value\n1,10,11\n2,20,21\n",
    )
    fixtures["table_real_ops"] = write_csv(
        FIXTURES / "realistic" / "service_metrics.csv",
        [
            {"date": "2026-01-01", "queue": "billing", "tickets": 31, "sla_hours": 6.5},
            {"date": "2026-02-01", "queue": "billing", "tickets": 28, "sla_hours": 5.9},
            {"date": "2026-03-01", "queue": "technical", "tickets": 45, "sla_hours": 8.1},
        ],
    )
    fixtures["cross_dir"] = FIXTURES / "cross_domain" / "happy"
    fixtures["cross_dir"].mkdir(parents=True)
    shutil.copy2(fixtures["table_happy"], fixtures["cross_dir"] / "support_happy.csv")
    fixtures["cross_real_dir"] = FIXTURES / "cross_domain" / "real_ops"
    fixtures["cross_real_dir"].mkdir(parents=True)
    shutil.copy2(fixtures["table_real_ops"], fixtures["cross_real_dir"] / "service_metrics.csv")
    write_raw(fixtures["cross_real_dir"] / "events.jsonl", '{"date":"2026-01-01","event":"handoff"}\n{"date":"2026-01-02","event":"review"}\n')
    fixtures["empty_dir"] = FIXTURES / "empty_dir"
    fixtures["empty_dir"].mkdir()

    fixtures["doc_one"] = write_text(FIXTURES / "docs" / "brief.md", "# Operations brief\n\nReview queue health and handoff notes.\n")
    fixtures["doc_two"] = write_text(FIXTURES / "docs" / "notes.txt", "Meeting notes\n- Follow up on open tickets\n")
    fixtures["docs_dir"] = FIXTURES / "docs"
    fixtures["doc_real_dir"] = FIXTURES / "realistic_docs"
    fixtures["doc_real_dir"].mkdir()
    write_text(fixtures["doc_real_dir"] / "policy_summary.md", "# Policy Summary\n\nThis package is for an internal administrative review.\n")
    write_text(fixtures["doc_real_dir"] / "handoff_notes.txt", "Owner: operations\nNext action: review attachments.\n")

    fixtures["safe_zip"] = FIXTURES / "containers" / "safe_bundle.zip"
    fixtures["safe_zip"].parent.mkdir(parents=True)
    with zipfile.ZipFile(fixtures["safe_zip"], "w") as archive:
        archive.writestr("data/readme.txt", "safe bundle")
        archive.writestr("data/table.csv", "id,value\n1,2\n")
    fixtures["unsafe_zip"] = FIXTURES / "containers" / "unsafe_bundle.zip"
    with zipfile.ZipFile(fixtures["unsafe_zip"], "w") as archive:
        archive.writestr("../escape.txt", "bad path")
        archive.writestr("normal.txt", "ok")
    fixtures["real_zip"] = FIXTURES / "containers" / "project_export.zip"
    with zipfile.ZipFile(fixtures["real_zip"], "w") as archive:
        archive.writestr("reports/summary.md", "# Summary\n")
        archive.writestr("tables/service_metrics.csv", fixtures["table_real_ops"].read_text(encoding="utf-8"))

    fixtures["baseline_csv"] = write_csv(
        FIXTURES / "diff" / "baseline.csv",
        [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}],
    )
    fixtures["candidate_csv"] = write_csv(
        FIXTURES / "diff" / "candidate.csv",
        [{"id": 1, "amount": 10}, {"id": 2, "amount": 24}],
    )
    fixtures["doc_a"] = write_text(FIXTURES / "diff" / "a.md", "# Same\n\nNo visible change.\n")
    fixtures["doc_b"] = write_text(FIXTURES / "diff" / "b.md", "# Same\n\nNo visible change.\n")
    fixtures["budget_a"] = write_csv(
        FIXTURES / "diff" / "budget_a.csv",
        [{"category": "rent", "budget": 900}, {"category": "utilities", "budget": 110}],
    )
    fixtures["budget_b"] = write_csv(
        FIXTURES / "diff" / "budget_b.csv",
        [{"category": "rent", "budget": 900}, {"category": "utilities", "budget": 130}],
    )

    fixtures["notebook_code"] = write_notebook(
        FIXTURES / "notebooks" / "analysis.ipynb",
        [markdown_cell("# Tiny analysis\n"), code_cell("value = 2 + 2\nprint('value', value)\n")],
    )
    fixtures["notebook_markdown_only"] = write_notebook(
        FIXTURES / "notebooks" / "markdown_only.ipynb",
        [markdown_cell("# Notes only\nNo code cells here.\n")],
    )
    fixtures["notebook_real"] = write_notebook(
        FIXTURES / "notebooks" / "personal_budget.ipynb",
        [markdown_cell("# Personal budget analysis\n"), code_cell("expenses = [12, 20, 18]\nprint(sum(expenses))\n")],
    )

    def month_date(index: int, start_year: int = 2025) -> str:
        year = start_year + (index - 1) // 12
        month = ((index - 1) % 12) + 1
        return f"{year}-{month:02d}-01"

    dates = [month_date(month) for month in range(1, 25)]
    fixtures["series_happy"] = write_csv(
        FIXTURES / "series" / "monthly_sales.csv",
        [{"date": date, "value": 100 + index * 3} for index, date in enumerate(dates)],
    )
    fixtures["series_warning"] = write_raw(
        FIXTURES / "series" / "monthly_sales_warning.csv",
        "date,value\n2025-01-01,100\n2025-01-01,105\n2025-02-01,not_a_number\n"
        + "\n".join(f"{month_date(month)},{100 + month}" for month in range(3, 26))
        + "\n",
    )
    fixtures["series_real"] = write_csv(
        FIXTURES / "series" / "home_energy.csv",
        [{"date": month_date(month), "kwh": 220 + (month % 4) * 18} for month in range(1, 25)],
    )

    return fixtures


def summary_path(target: str, case_type: str) -> Path:
    return RUNS / target / case_type / "summary.json"


def manifest_path(target: str, case_type: str) -> Path:
    return RUNS / target / case_type / "manifest.json"


def out_dir(target: str, case_type: str, name: str = "out") -> Path:
    return RUNS / target / case_type / name


def build_cases(fixtures: dict[str, Path]) -> list[Case]:
    cases: list[Case] = []

    def py(script: str, *args: object) -> list[str]:
        return [PYTHON, f"scripts/{script}", *[str(arg) for arg in args]]

    cases.extend(
        [
            Case("profile_table", "synthetic_happy", py("profile_table.py", fixtures["table_happy"], "--summary-json", summary_path("profile_table", "synthetic_happy"), "--manifest-json", manifest_path("profile_table", "synthetic_happy")), summary_path("profile_table", "synthetic_happy"), {"PASS"}, [fixtures["table_happy"]]),
            Case("profile_table", "synthetic_warning", py("profile_table.py", fixtures["table_duplicate_header"], "--summary-json", summary_path("profile_table", "synthetic_warning"), "--manifest-json", manifest_path("profile_table", "synthetic_warning")), summary_path("profile_table", "synthetic_warning"), {"WARNING"}, [fixtures["table_duplicate_header"]]),
            Case("profile_table", "broken_controlled", py("profile_table.py", FIXTURES / "missing.csv", "--summary-json", summary_path("profile_table", "broken_controlled"), "--manifest-json", manifest_path("profile_table", "broken_controlled")), summary_path("profile_table", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}),
            Case("profile_table", "realistic_copy", py("profile_table.py", fixtures["table_real_ops"], "--summary-json", summary_path("profile_table", "realistic_copy"), "--manifest-json", manifest_path("profile_table", "realistic_copy")), summary_path("profile_table", "realistic_copy"), {"PASS"}, [fixtures["table_real_ops"]]),
        ]
    )

    cases.extend(
        [
            Case("cross_domain_data_workbench", "synthetic_happy", py("cross_domain_data_workbench.py", fixtures["cross_dir"], "--output-dir", out_dir("cross_domain_data_workbench", "synthetic_happy"), "--summary-json", summary_path("cross_domain_data_workbench", "synthetic_happy"), "--manifest-json", manifest_path("cross_domain_data_workbench", "synthetic_happy")), summary_path("cross_domain_data_workbench", "synthetic_happy"), {"PASS", "WARNING"}, [fixtures["cross_dir"]]),
            Case("cross_domain_data_workbench", "synthetic_warning", py("cross_domain_data_workbench.py", fixtures["cross_dir"], FIXTURES / "missing_dir", "--output-dir", out_dir("cross_domain_data_workbench", "synthetic_warning"), "--summary-json", summary_path("cross_domain_data_workbench", "synthetic_warning"), "--manifest-json", manifest_path("cross_domain_data_workbench", "synthetic_warning")), summary_path("cross_domain_data_workbench", "synthetic_warning"), {"WARNING"}, [fixtures["cross_dir"]]),
            Case("cross_domain_data_workbench", "broken_controlled", py("cross_domain_data_workbench.py", fixtures["empty_dir"], "--output-dir", out_dir("cross_domain_data_workbench", "broken_controlled"), "--summary-json", summary_path("cross_domain_data_workbench", "broken_controlled"), "--manifest-json", manifest_path("cross_domain_data_workbench", "broken_controlled")), summary_path("cross_domain_data_workbench", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}),
            Case("cross_domain_data_workbench", "realistic_copy", py("cross_domain_data_workbench.py", fixtures["cross_real_dir"], "--sql", "SELECT queue, SUM(tickets) AS tickets FROM source0 GROUP BY queue", "--output-dir", out_dir("cross_domain_data_workbench", "realistic_copy"), "--summary-json", summary_path("cross_domain_data_workbench", "realistic_copy"), "--manifest-json", manifest_path("cross_domain_data_workbench", "realistic_copy")), summary_path("cross_domain_data_workbench", "realistic_copy"), {"PASS", "WARNING"}, [fixtures["cross_real_dir"]]),
        ]
    )

    bad_output_file = write_text(RUNS / "document_intake_workbench" / "broken_controlled" / "not_a_dir", "file blocks output dir\n")
    cases.extend(
        [
            Case("document_intake_workbench", "synthetic_happy", py("document_intake_workbench.py", fixtures["doc_one"], fixtures["doc_two"], "--output-dir", out_dir("document_intake_workbench", "synthetic_happy"), "--summary-json", summary_path("document_intake_workbench", "synthetic_happy"), "--manifest-json", manifest_path("document_intake_workbench", "synthetic_happy")), summary_path("document_intake_workbench", "synthetic_happy"), {"PASS", "WARNING"}, [fixtures["doc_one"], fixtures["doc_two"]]),
            Case("document_intake_workbench", "synthetic_warning", py("document_intake_workbench.py", fixtures["doc_one"], FIXTURES / "missing_document.pdf", "--output-dir", out_dir("document_intake_workbench", "synthetic_warning"), "--summary-json", summary_path("document_intake_workbench", "synthetic_warning"), "--manifest-json", manifest_path("document_intake_workbench", "synthetic_warning")), summary_path("document_intake_workbench", "synthetic_warning"), {"WARNING", "FAIL", "BLOCKED_CONTROLADO"}, [fixtures["doc_one"]]),
            Case("document_intake_workbench", "broken_controlled", py("document_intake_workbench.py", fixtures["doc_one"], "--output-dir", bad_output_file, "--summary-json", summary_path("document_intake_workbench", "broken_controlled"), "--manifest-json", manifest_path("document_intake_workbench", "broken_controlled")), summary_path("document_intake_workbench", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}, [fixtures["doc_one"]]),
            Case("document_intake_workbench", "realistic_copy", py("document_intake_workbench.py", fixtures["doc_real_dir"], "--output-dir", out_dir("document_intake_workbench", "realistic_copy"), "--summary-json", summary_path("document_intake_workbench", "realistic_copy"), "--manifest-json", manifest_path("document_intake_workbench", "realistic_copy")), summary_path("document_intake_workbench", "realistic_copy"), {"PASS", "WARNING"}, [fixtures["doc_real_dir"]]),
        ]
    )

    cases.extend(
        [
            Case("inspect_data_container", "synthetic_happy", py("inspect_data_container.py", fixtures["safe_zip"], "--summary-json", summary_path("inspect_data_container", "synthetic_happy"), "--manifest-json", manifest_path("inspect_data_container", "synthetic_happy")), summary_path("inspect_data_container", "synthetic_happy"), {"PASS"}, [fixtures["safe_zip"]]),
            Case("inspect_data_container", "synthetic_warning", py("inspect_data_container.py", fixtures["unsafe_zip"], "--summary-json", summary_path("inspect_data_container", "synthetic_warning"), "--manifest-json", manifest_path("inspect_data_container", "synthetic_warning")), summary_path("inspect_data_container", "synthetic_warning"), {"WARNING"}, [fixtures["unsafe_zip"]]),
            Case("inspect_data_container", "broken_controlled", py("inspect_data_container.py", FIXTURES / "containers" / "missing.zip", "--summary-json", summary_path("inspect_data_container", "broken_controlled"), "--manifest-json", manifest_path("inspect_data_container", "broken_controlled")), summary_path("inspect_data_container", "broken_controlled"), {"BLOCKED_CONTROLADO", "FAIL"}),
            Case("inspect_data_container", "realistic_copy", py("inspect_data_container.py", fixtures["real_zip"], "--summary-json", summary_path("inspect_data_container", "realistic_copy"), "--manifest-json", manifest_path("inspect_data_container", "realistic_copy")), summary_path("inspect_data_container", "realistic_copy"), {"PASS"}, [fixtures["real_zip"]]),
        ]
    )

    cases.extend(
        [
            Case("semantic_diff", "synthetic_happy", py("semantic_diff.py", fixtures["baseline_csv"], fixtures["candidate_csv"], "--summary-json", summary_path("semantic_diff", "synthetic_happy"), "--output-md", out_dir("semantic_diff", "synthetic_happy") / "diff.md", "--manifest-json", manifest_path("semantic_diff", "synthetic_happy")), summary_path("semantic_diff", "synthetic_happy"), {"PASS"}, [fixtures["baseline_csv"], fixtures["candidate_csv"]]),
            Case("semantic_diff", "synthetic_warning", py("semantic_diff.py", fixtures["doc_a"], fixtures["doc_b"], "--summary-json", summary_path("semantic_diff", "synthetic_warning"), "--output-md", out_dir("semantic_diff", "synthetic_warning") / "diff.md", "--manifest-json", manifest_path("semantic_diff", "synthetic_warning")), summary_path("semantic_diff", "synthetic_warning"), {"WARNING"}, [fixtures["doc_a"], fixtures["doc_b"]]),
            Case("semantic_diff", "broken_controlled", py("semantic_diff.py", FIXTURES / "diff" / "missing.csv", fixtures["candidate_csv"], "--summary-json", summary_path("semantic_diff", "broken_controlled"), "--output-md", out_dir("semantic_diff", "broken_controlled") / "diff.md", "--manifest-json", manifest_path("semantic_diff", "broken_controlled")), summary_path("semantic_diff", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}),
            Case("semantic_diff", "realistic_copy", py("semantic_diff.py", fixtures["budget_a"], fixtures["budget_b"], "--summary-json", summary_path("semantic_diff", "realistic_copy"), "--output-md", out_dir("semantic_diff", "realistic_copy") / "diff.md", "--manifest-json", manifest_path("semantic_diff", "realistic_copy")), summary_path("semantic_diff", "realistic_copy"), {"PASS"}, [fixtures["budget_a"], fixtures["budget_b"]]),
        ]
    )

    overwrite_dir = out_dir("deliverable_factory_scaffold", "synthetic_warning", "deliverable")
    write_text(overwrite_dir / "deliverable.md", "# Existing\n")
    bad_scaffold_file = write_text(RUNS / "deliverable_factory_scaffold" / "broken_controlled" / "not_a_dir", "file blocks output dir\n")
    cases.extend(
        [
            Case("deliverable_factory_scaffold", "synthetic_happy", py("deliverable_factory.py", "scaffold", out_dir("deliverable_factory_scaffold", "synthetic_happy", "deliverable"), "--kind", "status-report", "--title", "Weekly Status", "--summary-json", summary_path("deliverable_factory_scaffold", "synthetic_happy"), "--manifest-json", manifest_path("deliverable_factory_scaffold", "synthetic_happy")), summary_path("deliverable_factory_scaffold", "synthetic_happy"), {"PASS"}),
            Case("deliverable_factory_scaffold", "synthetic_warning", py("deliverable_factory.py", "scaffold", overwrite_dir, "--kind", "status-report", "--title", "Overwrite Status", "--overwrite", "--summary-json", summary_path("deliverable_factory_scaffold", "synthetic_warning"), "--manifest-json", manifest_path("deliverable_factory_scaffold", "synthetic_warning")), summary_path("deliverable_factory_scaffold", "synthetic_warning"), {"WARNING"}),
            Case("deliverable_factory_scaffold", "broken_controlled", py("deliverable_factory.py", "scaffold", bad_scaffold_file, "--kind", "status-report", "--title", "Bad Target", "--summary-json", summary_path("deliverable_factory_scaffold", "broken_controlled"), "--manifest-json", manifest_path("deliverable_factory_scaffold", "broken_controlled")), summary_path("deliverable_factory_scaffold", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}),
            Case("deliverable_factory_scaffold", "realistic_copy", py("deliverable_factory.py", "scaffold", out_dir("deliverable_factory_scaffold", "realistic_copy", "project_brief"), "--kind", "project-brief", "--title", "Home Renovation Plan", "--language", "bilingual", "--summary-json", summary_path("deliverable_factory_scaffold", "realistic_copy"), "--manifest-json", manifest_path("deliverable_factory_scaffold", "realistic_copy")), summary_path("deliverable_factory_scaffold", "realistic_copy"), {"PASS"}),
        ]
    )

    cases.extend(
        [
            Case("notebook_workbench_inspect_execute", "synthetic_happy", py("notebook_workbench.py", "inspect", fixtures["notebook_code"], "--summary-json", summary_path("notebook_workbench_inspect_execute", "synthetic_happy"), "--manifest-json", manifest_path("notebook_workbench_inspect_execute", "synthetic_happy")), summary_path("notebook_workbench_inspect_execute", "synthetic_happy"), {"PASS"}, [fixtures["notebook_code"]]),
            Case("notebook_workbench_inspect_execute", "synthetic_warning", py("notebook_workbench.py", "execute-copy", fixtures["notebook_markdown_only"], "--output-dir", out_dir("notebook_workbench_inspect_execute", "synthetic_warning", "exec"), "--timeout-sec", "30", "--summary-json", summary_path("notebook_workbench_inspect_execute", "synthetic_warning"), "--manifest-json", manifest_path("notebook_workbench_inspect_execute", "synthetic_warning")), summary_path("notebook_workbench_inspect_execute", "synthetic_warning"), {"WARNING"}, [fixtures["notebook_markdown_only"]]),
            Case("notebook_workbench_inspect_execute", "broken_controlled", py("notebook_workbench.py", "inspect", FIXTURES / "notebooks" / "missing.ipynb", "--summary-json", summary_path("notebook_workbench_inspect_execute", "broken_controlled"), "--manifest-json", manifest_path("notebook_workbench_inspect_execute", "broken_controlled")), summary_path("notebook_workbench_inspect_execute", "broken_controlled"), {"BLOCKED_CONTROLADO", "FAIL"}),
            Case("notebook_workbench_inspect_execute", "realistic_copy", py("notebook_workbench.py", "execute-copy", fixtures["notebook_real"], "--output-dir", out_dir("notebook_workbench_inspect_execute", "realistic_copy", "exec"), "--timeout-sec", "30", "--summary-json", summary_path("notebook_workbench_inspect_execute", "realistic_copy"), "--manifest-json", manifest_path("notebook_workbench_inspect_execute", "realistic_copy")), summary_path("notebook_workbench_inspect_execute", "realistic_copy"), {"PASS"}, [fixtures["notebook_real"]]),
        ]
    )

    cases.extend(
        [
            Case("timeseries_forecasting_workbench", "synthetic_happy", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir("timeseries_forecasting_workbench", "synthetic_happy", "forecast"), "--data-path", fixtures["series_happy"], "--date-column", "date", "--value-column", "value", "--summary-json", summary_path("timeseries_forecasting_workbench", "synthetic_happy"), "--manifest-json", manifest_path("timeseries_forecasting_workbench", "synthetic_happy")), summary_path("timeseries_forecasting_workbench", "synthetic_happy"), {"PASS"}, [fixtures["series_happy"]]),
            Case("timeseries_forecasting_workbench", "synthetic_warning", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir("timeseries_forecasting_workbench", "synthetic_warning", "forecast"), "--data-path", fixtures["series_warning"], "--date-column", "date", "--value-column", "value", "--summary-json", summary_path("timeseries_forecasting_workbench", "synthetic_warning"), "--manifest-json", manifest_path("timeseries_forecasting_workbench", "synthetic_warning")), summary_path("timeseries_forecasting_workbench", "synthetic_warning"), {"WARNING"}, [fixtures["series_warning"]]),
            Case("timeseries_forecasting_workbench", "broken_controlled", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir("timeseries_forecasting_workbench", "broken_controlled", "forecast"), "--frequency", "not_a_frequency", "--summary-json", summary_path("timeseries_forecasting_workbench", "broken_controlled"), "--manifest-json", manifest_path("timeseries_forecasting_workbench", "broken_controlled")), summary_path("timeseries_forecasting_workbench", "broken_controlled"), {"FAIL", "BLOCKED_CONTROLADO"}, artifact_required=False),
            Case("timeseries_forecasting_workbench", "realistic_copy", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir("timeseries_forecasting_workbench", "realistic_copy", "forecast"), "--data-path", fixtures["series_real"], "--date-column", "date", "--value-column", "kwh", "--summary-json", summary_path("timeseries_forecasting_workbench", "realistic_copy"), "--manifest-json", manifest_path("timeseries_forecasting_workbench", "realistic_copy")), summary_path("timeseries_forecasting_workbench", "realistic_copy"), {"PASS"}, [fixtures["series_real"]]),
        ]
    )

    cases.extend(
        [
            Case("duckdb_workbench", "synthetic_happy", py("duckdb_workbench.py", fixtures["table_happy"], "--sql", "SELECT team, COUNT(*) AS n FROM source0 GROUP BY team", "--output", out_dir("duckdb_workbench", "synthetic_happy") / "query.csv", "--summary-json", summary_path("duckdb_workbench", "synthetic_happy"), "--manifest-json", manifest_path("duckdb_workbench", "synthetic_happy")), summary_path("duckdb_workbench", "synthetic_happy"), {"PASS"}, [fixtures["table_happy"]]),
            Case("duckdb_workbench", "synthetic_warning", py("duckdb_workbench.py", fixtures["table_happy"], "--sql", "SELECT * FROM source0 LIMIT 2", "--summary-json", summary_path("duckdb_workbench", "synthetic_warning"), "--manifest-json", manifest_path("duckdb_workbench", "synthetic_warning")), summary_path("duckdb_workbench", "synthetic_warning"), {"WARNING"}, [fixtures["table_happy"]]),
            Case("duckdb_workbench", "broken_controlled", py("duckdb_workbench.py", fixtures["table_happy"], "--sql", "SELECT * FROM missing_alias", "--summary-json", summary_path("duckdb_workbench", "broken_controlled"), "--manifest-json", manifest_path("duckdb_workbench", "broken_controlled")), summary_path("duckdb_workbench", "broken_controlled"), {"BLOCKED_CONTROLADO", "FAIL"}, [fixtures["table_happy"]]),
            Case("duckdb_workbench", "realistic_copy", py("duckdb_workbench.py", fixtures["table_real_ops"], "--sql", "SELECT queue, SUM(tickets) AS tickets FROM source0 GROUP BY queue", "--output", out_dir("duckdb_workbench", "realistic_copy") / "queues.csv", "--summary-json", summary_path("duckdb_workbench", "realistic_copy"), "--manifest-json", manifest_path("duckdb_workbench", "realistic_copy")), summary_path("duckdb_workbench", "realistic_copy"), {"PASS"}, [fixtures["table_real_ops"]]),
        ]
    )
    return cases


def app_status(payload: dict) -> str:
    if payload.get("app_status"):
        return str(payload["app_status"])
    return APP_STATUS_BY_LEGACY.get(str(payload.get("status", "")).lower(), "WARNING")


def validate_payload(case: Case, payload: dict) -> list[str]:
    issues: list[str] = []
    actual = app_status(payload)
    if actual not in case.expected_app_statuses:
        issues.append(f"expected app status {sorted(case.expected_app_statuses)}, got {actual}")
    if payload.get("contract_version") != "1.8":
        issues.append("contract_version is not 1.8")
    if payload.get("original_modified") is not False:
        issues.append("original_modified is not false")
    typed_artifacts = payload.get("typed_artifacts")
    if not isinstance(typed_artifacts, list):
        issues.append("typed_artifacts is missing or not a list")
    elif case.artifact_required and not typed_artifacts:
        issues.append("typed_artifacts is empty")
    else:
        for index, artifact in enumerate(typed_artifacts or []):
            artifact_type = artifact.get("artifact_type") if isinstance(artifact, dict) else None
            if artifact_type not in ARTIFACT_TYPES:
                issues.append(f"typed artifact {index} has invalid type: {artifact_type}")
            if isinstance(artifact, dict) and str(Path.home()) in json.dumps(artifact, ensure_ascii=True):
                issues.append(f"typed artifact {index} leaks an unredacted home path")
    if not isinstance(payload.get("next_actions"), list) or not payload["next_actions"]:
        issues.append("next_actions missing or empty")
    app_hints = payload.get("app_hints")
    if not isinstance(app_hints, dict):
        issues.append("app_hints missing or not an object")
    else:
        for field_name in ("short_summary", "severity", "preview_artifact_types", "tags"):
            if field_name not in app_hints:
                issues.append(f"app_hints missing {field_name}")
    if actual == "WARNING" and not payload.get("warnings"):
        issues.append("WARNING payload has no warnings list")
    if actual in {"BLOCKED_CONTROLADO", "FAIL"} and not payload.get("errors"):
        issues.append(f"{actual} payload has no errors list")
    return issues


def run_case(case: Case) -> dict:
    case_dir = case.summary_json.parent
    case_dir.mkdir(parents=True, exist_ok=True)
    before = {str(path): sha256(path) for path in case.input_paths}
    completed = subprocess.run(case.command, cwd=ROOT, text=True, capture_output=True, timeout=120)
    (case_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (case_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    after = {str(path): sha256(path) for path in case.input_paths}
    issues = []
    if "Traceback (most recent call last)" in completed.stdout or "Traceback (most recent call last)" in completed.stderr:
        issues.append("raw traceback leaked to stdout/stderr")
    if before != after:
        issues.append("one or more copied input files changed")
    payload = None
    if case.summary_json.exists() and case.summary_json.is_file():
        try:
            payload = json.loads(case.summary_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"summary_json is not valid JSON: {exc}")
    else:
        issues.append("summary_json was not written")
    if payload is not None:
        issues.extend(validate_payload(case, payload))
    overall = "PASS" if not issues else "FAIL"
    return {
        "target": case.target,
        "case_type": case.case_type,
        "command": " ".join(case.command),
        "summary_json": str(case.summary_json),
        "returncode": completed.returncode,
        "app_status": app_status(payload) if isinstance(payload, dict) else None,
        "tool_status": payload.get("status") if isinstance(payload, dict) else None,
        "issues": issues,
        "result": overall,
        "artifacts": payload.get("typed_artifacts", []) if isinstance(payload, dict) else [],
        "notes": case.notes,
    }


def write_report(results: list[dict], payload: dict) -> None:
    lines = [
        "# AUDITORIA v1.8 - Fase 3: envelopes app-ready en rutas generales",
        "",
        f"Estado: {payload['status']}",
        "",
        "| target | case | app_status | result | hallazgo | artefactos |",
        "|---|---|---|---|---|---|",
    ]
    for item in results:
        artifacts = ", ".join(sorted({artifact.get("artifact_type", "unknown") for artifact in item.get("artifacts", []) if isinstance(artifact, dict)}))
        finding = "; ".join(item["issues"]) if item["issues"] else "Envelope app-ready valido; originals preservados."
        lines.append(
            f"| `{item['target']}` | `{item['case_type']}` | `{item.get('app_status')}` | `{item['result']}` | {finding} | {artifacts or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Problemas",
            "",
        ]
    )
    if payload["failures"]:
        for failure in payload["failures"]:
            lines.append(f"- {failure}")
    else:
        lines.append("- P0/P1: ninguno abierto en la regresion Fase 3.")
        lines.append("- P2: mantener migracion gradual de `status` canonico v1.8 en vez de reemplazar el status legacy de golpe.")
    lines.extend(
        [
            "",
            "## Arreglos aplicados",
            "",
            "- Enriquecimiento compatible del helper `standard_tool_payload` con contrato v1.8, `app_status`, `typed_artifacts`, `original_modified`, `warnings`, `errors`, `next_actions` y `app_hints`.",
            "- `duckdb_workbench.py`: artefactos summary/manifest en exito y warning cuando la consulta queda solo en preview.",
            "- `semantic_diff.py`: status warning cuando QA detecta ausencia de diferencias visibles.",
            "- `document_intake_workbench.py`, `timeseries_forecasting_workbench.py`, `notebook_workbench.py`: manifest_json declarado como artifact.",
            "- `deliverable_factory.py scaffold`: warning explicito cuando `--overwrite` reemplaza un output existente.",
            "- `notebook_workbench.py inspect/preflight-execution`: fallo limpio para rutas invalidas, sin traceback crudo.",
        ]
    )
    (TMP / "phase3_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    fixtures = make_fixtures()
    cases = build_cases(fixtures)
    results = [run_case(case) for case in cases]
    failures = [
        f"{item['target']}::{item['case_type']}: {', '.join(item['issues'])}"
        for item in results
        if item["issues"]
    ]
    counts: dict[str, int] = {}
    for item in results:
        counts[item["app_status"] or "UNKNOWN"] = counts.get(item["app_status"] or "UNKNOWN", 0) + 1
    payload = {
        "status": "FAIL" if failures else "PASS",
        "phase": "v1.8 phase 3 general app-ready envelopes",
        "case_count": len(results),
        "target_count": len({item["target"] for item in results}),
        "app_status_counts": counts,
        "results": results,
        "failures": failures,
        "tmp": str(TMP),
    }
    (TMP / "phase3_regression.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(results, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
