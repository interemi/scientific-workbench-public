#!/usr/bin/env python3
"""Inventory MULTISPE/echelle FITS files for legacy coursework."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.legacy_spectroscopy_common import csv_write, parse_multispec_entries, read_header_with_warnings
from _internal.provenance_utils import public_path, standard_tool_payload, write_manifest
from _internal.public_contract import build_blocked_payload, emit_payload_best_effort
from _internal.runtime_common import configure_runtime


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="A MULTISPE FITS file or a directory containing them.")
    parser.add_argument("--output-dir", required=True, help="Directory for CSV/JSON/Markdown inventory products.")
    parser.add_argument("--report-md", action="store_true", help="Also write a short Markdown report.")
    parser.add_argument("--summary-json", help="Optional summary JSON path. Defaults to output-dir/summary.json")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    return parser.parse_args()


def discover_fits(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    fits_suffixes = {".fit", ".fits", ".fts"}
    return sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in fits_suffixes)


def summary_path_from_args(args) -> Path:
    if args.summary_json:
        return Path(args.summary_json).expanduser().resolve()
    return Path(args.output_dir).expanduser().resolve() / "summary.json"


def save_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def blocked_payload(args, message: str) -> dict:
    summary_json = summary_path_from_args(args)
    return build_blocked_payload(
        "echelle_multispec_inventory",
        message,
        notes=[
            message,
            "No MULTISPE inventory was completed and no input FITS file was modified.",
        ],
        artifacts={
            "summary_json": str(summary_json),
            "output_dir": args.output_dir,
            "files_inventory_csv": None,
            "orders_inventory_csv": None,
            "report_md": None,
        },
        results={
            "input": public_path(Path(args.input).expanduser()),
            "error": message,
            "file_count": 0,
            "order_count": 0,
            "files": [],
            "failed_files": [],
        },
        inputs=[Path(args.input).expanduser()],
    )


def emit_blocked(args, message: str) -> int:
    payload = blocked_payload(args, message)
    emit_payload_best_effort(payload, summary_path_from_args(args))
    return 2


def write_report(path: Path, file_rows: list[dict], order_rows: list[dict], notes: list[str]) -> None:
    lines = [
        "# Inventario MULTISPE",
        "",
        f"- Ficheros inventariados: `{len(file_rows)}`",
        f"- Ordenes inventariadas: `{len(order_rows)}`",
        "",
        "## Ficheros",
        "",
    ]
    for row in file_rows:
        lines.append(
            f"- `{row['file_name']}` -> objeto `{row['object_name']}`, ordenes `{row['order_count']}`, lambda global `{row['lambda_min_global']}`--`{row['lambda_max_global']}`, warnings `{row['header_warning_count']}`"
        )
    lines.extend(["", "## Notas", ""])
    lines.extend(f"- {item}" for item in notes)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_inventory(args) -> int:
    ensure_datanalysis_runtime("echelle_multispec_inventory")
    configure_runtime("echelle_multispec_inventory")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"No existe la ruta indicada: {input_path}")

    files = discover_fits(input_path)
    if not files:
        raise SystemExit("No se encontraron FITS para inventariar.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    files_csv = output_dir / "files_inventory.csv"
    orders_csv = output_dir / "orders_inventory.csv"
    summary_json = summary_path_from_args(args)
    report_md = output_dir / "report.md"

    file_rows = []
    order_rows = []
    notes = []
    failed_files = []

    for fits_path in files:
        try:
            header, data_shape, header_warnings = read_header_with_warnings(fits_path)
        except Exception as exc:
            message = f"{fits_path.name}: no se pudo leer como FITS ({type(exc).__name__}: {exc})."
            notes.append(message)
            failed_files.append({"file_name": fits_path.name, "file_path": str(fits_path), "error": message})
            continue
        orders = parse_multispec_entries(header, fallback_pixels=data_shape[-1] if data_shape else None)
        object_name = header.get("OBJECT")
        ctype1 = str(header.get("CTYPE1", ""))
        ctype2 = str(header.get("CTYPE2", ""))
        if "MULTISPE" not in ctype1.upper() and "MULTISPE" not in ctype2.upper():
            notes.append(f"{fits_path.name}: no declara MULTISPE de forma explicita; se inventaria igual por si el header WAT sigue siendo util.")
        if not orders:
            notes.append(f"{fits_path.name}: no se pudieron parsear entradas WAT2 specN.")
        lambda_values = [item["lambda_min"] for item in orders] + [item["lambda_max"] for item in orders]
        file_rows.append(
            {
                "file_name": fits_path.name,
                "file_path": str(fits_path),
                "object_name": object_name,
                "naxis1": data_shape[-1] if data_shape else None,
                "naxis2": data_shape[0] if len(data_shape) >= 2 else None,
                "ctype1": ctype1,
                "ctype2": ctype2,
                "order_count": len(orders),
                "lambda_min_global": round(min(lambda_values), 6) if lambda_values else None,
                "lambda_max_global": round(max(lambda_values), 6) if lambda_values else None,
                "bandid": header.get("BANDID1"),
                "header_warning_count": len(header_warnings),
                "header_warning_excerpt": " | ".join(header_warnings[:3]) if header_warnings else "",
            }
        )
        for order in orders:
            order_rows.append(
                {
                    "file_name": fits_path.name,
                    "file_path": str(fits_path),
                    "object_name": object_name,
                    "aperture_1based": order["aperture_1based"],
                    "aperture_0based": order["aperture_0based"],
                    "spec_index": order["spec_index"],
                    "beam_index": order["beam_index"],
                    "pixels": order["pixels"],
                    "lambda_min": round(order["lambda_min"], 6),
                    "lambda_max": round(order["lambda_max"], 6),
                    "lambda_center": round(order["lambda_center"], 6),
                    "delta_lambda": order["delta_lambda"],
                    "bandid": order["bandid"],
                    "header_warning_count": len(header_warnings),
            }
        )

    if not file_rows:
        message = "No se pudo leer ningun FITS inventariable." if failed_files else "No se encontraron FITS inventariables."
        payload = standard_tool_payload(
            "echelle_multispec_inventory",
            status="blocked",
            notes=notes or [message],
            artifacts={
                "summary_json": str(summary_json),
                "output_dir": str(output_dir),
                "files_inventory_csv": None,
                "orders_inventory_csv": None,
                "report_md": None,
            },
            results={
                "file_count": 0,
                "order_count": 0,
                "files": [],
                "failed_files": failed_files,
            },
            qa={
                "status": "blocked",
                "findings": notes or [message],
                "metrics": {
                    "discovered_file_count": len(files),
                    "readable_file_count": 0,
                    "failed_file_count": len(failed_files),
                    "order_count": 0,
                },
            },
        )
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
        print(rendered)
        save_payload(summary_json, payload)
        return 2

    csv_write(
        files_csv,
        file_rows,
        [
            "file_name",
            "file_path",
            "object_name",
            "naxis1",
            "naxis2",
            "ctype1",
            "ctype2",
            "order_count",
            "lambda_min_global",
            "lambda_max_global",
            "bandid",
            "header_warning_count",
            "header_warning_excerpt",
        ],
    )
    csv_write(
        orders_csv,
        order_rows,
        [
            "file_name",
            "file_path",
            "object_name",
            "aperture_1based",
            "aperture_0based",
            "spec_index",
            "beam_index",
            "pixels",
            "lambda_min",
            "lambda_max",
            "lambda_center",
            "delta_lambda",
            "bandid",
            "header_warning_count",
        ],
    )

    if args.report_md:
        write_report(report_md, file_rows, order_rows, notes)

    status = "ok"
    if failed_files or not order_rows or notes:
        status = "warning"
    qa_findings = list(notes)
    if not order_rows and "No se pudieron inventariar ordenes MULTISPE." not in qa_findings:
        qa_findings.append("No se pudieron inventariar ordenes MULTISPE.")
    payload = standard_tool_payload(
        "echelle_multispec_inventory",
        status=status,
        notes=notes or ["Inventario MULTISPE generado sin tocar los originales."],
        artifacts={
            "summary_json": str(summary_json),
            "output_dir": str(output_dir),
            "files_inventory_csv": str(files_csv),
            "orders_inventory_csv": str(orders_csv),
            "report_md": str(report_md) if args.report_md else None,
        },
        results={
            "file_count": len(file_rows),
            "order_count": len(order_rows),
            "files": file_rows,
            "failed_files": failed_files,
        },
        qa={
            "status": status,
            "findings": qa_findings,
            "metrics": {
                "discovered_file_count": len(files),
                "readable_file_count": len(file_rows),
                "failed_file_count": len(failed_files),
                "order_count": len(order_rows),
            },
        },
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    print(rendered)
    save_payload(summary_json, payload)
    if args.manifest_json:
        outputs = [files_csv, orders_csv, summary_json]
        if args.report_md:
            outputs.append(report_md)
        write_manifest(
            args.manifest_json,
            inputs=files,
            outputs=outputs,
            parameters={"tool": "echelle_multispec_inventory", "report_md": bool(args.report_md)},
            command=" ".join(sys.argv),
            notes=notes,
        )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_inventory(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_blocked(args, str(exc) or "Inventario MULTISPE bloqueado.")
    except Exception as exc:
        return emit_blocked(args, f"Inventario MULTISPE bloqueado: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
