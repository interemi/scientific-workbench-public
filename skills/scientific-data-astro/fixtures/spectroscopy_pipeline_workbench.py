#!/usr/bin/env python3
"""Run a reproducible 2D spectroscopy workflow with reduction, extraction, calibration, and reporting."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import environment_summary, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.runtime_common import configure_runtime


TOOL_NAME = "spectroscopy_pipeline_workbench"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("science", nargs="+", help="2D science FITS frame(s) to reduce and extract.")
    parser.add_argument("--bias", action="append", default=[], help="Bias frame. Repeat as needed.")
    parser.add_argument("--dark", action="append", default=[], help="Dark frame. Repeat as needed.")
    parser.add_argument("--flat", action="append", default=[], help="Flat frame. Repeat as needed.")
    parser.add_argument("--arc", action="append", default=[], help="Optional arc/lamp frame. Repeat as needed.")
    parser.add_argument("--master-bias", help="Existing master bias FITS.")
    parser.add_argument("--master-dark", help="Existing master dark FITS.")
    parser.add_argument("--master-flat", help="Existing master flat FITS.")
    parser.add_argument("--calibration-table", help="Optional pixel-to-wavelength table for spectral_workbench.")
    parser.add_argument("--combine-method", choices=["median", "mean"], default="median")
    parser.add_argument("--scale-dark", action="store_true", help="Scale dark by exposure ratio in the calibration stage.")
    parser.add_argument("--spatial-half-width", type=int, default=3, help="Half-width for trace extraction.")
    parser.add_argument("--background-inner-half-width", type=int, default=5, help="Inner half-width for local background.")
    parser.add_argument("--background-outer-half-width", type=int, default=10, help="Outer half-width for local background.")
    parser.add_argument("--trace-degree", type=int, default=2, help="Polynomial degree for the traced center.")
    parser.add_argument("--optimal-extraction", action="store_true", help="Use weighted extraction in spectral_workbench.")
    parser.add_argument("--order-count", type=int, default=1, help="Number of candidate orders to inspect.")
    parser.add_argument("--order-index", type=int, default=0, help="Primary order index to export.")
    parser.add_argument("--line-window", nargs=2, type=float, metavar=("CENTER", "WIDTH"), help="Optional local line fit window.")
    parser.add_argument("--normalize", action="store_true", help="Normalize the extracted spectrum before plots and exports.")
    parser.add_argument("--output-dir", required=True, help="Directory for calibration products, extracted spectra, and reports.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def run_command(cmd: list[str], cwd: Path | None = None) -> dict:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def file_version(path: Path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return (info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)


def read_summary(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def extraction_evidence(payload, returncode, has_spectrum):
    result = payload.get("results") or payload
    findings = (payload.get("qa") or {}).get("findings") or []
    if returncode == 0 and payload.get("status") in {None, "ok", "warning"} and result.get("count") and has_spectrum:
        return ("warning" if payload.get("status") == "warning" or findings else "ok"), result, findings, None
    if result.get("blocked_reason"):
        return "blocked", {}, findings, result["blocked_reason"]
    reason = (
        "Extraction did not produce both a readable summary and a spectrum table."
        if returncode == 0
        else f"Extraction ended with exit code {returncode}. See the recorded process output."
    )
    return "fail", {}, findings, reason


def format_number(value, digits=6):
    return f"{value:.{digits}g}" if isinstance(value, (int, float)) and math.isfinite(value) else "unavailable"


def format_measurement(value, unit, uncertainty):
    central = format_number(value, digits=10)
    formal = format_number(uncertainty, digits=3)
    unit_text = unit or "(axis unit unspecified)"
    if formal == "unavailable":
        return f"{central} {unit_text} (uncertainty unavailable)"
    if central != "unavailable" and uncertainty > 0:
        decimals = 2 - math.floor(math.log10(uncertainty))
        if 0 <= decimals <= 10:
            return f"{value:.{decimals}f} ± {uncertainty:.{decimals}f} {unit_text}"
    return f"{central} ± {formal} {unit_text}"


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def write_report(path: Path, summary: dict):
    lines = [
        "# Spectroscopy Pipeline Report",
        "",
        f"- Science frames: `{summary['science_count']}`",
        f"- Batch status: `{summary['batch_status']}`",
        f"- Completed: `{summary['completed_science_count']}`",
        f"- Blocked: `{summary['blocked_science_count']}`",
        f"- Failed: `{summary['failed_science_count']}`",
        f"- Skipped: `{summary['skipped_science_count']}`",
        f"- Arc frames: `{summary['arc_count']}`",
        f"- Reduced science frames: `{summary['reduced_science_count']}`",
        f"- Calibration table supplied: `{summary['calibration_table'] is not None}`",
        f"- Optimal extraction: `{summary['settings']['optimal_extraction']}`",
        f"- Order count requested: `{summary['settings']['order_count']}`",
        "",
        "## Calibration Stage",
        "",
        f"- Reduction step executed: `{summary['calibration']['executed']}`",
        f"- Bias inputs: `{summary['calibration']['bias_count']}`",
        f"- Dark inputs: `{summary['calibration']['dark_count']}`",
        f"- Flat inputs: `{summary['calibration']['flat_count']}`",
        f"- Reduction return code: `{summary['calibration']['returncode']}`",
        "",
    ]
    if summary["calibration"]["failure_reason"]:
        lines.extend([f"- {summary['calibration']['failure_reason']}", ""])
    lines.extend(["## Extracted Products", ""])
    for item in summary["science_products"]:
        lines.extend(
            [
                f"### `{item['input_name']}`",
                "",
                f"- Working frame: `{item['working_path']}`",
                f"- Extraction return code: `{item['returncode']}`",
                f"- Frame status: `{item['status']}`",
            ]
        )
        if item["failure_reason"]:
            lines.append(f"- {item['failure_reason']}")
        else:
            unit = item["axis_unit"] or "(unit unspecified)"
            flux_unit = item["flux_unit"] or "(unit unspecified)"
            lines.extend(
                [
                    f"- Samples: `{item['count']}`",
                    f"- Spectral axis range: {format_number(item['wavelength_min'])} to {format_number(item['wavelength_max'])} {unit}",
                ]
            )
            if item.get("residual_rms") is not None:
                lines.append(f"- Spectrum residual RMS: {format_number(item['residual_rms'])} {flux_unit}")
            if item.get("snr_proxy") is not None:
                lines.append(f"- SNR proxy: {format_number(item['snr_proxy'])}")
            if item.get("calibration_residual_rms") is not None:
                lines.append(
                    f"- Wavelength calibration anchor residual RMS: {format_number(item['calibration_residual_rms'])} {unit}. "
                    "Absolute wavelength uncertainty is unavailable."
                )
                if item["calibration_method"]:
                    lines.append(f"- Calibration method: {item['calibration_method']} (degree {item['calibration_degree']}).")
            if item.get("line_fit_center") is not None:
                for label, key in [("Line center", "line_fit_center"), ("Line FWHM", "line_fit_fwhm"),
                                   ("Gaussian equivalent width", "line_equivalent_width")]:
                    measured = format_measurement(item[key], item["axis_unit"], item[f"{key}_uncertainty"])
                    lines.append(f"- {label}: {measured}")
                lines.append(f"- Line fit residual RMS: {format_number(item['line_fit_residual_rms'])} {flux_unit}")
                if item["line_fit_method"]:
                    lines.append(f"- Method: {item['line_fit_method']}. {item['line_fit_uncertainty_method']}")
        lines.extend(f"- Quality finding: {finding}" for finding in item["qa_findings"]
                     if finding != item["failure_reason"])
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- This workflow orchestrates the existing calibration and extraction tools into a single reproducible path.",
            "- If no calibration table is supplied, the pipeline still extracts and reports spectra honestly without inventing a wavelength solution.",
            "- For TEAREDUCE-specific wavelength-calibration notebooks or course recipes, route into TEAREDUCE instead of forcing this native pipeline.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    configure_runtime(TOOL_NAME)

    script_dir = Path(__file__).resolve().parent
    reduce_script = script_dir / "reduce_ccd_batch.py"
    spectral_script = script_dir / "spectral_workbench.py"

    output_dir = Path(args.output_dir)
    calibration_dir = output_dir / "calibration"
    products_dir = output_dir / "products"
    reports_dir = output_dir / "reports"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    products_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    science_paths = [Path(item).resolve() for item in args.science]
    arc_paths = [Path(item).resolve() for item in args.arc]
    if missing := [str(path) for path in [*science_paths, *arc_paths] if not path.exists()]:
        raise SystemExit(f"Input path(s) not found: {', '.join(missing)}")

    reduction_needed = bool(args.bias or args.dark or args.flat or args.master_bias or args.master_dark or args.master_flat)
    reduction_result = {
        "executed": reduction_needed,
        "returncode": None,
        "audit_json": None,
        "manifest_json": None,
    }
    reduction_failure_reason = None

    working_science = {path.name: path for path in science_paths}
    working_arcs = {path.name: path for path in arc_paths}

    if reduction_needed:
        reduction_audit = calibration_dir / "audit.json"
        reduction_manifest = calibration_dir / "manifest.json"
        previous_reduction = {path: file_version(path) for path in (reduction_audit, reduction_manifest)}
        cmd = [sys.executable, str(reduce_script), "--output-dir", str(calibration_dir), "--combine-method", args.combine_method]
        if args.scale_dark:
            cmd.append("--scale-dark")
        for label, values in [("--bias", args.bias), ("--dark", args.dark), ("--flat", args.flat), ("--science", [str(path) for path in science_paths]), ("--science", [str(path) for path in arc_paths])]:
            for value in values:
                cmd.extend([label, str(value)])
        if args.master_bias:
            cmd.extend(["--master-bias", args.master_bias])
        if args.master_dark:
            cmd.extend(["--master-dark", args.master_dark])
        if args.master_flat:
            cmd.extend(["--master-flat", args.master_flat])
        cmd.extend(["--audit-json", str(reduction_audit), "--manifest-json", str(reduction_manifest)])
        reduction_result = run_command(cmd)
        reduction_result["executed"] = True
        for key, path in [("audit_json", reduction_audit), ("manifest_json", reduction_manifest)]:
            reduction_result[key] = (
                str(path.resolve()) if path.is_file() and file_version(path) != previous_reduction[path] else None
            )
        if reduction_result["returncode"] != 0:
            reduction_failure_reason = f"CCD reduction failed with exit code {reduction_result['returncode']}. Extraction was skipped."
        else:
            for original in [*science_paths, *arc_paths]:
                reduced_candidate = calibration_dir / f"reduced_{original.name}"
                if reduced_candidate.exists():
                    if original in science_paths:
                        working_science[original.name] = reduced_candidate.resolve()
                    if original in arc_paths:
                        working_arcs[original.name] = reduced_candidate.resolve()

    product_rows = []
    extraction_inputs = science_paths if reduction_failure_reason is None else []
    duplicate_stems = len({path.stem for path in extraction_inputs}) != len(extraction_inputs)
    for science_path in extraction_inputs:
        working_path = working_science[science_path.name]
        item_dir = products_dir / (science_path.name if duplicate_stems else science_path.stem)
        item_dir.mkdir(parents=True, exist_ok=True)
        summary_json = item_dir / "summary.json"
        manifest_json = item_dir / "manifest.json"
        output_table = item_dir / "spectrum.ecsv"
        plot_path = item_dir / "spectrum.png"
        trace_plot = item_dir / "trace.png"
        html_report = item_dir / "spectrum.html"
        cmd = [
            sys.executable,
            str(spectral_script),
            str(working_path),
            "--spatial-half-width",
            str(args.spatial_half_width),
            "--background-inner-half-width",
            str(args.background_inner_half_width),
            "--background-outer-half-width",
            str(args.background_outer_half_width),
            "--trace-degree",
            str(args.trace_degree),
            "--order-count",
            str(args.order_count),
            "--order-index",
            str(args.order_index),
            "--output-table",
            str(output_table),
            "--plot",
            str(plot_path),
            "--trace-plot",
            str(trace_plot),
            "--html-report",
            str(html_report),
            "--summary-json",
            str(summary_json),
            "--manifest-json",
            str(manifest_json),
        ]
        if args.calibration_table:
            cmd.extend(["--calibration-table", args.calibration_table])
        if args.line_window:
            cmd.extend(["--line-window", str(args.line_window[0]), str(args.line_window[1])])
        if args.normalize:
            cmd.append("--normalize")
        if args.optimal_extraction:
            cmd.append("--optimal-extraction")
        if args.order_count > 1:
            cmd.extend(["--extract-all-orders-dir", str(item_dir / "orders")])
        product_paths = {
            "summary_json": summary_json, "manifest_json": manifest_json, "output_table": output_table,
            "plot": plot_path, "trace_plot": trace_plot, "html_report": html_report,
        }
        # A failed retry may leave artifacts from an earlier invocation in the same directory.
        previous = {key: file_version(path) for key, path in product_paths.items()}
        run_info = run_command(cmd)
        current = {
            key: str(path.resolve()) if path.is_file() and file_version(path) != previous[key] else None
            for key, path in product_paths.items()
        }
        payload = read_summary(summary_json) if current["summary_json"] else {}
        frame_status, spectrum, findings, failure_reason = extraction_evidence(
            payload, run_info["returncode"], current["output_table"] is not None,
        )
        line_fit = spectrum.get("line_fit") or {}
        uncertainties = line_fit.get("formal_uncertainties") or {}
        meta = spectrum.get("meta") or {}
        calibration = spectrum.get("calibration") or {}
        has_products = frame_status in {"ok", "warning"}
        product_rows.append(
            {
                "input_name": science_path.name,
                "working_path": str(working_path),
                "returncode": run_info["returncode"],
                "status": frame_status,
                "failure_reason": failure_reason,
                "qa_findings": findings,
                "summary_json": current["summary_json"],
                "manifest_json": current["manifest_json"],
                "count": spectrum.get("count"),
                "axis_unit": meta.get("axis_unit"),
                "flux_unit": meta.get("flux_unit"),
                "wavelength_min": spectrum.get("wavelength_min"),
                "wavelength_max": spectrum.get("wavelength_max"),
                "residual_rms": spectrum.get("residual_rms"),
                "snr_proxy": spectrum.get("snr_proxy"),
                "calibration_residual_rms": calibration.get("residual_rms"),
                "calibration_method": calibration.get("method"),
                "calibration_degree": calibration.get("degree"),
                "line_fit_center": line_fit.get("center"),
                "line_fit_center_uncertainty": uncertainties.get("center"),
                "line_fit_fwhm": line_fit.get("fwhm"),
                "line_fit_fwhm_uncertainty": uncertainties.get("fwhm"),
                "line_equivalent_width": line_fit.get("equivalent_width"),
                "line_equivalent_width_uncertainty": uncertainties.get("equivalent_width"),
                "line_fit_residual_rms": line_fit.get("residual_rms"),
                "line_fit_method": line_fit.get("method"),
                "line_fit_uncertainty_method": line_fit.get("uncertainty_method"),
                **{key: current[key] if has_products else None for key in ("plot", "trace_plot", "html_report", "output_table")},
                "stdout": run_info["stdout"],
                "stderr": run_info["stderr"],
            }
        )

    product_csv = reports_dir / "science_products.csv"
    write_csv(
        product_csv,
        [{**row, "qa_findings": json.dumps(row["qa_findings"], ensure_ascii=True)} for row in product_rows],
        [
            "input_name",
            "working_path",
            "returncode",
            "count",
            "wavelength_min",
            "wavelength_max",
            "residual_rms",
            "snr_proxy",
            "calibration_residual_rms",
            "line_fit_center",
            "line_fit_fwhm",
            "line_equivalent_width",
            "summary_json",
            "output_table",
            "plot",
            "trace_plot",
            "html_report",
            "status",
            "failure_reason",
            "qa_findings",
            "axis_unit",
            "flux_unit",
            "line_fit_center_uncertainty",
            "line_fit_fwhm_uncertainty",
            "line_equivalent_width_uncertainty",
            "line_fit_residual_rms",
            "line_fit_method",
            "line_fit_uncertainty_method",
            "calibration_method",
            "calibration_degree",
            "manifest_json",
        ],
    )

    completed_count = sum(item["status"] in {"ok", "warning"} for item in product_rows)
    blocked_count = sum(item["status"] == "blocked" for item in product_rows)
    failed_count = sum(item["status"] == "fail" for item in product_rows)
    skipped_count = len(science_paths) - len(product_rows)
    findings = []
    if reduction_failure_reason:
        findings.append(reduction_failure_reason)
    for row in product_rows:
        messages = row["qa_findings"]
        if row["failure_reason"] and row["failure_reason"] not in messages:
            messages = [row["failure_reason"], *messages]
        findings.extend(f"{row['input_name']}: {message}" for message in messages)
    if reduction_failure_reason or failed_count or (blocked_count and completed_count):
        status = "fail"
    elif blocked_count:
        status = "blocked"
    else:
        status = "warning" if findings or any(row["status"] == "warning" for row in product_rows) else "ok"
    metrics = {
        "completed_science_count": completed_count,
        "blocked_science_count": blocked_count,
        "failed_science_count": failed_count,
        "skipped_science_count": skipped_count,
    }
    report_path = reports_dir / "report.md"
    summary = {
        "environment": environment_summary(),
        "batch_status": status,
        "science_count": len(science_paths),
        **metrics,
        "arc_count": len(arc_paths),
        "reduced_science_count": sum(1 for item in product_rows if Path(item["working_path"]).name.startswith("reduced_")),
        "calibration_table": str(Path(args.calibration_table).resolve()) if args.calibration_table else None,
        "settings": {
            "combine_method": args.combine_method,
            "scale_dark": args.scale_dark,
            "spatial_half_width": args.spatial_half_width,
            "background_inner_half_width": args.background_inner_half_width,
            "background_outer_half_width": args.background_outer_half_width,
            "trace_degree": args.trace_degree,
            "optimal_extraction": args.optimal_extraction,
            "order_count": args.order_count,
            "order_index": args.order_index,
            "line_window": args.line_window,
            "normalize": args.normalize,
        },
        "calibration": {
            "executed": reduction_result["executed"],
            "returncode": reduction_result["returncode"],
            "failure_reason": reduction_failure_reason,
            "stderr": reduction_result.get("stderr") if reduction_failure_reason else None,
            "bias_count": len(args.bias),
            "dark_count": len(args.dark),
            "flat_count": len(args.flat),
            "audit_json": reduction_result.get("audit_json"),
            "manifest_json": reduction_result.get("manifest_json"),
        },
        "science_products": product_rows,
        "products": {
            "product_csv": str(product_csv.resolve()),
            "report_markdown": str(report_path.resolve()),
        },
        "notes": [
            "The workflow uses reduce_ccd_batch.py for calibration and spectral_workbench.py for 2D extraction and calibration products.",
            "If TEAREDUCE-specific cookbook behavior is required, prefer the TEAREDUCE optional backend instead of forcing this native path.",
        ],
    }
    write_report(report_path, summary)
    inputs = [
        *science_paths, *arc_paths, *args.bias, *args.dark, *args.flat,
        *[value for value in (args.master_bias, args.master_dark, args.master_flat, args.calibration_table) if value],
    ]
    payload = build_tool_payload(
        TOOL_NAME, status=status, notes=summary["notes"], results=summary, legacy=summary,
        artifacts={
            **summary["products"],
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
        },
        qa={"status": status, "findings": findings, "metrics": metrics},
        inputs=inputs,
    )
    emit_payload(payload, args.summary_json)

    if args.manifest_json:
        outputs = [product_csv, report_path]
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        if reduction_result.get("audit_json"):
            outputs.append(Path(reduction_result["audit_json"]))
        if reduction_result.get("manifest_json"):
            outputs.append(Path(reduction_result["manifest_json"]))
        for item in product_rows:
            for key in ["summary_json", "manifest_json", "output_table", "plot", "trace_plot", "html_report"]:
                value = item.get(key)
                if value:
                    outputs.append(Path(value))
        write_manifest(
            args.manifest_json,
            inputs=inputs,
            outputs=outputs,
            parameters={
                "master_bias": args.master_bias,
                "master_dark": args.master_dark,
                "master_flat": args.master_flat,
                **summary["settings"],
            },
            command="spectroscopy_pipeline_workbench.py",
            notes=summary["notes"],
            extra={"summary": summary},
        )
    return 2 if status == "blocked" else 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
