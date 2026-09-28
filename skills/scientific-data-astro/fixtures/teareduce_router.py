#!/usr/bin/env python3
"""Route TEAREDUCE-specific requests to an optional external notebook workflow."""

import argparse
import sys
import unicodedata
from pathlib import Path

from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path


TEAREDUCE_RULES = [
    ("cosmic rays", ["cosmic ray", "cosmic rays", "rayos cosmicos", "cr2images", "cleanest"], "teareduce"),
    ("wavelength calibration", ["wavelength calibration", "calibracion de longitud de onda", "wavecal", "tea wave", "cdistortion", "c distortion", "arcs", "arcos"], "teareduce"),
    ("spectral slicing", ["slice", "slicing", "recorte", "traza", "trace", "slit"], "teareduce"),
    ("spectroscopic cleanup", ["crmedian", "skysub", "sky subtraction", "sustraccion del cielo", "pincushion", "distortion"], "teareduce"),
    ("calibration-frame workflows", ["master bias", "master flat", "flat field", "bias correction", "imagefilecollection"], "teareduce"),
    ("teareduce notebook", ["teareduce", "practica 2", "practica 3", "cookbook"], "teareduce"),
]

LEGACY_NATIVE_RULES = [
    (
        "legacy spectroscopy coursework",
        [
            "iraf",
            "fxcor",
            "mkiraf",
            "xgterm",
            "multispe",
            "echelle legacy",
            "legacy spectroscopy",
            "legacy spectroscopic",
            "sb2",
            "v sin i",
            "vsini",
            "istarmod",
            "practica universitaria de espectroscopia",
        ],
        "native",
    ),
]

NATIVE_RULES = [
    ("tables and SQL", ["duckdb", "sql", "crossmatch", "cross-match", "catalog", "csv", "parquet"], "native"),
    ("documents", ["latex", "overleaf", "docx", "pdf", "pages", "numbers", "keynote", "pptx"], "native"),
    ("general reporting", ["report", "proposal", "deliverable", "template"], "native"),
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", default="", help="Free-form task description.")
    parser.add_argument("inputs", nargs="*", help="Optional file inputs to help route the task.")
    parser.add_argument("--summary-json", help="Optional JSON output path.")
    return parser.parse_args()


def normalize_text(value):
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def keyword_matches(keywords, text):
    return [keyword for keyword in keywords if normalize_text(keyword) in text]


def validate_summary_path(summary_json):
    if not summary_json:
        return None
    path = Path(summary_json)
    if path.exists() and not path.is_file():
        return f"--summary-json must point to a file path, not a directory: {public_path(path)}"
    parent = path.parent
    while parent and not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if parent.exists() and not parent.is_dir():
        return f"--summary-json parent is not a directory: {public_path(parent)}"
    return None


def classify(intent, inputs):
    text = normalize_text(intent)
    legacy_hits = []
    teareduce_hits = []
    native_hits = []
    findings = []
    suggested_entrypoint = "native"
    for label, keywords, backend in LEGACY_NATIVE_RULES:
        matches = keyword_matches(keywords, text)
        if matches:
            legacy_hits.append({"label": label, "matches": matches, "backend": backend})
    for label, keywords, backend in TEAREDUCE_RULES:
        matches = keyword_matches(keywords, text)
        if matches:
            teareduce_hits.append({"label": label, "matches": matches, "backend": backend})
    for label, keywords, backend in NATIVE_RULES:
        matches = keyword_matches(keywords, text)
        if matches:
            native_hits.append({"label": label, "matches": matches, "backend": backend})
    for raw in inputs:
        path = Path(raw)
        suffix = normalize_text(path.suffix)
        name = normalize_text(path.name)
        is_misnamed_notebook = name.endswith(".ipynb.txt")
        path_text = normalize_text(path)
        if suffix == ".sm" or name == "fwhm_vsini_datafit.csv" or "istarmod" in path_text or "fits_p1" in path_text:
            legacy_hits.append({"label": "legacy spectroscopy input", "matches": [path.name], "backend": "native"})
        if (suffix == ".ipynb" or is_misnamed_notebook) and (
            name.startswith("p2_")
            or name.startswith("p3_")
            or "teareduce" in path_text
            or "notebooks 24:25" in path_text
            or "notebooks jupyter clase" in path_text
        ):
            teareduce_hits.append({"label": "teareduce notebook input", "matches": [path.name], "backend": "teareduce"})
        if suffix in {".fits", ".fit", ".fts"} and ("tea_procesado" in path_text or "arc" in name):
            teareduce_hits.append({"label": "teareduce-style FITS input", "matches": [path.name], "backend": "teareduce"})
        if suffix in {".csv", ".jsonl", ".parquet", ".docx", ".pdf", ".tex"}:
            native_hits.append({"label": "native-first file family", "matches": [path.name], "backend": "native"})
        if suffix in {".fits", ".fit", ".fts"} and ("foces" in name or "n3.fits" in name or "n2.fits" in name):
            native_hits.append({"label": "legacy FITS family", "matches": [path.name], "backend": "native"})
    legacy_score = len(legacy_hits)
    teareduce_score = len(teareduce_hits)
    native_score = len(native_hits)
    explicit_teareduce = "teareduce" in text
    route_status = "ok"
    if legacy_score > 0 and explicit_teareduce and teareduce_score > 0:
        backend = "teareduce"
        route_status = "warning"
        suggested_entrypoint = "scripts/teareduce_healthcheck.py"
        findings.append(
            "The user explicitly requested TEAREDUCE, but legacy spectroscopy signals were also detected; keep IRAF/fxcor/MULTISPE/iSTARMOD steps on the native legacy route unless TEAREDUCE is intentionally scoped to preprocessing."
        )
        notes = [
            "TEAREDUCE is an external optional route because the user explicitly named it; availability and execution are not yet verified.",
            "Legacy spectroscopy indicators are present, so confirm that only TEAREDUCE-suitable preprocessing is being routed there.",
            "Keep downstream legacy coursework analysis on the native route when IRAF/fxcor/MULTISPE/iSTARMOD are involved.",
        ]
        confidence = min(0.85, 0.62 + 0.05 * teareduce_score)
    elif legacy_score > 0:
        backend = "native"
        suggested_entrypoint = "references/legacy-spectroscopy-coursework-macos.md"
        notes = [
            "This request looks like legacy spectroscopy coursework on macOS (IRAF/fxcor/MULTISPE/iSTARMOD).",
            "Do not route to TEAREDUCE by default for this family unless the user explicitly asks for it.",
            "Prefer the native legacy route: envcheck -> MULTISPE inventory -> fxcor bridge -> RV/v sin i analysis -> iSTARMOD copy -> Spanish report scaffold.",
        ]
        confidence = min(0.99, 0.9 + 0.02 * legacy_score)
    elif teareduce_score > native_score and teareduce_score > 0:
        backend = "teareduce"
        route_status = "warning"
        suggested_entrypoint = "scripts/teareduce_healthcheck.py"
        findings.append("TEAREDUCE is user-installed and external; metadata discovery does not verify its API or a notebook run.")
        notes = [
            "Consider the external TEAREDUCE route only because the request looks TEAREDUCE-specific or notebook-specific.",
            "Inspect the package and notebook first; execute only trusted notebook code in a copied workspace.",
            "Keep the native skill stack for reporting, packaging, and non-TEAREDUCE analysis steps.",
        ]
        confidence = min(0.95, 0.55 + 0.1 * abs(teareduce_score - native_score))
    else:
        backend = "native"
        notes = [
            "The native skill stack is preferred when the task is not explicitly TEAREDUCE-specific.",
            "TEAREDUCE can be used separately when the user installs it and runs a trusted notebook copy; this routing result does not verify that setup.",
        ]
        confidence = min(0.95, 0.55 + 0.1 * abs(teareduce_score - native_score))
        if legacy_score == 0 and teareduce_score == 0 and native_score == 0:
            route_status = "warning"
            findings.append("No routing signals were detected; defaulted to the native stack with low confidence.")
    return {
        "recommended_backend": backend,
        "route_status": route_status,
        "confidence": round(confidence, 2),
        "intent": intent,
        "inputs": [str(Path(item).resolve()) if Path(item).exists() else item for item in inputs],
        "signals": {"legacy_native": legacy_hits, "teareduce": teareduce_hits, "native": native_hits},
        "warning_findings": findings,
        "suggested_entrypoint": suggested_entrypoint,
        "supporting_scripts": [
            "scripts/teareduce_healthcheck.py",
            "scripts/teareduce_notebook_runner.py",
        ]
        if backend == "teareduce"
        else [
            "scripts/legacy_spectroscopy_envcheck.py",
            "scripts/echelle_multispec_inventory.py",
            "scripts/fxcor_iraf_workbench.py",
            "scripts/legacy_rv_coursework_workbench.py",
            "scripts/istarmod_workbench.py",
            "scripts/legacy_spectroscopy_report_builder.py",
        ],
        "notes": notes,
    }


def main():
    args = parse_args()
    summary_error = validate_summary_path(args.summary_json)
    legacy_payload = classify(args.intent, args.inputs)
    route_status = "blocked" if summary_error else legacy_payload["route_status"]
    findings = list(legacy_payload["warning_findings"])
    if summary_error:
        findings.append(summary_error)
    payload = build_tool_payload(
        "teareduce_router",
        status=route_status,
        notes=legacy_payload["notes"],
        artifacts={"summary_json": args.summary_json},
        results=legacy_payload,
        qa={
            "status": route_status,
            "findings": findings,
            "metrics": {
                "confidence": legacy_payload["confidence"],
                "legacy_signal_count": len(legacy_payload["signals"]["legacy_native"]),
                "teareduce_signal_count": len(legacy_payload["signals"]["teareduce"]),
                "native_signal_count": len(legacy_payload["signals"]["native"]),
            },
        },
        legacy=legacy_payload,
    )
    if summary_error:
        emit_payload(payload)
        return 2
    emit_payload(payload, args.summary_json)
    if args.summary_json:
        print(f"Saved summary: {public_path(args.summary_json)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
