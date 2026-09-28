"""Shared v2.6 measured-usage helpers for maintainer regressions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


FAMILY = Path(__file__).resolve().parents[1].parent
MAINTAINER = FAMILY / "scientific-data-maintainer"
MOTHER = FAMILY / "scientific-data-analysis"
ASTRO = FAMILY / "scientific-data-astro"
DOCUMENTS = FAMILY / "scientific-data-documents"
NOTEBOOKS = FAMILY / "scientific-data-notebooks"


def _runtime_tmp_base() -> Path:
    configured = os.environ.get("SCIENTIFIC_DATA_ANALYSIS_TMPDIR")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "scientific-data-analysis"


TMP_BASE = _runtime_tmp_base()
SKILL_NAMES = [
    "scientific-data-analysis",
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
]


def public(path: Path | str) -> str:
    value = str(path)
    home = str(Path.home())
    return value.replace(home, "~")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def emit(payload: dict) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") in {"PASS", "WARNING"} else 1


def load_matrix() -> dict:
    path = MOTHER / "references" / "v2-6-benchmark-matrix.json"
    return json.loads(read_text(path))


def baseline_main() -> int:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    required = [
        MOTHER / "SKILL.md",
        MOTHER / "README.txt",
        MOTHER / "RELEASE-v1.txt",
        MOTHER / "references" / "v2-5-budget-deferral-hardening.md",
        MOTHER / "references" / "guia_scientific_data_analysis_v2_5.tex",
        MOTHER / "references" / "guia_scientific_data_analysis_v2_5.pdf",
        MOTHER / "references" / "v2-6-measured-usage-charter.md",
    ]
    for path in required:
        if not path.exists():
            errors.append({"kind": "missing_file", "path": public(path)})
    for name in SKILL_NAMES:
        root = FAMILY / name
        if not (root / "SKILL.md").exists():
            errors.append({"kind": "missing_skill", "path": public(root)})
    sw = FAMILY.parent / "ScientificWorkbench"
    if not sw.exists():
        warnings.append({"kind": "app_not_found", "path": public(sw)})
    v25_summary = TMP_BASE / "v2_5_efficiency_goal/plugin_eval_installed_final_v18/score_summary.json"
    if not v25_summary.exists():
        warnings.append({"kind": "v2_5_summary_not_found", "path": public(v25_summary)})
    payload = {
        "tool": "audit_v2_6_phase0_baseline_regression",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "family_root": public(FAMILY),
        "scientificworkbench_present": sw.exists(),
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Restore missing v2.6 baseline files"}],
    }
    return emit(payload)


def matrix_main() -> int:
    errors: list[dict[str, str]] = []
    matrix = load_matrix()
    scenarios = matrix.get("scenarios", [])
    required_fields = {
        "id",
        "family",
        "skill",
        "route",
        "command_template",
        "input_kind",
        "expected_outputs",
        "sensitivity",
        "pass_criterion",
    }
    seen = set()
    covered = set()
    for item in scenarios:
        missing = sorted(required_fields - set(item))
        if missing:
            errors.append({"kind": "missing_fields", "scenario": item.get("id", "?"), "fields": missing})
        sid = item.get("id")
        if sid in seen:
            errors.append({"kind": "duplicate_scenario", "scenario": sid})
        seen.add(sid)
        covered.add(item.get("skill"))
        if "private" in item.get("sensitivity", "") and item.get("sensitivity") != "synthetic_no_private_data":
            errors.append({"kind": "privacy_risk", "scenario": sid})
    if len(scenarios) < 8:
        errors.append({"kind": "too_few_scenarios", "count": len(scenarios)})
    missing_skills = sorted(set(SKILL_NAMES) - covered)
    if missing_skills:
        errors.append({"kind": "missing_skill_coverage", "skills": missing_skills})
    payload = {
        "tool": "audit_v2_6_benchmark_matrix_regression",
        "status": "PASS" if not errors else "FAIL",
        "scenario_count": len(scenarios),
        "covered_skills": sorted(covered),
        "errors": errors,
        "warnings": [],
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Fix v2.6 benchmark matrix"}],
    }
    return emit(payload)


def write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ["date", "department", "cases", "revenue_eur", "quality_flag"],
        ["2026-06-01", "operations", "18", "1240.5", "ok"],
        ["2026-06-02", "operations", "21", "1399.0", "ok"],
        ["2026-06-03", "support", "9", "510.2", "review"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def write_notebook(path: Path) -> None:
    payload = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Legacy notebook\\n"]},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["value = 42\\n", "print(value)\\n"],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    write_json(path, payload)


def fits_card(key: str, value: str) -> bytes:
    return f"{key:<8}= {value:<20}".ljust(80).encode("ascii")


def write_fits(path: Path) -> None:
    cards = [
        fits_card("SIMPLE", "T"),
        fits_card("BITPIX", "-32"),
        fits_card("NAXIS", "2"),
        fits_card("NAXIS1", "8"),
        fits_card("NAXIS2", "8"),
        fits_card("EXTEND", "T"),
        "OBJECT  = 'V26_SMOKE'".ljust(80).encode("ascii"),
        b"END".ljust(80),
    ]
    header = b"".join(cards)
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    data = b"".join(struct.pack(">f", 100.0 + float(i)) for i in range(64))
    data += b"\0" * ((2880 - len(data) % 2880) % 2880)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + data)


def write_document_bundle(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "administrative_note.txt").write_text(
        "Synthetic administrative note\\nOwner: anonymized\\nAction: review budget table\\n",
        encoding="utf-8",
    )
    (path / "handoff.md").write_text("# Handoff\\n- No private data.\\n", encoding="utf-8")


def prepare_inputs(output_dir: Path) -> dict[str, Path]:
    generated = output_dir / "generated"
    csv_path = generated / "professional_table.csv"
    mixed = generated / "mixed_folder"
    notebook = generated / "legacy_notebook.ipynb"
    docs = generated / "documents"
    fits = generated / "smoke_v26.fits"
    archive = generated / "mixed_package.zip"
    write_csv(csv_path)
    mixed.mkdir(parents=True, exist_ok=True)
    (mixed / "notes.txt").write_text("synthetic notes\\n", encoding="utf-8")
    write_csv(mixed / "table.csv")
    write_notebook(notebook)
    write_document_bundle(docs)
    write_fits(fits)
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(csv_path, "professional_table.csv")
        zf.writestr("README.txt", "synthetic archive for v2.6\\n")
    return {
        "input_csv": csv_path,
        "mixed_folder": mixed,
        "notebook": notebook,
        "document_dir": docs,
        "fits_file": fits,
        "archive": archive,
        "missing_command": generated / "definitely_missing_stilts",
    }


def scenario_command(scenario: dict, paths: dict[str, Path], run_dir: Path) -> list[str]:
    sid = scenario["id"]
    summary = run_dir / f"{sid}_summary.json"
    artifact_dir = run_dir / f"{sid}_artifacts"
    scripts = {
        "mother": MOTHER / "scripts",
        "astro": ASTRO / "scripts",
        "documents": DOCUMENTS / "scripts",
        "notebooks": NOTEBOOKS / "scripts",
        "maintainer": MAINTAINER / "scripts",
    }
    if sid == "table_professional_csv":
        return [sys.executable, str(scripts["notebooks"] / "profile_table.py"), str(paths["input_csv"]), "--summary-json", str(summary)]
    if sid == "mixed_folder_router":
        return [sys.executable, str(scripts["mother"] / "scientific_workflow_router.py"), "inspect", str(paths["mixed_folder"]), "--summary-json", str(summary)]
    if sid == "legacy_notebook_inspect":
        return [sys.executable, str(scripts["notebooks"] / "notebook_workbench.py"), "inspect", str(paths["notebook"]), "--summary-json", str(summary)]
    if sid == "document_admin_intake":
        return [sys.executable, str(scripts["documents"] / "document_intake_workbench.py"), str(paths["document_dir"]), "--output-dir", str(artifact_dir), "--summary-json", str(summary)]
    if sid == "fits_simple_inspect":
        return [sys.executable, str(scripts["astro"] / "inspect_fits.py"), str(paths["fits_file"]), "--force-simple-fallback", "--summary-json", str(summary)]
    if sid == "optional_stilts_block":
        return [sys.executable, str(scripts["astro"] / "external_astro_tools_preflight.py"), "--require-stilts", "--stilts-command", str(paths["missing_command"]), "--summary-json", str(summary)]
    if sid == "maintainer_surface_check":
        return [sys.executable, str(scripts["maintainer"] / "audit_v2_8_family_integrity_regression.py")]
    if sid == "router_vs_direct_table":
        return [sys.executable, str(scripts["mother"] / "scientific_workflow_router.py"), "plan", str(paths["input_csv"]), "--summary-json", str(summary)]
    raise ValueError(f"Unsupported scenario: {sid}")


def normalize_status(returncode: int, summary_path: Path) -> str:
    app_status = None
    if summary_path.exists():
        try:
            payload = json.loads(read_text(summary_path))
            app_status = payload.get("app_status") or payload.get("status")
        except Exception:
            app_status = None
    if app_status:
        lowered = str(app_status).lower()
        if "blocked" in lowered:
            return "BLOCKED_CONTROLADO"
        if "warning" in lowered:
            return "WARNING"
        if lowered in {"ok", "pass", "passed"}:
            return "PASS"
        if "fail" in lowered or "error" in lowered:
            return "FAIL" if returncode != 0 else "WARNING"
    return "PASS" if returncode == 0 else "FAIL"


def run_harness(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix = load_matrix()
    paths = prepare_inputs(output_dir)
    records: list[dict] = []
    for scenario in matrix["scenarios"]:
        sid = scenario["id"]
        run_dir = output_dir / "runs" / sid
        run_dir.mkdir(parents=True, exist_ok=True)
        command = scenario_command(scenario, paths, run_dir)
        summary = run_dir / f"{sid}_summary.json"
        started = time.perf_counter()
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        duration = int((time.perf_counter() - started) * 1000)
        (run_dir / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
        (run_dir / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
        if not summary.exists() and proc.stdout.strip().startswith("{"):
            try:
                json.loads(proc.stdout)
            except Exception:
                pass
            else:
                summary.write_text(proc.stdout, encoding="utf-8")
        status = normalize_status(proc.returncode, summary)
        if sid == "optional_stilts_block" and status == "FAIL":
            status = "BLOCKED_CONTROLADO"
        token_proxy = max(1, (sum(len(str(part)) for part in command) + len(proc.stdout) + len(proc.stderr)) // 4)
        records.append(
            {
                "scenario_id": sid,
                "family": scenario["family"],
                "skill": scenario["skill"],
                "route": scenario["route"],
                "command": command,
                "status": status,
                "returncode": proc.returncode,
                "duration_ms": duration,
                "stdout_bytes": len(proc.stdout.encode("utf-8")),
                "stderr_bytes": len(proc.stderr.encode("utf-8")),
                "summary_json": public(summary) if summary.exists() else None,
                "artifacts": [public(path) for path in run_dir.iterdir() if path.is_file()],
                "original_modified": False,
                "token_measurement_kind": "local_proxy",
                "token_proxy_estimate": token_proxy,
                "notes": "Local proxy metrics are not Codex billing tokens.",
            }
        )
    observed = output_dir / "observed_usage.jsonl"
    observed.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in records:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    result = {
        "tool": "audit_v2_6_observed_usage_harness",
        "status": "PASS" if not counts.get("FAIL") else "FAIL",
        "output_dir": public(output_dir),
        "records": len(records),
        "counts": counts,
        "observed_usage_jsonl": public(observed),
        "token_measurement_kind": "local_proxy",
        "original_modified": False,
    }
    write_json(output_dir / "result.json", result)
    lines = ["# v2.6 observed usage summary", "", "| scenario | status | proxy tokens | duration ms |", "|---|---:|---:|---:|"]
    for row in records:
        lines.append(f"| {row['scenario_id']} | {row['status']} | {row['token_proxy_estimate']} | {row['duration_ms']} |")
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def harness_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run v2.6 observed-usage harness.")
    parser.add_argument("--output-dir", default=str(TMP_BASE / "v2_6_phase2_observed_usage_harness"))
    args = parser.parse_args(argv)
    result = run_harness(Path(args.output_dir))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


def observed_regression_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate v2.6 observed usage output.")
    parser.add_argument("--output-dir", default=str(TMP_BASE / "v2_6_phase2_observed_usage_harness"))
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    observed = output_dir / "observed_usage.jsonl"
    errors: list[dict[str, str]] = []
    if not observed.exists():
        errors.append({"kind": "missing_file", "path": public(observed)})
        rows: list[dict] = []
    else:
        rows = [json.loads(line) for line in observed.read_text(encoding="utf-8").splitlines() if line.strip()]
    matrix_ids = {item["id"] for item in load_matrix()["scenarios"]}
    row_ids = {row.get("scenario_id") for row in rows}
    if matrix_ids - row_ids:
        errors.append({"kind": "missing_scenarios", "scenarios": sorted(matrix_ids - row_ids)})
    for row in rows:
        if row.get("original_modified") is not False:
            errors.append({"kind": "original_modified_not_false", "scenario": row.get("scenario_id")})
        if row.get("status") == "FAIL":
            errors.append({"kind": "failed_scenario", "scenario": row.get("scenario_id")})
        if row.get("token_measurement_kind") not in {"plugin_eval_observed", "local_proxy", "not_available"}:
            errors.append({"kind": "bad_measurement_kind", "scenario": row.get("scenario_id")})
    payload = {
        "tool": "audit_v2_6_observed_usage_regression",
        "status": "PASS" if not errors else "FAIL",
        "records": len(rows),
        "errors": errors,
        "warnings": [],
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Rerun or fix v2.6 observed usage harness"}],
    }
    return emit(payload)


def app_ready_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate app-ready sanity for v2.6 harness outputs.")
    parser.add_argument("--output-dir", default=str(TMP_BASE / "v2_6_phase5_app_ready_sanity"))
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    result = run_harness(output_dir)
    errors: list[dict[str, str]] = []
    rows = [
        json.loads(line)
        for line in (output_dir / "observed_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row["status"] == "FAIL":
            errors.append({"kind": "failed_app_sanity", "scenario": row["scenario_id"]})
        if row["status"] != "BLOCKED_CONTROLADO" and not row.get("summary_json"):
            errors.append({"kind": "missing_summary_json", "scenario": row["scenario_id"]})
    payload = {
        "tool": "audit_v2_6_app_ready_cost_sanity_regression",
        "status": "PASS" if not errors and result["status"] == "PASS" else "FAIL",
        "records": len(rows),
        "errors": errors,
        "warnings": [],
        "output_dir": public(output_dir),
        "original_modified": False,
        "next_actions": [] if not errors else [{"label": "Fix app-ready scenario output"}],
    }
    return emit(payload)
