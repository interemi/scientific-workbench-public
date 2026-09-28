#!/usr/bin/env python3
"""Regression for the v1.9 artifact type freeze."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "v1_9_priority_artifact_types"
DEBT_TMP = ROOT / "tmp" / "v1_9_debt_A_artifact_types"
REFERENCE = ROOT / "references" / "v1-9-artifact-types-freeze.md"
TARGETS = [
    "datanalysis_healthcheck.py",
    "inspect_fits.py",
    "rgb_visual_fits_export.py",
    "astrometry_net_workbench.py verify-existing-wcs",
    "echelle_multispec_inventory.py",
    "document_intake_workbench.py",
    "presentation_workbench.py inspect",
    "presentation_workbench.py existing-deck-style-audit",
    "quicklook_bridge.py",
    "latex_workbench.py scaffold",
    "latex_workbench.py review",
    "semantic_diff.py",
    "notebook_workbench.py execute-copy",
]
V1_8_TYPES = {
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
V1_9_TYPES = {
    "fits_product",
    "fits_visual",
    "metadata_json",
    "preview_pdf",
}
PROHIBITED_ALIASES = {
    "json",
    "csv",
    "png",
    "pdf",
    "markdown",
    "fits",
    "directory",
    "folder",
    "preview",
    "report",
    "manifest",
    "notebook",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def import_helpers():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _internal.provenance_utils import (  # pylint: disable=import-outside-toplevel
        FROZEN_ARTIFACT_TYPES,
        V2_0_INTEGRATED_ARTIFACT_TYPES,
        V1_8_STABLE_ARTIFACT_TYPES,
        V1_9_ADDED_ARTIFACT_TYPES,
        typed_artifacts_from_legacy,
    )

    return {
        "frozen": set(FROZEN_ARTIFACT_TYPES),
        "v2_0": set(V2_0_INTEGRATED_ARTIFACT_TYPES),
        "v1_8": set(V1_8_STABLE_ARTIFACT_TYPES),
        "v1_9": set(V1_9_ADDED_ARTIFACT_TYPES),
        "typed": typed_artifacts_from_legacy,
    }


def ensure_fixture_files() -> dict[str, Path]:
    TMP.mkdir(parents=True, exist_ok=True)
    DEBT_TMP.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": TMP / "summary.json",
        "manifest": TMP / "manifest.json",
        "metadata": TMP / "presentation_constraints.json",
        "templates": TMP / "new_slide_templates.json",
        "asset_manifest": TMP / "scientific_asset_manifest.json",
        "report": TMP / "report.md",
        "style_report": TMP / "style_audit_report.md",
        "slide_content": TMP / "slide_content.md",
        "speaker_script": TMP / "speaker_script.md",
        "poster_text": TMP / "poster_text.md",
        "preview_png": TMP / "preview.png",
        "comparison_png": TMP / "comparison.png",
        "preview_pdf": TMP / "preview.pdf",
        "csv": TMP / "inventory.csv",
        "orders_csv": TMP / "orders.csv",
        "notebook": TMP / "executed.ipynb",
        "log": TMP / "stdout.txt",
        "fits_visual": TMP / "visual_rgb.fits",
        "fits_product": TMP / "derived_product.fits",
        "unknown": TMP / "sidecar.sidecar",
    }
    json_text = "{}\n"
    for key in ("summary", "manifest", "metadata", "templates", "asset_manifest"):
        paths[key].write_text(json_text, encoding="utf-8")
    for key in ("report", "style_report", "slide_content", "speaker_script", "poster_text", "log"):
        paths[key].write_text(f"{key}\n", encoding="utf-8")
    for key in ("csv", "orders_csv"):
        paths[key].write_text("a,b\n1,2\n", encoding="utf-8")
    paths["notebook"].write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}\n', encoding="utf-8")
    for key in ("preview_png", "comparison_png", "preview_pdf", "fits_visual", "fits_product", "unknown"):
        paths[key].write_bytes(b"fixture")
    paths["output_dir"] = TMP / "output_dir"
    paths["workspace"] = TMP / "workspace"
    paths["project_root"] = TMP / "latex_project"
    for key in ("output_dir", "workspace", "project_root"):
        paths[key].mkdir(exist_ok=True)
    return paths


def target_cases(paths: dict[str, Path]) -> list[dict[str, object]]:
    return [
        {
            "target": "datanalysis_healthcheck.py",
            "artifacts": {"summary_json": paths["summary"], "manifest_json": paths["manifest"]},
            "expected": {"summary_json", "manifest_json"},
        },
        {
            "target": "inspect_fits.py",
            "artifacts": {"summary_json": paths["summary"], "preview_png": paths["preview_png"]},
            "expected": {"summary_json", "preview_png"},
        },
        {
            "target": "rgb_visual_fits_export.py",
            "artifacts": {"output_fits": paths["fits_visual"], "manifest_json": paths["manifest"], "comparison_png": paths["comparison_png"]},
            "expected": {"fits_visual", "manifest_json", "preview_png"},
            "forbidden": {"unknown"},
        },
        {
            "target": "astrometry_net_workbench.py verify-existing-wcs",
            "artifacts": {
                "summary_json": paths["summary"],
                "report_md": paths["report"],
                "verification_products": {"existing_wcs_quicklook": paths["preview_png"]},
                "generated_outputs": [paths["output_dir"]],
            },
            "expected": {"summary_json", "report_md", "preview_png", "handoff_bundle"},
        },
        {
            "target": "echelle_multispec_inventory.py",
            "artifacts": {
                "summary_json": paths["summary"],
                "output_dir": paths["output_dir"],
                "files_inventory_csv": paths["csv"],
                "orders_inventory_csv": paths["orders_csv"],
                "report_md": paths["report"],
            },
            "expected": {"summary_json", "handoff_bundle", "table_csv", "report_md"},
        },
        {
            "target": "document_intake_workbench.py",
            "artifacts": {
                "summary_json": paths["summary"],
                "manifest_json": paths["manifest"],
                "inventory_csv": paths["csv"],
                "report_md": paths["report"],
                "output_dir": paths["output_dir"],
            },
            "expected": {"summary_json", "manifest_json", "table_csv", "report_md", "handoff_bundle"},
        },
        {
            "target": "presentation_workbench.py inspect",
            "artifacts": {"summary_json": paths["summary"], "preview_pdf": paths["preview_pdf"]},
            "expected": {"summary_json", "preview_pdf"},
        },
        {
            "target": "presentation_workbench.py existing-deck-style-audit",
            "artifacts": {
                "summary_json": paths["summary"],
                "output_dir": paths["output_dir"],
                "style_audit_report": paths["style_report"],
                "scientific_asset_manifest": paths["asset_manifest"],
                "presentation_constraints": paths["metadata"],
                "slide_content": paths["slide_content"],
                "speaker_script": paths["speaker_script"],
                "poster_text": paths["poster_text"],
                "new_slide_templates": paths["templates"],
            },
            "expected": {"summary_json", "handoff_bundle", "report_md", "manifest_json", "metadata_json"},
            "forbidden": {"unknown"},
        },
        {
            "target": "quicklook_bridge.py",
            "artifacts": {"summary_json": paths["summary"], "preview_png": paths["preview_png"], "manifest_json": paths["manifest"]},
            "expected": {"summary_json", "preview_png", "manifest_json"},
        },
        {
            "target": "latex_workbench.py scaffold",
            "artifacts": {"project_root": paths["project_root"], "summary_json": paths["summary"]},
            "expected": {"handoff_bundle", "summary_json"},
            "forbidden": {"unknown"},
        },
        {
            "target": "latex_workbench.py review",
            "artifacts": {"summary_json": paths["summary"], "report_md": paths["report"], "manifest_json": paths["manifest"]},
            "expected": {"summary_json", "report_md", "manifest_json"},
        },
        {
            "target": "semantic_diff.py",
            "artifacts": {"summary_json": paths["summary"], "report_md": paths["report"], "manifest_json": paths["manifest"]},
            "expected": {"summary_json", "report_md", "manifest_json"},
        },
        {
            "target": "notebook_workbench.py execute-copy",
            "artifacts": {
                "executed_copy": paths["notebook"],
                "workspace_dir": paths["workspace"],
                "summary_json": paths["summary"],
                "manifest_json": paths["manifest"],
            },
            "expected": {"notebook_ipynb", "handoff_bundle", "summary_json", "manifest_json"},
        },
    ]


def validate_reference(frozen: set[str]) -> None:
    if not REFERENCE.exists():
        fail(f"missing reference: {REFERENCE}")
    text = REFERENCE.read_text(encoding="utf-8")
    for artifact_type in sorted(frozen):
        if f"`{artifact_type}`" not in text:
            fail(f"reference does not document artifact type: {artifact_type}")
    for target in TARGETS:
        if f"`{target}`" not in text:
            fail(f"reference does not mention target: {target}")
    for alias in PROHIBITED_ALIASES:
        if f"| `{alias}` |" in text:
            fail(f"prohibited alias appears as a table artifact type: {alias}")


def validate_helper_contract(helpers: dict[str, object]) -> set[str]:
    helper_v1_8 = helpers["v1_8"]
    helper_v1_9 = helpers["v1_9"]
    frozen = helpers["frozen"]
    if helper_v1_8 != V1_8_TYPES:
        fail(f"v1.8 artifact types changed unexpectedly: {sorted(helper_v1_8 ^ V1_8_TYPES)}")
    if helper_v1_9 != V1_9_TYPES:
        fail(f"v1.9 added artifact types changed unexpectedly: {sorted(helper_v1_9 ^ V1_9_TYPES)}")
    if frozen != V1_8_TYPES | V1_9_TYPES:
        fail("frozen artifact type set is not v1.8 union v1.9 additions")
    if frozen & PROHIBITED_ALIASES:
        fail(f"prohibited aliases found in frozen types: {sorted(frozen & PROHIBITED_ALIASES)}")
    return frozen


def scan_literal_artifact_types(frozen: set[str]) -> list[dict[str, str]]:
    offenders = []
    pattern = re.compile(r"artifact_type['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")
    for path in (ROOT / "scripts").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.finditer(text):
            literal = match.group(1)
            if literal not in frozen:
                offenders.append({"path": str(path.relative_to(ROOT)), "artifact_type": literal})
    return offenders


def audit_files() -> list[Path]:
    paths: list[Path] = []
    for base in (ROOT / "scripts", ROOT / "references"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix in {".py", ".md", ".txt", ".tex", ".json", ".yaml", ".yml"}:
                paths.append(path)
    for name in ("README.txt", "SKILL.md", "RELEASE-v1.txt"):
        path = ROOT / name
        if path.exists():
            paths.append(path)
    return sorted(set(paths))


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def string_literals(block: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"['\"]([A-Za-z0-9_]+)['\"]", block)]


def scan_all_artifact_type_literals(frozen: set[str]) -> dict[str, object]:
    """Scan scripts, docs, and regressions for frozen artifact type literals."""
    offenders: list[dict[str, object]] = []
    references: list[dict[str, object]] = []
    patterns = [
        ("artifact_type_scalar", re.compile(r"artifact_type['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")),
        ("artifact_type_json_scalar", re.compile(r'\"artifact_type\"\s*:\s*\"([^\"]+)\"')),
        ("artifact_types_list", re.compile(r"(?:artifact_types|preview_artifact_types)['\"]?\s*[:=]\s*\[([^\]]*)\]", re.S)),
        ("artifact_types_json_list", re.compile(r'\"(?:artifact_types|preview_artifact_types)\"\s*:\s*\[([^\]]*)\]', re.S)),
        ("artifact_types_constant", re.compile(r"\bARTIFACT_TYPES\s*=\s*\{([^}]*)\}", re.S)),
    ]
    for path in audit_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(ROOT))
        for kind, pattern in patterns:
            for match in pattern.finditer(text):
                literals = [match.group(1)] if kind.endswith("scalar") else string_literals(match.group(1))
                for literal in literals:
                    if literal in {"artifact_type", "artifact_types", "preview_artifact_types"}:
                        continue
                    record = {
                        "path": rel,
                        "line": line_number(text, match.start()),
                        "kind": kind,
                        "artifact_type": literal,
                    }
                    references.append(record)
                    if literal not in frozen:
                        offenders.append(record)
    return {
        "checked_file_count": len(audit_files()),
        "reference_count": len(references),
        "references": references,
        "offenders": offenders,
    }


def validate_target_cases(typed_artifacts_from_legacy, frozen: set[str], paths: dict[str, Path]) -> list[dict[str, object]]:
    results = []
    for case in target_cases(paths):
        typed = typed_artifacts_from_legacy(case["artifacts"])
        observed = {item.get("artifact_type") for item in typed}
        unknown = sorted({item.get("label") for item in typed if item.get("artifact_type") == "unknown"})
        unexpected = sorted(observed - frozen)
        missing = sorted(set(case["expected"]) - observed)
        forbidden_observed = sorted(set(case.get("forbidden", set())) & observed)
        status = "PASS"
        findings = []
        if unexpected:
            status = "FAIL"
            findings.append(f"Unexpected artifact types: {unexpected}")
        if missing:
            status = "FAIL"
            findings.append(f"Missing expected artifact types: {missing}")
        if forbidden_observed:
            status = "FAIL"
            findings.append(f"Forbidden artifact types observed: {forbidden_observed}")
        results.append(
            {
                "target": case["target"],
                "status": status,
                "observed": sorted(observed),
                "unknown_labels": unknown,
                "typed_count": len(typed),
                "findings": findings,
            }
        )
    return results


def main() -> int:
    helpers = import_helpers()
    frozen = validate_helper_contract(helpers)
    allowed_current = frozen | helpers["v2_0"]
    validate_reference(frozen)
    paths = ensure_fixture_files()
    target_results = validate_target_cases(helpers["typed"], frozen, paths)
    offenders = scan_literal_artifact_types(allowed_current)
    global_scan = scan_all_artifact_type_literals(allowed_current)
    fallback = helpers["typed"]({"unsupported_sidecar": paths["unknown"]})
    fallback_types = {item.get("artifact_type") for item in fallback}

    failures = [item for item in target_results if item["status"] != "PASS"]
    if offenders:
        failures.append({"target": "literal_scan", "status": "FAIL", "findings": offenders})
    if global_scan["offenders"]:
        failures.append({"target": "global_literal_scan", "status": "FAIL", "findings": global_scan["offenders"]})
    if fallback_types != {"unknown"}:
        failures.append({"target": "unknown_fallback", "status": "FAIL", "findings": sorted(fallback_types)})

    summary = {
        "status": "PASS" if not failures else "FAIL",
        "check": "v1.9 artifact type freeze regression",
        "frozen_artifact_types": sorted(frozen),
        "v2_0_additive_artifact_types": sorted(helpers["v2_0"]),
        "target_count": len(target_results),
        "target_status_counts": dict(Counter(item["status"] for item in target_results)),
        "targets": target_results,
        "literal_scan_offenders": offenders,
        "global_literal_scan": {
            "checked_file_count": global_scan["checked_file_count"],
            "reference_count": global_scan["reference_count"],
            "offenders": global_scan["offenders"],
        },
        "unknown_fallback_types": sorted(fallback_types),
    }
    out_path = TMP / "artifact_types_regression.json"
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    debt_out_path = DEBT_TMP / "artifact_types_regression.json"
    debt_out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failures:
        fail(f"{len(failures)} artifact type checks failed; see {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
