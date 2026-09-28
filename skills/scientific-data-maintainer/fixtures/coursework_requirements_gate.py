#!/usr/bin/env python3
"""Gate literal coursework requirements so critical blocks cannot close as merely diagnostic."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest
from _internal.runtime_common import configure_runtime


FIELDNAMES = [
    "requirement_id",
    "block",
    "priority",
    "requirement",
    "expected_evidence",
    "evidence_path",
    "measurement_state",
    "adoption_state",
    "physical_robustness",
    "ready_for_report",
    "status",
    "notes",
]

NON_CLOSING_ADOPTION_STATES = {
    "",
    "diagnostic",
    "not_adopted",
    "measured_not_adopted",
    "not_measured",
    "pending",
}
NON_CLOSING_MEASUREMENT_STATES = {"", "missing", "not_measured", "pending"}
APPLICABLE_PRIORITIES = {"critical", "supporting", "optional"}
IGNORED_STATUSES = {"na", "n/a", "not_applicable", "skip", "skipped"}
CLOSED_STATUSES = {"closed", "complete", "ok", "ready"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", help="Create a template CSV for literal coursework requirements.")
    template.add_argument("--profile", choices=["legacy-spectroscopy-coursework", "generic"], default="legacy-spectroscopy-coursework")
    template.add_argument("--output-csv", required=True)
    template.add_argument("--summary-json")
    template.add_argument("--manifest-json")

    evaluate = sub.add_parser("evaluate", help="Evaluate a requirements CSV and block incomplete critical rows.")
    evaluate.add_argument("requirements_csv")
    evaluate.add_argument("--output-csv", help="Optional normalized copy of the evaluated table.")
    evaluate.add_argument("--report-md", help="Optional Markdown report path.")
    evaluate.add_argument("--summary-json", help="Optional JSON summary path.")
    evaluate.add_argument("--manifest-json")
    return parser.parse_args()


def profile_rows(profile: str) -> list[dict]:
    if profile == "generic":
        rows = [
            {
                "requirement_id": "critical_measurement_1",
                "block": "resultados",
                "priority": "critical",
                "requirement": "Sustituye esta fila por la medida literal no negociable pedida por el guion.",
                "expected_evidence": "tabla final + figura o log asociado",
                "notes": "Duplica o borra filas segun el guion concreto.",
            },
            {
                "requirement_id": "supporting_context_1",
                "block": "discusion",
                "priority": "supporting",
                "requirement": "Sustituye esta fila por un bloque de apoyo o comparacion externa.",
                "expected_evidence": "parrafo final o tabla comparativa",
                "notes": "Puede quedar como optional o not_applicable si no procede.",
            },
        ]
    else:
        rows = [
            {
                "requirement_id": "rv_single_primary",
                "block": "velocidad_radial",
                "priority": "critical",
                "requirement": "Cerrar la velocidad radial de la estrella simple con ordenes, media y error final.",
                "expected_evidence": "tabla por orden + resumen RV final",
                "notes": "No marcar como cerrado si solo existe una pasada automatica sin adopcion final.",
            },
            {
                "requirement_id": "rv_sb2_component_a",
                "block": "velocidad_radial",
                "priority": "critical",
                "requirement": "Cerrar la componente A de la SB2 con seleccion de ordenes y media final.",
                "expected_evidence": "tabla por orden + seleccion/rechazo + resumen SB2",
                "notes": "Si sigue diagnosticada o medida_no_adoptada, debe bloquear el cierre.",
            },
            {
                "requirement_id": "rv_sb2_component_b",
                "block": "velocidad_radial",
                "priority": "critical",
                "requirement": "Cerrar la componente B de la SB2 con seleccion de ordenes y media final.",
                "expected_evidence": "tabla por orden + seleccion/rechazo + resumen SB2",
                "notes": "No marcar ready_for_report hasta adoptar un valor final defendible.",
            },
            {
                "requirement_id": "vsini_primary_pass",
                "block": "velocidad_rotacion",
                "priority": "supporting",
                "requirement": "Documentar v sin i y dejar claro si es adoptado o solo primera pasada.",
                "expected_evidence": "tabla v sin i + calibracion o comparacion externa",
                "notes": "Puede cerrarse con cautela si el propio texto limita su fuerza.",
            },
            {
                "requirement_id": "chromosphere_caii_hk",
                "block": "actividad_cromosferica",
                "priority": "critical",
                "requirement": "Medir y reportar Ca II H&K para las estrellas problema si el guion lo exige.",
                "expected_evidence": "tabla final de EW + figura o salida iSTARMOD",
                "notes": "No dejarlo en observacion parcial o solo PW And si el guion pide ambas estrellas.",
            },
            {
                "requirement_id": "chromosphere_halpha",
                "block": "actividad_cromosferica",
                "priority": "critical",
                "requirement": "Medir y reportar Halpha para las estrellas problema segun el guion.",
                "expected_evidence": "tabla final de EW + figura o salida iSTARMOD",
                "notes": "",
            },
            {
                "requirement_id": "chromosphere_caii_irt",
                "block": "actividad_cromosferica",
                "priority": "critical",
                "requirement": "Medir y reportar Ca II IRT para las estrellas problema segun el guion.",
                "expected_evidence": "tabla final de EW + figura o salida iSTARMOD",
                "notes": "",
            },
            {
                "requirement_id": "li_6708",
                "block": "litio",
                "priority": "critical",
                "requirement": "Medir y discutir la anchura equivalente de Li I 6707.8 A cuando el guion lo pide.",
                "expected_evidence": "tabla EW Li + figura + comparacion con literatura",
                "notes": "",
            },
        ]

    normalized = []
    for row in rows:
        normalized.append({field: row.get(field, "") for field in FIELDNAMES})
    return normalized


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in FIELDNAMES})


def parse_bool(token: str | None) -> bool | None:
    if token is None:
        return None
    text = str(token).strip().lower()
    if text in {"1", "true", "yes", "y", "si", "s"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [normalize_row(row) for row in csv.DictReader(handle)]


def normalize_row(row: dict) -> dict:
    normalized = {field: str(row.get(field, "") or "").strip() for field in FIELDNAMES}
    normalized["priority"] = normalized["priority"].lower()
    normalized["measurement_state"] = normalized["measurement_state"].lower()
    normalized["adoption_state"] = normalized["adoption_state"].lower()
    normalized["physical_robustness"] = normalized["physical_robustness"].lower()
    normalized["status"] = normalized["status"].lower()
    return normalized


def classify_row(row: dict) -> tuple[str, list[str], str | None]:
    reasons: list[str] = []
    ready_flag = parse_bool(row.get("ready_for_report"))
    evidence_path = row.get("evidence_path", "")
    evidence_exists = None
    if evidence_path:
        evidence_exists = Path(evidence_path).expanduser().exists()
        if not evidence_exists:
            reasons.append("evidence_missing")
    measurement_state = row.get("measurement_state", "")
    adoption_state = row.get("adoption_state", "")
    manual_status = row.get("status", "")
    priority = row.get("priority", "")

    if manual_status in IGNORED_STATUSES or priority not in APPLICABLE_PRIORITIES:
        return "not_applicable", reasons, public_path(evidence_path) if evidence_path else None

    if manual_status in CLOSED_STATUSES:
        if ready_flag is False:
            reasons.append("ready_for_report_false")
            return "diagnostic", reasons, public_path(evidence_path) if evidence_path else None
        if evidence_path and evidence_exists is False:
            return "diagnostic", reasons, public_path(evidence_path)
        return "closed", reasons, public_path(evidence_path) if evidence_path else None

    if measurement_state in NON_CLOSING_MEASUREMENT_STATES and not evidence_path:
        reasons.append("missing_measurement")
        return "missing", reasons, None

    if adoption_state in NON_CLOSING_ADOPTION_STATES:
        reasons.append("adoption_not_closed")
        return "diagnostic", reasons, public_path(evidence_path) if evidence_path else None

    if ready_flag is False:
        reasons.append("ready_for_report_false")
        return "diagnostic", reasons, public_path(evidence_path) if evidence_path else None

    if evidence_path and evidence_exists is False:
        return "diagnostic", reasons, public_path(evidence_path)

    if measurement_state and adoption_state:
        return "closed", reasons, public_path(evidence_path) if evidence_path else None

    reasons.append("insufficient_fields")
    return "missing", reasons, public_path(evidence_path) if evidence_path else None


def evaluate_rows(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    evaluated = []
    blocking = []
    warnings = []
    for row in rows:
        derived_status, reasons, public_evidence = classify_row(row)
        evaluated_row = dict(row)
        evaluated_row["status"] = derived_status
        evaluated_row["evidence_path"] = public_evidence or row.get("evidence_path", "")
        evaluated_row["_reasons"] = reasons
        evaluated.append(evaluated_row)

        if derived_status == "not_applicable":
            continue
        finding = {
            "requirement_id": row.get("requirement_id"),
            "block": row.get("block"),
            "priority": row.get("priority"),
            "requirement": row.get("requirement"),
            "status": derived_status,
            "reasons": reasons,
            "evidence_path": public_evidence,
        }
        if row.get("priority") == "critical" and derived_status != "closed":
            blocking.append(finding)
        elif derived_status != "closed":
            warnings.append(finding)
    return evaluated, blocking, warnings


def write_report(path: Path, evaluated: list[dict], blocking: list[dict], warnings: list[dict]) -> None:
    lines = [
        "# Coursework Requirements Gate",
        "",
        f"- Requisitos evaluados: `{len(evaluated)}`",
        f"- Bloqueantes: `{len(blocking)}`",
        f"- Avisos: `{len(warnings)}`",
        "",
    ]
    if blocking:
        lines.append("## Bloqueantes")
        lines.append("")
        for item in blocking:
            lines.append(
                f"- `{item['requirement_id']}` ({item['block']}): {item['status']} :: {', '.join(item['reasons']) or 'sin detalle'}"
            )
        lines.append("")
    if warnings:
        lines.append("## Avisos")
        lines.append("")
        for item in warnings:
            lines.append(
                f"- `{item['requirement_id']}` ({item['block']}): {item['status']} :: {', '.join(item['reasons']) or 'sin detalle'}"
            )
        lines.append("")
    lines.append("## Tabla resumida")
    lines.append("")
    lines.append("| requirement_id | prioridad | estado | ready_for_report |")
    lines.append("| --- | --- | --- | --- |")
    for row in evaluated:
        lines.append(
            f"| {row.get('requirement_id','')} | {row.get('priority','')} | {row.get('status','')} | {row.get('ready_for_report','')} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_template(args) -> None:
    configure_runtime("coursework_requirements_gate_template")
    rows = profile_rows(args.profile)
    output_csv = Path(args.output_csv).expanduser().resolve()
    write_csv(output_csv, rows)
    notes = [
        "La plantilla fuerza a declarar evidencia, estados de adopcion y si cada bloque esta listo para pasar al informe.",
        "Borra o marca como not_applicable las filas que no correspondan al guion concreto.",
    ]
    payload = standard_tool_payload(
        "coursework_requirements_gate.template",
        status="ok",
        notes=notes,
        artifacts={"requirements_csv": str(output_csv)},
        results={"profile": args.profile, "row_count": len(rows), "fieldnames": FIELDNAMES},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    if args.summary_json:
        summary_path = Path(args.summary_json).expanduser().resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered + "\n", encoding="utf-8")
    if args.manifest_json:
        outputs = [output_csv]
        if args.summary_json:
            outputs.append(Path(args.summary_json).expanduser().resolve())
        write_manifest(
            args.manifest_json,
            outputs=outputs,
            parameters={"tool": "coursework_requirements_gate.template", "profile": args.profile},
            command=" ".join(sys.argv),
            notes=notes,
        )


def cmd_evaluate(args) -> None:
    configure_runtime("coursework_requirements_gate_evaluate")
    requirements_csv = Path(args.requirements_csv).expanduser().resolve()
    if not requirements_csv.exists():
        raise SystemExit(f"No existe el CSV de requisitos: {requirements_csv}")
    rows = load_rows(requirements_csv)
    if not rows:
        raise SystemExit("El CSV de requisitos esta vacio.")

    evaluated, blocking, warnings = evaluate_rows(rows)
    counts = Counter(row["status"] for row in evaluated)
    status = "blocked" if blocking else "warning" if warnings else "ok"
    notes = [
        "Los bloques critical no deben pasar a conclusiones si quedan como diagnostic, missing o measured_not_adopted.",
        "Este gate no sustituye el juicio cientifico; solo obliga a declarar evidencia y estados de cierre.",
    ]

    output_csv = None
    if args.output_csv:
        output_csv = Path(args.output_csv).expanduser().resolve()
        write_csv(output_csv, [{key: row.get(key, "") for key in FIELDNAMES} for row in evaluated])
    report_md = None
    if args.report_md:
        report_md = Path(args.report_md).expanduser().resolve()
        write_report(report_md, evaluated, blocking, warnings)

    payload = standard_tool_payload(
        "coursework_requirements_gate.evaluate",
        status=status,
        notes=notes,
        artifacts={
            "requirements_csv": str(output_csv) if output_csv else str(requirements_csv),
            "report_md": str(report_md) if report_md else None,
        },
        results={
            "blocking_findings": blocking,
            "warning_findings": warnings,
            "closure_table": [{key: row.get(key, "") for key in FIELDNAMES} for row in evaluated],
            "counts_by_status": dict(counts),
        },
        qa={
            "status": status,
            "findings": blocking + warnings,
            "metrics": {
                "row_count": len(evaluated),
                "blocking_count": len(blocking),
                "warning_count": len(warnings),
                "closed_count": counts.get("closed", 0),
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
            inputs=[requirements_csv],
            outputs=outputs,
            parameters={"tool": "coursework_requirements_gate.evaluate"},
            command=" ".join(sys.argv),
            notes=notes,
        )


def main():
    args = parse_args()
    if args.command == "template":
        cmd_template(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)


if __name__ == "__main__":
    main()
