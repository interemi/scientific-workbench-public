#!/usr/bin/env python3
"""Run a reproducible 2D spectroscopy workflow with reduction, extraction, calibration, and reporting."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import environment_summary, write_manifest
from _internal.runtime_common import configure_runtime


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


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
        "## Extracted Products",
        "",
    ]
    for item in summary["science_products"]:
        lines.extend(
            [
                f"### `{item['input_name']}`",
                "",
                f"- Working frame: `{item['working_path']}`",
                f"- Extraction return code: `{item['returncode']}`",
                f"- Samples: `{item.get('count')}`",
                f"- Wavelength range: `{item.get('wavelength_min')}` to `{item.get('wavelength_max')}`",
                f"- Residual RMS: `{item.get('residual_rms')}`",
                f"- SNR proxy: `{item.get('snr_proxy')}`",
                f"- Calibration residual RMS: `{item.get('calibration_residual_rms')}`",
                "",
            ]
        )
        if item.get("line_fit_center") is not None:
            lines.extend(
                [
                    f"- Line center: `{item['line_fit_center']}`",
                    f"- Line FWHM: `{item['line_fit_fwhm']}`",
                    f"- Equivalent width: `{item['line_equivalent_width']}`",
                    "",
                ]
            )
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
    configure_runtime("spectroscopy_pipeline_workbench")

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

    working_science = {path.name: path for path in science_paths}
    working_arcs = {path.name: path for path in arc_paths}

    if reduction_needed:
        reduction_audit = calibration_dir / "audit.json"
        reduction_manifest = calibration_dir / "manifest.json"
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
        reduction_result["audit_json"] = str(reduction_audit.resolve())
        reduction_result["manifest_json"] = str(reduction_manifest.resolve())
        if reduction_result["returncode"] != 0:
            raise SystemExit(f"CCD reduction stage failed. See {reduction_audit}")
        for original in [*science_paths, *arc_paths]:
            reduced_candidate = calibration_dir / f"reduced_{original.name}"
            if reduced_candidate.exists():
                if original in science_paths:
                    working_science[original.name] = reduced_candidate.resolve()
                if original in arc_paths:
                    working_arcs[original.name] = reduced_candidate.resolve()

    product_rows = []
    for science_path in science_paths:
        working_path = working_science[science_path.name]
        stem = science_path.stem
        item_dir = products_dir / stem
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
        run_info = run_command(cmd)
        summary_payload = load_json(summary_json) or {}
        line_fit = summary_payload.get("line_fit", {})
        calibration = summary_payload.get("calibration", {})
        product_rows.append(
            {
                "input_name": science_path.name,
                "working_path": str(working_path),
                "returncode": run_info["returncode"],
                "summary_json": str(summary_json.resolve()) if summary_json.exists() else None,
                "count": summary_payload.get("count"),
                "wavelength_min": summary_payload.get("wavelength_min"),
                "wavelength_max": summary_payload.get("wavelength_max"),
                "residual_rms": summary_payload.get("residual_rms"),
                "snr_proxy": summary_payload.get("snr_proxy"),
                "calibration_residual_rms": calibration.get("residual_rms"),
                "line_fit_center": line_fit.get("center"),
                "line_fit_fwhm": line_fit.get("fwhm"),
                "line_equivalent_width": line_fit.get("equivalent_width"),
                "plot": str(plot_path.resolve()) if plot_path.exists() else None,
                "trace_plot": str(trace_plot.resolve()) if trace_plot.exists() else None,
                "html_report": str(html_report.resolve()) if html_report.exists() else None,
                "output_table": str(output_table.resolve()) if output_table.exists() else None,
                "stdout": run_info["stdout"],
                "stderr": run_info["stderr"],
            }
        )

    product_csv = reports_dir / "science_products.csv"
    write_csv(
        product_csv,
        product_rows,
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
        ],
    )

    summary = {
        "tool": "spectroscopy_pipeline_workbench",
        "environment": environment_summary(),
        "science_count": len(science_paths),
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
            "bias_count": len(args.bias),
            "dark_count": len(args.dark),
            "flat_count": len(args.flat),
            "audit_json": reduction_result.get("audit_json"),
            "manifest_json": reduction_result.get("manifest_json"),
        },
        "science_products": product_rows,
        "products": {
            "product_csv": str(product_csv.resolve()),
        },
        "notes": [
            "The workflow uses reduce_ccd_batch.py for calibration and spectral_workbench.py for 2D extraction and calibration products.",
            "If TEAREDUCE-specific cookbook behavior is required, prefer the TEAREDUCE optional backend instead of forcing this native path.",
        ],
    }
    report_path = reports_dir / "report.md"
    write_report(report_path, summary)
    summary["products"]["report_markdown"] = str(report_path.resolve())

    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")

    if args.manifest_json:
        outputs = [product_csv, report_path]
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        if reduction_result.get("audit_json"):
            outputs.append(Path(reduction_result["audit_json"]))
        if reduction_result.get("manifest_json"):
            outputs.append(Path(reduction_result["manifest_json"]))
        for item in product_rows:
            for key in ["summary_json", "output_table", "plot", "trace_plot", "html_report"]:
                value = item.get(key)
                if value:
                    outputs.append(Path(value))
        write_manifest(
            args.manifest_json,
            inputs=[*science_paths, *arc_paths, *[Path(item) for item in args.bias], *[Path(item) for item in args.dark], *[Path(item) for item in args.flat]],
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


if __name__ == "__main__":
    main()
