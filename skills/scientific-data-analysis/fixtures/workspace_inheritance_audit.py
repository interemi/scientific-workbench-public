#!/usr/bin/env python3
"""Audit a previous coursework workspace before inheriting material into a new iteration."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest
from _internal.runtime_common import configure_runtime


FIELDNAMES = ["relative_path", "category", "inheritance_recommendation", "reason", "size_bytes"]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Previous CODEX or derived workspace to audit.")
    parser.add_argument("--output-csv")
    parser.add_argument("--report-md")
    parser.add_argument("--summary-json")
    parser.add_argument("--manifest-json")
    return parser.parse_args()


def classify_path(root: Path, path: Path) -> tuple[str, str, str]:
    rel = path.relative_to(root)
    rel_text = rel.as_posix().lower()
    name = path.name.lower()

    if any(part in {"__pycache__", ".git"} for part in rel.parts):
        return "obsolete_or_risky", "leave_behind", "cache_or_repo_metadata"
    if name in {".ds_store", "rvvalues.dat"}:
        return "obsolete_or_risky", "leave_behind", "persistent_cache_or_os_artifact"
    if any(token in rel_text for token in ["logs/", "/logs", "rvvalues_archive", "p_est_frias/res", "compile_final/"]):
        return "obsolete_or_risky", "leave_behind", "generated_runtime_or_compile_cache"
    if path.suffix.lower() in {".log", ".aux", ".fdb_latexmk", ".fls", ".out", ".toc", ".synctex.gz"}:
        return "obsolete_or_risky", "leave_behind", "latex_or_runtime_auxiliary"
    if any(token in rel_text for token in ["run_auto", "parsed/", "/parsed", "manual_overrides", "debug", "tmp", "smoke", "ccf", "first_pass", "provisional", "legacy_safe"]):
        return "provisional_output", "review_before_copy", "intermediate_or_diagnostic_output"
    if path.suffix.lower() in {".cl", ".txtonly"}:
        return "provisional_output", "review_before_copy", "legacy_execution_trace"
    if any(token in rel_text for token in ["fits_p1", "fwhm_vsini", "lambdas.dat"]) or path.suffix.lower() in {".fits", ".fit", ".fts", ".sm"}:
        return "stable_input", "safe_to_copy", "source_or_reference_input"
    if path.suffix.lower() in {".pdf", ".csv", ".ecsv", ".json", ".md", ".tex", ".png", ".jpg", ".jpeg"}:
        return "revisable_material", "copy_after_review", "derived_material_that_may_be_useful"
    return "revisable_material", "copy_after_review", "unclassified_file_review_manually"


def audit_workspace(root: Path) -> list[dict]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        category, recommendation, reason = classify_path(root, path)
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = None
        rows.append(
            {
                "relative_path": relpath_for_csv(root, path),
                "category": category,
                "inheritance_recommendation": recommendation,
                "reason": reason,
                "size_bytes": size_bytes,
            }
        )
    return rows


def relpath_for_csv(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in FIELDNAMES})


def write_report(path: Path, root: Path, rows: list[dict], counts: Counter) -> None:
    lines = [
        "# Workspace Inheritance Audit",
        "",
        f"- Workspace auditado: `{public_path(root)}`",
        f"- Ficheros evaluados: `{len(rows)}`",
        f"- stable_input: `{counts.get('stable_input', 0)}`",
        f"- revisable_material: `{counts.get('revisable_material', 0)}`",
        f"- provisional_output: `{counts.get('provisional_output', 0)}`",
        f"- obsolete_or_risky: `{counts.get('obsolete_or_risky', 0)}`",
        "",
        "## Recomendacion rapida",
        "",
        "- Copia sin miedo solo lo marcado como `stable_input`.",
        "- Revisa antes de arrastrar lo marcado como `revisable_material`.",
        "- No promociones sin revisar lo marcado como `provisional_output`.",
        "- Deja fuera lo marcado como `obsolete_or_risky` salvo necesidad muy justificada.",
        "",
    ]
    risky = [row for row in rows if row["category"] in {"provisional_output", "obsolete_or_risky"}][:20]
    if risky:
        lines.append("## Ficheros a mirar primero")
        lines.append("")
        for row in risky:
            lines.append(
                f"- `{row['relative_path']}` -> {row['category']} / {row['inheritance_recommendation']} / {row['reason']}"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    configure_runtime("workspace_inheritance_audit")
    root = Path(args.workspace).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"No existe la ruta indicada: {root}")
    if not root.is_dir():
        raise SystemExit("La ruta indicada no es un directorio.")

    rows = audit_workspace(root)
    if not rows:
        raise SystemExit("No se detectaron ficheros dentro del workspace a auditar.")

    counts = Counter(row["category"] for row in rows)
    status = "warning" if counts.get("provisional_output", 0) or counts.get("obsolete_or_risky", 0) else "ok"
    notes = [
        "Esta auditoria es deliberadamente estrecha y basada en rutas/nombres; no sustituye una revision cientifica del contenido.",
        "Su objetivo es evitar que outputs provisionales, caches o auxiliares pasen a una nueva iteracion como si fueran verdad estable.",
    ]

    output_csv = None
    if args.output_csv:
        output_csv = Path(args.output_csv).expanduser().resolve()
        write_csv(output_csv, rows)
    report_md = None
    if args.report_md:
        report_md = Path(args.report_md).expanduser().resolve()
        write_report(report_md, root, rows, counts)

    findings = [
        {"relative_path": row["relative_path"], "category": row["category"], "reason": row["reason"]}
        for row in rows
        if row["category"] in {"provisional_output", "obsolete_or_risky"}
    ]
    payload = standard_tool_payload(
        "workspace_inheritance_audit",
        status=status,
        notes=notes,
        artifacts={"output_csv": str(output_csv) if output_csv else None, "report_md": str(report_md) if report_md else None},
        results={
            "workspace_root": public_path(root),
            "counts_by_category": dict(counts),
            "rows": rows,
        },
        qa={
            "status": status,
            "findings": findings,
            "metrics": {
                "file_count": len(rows),
                "provisional_count": counts.get("provisional_output", 0),
                "obsolete_or_risky_count": counts.get("obsolete_or_risky", 0),
            },
        },
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        summary_path = Path(args.summary_json).expanduser().resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered + "\n", encoding="utf-8")
    if args.manifest_json:
        outputs = []
        if output_csv:
            outputs.append(output_csv)
        if report_md:
            outputs.append(report_md)
        if args.summary_json:
            outputs.append(Path(args.summary_json).expanduser().resolve())
        write_manifest(
            args.manifest_json,
            inputs=[root],
            outputs=outputs,
            parameters={"tool": "workspace_inheritance_audit"},
            command=" ".join(sys.argv),
            notes=notes,
        )


if __name__ == "__main__":
    main()
