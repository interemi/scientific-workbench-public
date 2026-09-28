#!/usr/bin/env python3
"""v1.9 phase 5 regression for exposure modes and sensitive capability boundaries."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scientific_workflow_router import EXPOSURE_LIMITS


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_9_phase5_exposure_modes"
FIXTURES = TMP / "fixtures"
RUNS = TMP / "runs"
SUMMARY = TMP / "exposure_modes_regression_summary.json"
REFERENCE = ROOT / "references" / "v1-9-exposure-modes.md"

EXPECTED_TARGETS = {
    "external_astro_tools_preflight.py": ("optional", "v1_9", "relegated_optional"),
    "external_astro_tools_local_validation.py": ("maintainer", "no_procede", "maintainer_only"),
    "stilts_workbench.py": ("optional", "v2_0", "relegated_optional"),
    "legacy_spectroscopy_envcheck.py": ("legacy", "no_procede", "legacy_expert_only"),
    "fxcor_iraf_workbench.py prepare-session": ("legacy", "no_procede", "legacy_expert_only"),
    "fxcor_iraf_workbench.py run-auto": ("legacy", "no_procede", "legacy_expert_only"),
    "legacy_rv_coursework_workbench.py analyze": ("legacy", "no_procede", "legacy_expert_only"),
    "sb2_double_gaussian_workbench.py fit": ("expert", "no_procede", "expert_only"),
    "li6708_equivalent_width_workbench.py measure": ("expert", "no_procede", "expert_only"),
    "legacy_external_reference_check.py": ("legacy", "no_procede", "legacy_expert_only"),
    "istarmod_workbench.py inspect-tree": ("legacy", "no_procede", "legacy_expert_only"),
    "istarmod_workbench.py prepare-copy": ("legacy", "no_procede", "legacy_expert_only"),
    "legacy_spectroscopy_report_builder.py scaffold": ("legacy", "no_procede", "legacy_expert_only"),
    "apt_workbench.py": ("optional", "v2_0", "relegated_optional"),
    "teareduce_router.py": ("optional", "v1_9", "relegated_optional"),
    "spectra_ascii_coursework_workbench.py": ("expert", "no_procede", "expert_only"),
    "keynote_export.py": ("optional", "v2_0", "relegated_optional"),
    "capability_probe_matrix.py": ("maintainer", "no_procede", "maintainer_only"),
    "portable_smoke_test.py": ("maintainer", "no_procede", "maintainer_only"),
    "validate_skill_samples.py": ("maintainer", "no_procede", "maintainer_only"),
    "sync_public_surface_docs.py": ("maintainer", "no_procede", "maintainer_only"),
    "skill_surface_audit.py": ("maintainer", "no_procede", "maintainer_only"),
}


def fail(message: str) -> None:
    raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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


def write_csv(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "department", "tickets", "hours"])
        writer.writerow(["2026-01-01", "ops", "12", "5.5"])
        writer.writerow(["2026-01-02", "support", "8", "4.0"])
    return path


def write_notebook(path: Path) -> Path:
    payload = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Received notebook\n"]},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["print('safe dry-run fixture')\n"],
            },
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def make_fixtures() -> dict[str, Path]:
    table = write_csv(FIXTURES / "professional_metrics.csv")
    mixed = FIXTURES / "mixed_admin_package"
    mixed.mkdir()
    write_csv(mixed / "ops.csv")
    (mixed / "brief.md").write_text("# Brief\n\nAnonimized project handoff.\n", encoding="utf-8")
    (mixed / "notes.txt").write_text("No private data.\n", encoding="utf-8")
    notebook = write_notebook(FIXTURES / "received_notebook.ipynb")
    document = FIXTURES / "admin_report.md"
    document.write_text("# Admin report\n\nA short administrative report for dry-run routing.\n", encoding="utf-8")
    return {"table": table, "mixed": mixed, "notebook": notebook, "document": document}


def run_router(case: str, mode: str, path: Path, task: str, capability: str | None = None) -> dict:
    run_dir = RUNS / case
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_json = run_dir / "summary.json"
    manifest_json = run_dir / "manifest.json"
    cmd = [
        sys.executable,
        str(SCRIPTS / "scientific_workflow_router.py"),
        mode,
        str(path),
        "--task",
        task,
        "--summary-json",
        str(summary_json),
        "--manifest-json",
        str(manifest_json),
    ]
    if capability:
        cmd.extend(["--capability", capability])
    before = hash_path(path)
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    after = hash_path(path)
    if before != after:
        fail(f"{case}: el router modifico el input")
    combined = result.stdout + result.stderr
    if "Traceback" in combined:
        fail(f"{case}: traceback crudo")
    if result.returncode != 0:
        fail(f"{case}: returncode inesperado {result.returncode}: {result.stderr}")
    payload = json.loads(result.stdout)
    if not summary_json.exists():
        fail(f"{case}: no escribio summary_json")
    if not manifest_json.exists():
        fail(f"{case}: no escribio manifest_json")
    return {
        "case": case,
        "mode": mode,
        "path": str(path),
        "task": task,
        "capability": capability,
        "payload": payload,
        "summary_json": str(summary_json),
        "manifest_json": str(manifest_json),
    }


def validate_static_contract() -> None:
    if set(EXPOSURE_LIMITS) != set(EXPECTED_TARGETS):
        missing = sorted(set(EXPECTED_TARGETS) - set(EXPOSURE_LIMITS))
        extra = sorted(set(EXPOSURE_LIMITS) - set(EXPECTED_TARGETS))
        fail(f"EXPOSURE_LIMITS mismatch; missing={missing}, extra={extra}")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    for label, (mode, decision, router_decision) in EXPECTED_TARGETS.items():
        if label not in reference_text:
            fail(f"reference missing target {label}")
        info = EXPOSURE_LIMITS[label]
        if info["exposure_mode"] != mode:
            fail(f"{label}: exposure_mode {info['exposure_mode']} != {mode}")
        if info["v1_9_decision"] != decision:
            fail(f"{label}: v1_9_decision {info['v1_9_decision']} != {decision}")
        if info["router_decision"] != router_decision:
            fail(f"{label}: router_decision {info['router_decision']} != {router_decision}")
        if info["normal_user_action"] is not False:
            fail(f"{label}: normal_user_action must be false")
        for field in ("allowed_context", "reason", "safer_next", "capability_id"):
            if not info.get(field):
                fail(f"{label}: missing {field}")


def validate_general_payload(record: dict) -> dict[str, object]:
    payload = record["payload"]
    case = record["case"]
    if payload.get("tool") != "scientific_workflow_router":
        fail(f"{case}: tool inesperado")
    if payload.get("original_modified") is not False:
        fail(f"{case}: original_modified debe ser false")
    if len(payload.get("exposure_modes", [])) != len(EXPECTED_TARGETS):
        fail(f"{case}: exposure_modes no cubre los targets obligatorios")

    limited_labels = set(EXPECTED_TARGETS)
    limited_ids = {EXPOSURE_LIMITS[label]["capability_id"] for label in limited_labels}
    recommended = payload.get("recommended_capabilities", [])
    recommended_names = {item.get("label") for item in recommended} | {item.get("capability_id") for item in recommended}
    overlap = sorted((limited_labels | limited_ids) & recommended_names)
    if overlap:
        fail(f"{case}: rutas limitadas recomendadas en modo normal: {overlap}")

    rejected = payload.get("rejected_capabilities", [])
    rejected_by_label = {item.get("label"): item for item in rejected}
    rejected_by_id = {item.get("capability_id"): item for item in rejected if item.get("capability_id")}
    for label, (mode, decision, router_decision) in EXPECTED_TARGETS.items():
        item = rejected_by_label.get(label) or rejected_by_id.get(EXPOSURE_LIMITS[label]["capability_id"])
        if not item:
            fail(f"{case}: no rechazo/relego {label}")
        if item.get("normal_user_action") is not False:
            fail(f"{case}: {label} no declara normal_user_action=false")
        if item.get("exposure_mode") != mode:
            fail(f"{case}: {label} exposure_mode incorrecto")
        if item.get("v1_9_decision") != decision:
            fail(f"{case}: {label} decision v1_9 incorrecta")
        if item.get("router_decision") != router_decision:
            fail(f"{case}: {label} router_decision incorrecta")
        if not item.get("allowed_context") or not item.get("safer_next"):
            fail(f"{case}: {label} no tiene contexto o safer_next")

    return {
        "case": case,
        "input_kind": payload.get("input_kind"),
        "app_status": payload.get("app_status"),
        "recommended_count": len(recommended),
        "rejected_count": len(rejected),
        "exposure_rejections": len(limited_labels),
    }


def validate_explain(record: dict, expected_decision: str, expected_mode: str) -> dict[str, object]:
    explanation = record["payload"].get("results", {}).get("capability_explanation")
    case = record["case"]
    if not explanation:
        fail(f"{case}: falta capability_explanation")
    if explanation.get("decision") != expected_decision:
        fail(f"{case}: decision {explanation.get('decision')} != {expected_decision}")
    if explanation.get("exposure_mode") != expected_mode:
        fail(f"{case}: exposure_mode {explanation.get('exposure_mode')} != {expected_mode}")
    if explanation.get("normal_user_action") is not False:
        fail(f"{case}: explanation debe declarar normal_user_action=false")
    return {
        "case": case,
        "capability": record["capability"],
        "decision": explanation.get("decision"),
        "exposure_mode": explanation.get("exposure_mode"),
    }


def main() -> int:
    reset_tmp()
    validate_static_contract()
    fixtures = make_fixtures()

    general_cases = [
        run_router("general_table", "inspect", fixtures["table"], "perfilar tabla profesional anonima"),
        run_router("mixed_folder", "plan", fixtures["mixed"], "diagnosticar paquete administrativo mixto"),
        run_router("received_notebook", "inspect", fixtures["notebook"], "revisar notebook heredado"),
        run_router("document_file", "inspect", fixtures["document"], "inspeccionar documento administrativo"),
    ]
    rows = [validate_general_payload(record) for record in general_cases]

    explain_cases = [
        (
            run_router(
                "explain_optional_preflight",
                "explain",
                fixtures["table"],
                "tabla general, no backend astro",
                "external_astro_tools_preflight.py",
            ),
            "relegated_optional",
            "optional",
        ),
        (
            run_router(
                "explain_stilts",
                "explain",
                fixtures["table"],
                "tabla general, no STILTS",
                "stilts_workbench.py",
            ),
            "relegated_optional",
            "optional",
        ),
        (
            run_router(
                "explain_apt",
                "explain",
                fixtures["table"],
                "tabla general, no APT",
                "apt_workbench.py",
            ),
            "relegated_optional",
            "optional",
        ),
        (
            run_router(
                "explain_teareduce",
                "explain",
                fixtures["table"],
                "tabla general, no TEAREDUCE",
                "teareduce_router.py",
            ),
            "relegated_optional",
            "optional",
        ),
        (
            run_router(
                "explain_keynote",
                "explain",
                fixtures["document"],
                "documento general, no export Keynote GUI",
                "keynote_export.py",
            ),
            "relegated_optional",
            "optional",
        ),
        (
            run_router(
                "explain_legacy_envcheck",
                "explain",
                fixtures["table"],
                "tabla general, no IRAF",
                "legacy_spectroscopy_envcheck.py",
            ),
            "legacy_expert_only",
            "legacy",
        ),
        (
            run_router(
                "explain_li6708",
                "explain",
                fixtures["table"],
                "tabla general, no linea espectral",
                "li6708_equivalent_width_workbench.py measure",
            ),
            "expert_only",
            "expert",
        ),
        (
            run_router(
                "explain_portable_smoke",
                "explain",
                fixtures["table"],
                "tabla general, no release gate",
                "portable_smoke_test.py",
            ),
            "maintainer_only",
            "maintainer",
        ),
    ]
    explain_rows = [validate_explain(record, decision, mode) for record, decision, mode in explain_cases]

    mode_counts: dict[str, int] = {}
    decision_counts: dict[str, int] = {}
    for info in EXPOSURE_LIMITS.values():
        mode_counts[info["exposure_mode"]] = mode_counts.get(info["exposure_mode"], 0) + 1
        decision_counts[info["v1_9_decision"]] = decision_counts.get(info["v1_9_decision"], 0) + 1

    output = {
        "tool": "audit_v1_9_exposure_modes_regression",
        "status": "PASS",
        "target_count": len(EXPECTED_TARGETS),
        "general_case_count": len(rows),
        "explain_case_count": len(explain_rows),
        "mode_counts": dict(sorted(mode_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "rows": rows,
        "explain_rows": explain_rows,
        "tmp_dir": str(TMP),
        "reference": str(REFERENCE),
    }
    SUMMARY.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        output = {
            "tool": "audit_v1_9_exposure_modes_regression",
            "status": "FAIL",
            "error": str(exc),
            "tmp_dir": str(TMP),
            "reference": str(REFERENCE),
        }
        TMP.mkdir(parents=True, exist_ok=True)
        SUMMARY.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(output, indent=2, sort_keys=True))
        raise SystemExit(1)
