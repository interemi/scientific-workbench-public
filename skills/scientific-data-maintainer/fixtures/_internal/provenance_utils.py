#!/usr/bin/env python3
"""Reusable provenance and manifest helpers for scientific-data-analysis."""

import hashlib
import json
import math
import numbers
import platform
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

STANDARD_TOOL_STATUSES = {"ok", "warning", "blocked", "fail", "broken"}
STANDARD_QA_STATUSES = STANDARD_TOOL_STATUSES | {"not_applicable"}
STATUS_ALIASES = {
    "pass": "ok",
    "ready": "ok",
    "success": "ok",
    "skip": "warning",
    "skipped": "warning",
    "error": "fail",
    "failed": "fail",
    "blocked_controlado": "blocked",
    "roto": "broken",
}
APP_STATUS_BY_STANDARD = {
    "ok": "PASS",
    "warning": "WARNING",
    "blocked": "BLOCKED_CONTROLADO",
    "fail": "FAIL",
    "broken": "ROTO",
}
APP_SEVERITY_BY_STATUS = {
    "PASS": "ok",
    "WARNING": "warning",
    "BLOCKED_CONTROLADO": "blocked",
    "FAIL": "error",
    "ROTO": "error",
}
APP_ERROR_KINDS = {
    "missing_input",
    "output_conflict",
    "corrupt_input",
    "missing_optional_backend",
    "invalid_argument",
    "unsupported_format",
    "permission_denied",
    "timeout",
    "dependency_error",
    "execution_error",
    "tool_error",
}
V1_8_STABLE_ARTIFACT_TYPES = {
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
V1_9_ADDED_ARTIFACT_TYPES = {
    "fits_product",
    "fits_visual",
    "metadata_json",
    "preview_pdf",
}
FROZEN_ARTIFACT_TYPES = V1_8_STABLE_ARTIFACT_TYPES | V1_9_ADDED_ARTIFACT_TYPES
V2_0_INTEGRATED_ARTIFACT_TYPES = {
    "edited_document",
    "app_preview",
}
KNOWN_ARTIFACT_TYPES = FROZEN_ARTIFACT_TYPES | V2_0_INTEGRATED_ARTIFACT_TYPES
ARTIFACT_TYPE_BY_KEY = {
    "summary_json": "summary_json",
    "summary_csv": "table_csv",
    "summary_md": "report_md",
    "manifest_json": "manifest_json",
    "report_md": "report_md",
    "output_md": "report_md",
    "report": "report_md",
    "preview_png": "preview_png",
    "preview_pdf": "preview_pdf",
    "plot_png": "preview_png",
    "residual_plot": "preview_png",
    "comparison_png": "preview_png",
    "previous_png": "preview_png",
    "table_csv": "table_csv",
    "inventory_csv": "table_csv",
    "query_output": "table_csv",
    "output_csv": "table_csv",
    "files_inventory_csv": "table_csv",
    "orders_inventory_csv": "table_csv",
    "notebook": "notebook_ipynb",
    "notebook_ipynb": "notebook_ipynb",
    "executed_copy": "notebook_ipynb",
    "log_txt": "log_txt",
    "stdout_txt": "log_txt",
    "stderr_txt": "log_txt",
    "command_txt": "log_txt",
    "next_steps_md": "report_md",
    "run_bundle": "handoff_bundle",
    "qa_report": "qa_report",
    "output_dir": "handoff_bundle",
    "workspace_dir": "handoff_bundle",
    "project_root": "handoff_bundle",
    "handoff_bundle": "handoff_bundle",
    "output_fits": "fits_visual",
    "visual_fits": "fits_visual",
    "rgb_cube_fits": "fits_visual",
    "fits_product": "fits_product",
    "presentation_constraints": "metadata_json",
    "new_slide_templates": "metadata_json",
    "metadata_json": "metadata_json",
    "scientific_asset_manifest": "manifest_json",
    "slide_content": "report_md",
    "speaker_script": "report_md",
    "poster_text": "report_md",
    "output_docx": "edited_document",
    "edited_document": "edited_document",
    "diff_json": "app_preview",
    "app_preview": "app_preview",
}
ARTIFACT_TYPE_BY_SUFFIX = {
    ".json": "unknown",
    ".md": "report_md",
    ".markdown": "report_md",
    ".png": "preview_png",
    ".pdf": "preview_pdf",
    ".csv": "table_csv",
    ".tsv": "table_csv",
    ".fits": "fits_product",
    ".fit": "fits_product",
    ".fts": "fits_product",
    ".ipynb": "notebook_ipynb",
    ".txt": "log_txt",
    ".log": "log_txt",
}


def redact_string(value):
    text = str(value)
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    text = text.replace("/private/tmp", "/tmp")
    hostname = socket.gethostname()
    if hostname:
        text = text.replace(hostname, "local-machine")
    return text


def sanitize_payload(value):
    if isinstance(value, Path):
        return public_path(value)
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, numbers.Real) and not isinstance(value, bool) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    return value


def _nonfinite_paths(value, path="$", limit=20):
    paths = []

    def visit(item, current):
        if len(paths) >= limit:
            return
        if isinstance(item, numbers.Real) and not isinstance(item, bool) and not math.isfinite(item):
            paths.append(current)
        elif isinstance(item, dict):
            for key, child in item.items():
                visit(child, f"{current}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{current}[{index}]")

    visit(value, path)
    return paths


_SENSITIVE_ARG_FLAGS = {
    "--api-key",
    "--apikey",
    "--credential",
    "--input-value",
    "--password",
    "--secret",
    "--token",
}
_SENSITIVE_ARG_NAMES = {item.lstrip("-") for item in _SENSITIVE_ARG_FLAGS} | {
    "authorization",
    "proxy-authorization",
}
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|password|secret|credential)=)([^&\s]+)"
)
_SENSITIVE_HEADER_RE = re.compile(r"(?i)^\s*(authorization|proxy-authorization|x-api-key)\s*:")


def _redact_sensitive_argv(argv):
    redacted = []
    hide_next = False
    for raw_item in argv:
        item = str(raw_item)
        if hide_next:
            redacted.append("[REDACTED]")
            hide_next = False
            continue
        option, separator, _value = item.partition("=")
        normalized = option.lower().replace("_", "-")
        bare_name = normalized.lstrip("-")
        sensitive_assignment = any(bare_name == name or bare_name.endswith(f"-{name}") for name in _SENSITIVE_ARG_NAMES)
        if normalized in _SENSITIVE_ARG_FLAGS or (separator and sensitive_assignment):
            if separator:
                redacted.append(f"{option}=[REDACTED]")
            else:
                redacted.append(item)
                hide_next = True
            continue
        if _SENSITIVE_HEADER_RE.match(item):
            redacted.append(f"{item.split(':', 1)[0]}: [REDACTED]")
            continue
        redacted.append(_SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", item))
    return redacted


def _artifact_value(value):
    if value is None:
        return None
    if isinstance(value, Path):
        return public_path(value)
    if isinstance(value, dict):
        return {key: _artifact_value(item) for key, item in value.items() if item is not None}
    if isinstance(value, (list, tuple)):
        return [_artifact_value(item) for item in value if item is not None]
    return sanitize_payload(value)


def app_status_for(status):
    normalized = normalize_status(status) or "warning"
    return APP_STATUS_BY_STANDARD.get(normalized, "WARNING")


def _artifact_type_for(key, value):
    key_text = str(key or "").lower()
    if key_text in ARTIFACT_TYPE_BY_KEY:
        return ARTIFACT_TYPE_BY_KEY[key_text]
    value_text = str(value or "").lower()
    if "preview" in key_text and value_text.endswith(".pdf"):
        return "preview_pdf"
    if "preview" in key_text and value_text.endswith(".png"):
        return "preview_png"
    if "manifest" in key_text or value_text.endswith("manifest.json"):
        return "manifest_json"
    if "summary" in key_text or value_text.endswith("summary.json"):
        return "summary_json"
    if key_text.endswith("_json") and value_text.endswith(".json"):
        return "metadata_json"
    if "report" in key_text:
        return "report_md"
    if "preview" in key_text or "plot" in key_text:
        return "preview_png"
    if "log" in key_text:
        return "log_txt"
    if "bundle" in key_text or key_text.endswith("_dir") or key_text == "target_dir":
        return "handoff_bundle"
    if isinstance(value, (str, Path)):
        try:
            if Path(value).expanduser().exists() and Path(value).expanduser().is_dir():
                return "handoff_bundle"
        except Exception:
            pass
    suffixes = [suffix.lower() for suffix in Path(str(value or "")).suffixes]
    if suffixes and suffixes[-1] in {".gz", ".bz2", ".xz"} and len(suffixes) >= 2:
        suffix = suffixes[-2]
    else:
        suffix = suffixes[-1] if suffixes else ""
    artifact_type = ARTIFACT_TYPE_BY_SUFFIX.get(suffix, "unknown")
    return artifact_type if artifact_type in KNOWN_ARTIFACT_TYPES else "unknown"


def _artifact_exists(value):
    if not isinstance(value, (str, Path)):
        return None
    try:
        return Path(value).expanduser().exists()
    except Exception:
        return None


def _iter_artifact_items(key, value):
    if value is None:
        return
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            combined_key = f"{key}_{child_key}" if key else child_key
            yield from _iter_artifact_items(combined_key, child_value)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_artifact_items(key, item)
        return
    yield key, value


def typed_artifacts_from_legacy(artifacts):
    typed = []
    for key, value in _iter_artifact_items("", artifacts or {}):
        if value is None:
            continue
        artifact_type = _artifact_type_for(key, value)
        record = {
            "path": public_path(value) if isinstance(value, (str, Path)) else sanitize_payload(value),
            "artifact_type": artifact_type,
            "label": str(key or artifact_type).replace("_", " ").strip() or artifact_type,
            "primary": artifact_type == "summary_json",
        }
        exists = _artifact_exists(value)
        if exists is True:
            record["exists"] = exists
        typed.append(sanitize_payload(record))
    return typed


def command_payload(command=None):
    if command is None:
        argv = list(sys.argv) if sys.argv else []
        payload = {"argv": argv, "cwd": public_path(Path.cwd()), "redacted": True}
    elif isinstance(command, dict):
        payload = dict(command)
        payload.setdefault("cwd", public_path(Path.cwd()))
        payload.setdefault("redacted", True)
        if "argv" in payload and not isinstance(payload["argv"], list):
            payload["argv"] = [str(payload["argv"])]
    elif isinstance(command, (list, tuple)):
        payload = {"argv": [str(item) for item in command], "cwd": public_path(Path.cwd()), "redacted": True}
    else:
        payload = {"argv": [str(command)], "cwd": public_path(Path.cwd()), "redacted": True}
    payload["argv"] = [redact_string(item) for item in _redact_sensitive_argv(payload.get("argv", []))]
    payload["cwd"] = public_path(payload.get("cwd", Path.cwd()))
    payload["redacted"] = bool(payload.get("redacted", True))
    return sanitize_payload(payload)


def input_records(inputs=None):
    records = []
    for index, item in enumerate(inputs or []):
        if item is None:
            continue
        if isinstance(item, dict):
            record = dict(item)
            path_value = record.get("path")
            if path_value is not None:
                record["path"] = public_path(path_value)
                record.setdefault("kind", _artifact_type_for("input", path_value))
                if "exists" not in record:
                    exists = _artifact_exists(path_value)
                    if exists is not None:
                        record["exists"] = exists
            record.setdefault("role", "primary_input" if index == 0 else "secondary_input")
            records.append(record)
            continue
        path = item
        record = {
            "path": public_path(path),
            "role": "primary_input" if index == 0 else "secondary_input",
            "kind": _artifact_type_for("input", path),
        }
        exists = _artifact_exists(path)
        if exists is not None:
            record["exists"] = exists
        records.append(record)
    return sanitize_payload(records)


def default_next_actions(app_status, tool):
    if app_status == "PASS":
        return [{"label": "Review generated artifacts", "kind": "inspect_artifact", "priority": "normal"}]
    if app_status == "WARNING":
        return [{"label": "Review warnings before using the result", "kind": "human_review", "priority": "high"}]
    if app_status == "BLOCKED_CONTROLADO":
        return [{"label": "Resolve the blocked precondition or choose another route", "kind": "route_decision", "priority": "high"}]
    return [{"label": f"Fix the input or command for {tool}", "kind": "user_input", "priority": "high"}]


APP_HINT_PROFILES = {
    "datanalysis_env.status": (
        ["environment", "datanalysis", "preflight"],
        {
            "PASS": "datanalysis is available; use it for heavy notebook, FITS, and scientific workflows.",
            "WARNING": "datanalysis is available, but an environment hint or override needs review.",
            "BLOCKED_CONTROLADO": "datanalysis is not ready; follow recovery before heavy workflows.",
        },
        {
            "PASS": [("Use datanalysis for heavy scientific workflows", "route_decision", "normal")],
            "WARNING": [("Review datanalysis warnings before heavy workflows", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Create or point to the datanalysis environment", "environment_setup", "high")],
        },
    ),
    "companion_route_check": (
        ["routing", "companion", "handoff"],
        {
            "PASS": "Companion routing produced advisory handoff options without invoking connectors.",
            "WARNING": "No companion route matched; keep the task in this skill or refine hints.",
        },
        {
            "PASS": [("Choose the recommended companion only if the handoff is justified", "route_decision", "normal")],
            "WARNING": [("Refine task/file hints or keep the workflow in scientific-data-analysis", "route_decision", "normal")],
        },
    ),
    "astrometry_net_workbench": (
        ["astronomy", "astrometry", "preflight", "expert-mode"],
        {
            "PASS": "Astrometry preflight found a plausible solve route; review local/web hints before solving.",
            "WARNING": "Astrometry preflight needs human review before attempting a solve.",
            "BLOCKED_CONTROLADO": "Astrometry route is blocked; fix input or backend preconditions before solving.",
        },
        {
            "PASS": [("Review solve hints and choose local or web solving intentionally", "route_decision", "normal")],
            "WARNING": [("Check WCS hints, scale, and backend availability before solving", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix image/FITS input or Astrometry.net backend preconditions", "user_input", "high")],
        },
    ),
    "radial_velocity_workbench.validate-manifest": (
        ["astronomy", "radial-velocity", "manifest", "expert-mode"],
        {
            "PASS": "Radial-velocity manifest is structurally ready for report building.",
            "WARNING": "Radial-velocity manifest is usable only after reviewing warnings.",
            "BLOCKED_CONTROLADO": "Radial-velocity manifest is blocked; fix missing or invalid fields before reporting.",
        },
        {
            "PASS": [("Proceed to build the RV report from this manifest", "inspect_artifact", "normal")],
            "WARNING": [("Review manifest warnings before using fitted values in a report", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix required manifest fields and rerun validation", "user_input", "high")],
        },
    ),
    "photometry_noise_budget": (
        ["measurement", "noise", "snr", "sensor"],
        {
            "PASS": "Noise budget and SNR estimate completed; review the limiting noise regime.",
            "WARNING": "Noise budget completed with assumptions or edge conditions to review.",
            "BLOCKED_CONTROLADO": "Noise budget is blocked by invalid physical or numeric inputs.",
        },
        {
            "PASS": [("Use the SNR and regime summary to adjust exposure or aperture choices", "human_review", "normal")],
            "WARNING": [("Review warning terms before comparing SNR scenarios", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Correct finite positive count/noise parameters and rerun", "user_input", "high")],
        },
    ),
    "teareduce_router": (
        ["routing", "optional-backend", "teareduce", "expert-mode"],
        {
            "PASS": "TEAREDUCE routing decision is available; use only if the legacy backend is justified.",
            "WARNING": "TEAREDUCE is not clearly the right route; prefer the native stack unless evidence says otherwise.",
            "BLOCKED_CONTROLADO": "TEAREDUCE route is blocked or optional backend conditions are not met.",
        },
        {
            "PASS": [("Follow the recommended backend route and keep provenance explicit", "route_decision", "normal")],
            "WARNING": [("Use the native stack unless TEAREDUCE-specific requirements are present", "route_decision", "high")],
            "BLOCKED_CONTROLADO": [("Keep this blocked optional or configure the backend intentionally", "route_decision", "high")],
        },
    ),
    "scientific_writeup_review": (
        ["writing", "review", "report", "qa"],
        {
            "PASS": "Write-up review completed with no major content warnings.",
            "WARNING": "Write-up review found issues to address before submission or handoff.",
            "BLOCKED_CONTROLADO": "Write-up review is blocked by an input or output-path problem.",
            "FAIL": "Write-up review failed before producing a trustworthy critique.",
        },
        {
            "PASS": [("Review the report artifact and keep strengths/caveats in the final draft", "inspect_artifact", "normal")],
            "WARNING": [("Revise flagged methodology, interpretation, or limitation sections", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix the draft path or output destination and rerun the review", "user_input", "high")],
            "FAIL": [("Fix input or command before trusting any review artifact", "user_input", "high")],
        },
    ),
    "deliverable_factory.scaffold": (
        ["deliverable", "scaffold", "handoff"],
        {
            "PASS": "Deliverable scaffold created; open the generated bundle and fill the content.",
            "WARNING": "Deliverable scaffold completed with warnings to review before handoff.",
            "BLOCKED_CONTROLADO": "Deliverable scaffold was blocked to avoid unsafe overwrite or invalid output.",
            "FAIL": "Deliverable scaffold failed before producing a usable bundle.",
        },
        {
            "PASS": [("Open the scaffolded deliverable and replace placeholders with final content", "inspect_artifact", "normal")],
            "WARNING": [("Review scaffold warnings before handing off the deliverable", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Choose a clean output path or use overwrite intentionally", "user_input", "high")],
            "FAIL": [("Fix output path or scaffold options and rerun", "user_input", "high")],
        },
    ),
    "profile_table": (
        ["table", "profile", "data-quality"],
        {
            "PASS": "Table profile completed; inspect columns, missingness, and numeric ranges before analysis.",
            "WARNING": "Table profile completed with data-quality warnings.",
            "FAIL": "Table profile failed before a trustworthy summary could be produced.",
        },
        {
            "PASS": [("Review column summaries before cleaning, plotting, or modeling", "inspect_artifact", "normal")],
            "WARNING": [("Resolve table-quality warnings before downstream analysis", "human_review", "high")],
            "FAIL": [("Fix table path, format, or malformed columns and rerun profiling", "user_input", "high")],
        },
    ),
    "cross_domain_data_workbench": (
        ["cross-domain", "table", "bundle", "first-pass"],
        {
            "PASS": "Cross-domain data bundle completed; review inventory and report before deeper analysis.",
            "WARNING": "Cross-domain data bundle completed with files or SQL warnings to review.",
            "BLOCKED_CONTROLADO": "Cross-domain data route is blocked by input or output preconditions.",
        },
        {
            "PASS": [("Inspect the inventory/report and decide the next analysis route", "route_decision", "normal")],
            "WARNING": [("Review skipped files, profile warnings, or SQL issues before continuing", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix input folder/table or destination and rerun", "user_input", "high")],
        },
    ),
    "document_intake_workbench": (
        ["documents", "intake", "safe-intake", "handoff"],
        {
            "PASS": "Document intake completed; review inventory and report before editing or handoff.",
            "WARNING": "Document intake completed with missing, unsupported, or fallback-inspection warnings.",
            "BLOCKED_CONTROLADO": "Document intake is blocked by input discovery or output destination preconditions.",
            "FAIL": "Document intake failed before producing a trustworthy bundle.",
        },
        {
            "PASS": [("Open the intake report and decide which documents need deeper review", "route_decision", "normal")],
            "WARNING": [("Review missing, unsupported, or failed document inspections before handoff", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix document paths or output directory and rerun intake", "user_input", "high")],
            "FAIL": [("Fix the document input or destination before trusting partial outputs", "user_input", "high")],
        },
    ),
    "semantic_diff": (
        ["diff", "comparison", "documents", "tables"],
        {
            "PASS": "Semantic diff completed; review the changed cells or text excerpts before handoff.",
            "WARNING": "Semantic diff completed with no visible change or comparison warnings to review.",
            "BLOCKED_CONTROLADO": "Semantic diff is blocked by missing, mismatched, or unsupported inputs.",
            "FAIL": "Semantic diff failed before producing a trustworthy comparison.",
        },
        {
            "PASS": [("Review the diff report and confirm the change is expected", "inspect_artifact", "normal")],
            "WARNING": [("Check whether no-change or extraction warnings are acceptable", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide two comparable files and rerun the diff", "user_input", "high")],
            "FAIL": [("Fix input paths, formats, or output destinations and rerun", "user_input", "high")],
        },
    ),
    "duckdb_workbench": (
        ["duckdb", "sql", "table", "optional-backend"],
        {
            "PASS": "DuckDB query completed and saved a typed output table.",
            "WARNING": "DuckDB query completed as preview-only; save an output table for app handoff.",
            "BLOCKED_CONTROLADO": "DuckDB route is blocked by SQL, input, output, or optional-backend preconditions.",
            "FAIL": "DuckDB query failed before a trustworthy result could be produced.",
        },
        {
            "PASS": [("Open the saved query table and confirm source aliases", "inspect_artifact", "normal")],
            "WARNING": [("Pass --output if this SQL result should become an app artifact", "user_input", "normal")],
            "BLOCKED_CONTROLADO": [("Fix SQL aliases, input tables, or install DuckDB intentionally", "user_input", "high")],
            "FAIL": [("Fix SQL, backend, or output path before trusting the result", "user_input", "high")],
        },
    ),
    "notebook_workbench": (
        ["notebook", "copy-safe", "execution", "handoff"],
        {
            "PASS": "Notebook workbench completed on a read-only inspection or copied execution path.",
            "WARNING": "Notebook workbench completed with execution, portability, or empty-output warnings.",
            "BLOCKED_CONTROLADO": "Notebook route is blocked by missing input, unsafe execution preconditions, or output path issues.",
            "FAIL": "Notebook route failed before producing a trustworthy copied result.",
        },
        {
            "PASS": [("Inspect the copied notebook or summary before using it downstream", "inspect_artifact", "normal")],
            "WARNING": [("Review notebook execution and portability warnings before handoff", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix notebook path, execution risks, or output directory and rerun", "user_input", "high")],
            "FAIL": [("Fix notebook input or runtime failure before trusting outputs", "user_input", "high")],
        },
    ),
    "bootstrap_analysis_notebook.py": (
        ["notebook", "scaffold", "analysis"],
        {
            "PASS": "Analysis notebook scaffold created; open it and fill dataset-specific cells.",
            "WARNING": "Notebook scaffold created with runtime, path, or assumption warnings.",
            "FAIL": "Notebook scaffold failed before producing a usable notebook.",
        },
        {
            "PASS": [("Open the notebook and adapt intake, method, and output cells", "inspect_artifact", "normal")],
            "WARNING": [("Review scaffold warnings before executing the notebook", "human_review", "high")],
            "FAIL": [("Fix notebook destination or scaffold options and rerun", "user_input", "high")],
        },
    ),
    "coursework_notebook_fidelity_check": (
        ["notebook", "fidelity", "received-notebook", "portability"],
        {
            "PASS": "Received-notebook fidelity check completed with no blocking risks.",
            "WARNING": "Received-notebook fidelity check found portability or answer-cell risks.",
            "BLOCKED_CONTROLADO": "Notebook fidelity check is blocked by missing or invalid notebook input.",
        },
        {
            "PASS": [("Proceed with copied-notebook execution or reporting", "route_decision", "normal")],
            "WARNING": [("Review input, sidecar, answer-cell, and Plotly risks before editing or executing", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide a valid notebook copy and rerun the fidelity check", "user_input", "high")],
        },
    ),
    "notebook_branch_compare": (
        ["notebook", "branches", "comparison", "handoff"],
        {
            "PASS": "Branch comparison completed; outputs look consistent enough for handoff review.",
            "WARNING": "Branch comparison found missing, duplicate, or inconsistent products.",
            "BLOCKED_CONTROLADO": "Branch comparison is blocked by the project root or output destination.",
        },
        {
            "PASS": [("Use comparison tables to choose branch outputs for the final bundle", "inspect_artifact", "normal")],
            "WARNING": [("Resolve missing or duplicate products before final assembly", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide a valid project root and rerun branch comparison", "user_input", "high")],
        },
    ),
    "timeseries_forecasting_workbench": (
        ["timeseries", "forecasting", "notebook", "scaffold"],
        {
            "PASS": "Forecasting notebook scaffold created; review frequency, horizon, and generated cells.",
            "WARNING": "Forecasting scaffold created with data warnings to review before execution.",
            "BLOCKED_CONTROLADO": "Forecasting scaffold is blocked by invalid parameters, data, or destination.",
        },
        {
            "PASS": [("Open the notebook and verify frequency, split, and forecast horizon", "inspect_artifact", "normal")],
            "WARNING": [("Review duplicate dates, missing values, or inferred columns before modeling", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix data path, notebook name, frequency, or horizon and rerun", "user_input", "high")],
        },
    ),
    "inspect_data_container": (
        ["container", "archive", "inspection", "safe-intake"],
        {
            "PASS": "Container inspection completed; review contents before extraction or conversion.",
            "WARNING": "Container inspection completed with structure or fallback-reader warnings.",
            "BLOCKED_CONTROLADO": "Container inspection is blocked by missing input or unsupported format.",
        },
        {
            "PASS": [("Review discovered entries and decide whether deeper extraction is safe", "route_decision", "normal")],
            "WARNING": [("Review archive warnings or raw-byte fallback before trusting contents", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide a supported container/archive copy and rerun inspection", "user_input", "high")],
        },
    ),
    "catalog_workbench.crossmatch-sky": (
        ["catalog", "crossmatch", "sky-only", "expert-mode"],
        {
            "PASS": "Sky crossmatch completed; inspect match counts and unmatched rows.",
            "WARNING": "Sky crossmatch completed with coordinate or match-quality warnings.",
            "BLOCKED_CONTROLADO": "Sky crossmatch is blocked by missing columns, invalid radius, or input paths.",
        },
        {
            "PASS": [("Inspect match table and verify radius/coordinate assumptions", "inspect_artifact", "normal")],
            "WARNING": [("Review coordinate quality, duplicate matches, or tolerance assumptions", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Fix catalog paths, RA/Dec columns, or radius and rerun", "user_input", "high")],
        },
    ),
    "physical_qa": (
        ["qa", "measurement", "sensor", "sanity-check"],
        {
            "PASS": "Physical QA completed with no conservative sanity warnings.",
            "WARNING": "Physical QA found suspicious values or metadata to review.",
            "BLOCKED_CONTROLADO": "Physical QA is blocked because the input cannot be read for sanity checks.",
        },
        {
            "PASS": [("Use QA metrics as a first-pass sanity gate before deeper analysis", "route_decision", "normal")],
            "WARNING": [("Review NaN/Inf, ranges, ordering, units, or metadata warnings before analysis", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide a readable FITS, spectrum, or table and rerun QA", "user_input", "high")],
        },
    ),
    "apt_workbench": (
        ["astronomy", "photometry", "apt", "optional-backend"],
        {
            "PASS": "APT completed the requested optional workflow; review preferences, logs, and photometry outputs.",
            "WARNING": "APT produced a usable result with preferences or output warnings that need review.",
            "BLOCKED_CONTROLADO": "APT is unavailable or incomplete; configure APT and APT.pref, or use a native photometry route.",
            "FAIL": "APT launched but did not produce a trustworthy result; inspect backend logs before retrying.",
        },
        {
            "PASS": [("Review APT preferences, logs, and generated photometry artifacts", "inspect_artifact", "normal")],
            "WARNING": [("Review APT preferences and warnings before using the photometry", "human_review", "high")],
            "BLOCKED_CONTROLADO": [
                ("Configure APT.csh/APT.bat and save APT.pref, or choose native FITS/photometry tools", "route_decision", "high")
            ],
            "FAIL": [("Inspect APT stdout/stderr logs and fix the backend command or preferences", "inspect_artifact", "high")],
        },
    ),
    "office_roundtrip": (
        ["documents", "docx", "copy-safe", "visual-review"],
        {
            "PASS": "DOCX review completed on a copy; inspect the inventory, diff, or edited document.",
            "WARNING": "DOCX review completed with zero matches or limitations that require visual review.",
            "BLOCKED_CONTROLADO": "DOCX workflow is blocked by invalid input, output conflict, or missing confirmation.",
            "FAIL": "DOCX workflow failed before producing a trustworthy inventory or edited copy.",
        },
        {
            "PASS": [("Review the inventory or edited copy before any handoff", "inspect_artifact", "normal")],
            "WARNING": [("Review style matches and visual fidelity before continuing", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Provide a valid DOCX copy and keep input/output paths separate", "user_input", "high")],
            "FAIL": [("Inspect the structured error and rerun on a fresh DOCX copy", "human_review", "high")],
        },
    ),
    "keynote_export": (
        ["documents", "presentation", "keynote", "optional-gui"],
        {
            "PASS": "Keynote preflight or copied-deck PDF export completed successfully.",
            "WARNING": "Keynote workflow completed with warnings that require visual review.",
            "BLOCKED_CONTROLADO": "Keynote export is unavailable or blocked; the original deck remains untouched.",
            "FAIL": "Keynote automation failed before producing a trustworthy PDF.",
        },
        {
            "PASS": [("Review the exported PDF against the copied deck", "inspect_artifact", "normal")],
            "WARNING": [("Review the PDF visually before delivery", "human_review", "high")],
            "BLOCKED_CONTROLADO": [("Install or authorize Keynote, then rerun preflight on a copied deck", "route_decision", "high")],
            "FAIL": [("Inspect AppleScript output and macOS automation permissions before retrying", "human_review", "high")],
        },
    ),
}


def _action_tuple_to_record(item):
    label, kind, priority = item
    return {"label": label, "kind": kind, "priority": priority}


def app_hint_profile_for(tool):
    key = str(tool or "")
    candidates = [key]
    if key.endswith(".py"):
        candidates.append(key[:-3])
    elif key:
        candidates.append(f"{key}.py")
    if "." in key:
        candidates.append(key.split(".")[0])
    for candidate in candidates:
        if candidate in APP_HINT_PROFILES:
            tags, summaries, actions = APP_HINT_PROFILES[candidate]
            return {"tags": tags, "summary": summaries, "next_actions": actions}
    return {}


def profile_next_actions(app_status, tool):
    profile = app_hint_profile_for(tool)
    actions = (profile.get("next_actions") or {}).get(app_status)
    if actions:
        return [_action_tuple_to_record(item) for item in actions]
    if profile:
        priority = "normal" if app_status == "PASS" else "high"
        kind = "inspect_artifact" if app_status == "PASS" else "human_review"
        return [
            {
                "label": f"Review the {tool} result and choose the next route intentionally",
                "kind": kind,
                "priority": priority,
            }
        ]
    return default_next_actions(app_status, tool)


def profile_short_summary(app_status, tool):
    profile = app_hint_profile_for(tool)
    summary = (profile.get("summary") or {}).get(app_status)
    if summary:
        return summary
    if profile:
        return f"{tool} returned {app_status}; review domain-specific warnings before continuing."
    return f"{tool} finished with {app_status}."


def infer_error_kind(message, *, error_type=None):
    text = f"{error_type or ''} {message or ''}".strip().lower()
    if not text:
        return "tool_error"
    if any(
        token in text
        for token in (
            "filenotfounderror",
            "file not found",
            "does not exist",
            "missing input",
            "missing_path",
            "no existe",
            "no se encontro",
            "no se encontraron",
        )
    ):
        return "missing_input"
    if any(
        token in text
        for token in (
            "must point to a file, not a directory",
            "parent is not a directory",
            "exists and is not a directory",
            "output target exists",
            "could not write",
            "notadirectoryerror",
            "is a directory",
        )
    ):
        return "output_conflict"
    if any(token in text for token in ("badzipfile", "not a readable", "corrupt", "truncated", "bad magic", "not a parquet")):
        return "corrupt_input"
    if any(token in text for token in ("unsupported", "unsupportedformat", "unsupported format", "unsupported suffix")):
        return "unsupported_format"
    if any(token in text for token in ("preview-rows must be positive", "invalid argument", "invalid option", "argument")):
        return "invalid_argument"
    if any(token in text for token in ("permission denied", "permissionerror", "operation not permitted")):
        return "permission_denied"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if any(
        token in text
        for token in (
            "optional backend",
            "backend absent",
            "duckdb is not installed",
            "executable was not found",
            "qlmanage is not available",
            "keynote is not available",
            "keynote.app is not installed",
            "keynote.app is not discoverable",
            "stilts executable was not found",
            "no apt command",
            "no apt preferences",
            "apt.csh",
            "apt.bat",
            "apt.pref",
        )
    ):
        return "missing_optional_backend"
    if any(token in text for token in ("importerror", "modulenotfounderror", "module not found", "not installed")):
        return "dependency_error"
    if "could not register input" in text or "could not inspect" in text or "failed" in text:
        return "execution_error"
    return "tool_error"


def error_records_from_messages(messages):
    records = []
    for item in messages or []:
        if isinstance(item, dict):
            message = str(item.get("message") or item.get("detail") or item)
            kind = item.get("kind") or infer_error_kind(message, error_type=item.get("error_type"))
        else:
            message = str(item)
            kind = infer_error_kind(message)
        if kind not in APP_ERROR_KINDS:
            kind = "tool_error"
        records.append({"message": message, "kind": kind})
    return records


def app_ready_fields(tool, status, notes=None, artifacts=None, qa=None, command=None, inputs=None):
    qa_payload = ensure_qa_payload(qa)
    qa_status = normalize_status(qa_payload.get("status")) or "not_applicable"
    severity = {"not_applicable": 0, "ok": 0, "warning": 1, "blocked": 2, "fail": 3, "broken": 4}
    tool_status = normalize_status(status) or "warning"
    effective_status = max((tool_status, qa_status), key=lambda item: severity.get(item, 3))
    app_status = app_status_for(effective_status)
    findings = [str(item) for item in qa_payload.get("findings", [])]
    note_text = [str(item) for item in (notes or [])]
    warnings = note_text + findings if app_status == "WARNING" else []
    errors = findings or note_text if app_status in {"BLOCKED_CONTROLADO", "FAIL", "ROTO"} else []
    typed_artifacts = typed_artifacts_from_legacy(artifacts or {})
    preview_types = sorted({item.get("artifact_type") for item in typed_artifacts if item.get("artifact_type")})
    profile = app_hint_profile_for(tool)
    tags = list(profile.get("tags") or [str(tool).replace(".", "_")])
    return {
        "contract_version": "1.8",
        "app_status": app_status,
        "warnings": warnings,
        "errors": error_records_from_messages(errors),
        "typed_artifacts": typed_artifacts,
        "outputs": typed_artifacts,
        "command": command_payload(command),
        "inputs": input_records(inputs),
        "original_modified": False,
        "provenance": {
            "created_by": "scientific-data-analysis",
            "skill_contract_version": "v1.8",
            "originals_policy": "read_only_or_copied_inputs",
        },
        "next_actions": profile_next_actions(app_status, tool),
        "app_hints": {
            "short_summary": profile_short_summary(app_status, tool),
            "severity": APP_SEVERITY_BY_STATUS.get(app_status, "warning"),
            "preview_artifact_types": preview_types,
            "tags": tags,
        },
    }


def normalize_status(status):
    if status is None:
        return None
    rendered = str(status).strip().lower()
    if not rendered:
        return None
    return STATUS_ALIASES.get(rendered, rendered)


def standard_qa_payload(status="not_applicable", findings=None, metrics=None):
    normalized = normalize_status(status) or "not_applicable"
    if normalized not in STANDARD_QA_STATUSES:
        normalized = "warning"
    return sanitize_payload(
        {
            "status": normalized,
            "findings": list(findings or []),
            "metrics": metrics or {},
        }
    )


def ensure_qa_payload(qa):
    if qa is None:
        return standard_qa_payload()
    if not isinstance(qa, dict):
        return standard_qa_payload(status="warning", findings=["Non-dict QA payload was coerced to a warning."])
    return standard_qa_payload(
        status=qa.get("status", "not_applicable"),
        findings=qa.get("findings") or [],
        metrics=qa.get("metrics") or {},
    )


def standard_tool_payload(
    tool,
    status=None,
    notes=None,
    artifacts=None,
    results=None,
    qa=None,
    legacy=None,
    include_environment=False,
    command=None,
    inputs=None,
):
    normalized_status = normalize_status(status)
    if normalized_status not in STANDARD_TOOL_STATUSES:
        normalized_status = "warning"
    normalized_artifacts = _artifact_value(artifacts or {})
    normalized_qa = ensure_qa_payload(qa)
    nonfinite_paths = _nonfinite_paths({"artifacts": artifacts, "results": results, "qa": qa, "legacy": legacy})
    if nonfinite_paths:
        qa_findings = list(normalized_qa.get("findings") or [])
        qa_findings.append("Non-finite numeric values were converted to explicit JSON-safe strings at: " + ", ".join(nonfinite_paths))
        qa_status = normalize_status(normalized_qa.get("status")) or "not_applicable"
        if qa_status in {"not_applicable", "ok"}:
            qa_status = "warning"
        normalized_qa = standard_qa_payload(qa_status, qa_findings, normalized_qa.get("metrics") or {})
    payload = {
        "tool": tool,
        "status": normalized_status,
        "notes": list(notes or []),
        "artifacts": normalized_artifacts,
        "results": results or {},
        "qa": normalized_qa,
    }
    payload.update(
        app_ready_fields(
            tool,
            normalized_status,
            notes=notes,
            artifacts=normalized_artifacts,
            qa=normalized_qa,
            command=command,
            inputs=inputs,
        )
    )
    if include_environment:
        payload["environment"] = environment_summary()
    if legacy:
        reserved = {
            "tool",
            "status",
            "notes",
            "artifacts",
            "results",
            "qa",
            "contract_version",
            "app_status",
            "warnings",
            "errors",
            "typed_artifacts",
            "outputs",
            "command",
            "inputs",
            "original_modified",
            "provenance",
            "next_actions",
            "app_hints",
        }
        if include_environment:
            reserved.add("environment")
        for key, value in legacy.items():
            if key in reserved:
                continue
            payload[key] = value
    return sanitize_payload(payload)


def public_path(path):
    candidate = Path(path)
    try:
        rendered = str(candidate.resolve()) if candidate.exists() else str(candidate)
    except Exception:
        rendered = str(candidate)
    return redact_string(rendered)


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def describe_path(path):
    path = Path(path)
    entry = {"path": public_path(path)}
    if not path.exists():
        entry["exists"] = False
        return entry
    stat = path.stat()
    entry.update(
        {
            "exists": True,
            "size_bytes": int(stat.st_size),
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
    )
    return entry


def environment_summary(extra=None):
    payload = {
        "python_executable": public_path(sys.executable),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "hostname": "redacted",
        "cwd": public_path(Path.cwd()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return sanitize_payload(payload)


def build_manifest(inputs=None, outputs=None, parameters=None, command=None, notes=None, extra=None):
    manifest = {
        "environment": environment_summary(),
        "inputs": [describe_path(item) for item in (inputs or [])],
        "outputs": [describe_path(item) for item in (outputs or [])],
        "parameters": parameters or {},
        "command": command,
        "notes": notes or [],
    }
    if extra:
        manifest["extra"] = extra
    return sanitize_payload(manifest)


def write_manifest(path, **kwargs):
    manifest = build_manifest(**kwargs)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    return manifest
