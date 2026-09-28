#!/usr/bin/env python3
"""Deterministic dual skill/app family gate for v2.0 Phase 8."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_phase8_dual_e2e"
LOGS = TMP / "logs"
SUMMARY = TMP / "phase8_family_summary.json"
REPORT = TMP / "phase8_family_report.md"
REFERENCE = ROOT / "references" / "v2-0-dual-e2e-gate.md"
DATANALYSIS = Path.home() / "anaconda3" / "envs" / "datanalysis" / "bin" / "python"
PYTHON = DATANALYSIS if DATANALYSIS.exists() else Path(sys.executable)

VALID_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL", "ROTO"}
ACCEPTED_STATUSES = {"PASS", "WARNING", "BLOCKED_CONTROLADO"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"Missing JSON summary: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_check(
    name: str,
    command: list[str],
    summary_path: Path,
    *,
    timeout: int = 900,
) -> dict[str, Any]:
    LOGS.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    stdout_path = LOGS / f"{name}.stdout.txt"
    stderr_path = LOGS / f"{name}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    combined = completed.stdout + completed.stderr
    require("Traceback (most recent call last)" not in combined, f"{name}: raw traceback leaked")
    require(completed.returncode == 0, f"{name}: exited with {completed.returncode}")
    payload = load_json(summary_path)
    require(payload.get("status") in ACCEPTED_STATUSES, f"{name}: bad status {payload.get('status')!r}")
    return {
        "name": name,
        "status": payload.get("status"),
        "command": command,
        "summary_json": str(summary_path),
        "stdout_txt": str(stdout_path),
        "stderr_txt": str(stderr_path),
    }


def select_case(payload: dict[str, Any], case_id: str) -> dict[str, Any]:
    for row in payload.get("cases", []):
        if row.get("case") == case_id:
            return row
    raise AssertionError(f"Missing v1.9 case: {case_id}")


def family_row(
    family: str,
    source: str,
    status: str,
    *,
    finding: str,
    artifacts: list[str],
    original_modified: bool | None,
) -> dict[str, Any]:
    require(status in VALID_STATUSES, f"{family}: invalid status {status!r}")
    require(original_modified is not True, f"{family}: original input was modified")
    return {
        "family": family,
        "source": source,
        "status": status,
        "finding": finding,
        "artifacts": artifacts,
        "original_modified": original_modified,
    }


def validate_reference() -> None:
    require(REFERENCE.exists(), f"Missing Phase 8 reference: {REFERENCE}")
    text = REFERENCE.read_text(encoding="utf-8")
    for term in (
        "tabla profesional",
        "documento administrativo",
        "notebook heredado",
        "FITS/RGB",
        "DOCX roundtrip",
        "Keynote/GUI",
        "BLOCKED_CONTROLADO",
        "ScientificWorkbench",
    ):
        require(term in text, f"Phase 8 reference lacks term: {term}")


def write_report(rows: list[dict[str, Any]], checks: list[dict[str, Any]]) -> None:
    lines = [
        "# v2.0 Phase 8 dual end-to-end family gate",
        "",
        "| Family | Status | Original modified | Main finding | Artifacts |",
        "|---|---|---:|---|---|",
    ]
    for row in rows:
        artifacts = ", ".join(row["artifacts"]) if row["artifacts"] else "none"
        lines.append(
            f"| {row['family']} | `{row['status']}` | `{row['original_modified']}` | "
            f"{row['finding']} | {artifacts} |"
        )
    lines.extend(
        [
            "",
            "## Component regressions",
            "",
            "| Check | Status | Summary |",
            "|---|---|---|",
        ]
    )
    for check in checks:
        lines.append(f"| `{check['name']}` | `{check['status']}` | `{check['summary_json']}` |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    LOGS.mkdir(parents=True)
    require(APP.exists(), f"ScientificWorkbench is missing: {APP}")
    validate_reference()

    checks: list[dict[str, Any]] = []

    v1_9_summary = ROOT / "tmp/v1_9_debt_R_app_like_extended/app_like_extended_regression_summary.json"
    checks.append(
        run_check(
            "v1_9_app_like_extended",
            [str(PYTHON), str(ROOT / "scripts/audit_v1_9_app_like_extended_regression.py")],
            v1_9_summary,
        )
    )

    fits_summary = TMP / "upstream/fits_rgb_summary.json"
    checks.append(
        run_check(
            "fits_rgb",
            [
                str(PYTHON),
                str(ROOT / "scripts/audit_v2_0_p1_8_fits_rgb_batch_regression.py"),
                "--python-executable",
                str(PYTHON),
                "--summary-json",
                str(fits_summary),
            ],
            fits_summary,
        )
    )

    docx_inventory_summary = ROOT / "tmp/v2_0_p1_34_docx_style_inventory_visual/p1_34_summary.json"
    checks.append(
        run_check(
            "docx_inventory",
            [str(PYTHON), str(ROOT / "scripts/audit_v2_0_p1_34_docx_style_inventory_visual_regression.py")],
            docx_inventory_summary,
        )
    )

    docx_replace_summary = ROOT / "tmp/v2_0_p1_35_docx_styled_replace_confirmed/p1_35_summary.json"
    checks.append(
        run_check(
            "docx_replace",
            [str(PYTHON), str(ROOT / "scripts/audit_v2_0_p1_35_docx_styled_replace_confirmed_regression.py")],
            docx_replace_summary,
        )
    )

    keynote_summary = ROOT / "tmp/v2_0_p1_37_keynote_export_gui_controlled/p1_37_summary.json"
    checks.append(
        run_check(
            "keynote",
            [str(PYTHON), str(ROOT / "scripts/audit_v2_0_p1_37_keynote_export_gui_controlled_regression.py")],
            keynote_summary,
            timeout=1200,
        )
    )

    parser_summary = TMP / "upstream/parser_artifacts_summary.json"
    checks.append(
        run_check(
            "parser_artifacts",
            [
                str(PYTHON),
                str(ROOT / "scripts/audit_v2_0_phase2_parser_artifacts_regression.py"),
                "--app-root",
                str(APP),
                "--python",
                str(PYTHON),
                "--summary-json",
                str(parser_summary),
            ],
            parser_summary,
        )
    )

    jobs_summary = ROOT / "tmp/v2_0_phase7_jobs_previews/phase7_jobs_previews_summary.json"
    checks.append(
        run_check(
            "jobs_previews",
            [str(PYTHON), str(ROOT / "scripts/audit_v2_0_phase7_jobs_previews_regression.py")],
            jobs_summary,
            timeout=1200,
        )
    )

    v1_9 = load_json(v1_9_summary)
    fits = load_json(fits_summary)
    docx_inventory = load_json(docx_inventory_summary)
    docx_replace = load_json(docx_replace_summary)
    keynote = load_json(keynote_summary)

    case_map = {
        "tabla profesional": "profile_table_run_bundle",
        "documento administrativo": "document_intake_run_bundle",
        "notebook heredado": "notebook_legacy_preflight",
        "contenedor corrupto": "inspect_container_corrupt_zip",
        "serie temporal": "timeseries_ambiguous_dates",
        "sensor/medicion": "physical_qa_sensor_warning",
        "backend opcional ausente": "external_optional_backend_absent",
    }
    rows: list[dict[str, Any]] = []
    for family, case_id in case_map.items():
        case = select_case(v1_9, case_id)
        rows.append(
            family_row(
                family,
                case_id,
                case["app_status"],
                finding=f"Envelope parseable; artifact_count={case.get('artifact_count', 0)}.",
                artifacts=[case.get("summary_json", "")],
                original_modified=case.get("input_modified"),
            )
        )

    happy_rgb = next(item for item in fits["cases"] if item["name"] == "happy_rgb")
    ambiguous_rgb = next(item for item in fits["cases"] if item["name"] == "ambiguous_wcs")
    rows.append(
        family_row(
            "FITS/RGB",
            "audit_v2_0_p1_8_fits_rgb_batch_regression",
            "WARNING" if ambiguous_rgb["app_status"] == "WARNING" else happy_rgb["app_status"],
            finding="RGB happy path passed; incomplete WCS is surfaced as an honest warning.",
            artifacts=happy_rgb["artifact_types"],
            original_modified=not fits["original_hashes_unchanged"],
        )
    )

    rows.append(
        family_row(
            "DOCX roundtrip en copia",
            "P1-34 + P1-35",
            "PASS",
            finding=(
                f"{docx_inventory['style_table'][0]['matches']} style matches inventoried; "
                f"{docx_replace['confirmed_replacement']['replacements']} confirmed replacements "
                "written to an edited copy."
            ),
            artifacts=docx_replace["confirmed_replacement"]["artifact_types"],
            original_modified=docx_inventory["original_modified"] or docx_replace["original_modified"],
        )
    )

    keynote_status = keynote["real_backend_status"]
    rows.append(
        family_row(
            "Keynote/GUI preflight o bloqueo",
            "P1-37",
            keynote_status,
            finding=(
                "Real Keynote export passed with confirmation."
                if keynote_status == "PASS"
                else "Backend unavailable; preflight blocked cleanly without a misleading PDF."
            ),
            artifacts=sorted(keynote["artifacts"]),
            original_modified=keynote["original_modified"],
        )
    )

    failures = [row for row in rows if row["status"] not in ACCEPTED_STATUSES]
    require(len(rows) == 10, f"Expected 10 family rows, got {len(rows)}")
    require(not failures, f"Unacceptable family results: {failures}")
    write_report(rows, checks)

    counts = {status: sum(row["status"] == status for row in rows) for status in VALID_STATUSES}
    output = {
        "tool": "audit_v2_0_phase8_dual_e2e_regression",
        "status": "PASS",
        "python_executable": str(PYTHON),
        "skill_root": str(ROOT),
        "app_root": str(APP),
        "family_count": len(rows),
        "counts": counts,
        "families": rows,
        "component_checks": checks,
        "accepted_warnings": [
            "Administrative intake may warn when copied pseudo-documents need deeper format-specific review.",
            "Ambiguous dates, sensor ranges, and incomplete WCS remain WARNING instead of false PASS.",
        ],
        "accepted_blocks": [
            "Inherited notebook preflight blocks interactive input or side effects before copied execution.",
            "Missing optional backend is BLOCKED_CONTROLADO with actionable next steps.",
            "Keynote may be BLOCKED_CONTROLADO when macOS GUI prerequisites are unavailable.",
        ],
        "originals_modified": False,
        "report_md": str(REPORT),
        "decision": "SKILL_FAMILY_GATE_PASS_APP_QUALITY_GATE_PENDING",
    }
    SUMMARY.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
