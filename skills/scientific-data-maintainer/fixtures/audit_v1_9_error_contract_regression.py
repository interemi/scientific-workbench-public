#!/usr/bin/env python3
"""Regression checks for the v1.9 app-facing error contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from _internal.provenance_utils import APP_ERROR_KINDS, standard_tool_payload


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "v1_9_priority_errors"
ENV_DOCTOR = ROOT / "scripts" / "env_doctor.py"
IWORK = ROOT / "scripts" / "iwork_workbench.py"
DUCKDB = ROOT / "scripts" / "duckdb_workbench.py"
DOC = ROOT / "references" / "v1-9-error-contract.md"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
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


def load_payload(completed: subprocess.CompletedProcess[str], summary_path: Path | None = None) -> dict:
    if summary_path and summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return first_json_object(completed.stdout)


def combined_output(completed: subprocess.CompletedProcess[str]) -> str:
    return f"{completed.stdout}\n{completed.stderr}"


def assert_no_traceback(completed: subprocess.CompletedProcess[str], case_id: str) -> None:
    combined = combined_output(completed)
    if "Traceback (most recent call last)" in combined or "\nTraceback" in combined:
        raise AssertionError(f"{case_id}: raw traceback leaked\n{combined}")


def app_status(payload: dict) -> str:
    return str(payload.get("app_status") or payload.get("status") or "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def assert_error_contract(
    payload: dict,
    *,
    case_id: str,
    expected_kind: str,
    expected_status: str = "BLOCKED_CONTROLADO",
    original_modified: bool | str = False,
    require_input: bool = False,
) -> None:
    status = app_status(payload)
    if status != expected_status and payload.get("status") != "blocked":
        raise AssertionError(f"{case_id}: expected blocked app status, got {status!r}")
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        raise AssertionError(f"{case_id}: missing non-empty errors[]")
    kinds = {item.get("kind") for item in errors if isinstance(item, dict)}
    unknown = kinds - APP_ERROR_KINDS
    if unknown:
        raise AssertionError(f"{case_id}: unregistered error kinds: {sorted(unknown)}")
    if expected_kind not in kinds:
        raise AssertionError(f"{case_id}: expected error kind {expected_kind!r}, got {sorted(kinds)}")
    next_actions = payload.get("next_actions")
    if not isinstance(next_actions, list) or not next_actions:
        raise AssertionError(f"{case_id}: missing next_actions[]")
    for index, action in enumerate(next_actions):
        if not isinstance(action, dict):
            raise AssertionError(f"{case_id}: next_actions[{index}] is not an object")
        for key in ("label", "kind", "priority"):
            if not action.get(key):
                raise AssertionError(f"{case_id}: next_actions[{index}] missing {key}")
    if payload.get("original_modified") != original_modified:
        raise AssertionError(
            f"{case_id}: expected original_modified={original_modified!r}, got {payload.get('original_modified')!r}"
        )
    command = payload.get("command")
    if not isinstance(command, dict):
        raise AssertionError(f"{case_id}: missing command object")
    if not isinstance(command.get("argv"), list) or not command["argv"]:
        raise AssertionError(f"{case_id}: command.argv missing or empty")
    if not command.get("cwd"):
        raise AssertionError(f"{case_id}: command.cwd missing")
    if command.get("redacted") is not True:
        raise AssertionError(f"{case_id}: command.redacted must be true")
    inputs = payload.get("inputs")
    if not isinstance(inputs, list):
        raise AssertionError(f"{case_id}: inputs must be a list")
    if require_input and not inputs:
        raise AssertionError(f"{case_id}: expected at least one input record")
    typed_artifacts = payload.get("typed_artifacts")
    if not isinstance(typed_artifacts, list):
        raise AssertionError(f"{case_id}: typed_artifacts must be a list")
    app_hints = payload.get("app_hints")
    if not isinstance(app_hints, dict) or not app_hints.get("short_summary"):
        raise AssertionError(f"{case_id}: app_hints.short_summary missing")


def make_iwork_bundle(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(
            "Metadata/Properties.plist",
            "<?xml version='1.0'?><plist version='1.0'><dict><key>fileFormatVersion</key><string>synthetic</string></dict></plist>",
        )
        bundle.writestr("Index/Document.iwa", b"synthetic iWork package for blocked-output testing")


def prepare_fixtures() -> dict[str, Path]:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    fixtures = {
        "csv": TMP / "sales.csv",
        "corrupt_parquet": TMP / "corrupt.parquet",
        "valid_pages": TMP / "valid.pages",
        "corrupt_pages": TMP / "corrupt.pages",
        "unsupported_zip": TMP / "unsupported.zip",
    }
    fixtures["csv"].write_text("region,revenue\nnorth,10\nsouth,15\n", encoding="utf-8")
    fixtures["corrupt_parquet"].write_bytes(b"not a parquet file\n")
    make_iwork_bundle(fixtures["valid_pages"])
    fixtures["corrupt_pages"].write_bytes(b"not an iWork zip\n")
    make_iwork_bundle(fixtures["unsupported_zip"])
    return fixtures


def assert_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "missing_input",
        "output_conflict",
        "corrupt_input",
        "missing_optional_backend",
        "invalid_argument",
        "env_doctor.py",
        "iwork_workbench.py",
        "duckdb_workbench.py",
        "command",
        "inputs",
        "typed_artifacts",
        "short_summary",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"v1.9 error contract doc missing: {missing}")


def helper_kind_matrix() -> list[dict]:
    examples = {
        "missing_input": "File not found: missing.csv",
        "output_conflict": "--output must point to a file, not a directory.",
        "corrupt_input": "BadZipFile: input is not a readable package",
        "missing_optional_backend": "DuckDB is not installed.",
        "invalid_argument": "--preview-rows must be positive.",
        "unsupported_format": "Unsupported format: .exe",
        "permission_denied": "PermissionError: permission denied",
        "timeout": "qlmanage timed out after 10 seconds.",
        "dependency_error": "ModuleNotFoundError: module not found",
        "execution_error": "Could not inspect input: failed during execution",
        "tool_error": "Unexpected blocked condition without known signature",
    }
    results = []
    for expected_kind, message in examples.items():
        payload = standard_tool_payload(
            "v1_9_error_contract_helper_probe",
            status="blocked",
            notes=["helper kind matrix"],
            artifacts={},
            results={"blocked_reason": message},
            qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": 1}},
            inputs=[{"path": str(TMP / "helper_input.csv"), "role": "primary_input", "kind": "table_csv", "exists": False}],
        )
        assert_error_contract(payload, case_id=f"helper_{expected_kind}", expected_kind=expected_kind, require_input=True)
        results.append(
            {
                "case": f"helper_{expected_kind}",
                "target": "_internal.provenance_utils",
                "expected_kind": expected_kind,
                "status": "PASS",
                "app_status": app_status(payload),
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    assert_doc()
    fixtures = prepare_fixtures()
    csv_hash_before = sha256(fixtures["csv"])
    pages_hash_before = sha256(fixtures["valid_pages"])
    results: list[dict] = []

    cases = [
        {
            "case": "env_doctor_output_conflict_summary_dir",
            "target": "env_doctor.py",
            "kind": "output_conflict",
            "cmd": [sys.executable, str(ENV_DOCTOR), "--summary-json", str(TMP / "summary_dir")],
            "prepare": lambda: (TMP / "summary_dir").mkdir(),
        },
        {
            "case": "env_doctor_output_conflict_manifest_parent_file",
            "target": "env_doctor.py",
            "kind": "output_conflict",
            "summary": TMP / "env_manifest_parent_summary.json",
            "cmd": [
                sys.executable,
                str(ENV_DOCTOR),
                "--summary-json",
                str(TMP / "env_manifest_parent_summary.json"),
                "--manifest-json",
                str(TMP / "not_a_dir_parent" / "manifest.json"),
            ],
            "prepare": lambda: (TMP / "not_a_dir_parent").write_text("not a directory\n", encoding="utf-8"),
        },
        {
            "case": "iwork_missing_input",
            "target": "iwork_workbench.py",
            "kind": "missing_input",
            "summary": TMP / "iwork_missing_summary.json",
            "cmd": [
                sys.executable,
                str(IWORK),
                str(TMP / "missing.pages"),
                "--output-dir",
                str(TMP / "iwork_missing_out"),
                "--output-json",
                str(TMP / "iwork_missing_summary.json"),
            ],
        },
        {
            "case": "iwork_corrupt_format",
            "target": "iwork_workbench.py",
            "kind": "corrupt_input",
            "summary": TMP / "iwork_corrupt_summary.json",
            "cmd": [
                sys.executable,
                str(IWORK),
                str(fixtures["corrupt_pages"]),
                "--output-dir",
                str(TMP / "iwork_corrupt_out"),
                "--output-json",
                str(TMP / "iwork_corrupt_summary.json"),
            ],
        },
        {
            "case": "iwork_unsupported_format",
            "target": "iwork_workbench.py",
            "kind": "unsupported_format",
            "summary": TMP / "iwork_unsupported_summary.json",
            "cmd": [
                sys.executable,
                str(IWORK),
                str(fixtures["unsupported_zip"]),
                "--output-dir",
                str(TMP / "iwork_unsupported_out"),
                "--output-json",
                str(TMP / "iwork_unsupported_summary.json"),
            ],
        },
        {
            "case": "iwork_output_conflict",
            "target": "iwork_workbench.py",
            "kind": "output_conflict",
            "summary": TMP / "iwork_output_conflict_summary.json",
            "cmd": [
                sys.executable,
                str(IWORK),
                str(fixtures["valid_pages"]),
                "--output-dir",
                str(TMP / "iwork_output_is_file"),
                "--output-json",
                str(TMP / "iwork_output_conflict_summary.json"),
            ],
            "prepare": lambda: (TMP / "iwork_output_is_file").write_text("conflict\n", encoding="utf-8"),
        },
        {
            "case": "duckdb_invalid_argument",
            "target": "duckdb_workbench.py",
            "kind": "invalid_argument",
            "summary": TMP / "duckdb_invalid_arg_summary.json",
            "cmd": [
                sys.executable,
                str(DUCKDB),
                str(fixtures["csv"]),
                "--preview-rows",
                "0",
                "--summary-json",
                str(TMP / "duckdb_invalid_arg_summary.json"),
            ],
        },
        {
            "case": "duckdb_missing_input",
            "target": "duckdb_workbench.py",
            "kind": "missing_input",
            "summary": TMP / "duckdb_missing_summary.json",
            "cmd": [
                sys.executable,
                str(DUCKDB),
                str(TMP / "missing.csv"),
                "--summary-json",
                str(TMP / "duckdb_missing_summary.json"),
            ],
        },
        {
            "case": "duckdb_output_conflict",
            "target": "duckdb_workbench.py",
            "kind": "output_conflict",
            "summary": TMP / "duckdb_output_conflict_summary.json",
            "cmd": [
                sys.executable,
                str(DUCKDB),
                str(fixtures["csv"]),
                "--output",
                str(TMP / "duckdb_output_dir"),
                "--summary-json",
                str(TMP / "duckdb_output_conflict_summary.json"),
            ],
            "prepare": lambda: (TMP / "duckdb_output_dir").mkdir(),
        },
        {
            "case": "duckdb_corrupt_format",
            "target": "duckdb_workbench.py",
            "kind": "corrupt_input",
            "summary": TMP / "duckdb_corrupt_summary.json",
            "cmd": [
                sys.executable,
                str(DUCKDB),
                str(fixtures["corrupt_parquet"]),
                "--summary-json",
                str(TMP / "duckdb_corrupt_summary.json"),
            ],
        },
        {
            "case": "duckdb_missing_optional_backend",
            "target": "duckdb_workbench.py",
            "kind": "missing_optional_backend",
            "summary": TMP / "duckdb_missing_backend_summary.json",
            "cmd": [
                sys.executable,
                str(DUCKDB),
                str(fixtures["csv"]),
                "--summary-json",
                str(TMP / "duckdb_missing_backend_summary.json"),
            ],
            "env": "shadow_duckdb",
        },
    ]

    shadow_dir = TMP / "shadow_duckdb"
    shadow_dir.mkdir()
    (shadow_dir / "duckdb.py").write_text("raise ImportError('simulated missing optional backend')\n", encoding="utf-8")

    for case in cases:
        prepare = case.get("prepare")
        if prepare:
            prepare()
        env = os.environ.copy()
        if case.get("env") == "shadow_duckdb":
            env["PYTHONPATH"] = str(shadow_dir) + os.pathsep + env.get("PYTHONPATH", "")
        completed = run(case["cmd"], env=env)
        assert_no_traceback(completed, case["case"])
        if completed.returncode == 0:
            raise AssertionError(f"{case['case']}: expected non-zero blocked return code")
        payload = load_payload(completed, case.get("summary"))
        assert_error_contract(
            payload,
            case_id=case["case"],
            expected_kind=case["kind"],
            require_input=case["target"] in {"iwork_workbench.py", "duckdb_workbench.py"},
        )
        results.append(
            {
                "case": case["case"],
                "target": case["target"],
                "expected_kind": case["kind"],
                "status": "PASS",
                "returncode": completed.returncode,
                "app_status": app_status(payload),
            }
        )

    if sha256(fixtures["csv"]) != csv_hash_before:
        raise AssertionError("duckdb regression modified the original CSV fixture")
    if sha256(fixtures["valid_pages"]) != pages_hash_before:
        raise AssertionError("iwork regression modified the original iWork fixture")
    helper_results = helper_kind_matrix()
    results.extend(helper_results)
    debt_report_dir = ROOT / "tmp" / "v1_9_debt_C_errors"
    debt_report_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "tool": "audit_v1_9_error_contract_regression",
        "status": "PASS",
        "target_count": len({item["target"] for item in results}),
        "case_count": len(results),
        "command_case_count": len(cases),
        "helper_case_count": len(helper_results),
        "tmp_dir": str(TMP),
        "allowed_error_kinds": sorted(APP_ERROR_KINDS),
        "results": results,
        "original_modified": False,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    (debt_report_dir / "error_contract_regression.json").write_text(rendered, encoding="utf-8")
    if args.summary_json:
        Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_json).write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
