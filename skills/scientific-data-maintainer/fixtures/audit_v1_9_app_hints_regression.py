#!/usr/bin/env python3
"""Regression checks for v1.9 app_hints and next_actions debt B."""

from __future__ import annotations

import csv
import json
import argparse
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_TMP = ROOT / "tmp" / "v1_9_debt_B_app_hints"
TMP = DEFAULT_TMP
FIXTURES = TMP / "fixtures"
RUNS = TMP / "runs"
DATANALYSIS_PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
PYTHON = str(DATANALYSIS_PYTHON if DATANALYSIS_PYTHON.exists() else sys.executable)


@dataclass
class Case:
    label: str
    target: str
    command: list[str]
    summary_json: Path
    expected_tags: set[str]
    accepted_statuses: set[str]
    p_level: str
    before: str


def set_tmp_dir(path: Path) -> None:
    global TMP, FIXTURES, RUNS
    TMP = path
    FIXTURES = TMP / "fixtures"
    RUNS = TMP / "runs"


def write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_notebook(path: Path, source: str = "print('ok')\n") -> Path:
    payload = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Tiny notebook\n"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(True)},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def make_fixtures() -> dict[str, Path]:
    if TMP.exists():
        shutil.rmtree(TMP)
    FIXTURES.mkdir(parents=True)
    RUNS.mkdir(parents=True)
    fixtures: dict[str, Path] = {}
    fixtures["table"] = write_csv(
        FIXTURES / "tables" / "ops_metrics.csv",
        [
            {"id": 1, "date": "2026-01-01", "value": 10.0, "team": "ops", "ra_deg": 120.0, "dec_deg": 22.0},
            {"id": 2, "date": "2026-02-01", "value": 12.5, "team": "data", "ra_deg": 120.002, "dec_deg": 22.001},
            {"id": 3, "date": "2026-03-01", "value": 13.2, "team": "ops", "ra_deg": 121.0, "dec_deg": 23.0},
        ],
    )
    fixtures["right_catalog"] = write_csv(
        FIXTURES / "tables" / "right_catalog.csv",
        [
            {"source": "x", "ra_deg": 120.0001, "dec_deg": 22.0001},
            {"source": "y", "ra_deg": 130.0, "dec_deg": 25.0},
        ],
    )
    fixtures["series"] = write_csv(
        FIXTURES / "tables" / "series.csv",
        [{"date": f"2025-{month:02d}-01", "value": 100 + month} for month in range(1, 25)],
    )
    fixtures["draft"] = write_text(
        FIXTURES / "docs" / "draft.md",
        "# Results\n\nWe measured the dataset and found a trend. More limitations should be written.\n",
    )
    fixtures["notebook"] = write_notebook(FIXTURES / "notebooks" / "received.ipynb", "name = input('Name?')\nprint(name)\n")
    fixtures["container"] = FIXTURES / "containers" / "bundle.zip"
    fixtures["container"].parent.mkdir(parents=True)
    with zipfile.ZipFile(fixtures["container"], "w") as archive:
        archive.writestr("README.txt", "safe small archive")
        archive.writestr("tables/ops_metrics.csv", fixtures["table"].read_text(encoding="utf-8"))
    branch_root = FIXTURES / "branches"
    (branch_root / "alice").mkdir(parents=True)
    (branch_root / "bob").mkdir(parents=True)
    write_text(branch_root / "alice" / "analysis.ipynb", fixtures["notebook"].read_text(encoding="utf-8"))
    write_text(branch_root / "alice" / "result.png", "fake-png")
    write_text(branch_root / "bob" / "analysis.ipynb", fixtures["notebook"].read_text(encoding="utf-8"))
    fixtures["branches"] = branch_root
    fixtures["cross_dir"] = FIXTURES / "cross_domain"
    fixtures["cross_dir"].mkdir()
    shutil.copy2(fixtures["table"], fixtures["cross_dir"] / "ops_metrics.csv")
    return fixtures


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def first_json_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise AssertionError(f"No JSON object found in output: {text[:500]}")
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(payload, dict):
        raise AssertionError("First JSON value is not an object")
    return payload


def load_payload(completed: subprocess.CompletedProcess[str], summary_json: Path) -> dict:
    if summary_json.exists():
        return json.loads(summary_json.read_text(encoding="utf-8"))
    return first_json_object(completed.stdout)


def app_status(payload: dict) -> str:
    explicit = payload.get("app_status")
    if explicit:
        return str(explicit)
    return {
        "ok": "PASS",
        "warning": "WARNING",
        "blocked": "BLOCKED_CONTROLADO",
        "fail": "FAIL",
        "failed": "FAIL",
    }.get(str(payload.get("status", "")).lower(), "FAIL")


def validate_payload(case: Case, payload: dict, completed: subprocess.CompletedProcess[str]) -> dict:
    combined = f"{completed.stdout}\n{completed.stderr}"
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        raise AssertionError(f"{case.target}: raw traceback leaked")
    status = app_status(payload)
    if status not in case.accepted_statuses:
        raise AssertionError(f"{case.target}: app_status {status} not in {sorted(case.accepted_statuses)}")
    hints = payload.get("app_hints")
    if not isinstance(hints, dict):
        raise AssertionError(f"{case.target}: missing app_hints object")
    for field in ("short_summary", "severity", "preview_artifact_types", "tags"):
        if field not in hints:
            raise AssertionError(f"{case.target}: missing app_hints.{field}")
    if not isinstance(hints["short_summary"], str) or not hints["short_summary"].strip():
        raise AssertionError(f"{case.target}: empty short_summary")
    if "finished with" in hints["short_summary"]:
        raise AssertionError(f"{case.target}: still uses generic short_summary: {hints['short_summary']}")
    if hints["severity"] not in {"ok", "warning", "blocked", "error"}:
        raise AssertionError(f"{case.target}: invalid severity {hints['severity']!r}")
    if not isinstance(hints["preview_artifact_types"], list):
        raise AssertionError(f"{case.target}: preview_artifact_types must be a list")
    tags = set(str(item) for item in hints.get("tags") or [])
    if not tags or not (tags & case.expected_tags):
        raise AssertionError(f"{case.target}: tags {sorted(tags)} do not include expected {sorted(case.expected_tags)}")
    actions = payload.get("next_actions")
    if not isinstance(actions, list) or not actions:
        raise AssertionError(f"{case.target}: missing next_actions")
    rendered_actions = " ".join(str(action.get("label", "")) for action in actions if isinstance(action, dict)).lower()
    if not rendered_actions or "review generated artifacts" in rendered_actions:
        raise AssertionError(f"{case.target}: next_actions still look generic: {actions!r}")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise AssertionError(f"{case.target}: next_actions[{index}] is not an object")
        for field in ("label", "kind", "priority"):
            if not action.get(field):
                raise AssertionError(f"{case.target}: next_actions[{index}] missing {field}")
    return {
        "target": case.target,
        "p_level": case.p_level,
        "status": "PASS",
        "app_status": status,
        "before": case.before,
        "after_short_summary": hints["short_summary"],
        "after_tags": sorted(tags),
        "next_action_count": len(actions),
    }


def build_cases(fixtures: dict[str, Path]) -> list[Case]:
    def run_dir(name: str) -> Path:
        path = RUNS / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    cases: list[Case] = []
    rd = run_dir("datanalysis_env")
    cases.append(
        Case(
            "1",
            "datanalysis_env.py status",
            [sys.executable, str(SCRIPTS / "datanalysis_env.py"), "status", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"environment", "datanalysis"},
            {"PASS", "BLOCKED_CONTROLADO"},
            "P2",
            "legacy status JSON without app_hints profile",
        )
    )
    rd = run_dir("companion_route")
    cases.append(
        Case(
            "4",
            "companion_route_check.py",
            [PYTHON, str(SCRIPTS / "companion_route_check.py"), "--task", "review a layout-sensitive pdf deck", "--file", "report.pdf", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"routing", "companion"},
            {"PASS", "WARNING"},
            "P2",
            "generic app_hints from standard envelope",
        )
    )
    rd = run_dir("astrometry_preflight")
    cases.append(
        Case(
            "11",
            "astrometry_net_workbench.py preflight",
            [PYTHON, str(SCRIPTS / "astrometry_net_workbench.py"), "preflight", str(FIXTURES / "missing.fits"), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"astrometry", "expert-mode"},
            {"BLOCKED_CONTROLADO", "WARNING", "PASS"},
            "P1",
            "generic app_hints; did not distinguish solve route or expert mode",
        )
    )
    rd = run_dir("rv_validate")
    cases.append(
        Case(
            "14",
            "radial_velocity_workbench.py validate-manifest",
            [PYTHON, str(SCRIPTS / "radial_velocity_workbench.py"), "validate-manifest", str(FIXTURES / "missing_manifest.json"), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"radial-velocity", "manifest"},
            {"BLOCKED_CONTROLADO", "WARNING", "PASS"},
            "P1",
            "generic app_hints; manifest route not described",
        )
    )
    rd = run_dir("photometry_noise")
    cases.append(
        Case(
            "27",
            "photometry_noise_budget.py",
            [PYTHON, str(SCRIPTS / "photometry_noise_budget.py"), "--source", "1000", "--sky-per-pixel", "4", "--read-noise", "3", "--n-pixels", "20", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"noise", "snr", "sensor"},
            {"PASS", "WARNING"},
            "P2",
            "generic app_hints; no SNR/noise-regime action",
        )
    )
    rd = run_dir("teareduce_router")
    cases.append(
        Case(
            "29",
            "teareduce_router.py",
            [PYTHON, str(SCRIPTS / "teareduce_router.py"), "--intent", "general csv table reporting with SQL", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"routing", "teareduce", "optional-backend"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P1",
            "generic app_hints; native-vs-TEAREDUCE decision not explicit",
        )
    )
    rd = run_dir("writeup_review")
    cases.append(
        Case(
            "40",
            "scientific_writeup_review.py",
            [PYTHON, str(SCRIPTS / "scientific_writeup_review.py"), str(fixtures["draft"]), "--report-md", str(rd / "review.md"), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"writing", "review"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"},
            "P2",
            "generic app_hints; no writing-section action",
        )
    )
    rd = run_dir("deliverable_factory")
    cases.append(
        Case(
            "41",
            "deliverable_factory.py scaffold",
            [PYTHON, str(SCRIPTS / "deliverable_factory.py"), "scaffold", str(rd / "deliverable"), "--kind", "status-report", "--title", "Weekly Status", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"deliverable", "scaffold"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"},
            "P2",
            "generic app_hints; no scaffold handoff action",
        )
    )
    rd = run_dir("profile_table")
    cases.append(
        Case(
            "43",
            "profile_table.py",
            [PYTHON, str(SCRIPTS / "profile_table.py"), str(fixtures["table"]), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"table", "profile"},
            {"PASS", "WARNING", "FAIL"},
            "P2",
            "generic app_hints; no column-review action",
        )
    )
    rd = run_dir("cross_domain")
    cases.append(
        Case(
            "45",
            "cross_domain_data_workbench.py",
            [PYTHON, str(SCRIPTS / "cross_domain_data_workbench.py"), str(fixtures["cross_dir"]), "--output-dir", str(rd / "bundle"), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"cross-domain", "bundle"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"},
            "P2",
            "generic app_hints; no bundle next-route action",
        )
    )
    rd = run_dir("bootstrap_notebook")
    cases.append(
        Case(
            "46",
            "bootstrap_analysis_notebook.py",
            [PYTHON, str(SCRIPTS / "bootstrap_analysis_notebook.py"), str(rd / "analysis.ipynb"), "--summary-json", str(rd / "summary.json"), "--domain", "general"],
            rd / "summary.json",
            {"notebook", "scaffold"},
            {"PASS", "WARNING", "FAIL"},
            "P2",
            "generic app_hints; no notebook opening/runtime action",
        )
    )
    rd = run_dir("coursework_fidelity")
    cases.append(
        Case(
            "48",
            "coursework_notebook_fidelity_check.py",
            [PYTHON, str(SCRIPTS / "coursework_notebook_fidelity_check.py"), str(fixtures["notebook"]), "--summary-json", str(rd / "summary.json"), "--report-md", str(rd / "report.md")],
            rd / "summary.json",
            {"notebook", "fidelity", "received-notebook"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P1",
            "generic app_hints; coursework wording not converted into received-notebook action",
        )
    )
    rd = run_dir("branch_compare")
    cases.append(
        Case(
            "49",
            "notebook_branch_compare.py",
            [PYTHON, str(SCRIPTS / "notebook_branch_compare.py"), str(fixtures["branches"]), "--output-dir", str(rd / "compare"), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"notebook", "branches", "comparison"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P1",
            "generic app_hints; no branch-difference action",
        )
    )
    rd = run_dir("timeseries")
    cases.append(
        Case(
            "51",
            "timeseries_forecasting_workbench.py",
            [PYTHON, str(SCRIPTS / "timeseries_forecasting_workbench.py"), "--output-dir", str(rd / "forecast"), "--data-path", str(fixtures["series"]), "--test-horizon", "6", "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"timeseries", "forecasting"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P2",
            "generic app_hints; no frequency/horizon action",
        )
    )
    rd = run_dir("container")
    cases.append(
        Case(
            "52",
            "inspect_data_container.py",
            [PYTHON, str(SCRIPTS / "inspect_data_container.py"), str(fixtures["container"]), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"container", "safe-intake"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P2",
            "generic app_hints; no safe-extraction action",
        )
    )
    rd = run_dir("catalog_crossmatch")
    cases.append(
        Case(
            "53",
            "catalog_workbench.py crossmatch-sky",
            [
                PYTHON,
                str(SCRIPTS / "catalog_workbench.py"),
                "crossmatch-sky",
                str(fixtures["table"]),
                str(fixtures["right_catalog"]),
                str(rd / "matches.csv"),
                "--left-ra",
                "ra_deg",
                "--left-dec",
                "dec_deg",
                "--right-ra",
                "ra_deg",
                "--right-dec",
                "dec_deg",
                "--radius-arcsec",
                "5",
                "--summary-json",
                str(rd / "summary.json"),
            ],
            rd / "summary.json",
            {"catalog", "crossmatch", "sky-only"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"},
            "P1",
            "generic app_hints; no sky-only/radius action",
        )
    )
    rd = run_dir("physical_qa")
    cases.append(
        Case(
            "54",
            "physical_qa.py",
            [PYTHON, str(SCRIPTS / "physical_qa.py"), str(fixtures["table"]), "--summary-json", str(rd / "summary.json")],
            rd / "summary.json",
            {"qa", "measurement", "sensor"},
            {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "P2",
            "generic app_hints; no QA/range-review action",
        )
    )
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tmp-dir",
        default=str(DEFAULT_TMP),
        help="Temporary working directory for fixtures and per-target summaries.",
    )
    parser.add_argument("--summary-json", help="Optional path for the regression summary JSON.")
    args = parser.parse_args(argv)

    set_tmp_dir(Path(args.tmp_dir))
    fixtures = make_fixtures()
    rows = []
    for case in build_cases(fixtures):
        completed = run(case.command)
        payload = load_payload(completed, case.summary_json)
        rows.append(validate_payload(case, payload, completed))
    report = {
        "tool": "audit_v1_9_app_hints_regression",
        "status": "PASS",
        "target_count": len(rows),
        "tmp_dir": str(TMP),
        "rows": rows,
        "not_applied": [],
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
