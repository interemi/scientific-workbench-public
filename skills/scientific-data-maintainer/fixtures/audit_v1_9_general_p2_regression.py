#!/usr/bin/env python3
"""v1.9 phase 4 regression for general app-facing P2/P1 routes."""

from __future__ import annotations

import argparse
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

from _internal.provenance_utils import FROZEN_ARTIFACT_TYPES


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_TMP = ROOT / "tmp" / "v1_9_phase4_general_app_facing"
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
SEVERITY_BY_APP_STATUS = {
    "PASS": "ok",
    "WARNING": "warning",
    "BLOCKED_CONTROLADO": "blocked",
    "FAIL": "error",
}


@dataclass
class Case:
    target: str
    case_type: str
    command: list[str]
    summary_json: Path
    expected_app_statuses: set[str]
    expected_tags: set[str]
    input_paths: list[Path] = field(default_factory=list)
    artifact_required: bool = True


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
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


def markdown_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}


def code_cell(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(True)}


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_digest(path: Path) -> object:
    if not path.exists():
        return None
    if path.is_file():
        return file_digest(path)
    if path.is_dir():
        records = []
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            records.append([str(child.relative_to(path)), file_digest(child)])
        return records
    return None


def make_fixtures(tmp: Path) -> dict[str, Path]:
    if tmp.exists():
        shutil.rmtree(tmp)
    fixtures = tmp / "fixtures"
    fixtures.mkdir(parents=True)
    data: dict[str, Path] = {}

    data["table_happy"] = write_csv(
        fixtures / "tables" / "ops_metrics.csv",
        [
            {"ticket_id": 1, "team": "ops", "hours": 2.5, "priority": "low"},
            {"ticket_id": 2, "team": "data", "hours": 4.0, "priority": "high"},
            {"ticket_id": 3, "team": "ops", "hours": 1.25, "priority": "medium"},
        ],
    )
    data["table_warning"] = write_text(fixtures / "tables" / "duplicate_header.csv", "id,value,value\n1,10,11\n2,20,21\n")
    data["table_ops"] = write_csv(
        fixtures / "tables" / "service_metrics.csv",
        [
            {"date": "2026-01-01", "queue": "billing", "tickets": 31, "sla_hours": 6.5},
            {"date": "2026-02-01", "queue": "billing", "tickets": 28, "sla_hours": 5.9},
            {"date": "2026-03-01", "queue": "technical", "tickets": 45, "sla_hours": 8.1},
        ],
    )

    data["cross_dir"] = fixtures / "cross_domain"
    data["cross_dir"].mkdir()
    shutil.copy2(data["table_happy"], data["cross_dir"] / "ops_metrics.csv")

    data["empty_dir"] = fixtures / "empty"
    data["empty_dir"].mkdir()

    data["doc_a"] = write_text(fixtures / "docs" / "brief.md", "# Operations brief\n\nReview queue health and handoff notes.\n")
    data["doc_b"] = write_text(fixtures / "docs" / "notes.txt", "Meeting notes\n- Follow up on open tickets\n")
    data["docs_dir"] = fixtures / "docs"
    data["unsupported_doc"] = write_text(fixtures / "docs" / "raw.bin", "binary-ish text\n")

    data["safe_zip"] = fixtures / "containers" / "safe_bundle.zip"
    data["safe_zip"].parent.mkdir(parents=True)
    with zipfile.ZipFile(data["safe_zip"], "w") as archive:
        archive.writestr("README.txt", "safe bundle")
        archive.writestr("tables/ops_metrics.csv", data["table_happy"].read_text(encoding="utf-8"))
    data["unsafe_zip"] = fixtures / "containers" / "unsafe_bundle.zip"
    with zipfile.ZipFile(data["unsafe_zip"], "w") as archive:
        archive.writestr("../escape.txt", "bad path")
        archive.writestr("normal.txt", "ok")

    data["baseline_csv"] = write_csv(fixtures / "diff" / "baseline.csv", [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}])
    data["candidate_csv"] = write_csv(fixtures / "diff" / "candidate.csv", [{"id": 1, "amount": 10}, {"id": 2, "amount": 24}])
    data["same_a"] = write_text(fixtures / "diff" / "same_a.md", "# Same\n\nNo visible change.\n")
    data["same_b"] = write_text(fixtures / "diff" / "same_b.md", "# Same\n\nNo visible change.\n")

    data["notebook_ok"] = write_notebook(
        fixtures / "notebooks" / "analysis.ipynb",
        [markdown_cell("# Tiny analysis\n"), code_cell("value = 2 + 2\nprint('value', value)\n")],
    )
    data["notebook_input"] = write_notebook(
        fixtures / "notebooks" / "input_risk.ipynb",
        [markdown_cell("# Needs input\n"), code_cell("name = input('Name?')\nprint(name)\n")],
    )
    data["notebook_clean"] = write_notebook(
        fixtures / "notebooks" / "clean_received.ipynb",
        [markdown_cell("# Completed notebook\nThis received notebook has completed explanatory text and no interactive prompts.\n")],
    )
    data["notebook_risky"] = write_notebook(
        fixtures / "notebooks" / "risky_received.ipynb",
        [markdown_cell("## Question?\nAnswer:\n"), code_cell("x = input('value')\n")],
    )
    data["notebook_corrupt"] = write_text(fixtures / "notebooks" / "corrupt.ipynb", "{not valid json\n")

    branches_ok = fixtures / "branches_ok"
    for branch in ("alice", "bob"):
        (branches_ok / branch).mkdir(parents=True)
        shutil.copy2(data["notebook_clean"], branches_ok / branch / "analysis.ipynb")
        write_text(branches_ok / branch / "result.png", "fake png")
    data["branches_ok"] = branches_ok
    branches_warn = fixtures / "branches_warn"
    (branches_warn / "alice").mkdir(parents=True)
    (branches_warn / "bob").mkdir(parents=True)
    shutil.copy2(data["notebook_clean"], branches_warn / "alice" / "analysis.ipynb")
    write_text(branches_warn / "alice" / "result.png", "fake png")
    shutil.copy2(data["notebook_clean"], branches_warn / "bob" / "analysis.ipynb")
    data["branches_warn"] = branches_warn

    def month_date(index: int) -> str:
        year = 2025 + (index - 1) // 12
        month = ((index - 1) % 12) + 1
        return f"{year}-{month:02d}-01"

    data["series_ok"] = write_csv(
        fixtures / "series" / "monthly_sales.csv",
        [{"date": month_date(index), "value": 100 + index * 2} for index in range(1, 25)],
    )
    warning_rows = [{"date": "2025-01-01", "value": 100}, {"date": "2025-01-01", "value": 105}]
    warning_rows.extend({"date": month_date(index), "value": 100 + index} for index in range(2, 25))
    data["series_warning"] = write_csv(fixtures / "series" / "monthly_sales_warning.csv", warning_rows)

    good_sections = []
    for title, body in [
        ("Method", "We describe the data, procedure, and traceability. Measurements are reported in km/s and hours, with uncertainty terms of 0.3 km/s and sigma estimates. The method records inputs, calibration assumptions, and repeat checks for reproducibility."),
        ("Results", "The main result is a stable measured trend of 12.4 km/s with uncertainty +/- 0.3 km/s. The table reports values in hours and km/s, and the interpretation compares the measured values with literature and external references."),
        ("Discussion", "The comparison is consistent with the reference within uncertainty. The result may depend on sampling and calibration assumptions, so the text keeps cautious wording. Limitations include finite sample size, possible bias, and data-quality constraints. The discussion separates interpretation from the numeric result and explains why the uncertainty matters for the final claim. It also states that the measured trend should be treated as a supported but conditional result rather than a definitive measurement. These caveats are enough for a first-pass scientific report and leave room for expert review before final delivery. The discussion also names the practical consequence of the uncertainty budget: the trend should guide follow-up checks, not replace the raw measurements or independent verification. This gives the app-facing review enough context to classify the document as a complete draft rather than a fragile note."),
        ("Conclusions", "The analysis supports a cautious conclusion: the measured trend is plausible under the stated assumptions and uncertainty budget. The report should preserve the units, uncertainty terms, comparison with literature, and limitations when moved to a final document or presentation handoff. A final reader can therefore see the evidence, the scale of the uncertainty, and the conditions under which the conclusion remains valid. The closing paragraph states the next step clearly: keep the measurements, assumptions, and comparison together so another reviewer can reproduce the reasoning and decide whether more data are needed."),
    ]:
        good_sections.append(f"## {title}\n\n{body}\n")
    data["writeup_good"] = write_text(fixtures / "writeups" / "good.md", "# Report\n\n" + "\n".join(good_sections))
    data["writeup_warning"] = write_text(
        fixtures / "writeups" / "weak.md",
        "# Results\n\nWe found a strong result from the available data and claim that it is definitive. "
        "The text gives a few numbers but does not explain method, uncertainty, units, limitations, or comparison.\n",
    )

    return data


def summary_path(tmp: Path, target: str, case_type: str) -> Path:
    return tmp / "runs" / target / case_type / "summary.json"


def manifest_path(tmp: Path, target: str, case_type: str) -> Path:
    return tmp / "runs" / target / case_type / "manifest.json"


def out_dir(tmp: Path, target: str, case_type: str, name: str = "out") -> Path:
    return tmp / "runs" / target / case_type / name


def build_cases(tmp: Path, fixtures: dict[str, Path]) -> list[Case]:
    cases: list[Case] = []

    def py(script: str, *args: object) -> list[str]:
        return [PYTHON, str(SCRIPTS / script), *[str(item) for item in args]]

    def add(target: str, case_type: str, command: list[str], statuses: set[str], tags: set[str], inputs=None, artifact_required=True) -> None:
        cases.append(Case(target, case_type, command, summary_path(tmp, target, case_type), statuses, tags, list(inputs or []), artifact_required))

    add("profile_table", "happy", py("profile_table.py", fixtures["table_happy"], "--summary-json", summary_path(tmp, "profile_table", "happy"), "--manifest-json", manifest_path(tmp, "profile_table", "happy")), {"PASS"}, {"table", "profile"}, [fixtures["table_happy"]])
    add("profile_table", "warning", py("profile_table.py", fixtures["table_warning"], "--summary-json", summary_path(tmp, "profile_table", "warning"), "--manifest-json", manifest_path(tmp, "profile_table", "warning")), {"WARNING"}, {"table", "profile"}, [fixtures["table_warning"]])
    add("profile_table", "broken", py("profile_table.py", tmp / "fixtures" / "missing.csv", "--summary-json", summary_path(tmp, "profile_table", "broken"), "--manifest-json", manifest_path(tmp, "profile_table", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"table", "profile"})

    add("cross_domain_data_workbench", "happy", py("cross_domain_data_workbench.py", fixtures["cross_dir"], "--output-dir", out_dir(tmp, "cross_domain_data_workbench", "happy"), "--summary-json", summary_path(tmp, "cross_domain_data_workbench", "happy"), "--manifest-json", manifest_path(tmp, "cross_domain_data_workbench", "happy")), {"PASS", "WARNING"}, {"cross-domain", "bundle"}, [fixtures["cross_dir"]])
    add("cross_domain_data_workbench", "warning", py("cross_domain_data_workbench.py", fixtures["cross_dir"], tmp / "fixtures" / "missing_dir", "--output-dir", out_dir(tmp, "cross_domain_data_workbench", "warning"), "--summary-json", summary_path(tmp, "cross_domain_data_workbench", "warning"), "--manifest-json", manifest_path(tmp, "cross_domain_data_workbench", "warning")), {"WARNING"}, {"cross-domain", "bundle"}, [fixtures["cross_dir"]])
    add("cross_domain_data_workbench", "broken", py("cross_domain_data_workbench.py", fixtures["empty_dir"], "--output-dir", out_dir(tmp, "cross_domain_data_workbench", "broken"), "--summary-json", summary_path(tmp, "cross_domain_data_workbench", "broken"), "--manifest-json", manifest_path(tmp, "cross_domain_data_workbench", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"cross-domain", "bundle"}, [fixtures["empty_dir"]])

    blocked_doc_out = write_text(out_dir(tmp, "document_intake_workbench", "broken", "not_a_dir"), "blocks output dir\n")
    add("document_intake_workbench", "happy", py("document_intake_workbench.py", fixtures["doc_a"], fixtures["doc_b"], "--output-dir", out_dir(tmp, "document_intake_workbench", "happy"), "--summary-json", summary_path(tmp, "document_intake_workbench", "happy"), "--manifest-json", manifest_path(tmp, "document_intake_workbench", "happy")), {"PASS", "WARNING"}, {"documents", "intake"}, [fixtures["doc_a"], fixtures["doc_b"]])
    add("document_intake_workbench", "warning", py("document_intake_workbench.py", fixtures["doc_a"], fixtures["unsupported_doc"], "--output-dir", out_dir(tmp, "document_intake_workbench", "warning"), "--summary-json", summary_path(tmp, "document_intake_workbench", "warning"), "--manifest-json", manifest_path(tmp, "document_intake_workbench", "warning")), {"WARNING"}, {"documents", "intake"}, [fixtures["doc_a"], fixtures["unsupported_doc"]])
    add("document_intake_workbench", "broken", py("document_intake_workbench.py", fixtures["doc_a"], "--output-dir", blocked_doc_out, "--summary-json", summary_path(tmp, "document_intake_workbench", "broken"), "--manifest-json", manifest_path(tmp, "document_intake_workbench", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"documents", "intake"}, [fixtures["doc_a"]])

    add("inspect_data_container", "happy", py("inspect_data_container.py", fixtures["safe_zip"], "--summary-json", summary_path(tmp, "inspect_data_container", "happy"), "--manifest-json", manifest_path(tmp, "inspect_data_container", "happy")), {"PASS"}, {"container", "safe-intake"}, [fixtures["safe_zip"]])
    add("inspect_data_container", "warning", py("inspect_data_container.py", fixtures["unsafe_zip"], "--summary-json", summary_path(tmp, "inspect_data_container", "warning"), "--manifest-json", manifest_path(tmp, "inspect_data_container", "warning")), {"WARNING"}, {"container", "safe-intake"}, [fixtures["unsafe_zip"]])
    add("inspect_data_container", "broken", py("inspect_data_container.py", tmp / "fixtures" / "missing.zip", "--summary-json", summary_path(tmp, "inspect_data_container", "broken"), "--manifest-json", manifest_path(tmp, "inspect_data_container", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"container", "safe-intake"})

    add("semantic_diff", "happy", py("semantic_diff.py", fixtures["baseline_csv"], fixtures["candidate_csv"], "--summary-json", summary_path(tmp, "semantic_diff", "happy"), "--output-md", out_dir(tmp, "semantic_diff", "happy") / "diff.md", "--manifest-json", manifest_path(tmp, "semantic_diff", "happy")), {"PASS"}, {"diff", "comparison"}, [fixtures["baseline_csv"], fixtures["candidate_csv"]])
    add("semantic_diff", "warning", py("semantic_diff.py", fixtures["same_a"], fixtures["same_b"], "--summary-json", summary_path(tmp, "semantic_diff", "warning"), "--output-md", out_dir(tmp, "semantic_diff", "warning") / "diff.md", "--manifest-json", manifest_path(tmp, "semantic_diff", "warning")), {"WARNING"}, {"diff", "comparison"}, [fixtures["same_a"], fixtures["same_b"]])
    add("semantic_diff", "broken", py("semantic_diff.py", tmp / "fixtures" / "missing.csv", fixtures["candidate_csv"], "--summary-json", summary_path(tmp, "semantic_diff", "broken"), "--output-md", out_dir(tmp, "semantic_diff", "broken") / "diff.md", "--manifest-json", manifest_path(tmp, "semantic_diff", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"diff", "comparison"}, [fixtures["candidate_csv"]])

    overwrite_dir = out_dir(tmp, "deliverable_factory_scaffold", "warning", "deliverable")
    write_text(overwrite_dir / "deliverable.md", "# Existing\n")
    bad_scaffold = write_text(out_dir(tmp, "deliverable_factory_scaffold", "broken", "not_a_dir"), "blocks target\n")
    add("deliverable_factory_scaffold", "happy", py("deliverable_factory.py", "scaffold", out_dir(tmp, "deliverable_factory_scaffold", "happy", "deliverable"), "--kind", "status-report", "--title", "Weekly Status", "--summary-json", summary_path(tmp, "deliverable_factory_scaffold", "happy"), "--manifest-json", manifest_path(tmp, "deliverable_factory_scaffold", "happy")), {"PASS"}, {"deliverable", "scaffold"})
    add("deliverable_factory_scaffold", "warning", py("deliverable_factory.py", "scaffold", overwrite_dir, "--kind", "status-report", "--title", "Overwrite Status", "--overwrite", "--summary-json", summary_path(tmp, "deliverable_factory_scaffold", "warning"), "--manifest-json", manifest_path(tmp, "deliverable_factory_scaffold", "warning")), {"WARNING"}, {"deliverable", "scaffold"})
    add("deliverable_factory_scaffold", "broken", py("deliverable_factory.py", "scaffold", bad_scaffold, "--kind", "status-report", "--title", "Bad Target", "--summary-json", summary_path(tmp, "deliverable_factory_scaffold", "broken"), "--manifest-json", manifest_path(tmp, "deliverable_factory_scaffold", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"deliverable", "scaffold"})

    add("bootstrap_analysis_notebook", "happy", py("bootstrap_analysis_notebook.py", out_dir(tmp, "bootstrap_analysis_notebook", "happy") / "analysis.ipynb", "--domain", "general", "--summary-json", summary_path(tmp, "bootstrap_analysis_notebook", "happy"), "--manifest-json", manifest_path(tmp, "bootstrap_analysis_notebook", "happy")), {"PASS"}, {"notebook", "scaffold"})
    add("bootstrap_analysis_notebook", "warning", py("bootstrap_analysis_notebook.py", out_dir(tmp, "bootstrap_analysis_notebook", "warning") / "analysis.ipynb", "--domain", "general", "--data-path", tmp / "fixtures" / "missing_data.csv", "--summary-json", summary_path(tmp, "bootstrap_analysis_notebook", "warning"), "--manifest-json", manifest_path(tmp, "bootstrap_analysis_notebook", "warning")), {"WARNING"}, {"notebook", "scaffold"})
    add("bootstrap_analysis_notebook", "broken", py("bootstrap_analysis_notebook.py", out_dir(tmp, "bootstrap_analysis_notebook", "broken") / "analysis.txt", "--summary-json", summary_path(tmp, "bootstrap_analysis_notebook", "broken"), "--manifest-json", manifest_path(tmp, "bootstrap_analysis_notebook", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"notebook", "scaffold"})

    add("notebook_workbench", "happy", py("notebook_workbench.py", "execute-copy", fixtures["notebook_ok"], "--output-dir", out_dir(tmp, "notebook_workbench", "happy", "exec"), "--timeout-sec", "30", "--summary-json", summary_path(tmp, "notebook_workbench", "happy"), "--manifest-json", manifest_path(tmp, "notebook_workbench", "happy")), {"PASS", "WARNING"}, {"notebook", "copy-safe"}, [fixtures["notebook_ok"]])
    add("notebook_workbench", "warning", py("notebook_workbench.py", "preflight-execution", fixtures["notebook_input"], "--summary-json", summary_path(tmp, "notebook_workbench", "warning"), "--manifest-json", manifest_path(tmp, "notebook_workbench", "warning")), {"WARNING", "BLOCKED_CONTROLADO"}, {"notebook", "copy-safe"}, [fixtures["notebook_input"]])
    add("notebook_workbench", "broken", py("notebook_workbench.py", "inspect", tmp / "fixtures" / "missing.ipynb", "--summary-json", summary_path(tmp, "notebook_workbench", "broken"), "--manifest-json", manifest_path(tmp, "notebook_workbench", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"notebook", "copy-safe"})

    add("coursework_notebook_fidelity_check", "happy", py("coursework_notebook_fidelity_check.py", fixtures["notebook_clean"], "--report-md", out_dir(tmp, "coursework_notebook_fidelity_check", "happy") / "report.md", "--summary-json", summary_path(tmp, "coursework_notebook_fidelity_check", "happy")), {"PASS"}, {"notebook", "fidelity"}, [fixtures["notebook_clean"]])
    add("coursework_notebook_fidelity_check", "warning", py("coursework_notebook_fidelity_check.py", fixtures["notebook_risky"], "--report-md", out_dir(tmp, "coursework_notebook_fidelity_check", "warning") / "report.md", "--summary-json", summary_path(tmp, "coursework_notebook_fidelity_check", "warning")), {"WARNING"}, {"notebook", "fidelity"}, [fixtures["notebook_risky"]])
    add("coursework_notebook_fidelity_check", "broken", py("coursework_notebook_fidelity_check.py", fixtures["notebook_corrupt"], "--report-md", out_dir(tmp, "coursework_notebook_fidelity_check", "broken") / "report.md", "--summary-json", summary_path(tmp, "coursework_notebook_fidelity_check", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"notebook", "fidelity"}, [fixtures["notebook_corrupt"]])

    add("notebook_branch_compare", "happy", py("notebook_branch_compare.py", fixtures["branches_ok"], "--output-dir", out_dir(tmp, "notebook_branch_compare", "happy"), "--summary-json", summary_path(tmp, "notebook_branch_compare", "happy")), {"PASS", "WARNING"}, {"notebook", "branches"}, [fixtures["branches_ok"]])
    add("notebook_branch_compare", "warning", py("notebook_branch_compare.py", fixtures["branches_warn"], "--output-dir", out_dir(tmp, "notebook_branch_compare", "warning"), "--summary-json", summary_path(tmp, "notebook_branch_compare", "warning")), {"WARNING"}, {"notebook", "branches"}, [fixtures["branches_warn"]])
    add("notebook_branch_compare", "broken", py("notebook_branch_compare.py", tmp / "fixtures" / "missing_branches", "--output-dir", out_dir(tmp, "notebook_branch_compare", "broken"), "--summary-json", summary_path(tmp, "notebook_branch_compare", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"notebook", "branches"})

    add("timeseries_forecasting_workbench", "happy", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir(tmp, "timeseries_forecasting_workbench", "happy", "forecast"), "--data-path", fixtures["series_ok"], "--date-column", "date", "--value-column", "value", "--summary-json", summary_path(tmp, "timeseries_forecasting_workbench", "happy"), "--manifest-json", manifest_path(tmp, "timeseries_forecasting_workbench", "happy")), {"PASS"}, {"timeseries", "forecasting"}, [fixtures["series_ok"]])
    add("timeseries_forecasting_workbench", "warning", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir(tmp, "timeseries_forecasting_workbench", "warning", "forecast"), "--data-path", fixtures["series_warning"], "--date-column", "date", "--value-column", "value", "--summary-json", summary_path(tmp, "timeseries_forecasting_workbench", "warning"), "--manifest-json", manifest_path(tmp, "timeseries_forecasting_workbench", "warning")), {"WARNING"}, {"timeseries", "forecasting"}, [fixtures["series_warning"]])
    add("timeseries_forecasting_workbench", "broken", py("timeseries_forecasting_workbench.py", "--output-dir", out_dir(tmp, "timeseries_forecasting_workbench", "broken", "forecast"), "--frequency", "not_a_frequency", "--summary-json", summary_path(tmp, "timeseries_forecasting_workbench", "broken"), "--manifest-json", manifest_path(tmp, "timeseries_forecasting_workbench", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"timeseries", "forecasting"}, artifact_required=False)

    add("scientific_writeup_review", "happy", py("scientific_writeup_review.py", fixtures["writeup_good"], "--report-md", out_dir(tmp, "scientific_writeup_review", "happy") / "review.md", "--summary-json", summary_path(tmp, "scientific_writeup_review", "happy"), "--manifest-json", manifest_path(tmp, "scientific_writeup_review", "happy")), {"PASS", "WARNING"}, {"writing", "review"}, [fixtures["writeup_good"]])
    add("scientific_writeup_review", "warning", py("scientific_writeup_review.py", fixtures["writeup_warning"], "--report-md", out_dir(tmp, "scientific_writeup_review", "warning") / "review.md", "--summary-json", summary_path(tmp, "scientific_writeup_review", "warning"), "--manifest-json", manifest_path(tmp, "scientific_writeup_review", "warning")), {"WARNING", "BLOCKED_CONTROLADO"}, {"writing", "review"}, [fixtures["writeup_warning"]])
    add("scientific_writeup_review", "broken", py("scientific_writeup_review.py", tmp / "fixtures" / "missing_writeup.md", "--report-md", out_dir(tmp, "scientific_writeup_review", "broken") / "review.md", "--summary-json", summary_path(tmp, "scientific_writeup_review", "broken"), "--manifest-json", manifest_path(tmp, "scientific_writeup_review", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"writing", "review"})

    add("duckdb_workbench", "happy", py("duckdb_workbench.py", fixtures["table_ops"], "--sql", "SELECT queue, SUM(tickets) AS tickets FROM source0 GROUP BY queue", "--output", out_dir(tmp, "duckdb_workbench", "happy") / "query.csv", "--summary-json", summary_path(tmp, "duckdb_workbench", "happy"), "--manifest-json", manifest_path(tmp, "duckdb_workbench", "happy")), {"PASS", "BLOCKED_CONTROLADO"}, {"duckdb", "sql"}, [fixtures["table_ops"]])
    add("duckdb_workbench", "warning", py("duckdb_workbench.py", fixtures["table_ops"], "--sql", "SELECT * FROM source0 LIMIT 2", "--summary-json", summary_path(tmp, "duckdb_workbench", "warning"), "--manifest-json", manifest_path(tmp, "duckdb_workbench", "warning")), {"WARNING", "BLOCKED_CONTROLADO"}, {"duckdb", "sql"}, [fixtures["table_ops"]])
    add("duckdb_workbench", "broken", py("duckdb_workbench.py", fixtures["table_ops"], "--sql", "SELECT * FROM missing_alias", "--summary-json", summary_path(tmp, "duckdb_workbench", "broken"), "--manifest-json", manifest_path(tmp, "duckdb_workbench", "broken")), {"FAIL", "BLOCKED_CONTROLADO"}, {"duckdb", "sql"}, [fixtures["table_ops"]])
    return cases


def app_status(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    explicit = payload.get("app_status")
    if explicit:
        return str(explicit)
    return APP_STATUS_BY_LEGACY.get(str(payload.get("status", "")).lower(), "FAIL")


def validate_payload(case: Case, payload: dict | None) -> list[str]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["summary_json did not decode to an object"]
    status = app_status(payload)
    if status not in case.expected_app_statuses:
        issues.append(f"expected app_status {sorted(case.expected_app_statuses)}, got {status}")
    if payload.get("original_modified") is not False:
        issues.append("original_modified is not false")
    typed_artifacts = payload.get("typed_artifacts")
    if not isinstance(typed_artifacts, list):
        issues.append("typed_artifacts is missing or not a list")
    elif case.artifact_required and not typed_artifacts:
        issues.append("typed_artifacts is empty")
    for index, artifact in enumerate(typed_artifacts or []):
        if not isinstance(artifact, dict):
            issues.append(f"typed_artifacts[{index}] is not an object")
            continue
        artifact_type = artifact.get("artifact_type")
        if artifact_type not in FROZEN_ARTIFACT_TYPES:
            issues.append(f"typed_artifacts[{index}] has unfrozen artifact_type {artifact_type!r}")
    hints = payload.get("app_hints")
    if not isinstance(hints, dict):
        issues.append("app_hints missing or not an object")
    else:
        short_summary = str(hints.get("short_summary") or "")
        if not short_summary.strip():
            issues.append("app_hints.short_summary is empty")
        if "finished with" in short_summary:
            issues.append("app_hints.short_summary is still generic")
        severity = hints.get("severity")
        expected_severity = SEVERITY_BY_APP_STATUS.get(status or "")
        if expected_severity and severity != expected_severity:
            issues.append(f"severity {severity!r} does not match app_status {status}")
        if not isinstance(hints.get("preview_artifact_types"), list):
            issues.append("app_hints.preview_artifact_types is not a list")
        tags = {str(item) for item in hints.get("tags") or []}
        if not tags or not (tags & case.expected_tags):
            issues.append(f"app_hints.tags {sorted(tags)} lacks expected {sorted(case.expected_tags)}")
    actions = payload.get("next_actions")
    if not isinstance(actions, list) or not actions:
        issues.append("next_actions missing or empty")
    else:
        rendered = " ".join(str(action.get("label", "")) for action in actions if isinstance(action, dict)).lower()
        if "review generated artifacts" in rendered:
            issues.append("next_actions still use generic review text")
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                issues.append(f"next_actions[{index}] is not an object")
                continue
            for field_name in ("label", "kind", "priority"):
                if not action.get(field_name):
                    issues.append(f"next_actions[{index}] missing {field_name}")
    if status == "WARNING" and not payload.get("warnings"):
        issues.append("WARNING payload lacks warnings")
    if status in {"BLOCKED_CONTROLADO", "FAIL"} and not payload.get("errors"):
        issues.append(f"{status} payload lacks errors")
    return issues


def run_case(case: Case) -> dict:
    case.summary_json.parent.mkdir(parents=True, exist_ok=True)
    before = {str(path): path_digest(path) for path in case.input_paths}
    completed = subprocess.run(
        case.command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
        check=False,
    )
    (case.summary_json.parent / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (case.summary_json.parent / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    after = {str(path): path_digest(path) for path in case.input_paths}

    issues: list[str] = []
    combined = f"{completed.stdout}\n{completed.stderr}"
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        issues.append("raw traceback leaked")
    if before != after:
        issues.append("input fixture was modified")
    payload = None
    if not case.summary_json.exists():
        issues.append("summary_json was not written")
    else:
        try:
            payload = json.loads(case.summary_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"summary_json is invalid JSON: {exc}")
    issues.extend(validate_payload(case, payload))
    artifacts = payload.get("typed_artifacts", []) if isinstance(payload, dict) else []
    return {
        "target": case.target,
        "case_type": case.case_type,
        "status": "PASS" if not issues else "FAIL",
        "returncode": completed.returncode,
        "app_status": app_status(payload),
        "summary_json": str(case.summary_json),
        "artifact_types": sorted({artifact.get("artifact_type", "unknown") for artifact in artifacts if isinstance(artifact, dict)}),
        "issues": issues,
        "command": " ".join(case.command),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tmp-dir", default=str(DEFAULT_TMP))
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    tmp = Path(args.tmp_dir)
    fixtures = make_fixtures(tmp)
    cases = build_cases(tmp, fixtures)
    rows = [run_case(case) for case in cases]
    failures = [f"{row['target']}::{row['case_type']}: {'; '.join(row['issues'])}" for row in rows if row["issues"]]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["app_status"] or "UNKNOWN"] = counts.get(row["app_status"] or "UNKNOWN", 0) + 1
    report = {
        "tool": "audit_v1_9_general_p2_regression",
        "phase": "v1.9 phase 4 general app-facing P2/P1",
        "status": "FAIL" if failures else "PASS",
        "target_count": len({row["target"] for row in rows}),
        "case_count": len(rows),
        "app_status_counts": counts,
        "tmp_dir": str(tmp),
        "rows": rows,
        "failures": failures,
        "not_applied": [],
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
