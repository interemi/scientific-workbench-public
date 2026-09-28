#!/usr/bin/env python3
"""Run the canonical TEAREDUCE flat-field workflow and compare it to the native stack."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import warnings
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime

ensure_datanalysis_runtime("teareduce_flat_workflow")

import ccdproc
import numpy as np
from astropy.io import fits
from astropy.nddata import CCDData
from astropy.stats import mad_std
from astropy.wcs import FITSFixedWarning

from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from teareduce_healthcheck import bootstrap_runtime_dirs, inspect_teareduce_environment, scan_notebook
from teareduce_notebook_runner import block_notebook_output_collisions, execute_copy, require_trusted_notebook_code

warnings.filterwarnings("ignore", category=FITSFixedWarning)

OFFICIAL_FILTER_CURVES = {
    "49": "https://www.not.iac.es/instruments/filters/curves-ascii/49.txt",
    "76": "https://www.not.iac.es/instruments/filters/curves-ascii/76.txt",
    "78": "https://www.not.iac.es/instruments/filters/curves-ascii/78.txt",
}

FLAT_FRAME_IDS = {
    "49": ["120051", "120052", "120053", "120054", "120055", "120056"],
    "76": ["120057", "120058", "120059", "120060", "120061", "120062"],
    "78": ["120046", "120047", "120048", "120049", "120050"],
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", help="Path to the TEAREDUCE flat notebook.")
    parser.add_argument("--output-dir", required=True, help="Directory for copied notebook outputs and comparison products.")
    parser.add_argument("--kernel-name", default="python3", help="Kernel name for copied execution.")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="Per-cell execution timeout.")
    parser.add_argument("--trust-notebook-code", action="store_true", help="Confirm that the notebook code is explicitly trusted.")
    parser.add_argument("--sidecar", action="append", default=[], help="Extra sidecar file to stage before notebook execution.")
    parser.add_argument(
        "--fetch-official-sidecars",
        action="store_true",
        help="Fetch the official NOT filter ASCII curves for 49, 76, and 78 if they are not supplied explicitly.",
    )
    parser.add_argument(
        "--limit-science-products-per-filter",
        type=int,
        default=0,
        help="If > 0, only write this many native flat-corrected science products per filter. Useful for smoke tests.",
    )
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--report-md", help="Optional Markdown report path.")
    parser.add_argument("--manifest-json", help="Optional manifest path.")
    return parser.parse_args()


def prepare_sidecars(output_dir: Path, explicit_paths: list[str], fetch_official: bool) -> list[str]:
    sidecar_dir = output_dir / "sidecars"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []
    for raw in explicit_paths:
        path = Path(raw).expanduser().resolve()
        if path.exists():
            staged.append(str(path))
    if fetch_official:
        for filter_id, url in OFFICIAL_FILTER_CURVES.items():
            target = sidecar_dir / f"filter_NOT_{filter_id}.txt"
            if not target.exists():
                urllib.request.urlretrieve(url, target)
            staged.append(str(target))
    return staged


def select_dataset_dir(run: dict) -> Path:
    staged = run.get("staged_path_map") or {}
    if not staged:
        raise RuntimeError("Notebook execution did not expose a staged dataset tree.")
    dataset_dir = Path(next(iter(staged.values())))
    if not dataset_dir.is_dir():
        raise RuntimeError(f"Dataset directory missing: {dataset_dir}")
    return dataset_dir


def normalized_flat_combine(paths: list[Path], output_path: Path) -> dict:
    started = time.perf_counter()
    images = []
    for path in paths:
        ccdimage = CCDData.read(path)
        ccdimage = ccdimage.divide(np.median(ccdimage.data), handle_meta="first_found")
        images.append(ccdimage)
    master_flat = ccdproc.combine(
        img_list=images,
        method="average",
        sigma_clip=True,
        sigma_clip_low_thres=5,
        sigma_clip_high_thres=5,
        sigma_clip_func=np.ma.median,
        sigma_clip_dev_func=mad_std,
    )
    master_flat.header["FILENAME"] = output_path.name
    master_flat.header["HISTORY"] = "native scientific-data-analysis master flat"
    master_flat.write(output_path, overwrite=True)
    return {"path": output_path, "duration_sec": round(time.perf_counter() - started, 2)}


def select_science_for_filter(dataset_dir: Path, filter_id: str) -> list[Path]:
    selected = []
    for path in sorted(dataset_dir.glob("zt_AL*.fits")):
        header = fits.getheader(path)
        obj = str(header.get("OBJECT", "")).lower()
        if "flat" in obj or "focusing" in obj:
            continue
        if filter_id in {"49", "78"}:
            value = str(header.get("FBFLTID", "")).strip()
        else:
            value = str(header.get("ALFLTID", "")).strip()
        if value == filter_id:
            selected.append(path)
    return selected


def apply_flat_native(master_flat_path: Path, science_paths: list[Path], output_dir: Path) -> dict:
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    master_flat = CCDData.read(master_flat_path)
    created = []
    for path in science_paths:
        ccdimage = CCDData.read(path)
        reduced = ccdproc.flat_correct(ccdimage, master_flat)
        output_name = f"f{path.name}"
        target = output_dir / output_name
        reduced.header["FILENAME"] = output_name
        reduced.header["HISTORY"] = f"master Flat Field file: {master_flat_path.name}"
        reduced.write(target, overwrite=True)
        created.append(target)
    return {"paths": created, "duration_sec": round(time.perf_counter() - started, 2)}


def array_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    delta = a.astype(float) - b.astype(float)
    return {
        "shape": list(a.shape),
        "mean_abs_diff": float(np.mean(np.abs(delta))),
        "max_abs_diff": float(np.max(np.abs(delta))),
        "std_diff": float(np.std(delta)),
        "allclose_atol_1e-6": bool(np.allclose(a, b, atol=1e-6, rtol=0)),
        "median_a": float(np.median(a)),
        "median_b": float(np.median(b)),
    }


def flat_stats(path: Path) -> dict:
    with fits.open(path) as hdul:
        data = hdul[0].data.astype(float)
    return {
        "median": float(np.median(data)),
        "mean": float(np.mean(data)),
        "std": float(np.std(data)),
        "p05": float(np.percentile(data, 5)),
        "p95": float(np.percentile(data, 95)),
    }


def build_report(payload: dict) -> str:
    lines = [
        "# Canonical TEAREDUCE Workflow: Flat Field",
        "",
        "## Selected case",
        f"- Notebook: `{payload['notebook']}`",
        f"- TEAREDUCE in launcher Python: `{payload['teareduce'].get('version') or 'not detected'}`; selected notebook kernel version not verified.",
        f"- Notebook-observed TEAREDUCE version: `{', '.join(payload['notebook_scan'].get('observed_versions') or ['unknown'])}`",
        f"- Notebook execution status: `{payload['teareduce_run']['assessment']['status']}`",
        "",
        "## Filter sidecars",
    ]
    for item in payload["sidecars"]:
        lines.append(f"- `{item['filter_id']}` -> `{item['path']}`")
    lines.extend(["", "## Per-filter comparison"])
    for filter_id, info in payload["filters"].items():
        lines.extend(
            [
                f"### Filter {filter_id}",
                f"- TEAREDUCE master flat: `{info['teareduce_master_flat']}`",
                f"- Native master flat: `{info['native_master_flat']}`",
                f"- Master-flat mean abs diff: `{info['master_metrics']['mean_abs_diff']:.6g}`",
                f"- Master-flat max abs diff: `{info['master_metrics']['max_abs_diff']:.6g}`",
                f"- Sample flat-corrected frame allclose: `{info['sample_metrics']['allclose_atol_1e-6']}`",
                f"- TEAREDUCE master-flat median/std: `{info['teareduce_stats']['median']:.6g}` / `{info['teareduce_stats']['std']:.6g}`",
                f"- Native master-flat median/std: `{info['native_stats']['median']:.6g}` / `{info['native_stats']['std']:.6g}`",
                f"- Science frames corrected in this filter: `{info['native_science_count']}`",
                f"- Total science frames available in this filter: `{info['science_count']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommendation",
            "- Prefer TEAREDUCE here when you want the original notebook workflow, the filter-curve context, and the classroom-style sequence of plots and checks.",
            "- Prefer the native stack when you only need the calibrated flat products and batch correction with fewer notebook-specific dependencies.",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    bootstrap = bootstrap_runtime_dirs()
    args = parse_args()
    require_trusted_notebook_code("teareduce_flat_workflow", args.trust_notebook_code)
    notebook_path = Path(args.notebook).resolve()
    output_dir = Path(args.output_dir)
    report_path = Path(args.report_md) if args.report_md else output_dir / "report.md"
    block_notebook_output_collisions(
        "teareduce_flat_workflow",
        notebook_paths=[notebook_path],
        extra_paths=args.sidecar,
        outputs=[
            ("--summary-json", args.summary_json),
            ("--report-md/default", report_path),
            ("--manifest-json", args.manifest_json),
        ],
        output_dirs=[("--output-dir", output_dir)],
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sidecars = prepare_sidecars(output_dir, args.sidecar, args.fetch_official_sidecars)
    run = execute_copy(
        notebook_path,
        output_dir / "teareduce_copy",
        kernel_name=args.kernel_name,
        timeout_sec=args.timeout_sec,
        extra_stage_paths=sidecars,
    )
    if not run["success"]:
        raise SystemExit(f"TEAREDUCE flat notebook execution failed: {run['assessment']['reason']}")

    dataset_dir = select_dataset_dir(run)
    native_root = output_dir / "native_stack"
    native_root.mkdir(parents=True, exist_ok=True)

    filters_payload = {}
    outputs = [Path(run["executed_copy"])]
    for filter_id, ids in FLAT_FRAME_IDS.items():
        input_flats = [dataset_dir / f"zt_ALrd{frame_id}.fits" for frame_id in ids]
        master_flat_native = native_root / f"N1_master_flat_{filter_id}_native.fits"
        normalized_flat_combine(input_flats, master_flat_native)
        science_paths = select_science_for_filter(dataset_dir, filter_id)
        native_science_paths = science_paths[: args.limit_science_products_per_filter] if args.limit_science_products_per_filter > 0 else science_paths
        native_products = apply_flat_native(master_flat_native, native_science_paths, native_root / filter_id)
        teareduce_master = dataset_dir / f"N1_master_flat_{filter_id}.fits"
        if not teareduce_master.exists():
            raise RuntimeError(f"Notebook did not produce expected master flat {teareduce_master.name}")

        with fits.open(teareduce_master) as hdul_a, fits.open(master_flat_native) as hdul_b:
            master_metrics = array_metrics(hdul_a[0].data, hdul_b[0].data)

        sample_source = science_paths[0] if science_paths else None
        sample_teareduce = dataset_dir / f"f{sample_source.name}" if sample_source else None
        sample_native = native_products["paths"][0] if native_products["paths"] else None
        sample_metrics = {}
        if sample_source and sample_teareduce and sample_teareduce.exists() and sample_native:
            with fits.open(sample_teareduce) as hdul_a, fits.open(sample_native) as hdul_b:
                sample_metrics = array_metrics(hdul_a[0].data, hdul_b[0].data)

        outputs.extend([master_flat_native, *native_products["paths"]])
        filters_payload[filter_id] = {
            "teareduce_master_flat": public_path(teareduce_master),
            "native_master_flat": public_path(master_flat_native),
            "teareduce_stats": flat_stats(teareduce_master),
            "native_stats": flat_stats(master_flat_native),
            "master_metrics": master_metrics,
            "science_count": len(science_paths),
            "native_science_count": len(native_products["paths"]),
            "sample_source": public_path(sample_source) if sample_source else None,
            "sample_teareduce": public_path(sample_teareduce) if sample_teareduce and sample_teareduce.exists() else None,
            "sample_native": public_path(sample_native) if sample_native else None,
            "sample_metrics": sample_metrics,
        }

    payload = {
        "tool": "teareduce_flat_workflow",
        "environment": environment_summary(extra={"runtime_overrides": bootstrap}),
        "notebook": public_path(notebook_path),
        "notebook_scan": scan_notebook(notebook_path),
        "teareduce": inspect_teareduce_environment(),
        "sidecars": [
            {"filter_id": path.stem.split("_")[-1], "path": public_path(path)}
            for path in sorted({Path(item).resolve() for item in sidecars})
        ],
        "teareduce_run": run,
        "filters": filters_payload,
    }
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")

    report_path.write_text(build_report(sanitize_payload(payload)), encoding="utf-8")

    if args.summary_json:
        Path(args.summary_json).write_text(rendered, encoding="utf-8")
        outputs.append(Path(args.summary_json))
    outputs.append(report_path)
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[notebook_path, *map(Path, sidecars)],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "limit_science_products_per_filter": args.limit_science_products_per_filter,
            },
            command="teareduce_flat_workflow.py",
            notes=[
                "Runs the TEAREDUCE flat notebook in copy with staged filter transmission sidecars.",
                "Replays the same master-flat and flat-correction logic through the native stack for comparison.",
            ],
            extra={"filters": filters_payload, "teareduce_version": payload["teareduce"].get("version"), "teareduce_version_scope": "launcher_python_only"},
        )


if __name__ == "__main__":
    main()
