#!/usr/bin/env python3
"""Regression checks for v1.9 duplicate helper consolidation."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "v1_9_priority_dedupe"
LEGACY_TMP = ROOT / "tmp" / "v1_9_debt_F_dedupe"
PHASE3_TMP = ROOT / "tmp" / "v1_9_phase3_dedupe"

MIGRATED_TARGETS = {
    "photometry_noise_budget.py": ROOT / "scripts" / "photometry_noise_budget.py",
    "timeseries_forecasting_workbench.py": ROOT / "scripts" / "timeseries_forecasting_workbench.py",
    "coursework_notebook_fidelity_check.py": ROOT / "scripts" / "coursework_notebook_fidelity_check.py",
    "notebook_branch_compare.py": ROOT / "scripts" / "notebook_branch_compare.py",
}

PHASE3_TARGETS = {
    "photometric_solution.py": ROOT / "scripts" / "photometric_solution.py",
    "li6708_equivalent_width_workbench.py": ROOT / "scripts" / "li6708_equivalent_width_workbench.py",
    "echelle_multispec_inventory.py": ROOT / "scripts" / "echelle_multispec_inventory.py",
    "spectra_ascii_coursework_workbench.py": ROOT / "scripts" / "spectra_ascii_coursework_workbench.py",
}

BACKLOG = [
    {
        "target": "external_astro_tools_local_validation.py",
        "reason": "Has a local build_blocked_payload with maintainer-only validation metrics; migrate in a maintainer/exposure-mode pass.",
        "risk": "medium",
    },
    {
        "target": "legacy_spectroscopy_envcheck.py",
        "reason": "Has a local build_blocked_payload with macOS legacy environment context; migrate only with legacy regression in hand.",
        "risk": "medium",
    },
    {
        "target": "quicklook_bridge.py/keynote_export.py/presentation_workbench.py",
        "reason": "Blocked payloads carry platform/preview-specific context; avoid broad refactor in Deuda F.",
        "risk": "medium-high",
    },
]

DUPLICATE_FAMILIES = [
    {
        "family": "blocked_payloads",
        "shared_helper": "scripts/_internal/public_contract.py::build_blocked_payload",
        "status": "PASS",
        "migrated_now": sorted(PHASE3_TARGETS),
        "backlog_reason": "Remaining emit_blocked variants carry platform, FITS, legacy, optional-backend, or run-mode context and need per-family regressions.",
    },
    {
        "family": "summary_writers",
        "shared_helper": "scripts/_internal/public_contract.py::emit_payload_best_effort",
        "status": "PASS",
        "migrated_now": ["spectra_ascii_coursework_workbench.py", "timeseries_forecasting_workbench.py"],
        "backlog_reason": "Maintainer scripts still keep local stdout policies; migrate only when their public stdout contract is under test.",
    },
    {
        "family": "typed_artifacts",
        "shared_helper": "scripts/_internal/provenance_utils.py::typed_artifacts_from_legacy",
        "status": "PASS",
        "migrated_now": [],
        "backlog_reason": "No safe extra migration in this priority pass; artifact type freeze regression owns this family.",
    },
    {
        "family": "manifests",
        "shared_helper": "scripts/_internal/provenance_utils.py::write_manifest",
        "status": "PASS",
        "migrated_now": [],
        "backlog_reason": "Several scripts have domain-specific manifest payloads; keep them local until a targeted capability regression covers the output schema.",
    },
    {
        "family": "next_actions",
        "shared_helper": "scripts/_internal/provenance_utils.py::default_next_actions",
        "status": "PASS",
        "migrated_now": [],
        "backlog_reason": "App-facing next_actions were standardized in the envelope helper; command-specific handoff text remains intentionally local.",
    },
    {
        "family": "run_bundle_next_steps",
        "shared_helper": "scripts/_internal/run_bundle.py::write_next_steps_md",
        "status": "PASS",
        "migrated_now": [],
        "backlog_reason": "Run bundle adoption is intentionally gradual and covered by the v1.8/v1.9 bundle contract.",
    },
]


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


def load_payload(completed: subprocess.CompletedProcess[str], summary_path: Path | None) -> dict:
    if summary_path and summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return first_json_object(completed.stdout)


def assert_no_traceback(completed: subprocess.CompletedProcess[str], case_id: str) -> None:
    combined = f"{completed.stdout}\n{completed.stderr}"
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        raise AssertionError(f"{case_id}: raw traceback leaked\n{combined}")


def assert_blocked_payload(payload: dict, case_id: str) -> None:
    if payload.get("app_status") != "BLOCKED_CONTROLADO" and payload.get("status") != "blocked":
        raise AssertionError(f"{case_id}: expected blocked payload, got {payload.get('status')}/{payload.get('app_status')}")
    if payload.get("original_modified") is not False:
        raise AssertionError(f"{case_id}: original_modified must be false")
    if not isinstance(payload.get("errors"), list) or not payload["errors"]:
        raise AssertionError(f"{case_id}: missing errors[]")
    for item in payload["errors"]:
        if not isinstance(item, dict) or not item.get("message") or not item.get("kind"):
            raise AssertionError(f"{case_id}: malformed errors[] item: {item!r}")
    if not isinstance(payload.get("next_actions"), list) or not payload["next_actions"]:
        raise AssertionError(f"{case_id}: missing next_actions")
    if not isinstance(payload.get("command"), dict) or not payload["command"].get("argv"):
        raise AssertionError(f"{case_id}: missing command.argv")
    if not isinstance(payload.get("typed_artifacts"), list):
        raise AssertionError(f"{case_id}: missing typed_artifacts")


def source_checks() -> list[dict]:
    helper_source = (ROOT / "scripts" / "_internal" / "public_contract.py").read_text(encoding="utf-8")
    if "def build_blocked_payload(" not in helper_source:
        raise AssertionError("Missing shared build_blocked_payload helper")
    if "def emit_payload_best_effort(" not in helper_source:
        raise AssertionError("Missing shared emit_payload_best_effort helper")
    provenance_source = (ROOT / "scripts" / "_internal" / "provenance_utils.py").read_text(encoding="utf-8")
    for needle in ("def typed_artifacts_from_legacy(", "def default_next_actions(", "def write_manifest("):
        if needle not in provenance_source:
            raise AssertionError(f"Missing shared provenance helper: {needle}")
    if "if item is None:" not in provenance_source:
        raise AssertionError("input_records must skip None entries defensively")
    run_bundle_source = (ROOT / "scripts" / "_internal" / "run_bundle.py").read_text(encoding="utf-8")
    if "def write_next_steps_md(" not in run_bundle_source:
        raise AssertionError("Missing shared run bundle next_steps helper")

    rows = []
    for name, path in MIGRATED_TARGETS.items():
        text = path.read_text(encoding="utf-8")
        if "from _internal.public_contract import" not in text or "build_blocked_payload" not in text:
            raise AssertionError(f"{name}: does not import/use shared build_blocked_payload")
        rows.append({"target": name, "status": "PASS", "check": "uses shared build_blocked_payload"})
    timeseries_text = (ROOT / "scripts" / "timeseries_forecasting_workbench.py").read_text(encoding="utf-8")
    if "def write_payload_safely(" in timeseries_text:
        raise AssertionError("timeseries_forecasting_workbench.py still defines local write_payload_safely")
    if "emit_payload_best_effort(payload, summary_path)" not in timeseries_text:
        raise AssertionError("timeseries_forecasting_workbench.py does not use shared emit_payload_best_effort")
    rows.append(
        {
            "target": "timeseries_forecasting_workbench.py",
            "status": "PASS",
            "check": "uses shared emit_payload_best_effort for blocked summary writes",
        }
    )
    if not 3 <= len(MIGRATED_TARGETS) <= 6:
        raise AssertionError(f"Priority migrated target count outside safety limit: {len(MIGRATED_TARGETS)}")
    if not 3 <= len(PHASE3_TARGETS) <= 6:
        raise AssertionError(f"Phase 3 migrated target count outside safety limit: {len(PHASE3_TARGETS)}")
    for name, path in PHASE3_TARGETS.items():
        text = path.read_text(encoding="utf-8")
        if "build_blocked_payload" not in text:
            raise AssertionError(f"{name}: does not use shared build_blocked_payload")
        if name in {
            "photometric_solution.py",
            "li6708_equivalent_width_workbench.py",
            "echelle_multispec_inventory.py",
            "spectra_ascii_coursework_workbench.py",
        } and "emit_payload_best_effort" not in text:
            raise AssertionError(f"{name}: does not use shared emit_payload_best_effort for blocked summary writes")
        if name == "spectra_ascii_coursework_workbench.py" and "def write_payload(" in text:
            raise AssertionError(f"{name}: still defines local write_payload")
        rows.append({"target": name, "status": "PASS", "check": "phase3 helper dedupe applied"})
    return rows


def priority_command_cases() -> list[dict]:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    cases = [
        {
            "case": "photometry_noise_budget_negative_source",
            "target": "photometry_noise_budget.py",
            "summary": TMP / "photometry_summary.json",
            "cmd": [
                sys.executable,
                "scripts/photometry_noise_budget.py",
                "--source",
                "-1",
                "--read-noise",
                "3",
                "--n-pixels",
                "5",
                "--summary-json",
                str(TMP / "photometry_summary.json"),
            ],
        },
        {
            "case": "timeseries_invalid_notebook_name",
            "target": "timeseries_forecasting_workbench.py",
            "summary": TMP / "timeseries_summary.json",
            "cmd": [
                sys.executable,
                "scripts/timeseries_forecasting_workbench.py",
                "--output-dir",
                str(TMP / "ts_out"),
                "--notebook-name",
                "../bad.ipynb",
                "--summary-json",
                str(TMP / "timeseries_summary.json"),
            ],
        },
        {
            "case": "coursework_missing_notebook",
            "target": "coursework_notebook_fidelity_check.py",
            "summary": TMP / "coursework_summary.json",
            "cmd": [
                sys.executable,
                "scripts/coursework_notebook_fidelity_check.py",
                str(TMP / "missing.ipynb"),
                "--summary-json",
                str(TMP / "coursework_summary.json"),
            ],
        },
        {
            "case": "notebook_branch_missing_root",
            "target": "notebook_branch_compare.py",
            "summary": TMP / "branch_summary.json",
            "cmd": [
                sys.executable,
                "scripts/notebook_branch_compare.py",
                str(TMP / "missing_root"),
                "--summary-json",
                str(TMP / "branch_summary.json"),
            ],
        },
    ]
    rows = []
    for case in cases:
        completed = run(case["cmd"])
        assert_no_traceback(completed, case["case"])
        if completed.returncode == 0:
            raise AssertionError(f"{case['case']}: expected blocked non-zero return code")
        payload = load_payload(completed, case["summary"])
        assert_blocked_payload(payload, case["case"])
        rows.append(
            {
                "target": case["target"],
                "case": case["case"],
                "status": "PASS",
                "returncode": completed.returncode,
                "error_kinds": sorted({item["kind"] for item in payload["errors"] if isinstance(item, dict)}),
            }
        )
    return rows


def phase3_command_cases() -> list[dict]:
    if PHASE3_TMP.exists():
        shutil.rmtree(PHASE3_TMP)
    PHASE3_TMP.mkdir(parents=True)
    cases = [
        {
            "case": "photometric_solution_missing_table",
            "target": "photometric_solution.py",
            "summary": PHASE3_TMP / "photometric_blocked.json",
            "cmd": [
                sys.executable,
                "scripts/photometric_solution.py",
                str(PHASE3_TMP / "missing_standards.csv"),
                "--summary-json",
                str(PHASE3_TMP / "photometric_blocked.json"),
            ],
        },
        {
            "case": "li6708_missing_spectrum",
            "target": "li6708_equivalent_width_workbench.py",
            "summary": PHASE3_TMP / "li_blocked.json",
            "cmd": [
                sys.executable,
                "scripts/li6708_equivalent_width_workbench.py",
                "measure",
                str(PHASE3_TMP / "missing_li.dat"),
                "--output-dir",
                str(PHASE3_TMP / "li_out"),
                "--summary-json",
                str(PHASE3_TMP / "li_blocked.json"),
            ],
        },
        {
            "case": "echelle_missing_input",
            "target": "echelle_multispec_inventory.py",
            "summary": PHASE3_TMP / "echelle_blocked.json",
            "cmd": [
                sys.executable,
                "scripts/echelle_multispec_inventory.py",
                str(PHASE3_TMP / "missing.fits"),
                "--output-dir",
                str(PHASE3_TMP / "echelle_out"),
                "--summary-json",
                str(PHASE3_TMP / "echelle_blocked.json"),
            ],
        },
        {
            "case": "spectra_missing_or_dependency_blocked",
            "target": "spectra_ascii_coursework_workbench.py",
            "summary": PHASE3_TMP / "spectra_blocked.json",
            "cmd": [
                sys.executable,
                "scripts/spectra_ascii_coursework_workbench.py",
                str(PHASE3_TMP / "missing_spectrum.dat"),
                "--output-dir",
                str(PHASE3_TMP / "spectra_out"),
                "--summary-json",
                str(PHASE3_TMP / "spectra_blocked.json"),
            ],
        },
    ]
    rows = []
    for case in cases:
        completed = run(case["cmd"])
        assert_no_traceback(completed, case["case"])
        if completed.returncode == 0:
            raise AssertionError(f"{case['case']}: expected blocked non-zero return code")
        payload = load_payload(completed, case["summary"])
        assert_blocked_payload(payload, case["case"])
        rows.append(
            {
                "target": case["target"],
                "case": case["case"],
                "status": "PASS",
                "returncode": completed.returncode,
                "error_kinds": sorted({item["kind"] for item in payload["errors"] if isinstance(item, dict)}),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    source_rows = source_checks()
    command_rows = priority_command_cases()
    phase3_rows = phase3_command_cases()
    report = {
        "tool": "audit_v1_9_dedupe_regression",
        "status": "PASS",
        "scope": "Prioridad v1.9 / reducir duplicacion",
        "helpers": [
            "scripts/_internal/public_contract.py::build_blocked_payload",
            "scripts/_internal/public_contract.py::emit_payload_best_effort",
            "scripts/_internal/provenance_utils.py::typed_artifacts_from_legacy",
            "scripts/_internal/provenance_utils.py::default_next_actions",
            "scripts/_internal/provenance_utils.py::write_manifest",
            "scripts/_internal/run_bundle.py::write_next_steps_md",
        ],
        "migrated_target_count": len(MIGRATED_TARGETS),
        "phase3_migrated_target_count": len(PHASE3_TARGETS),
        "migration_check_count": len(source_rows),
        "migrated_targets": sorted(MIGRATED_TARGETS),
        "phase3_migrated_targets": sorted(PHASE3_TARGETS),
        "duplicate_families": DUPLICATE_FAMILIES,
        "source_checks": source_rows,
        "command_checks": command_rows,
        "phase3_command_checks": phase3_rows,
        "backlog_not_migrated": BACKLOG,
        "tmp_dir": str(TMP),
        "phase3_tmp_dir": str(PHASE3_TMP),
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        if path.resolve() == (TMP / "summary.json").resolve():
            LEGACY_TMP.mkdir(parents=True, exist_ok=True)
            (LEGACY_TMP / "summary.json").write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
