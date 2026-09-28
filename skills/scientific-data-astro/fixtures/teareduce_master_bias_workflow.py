#!/usr/bin/env python3
"""Run a canonical TEAREDUCE master-bias workflow and compare it to the native stack."""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime

ensure_datanalysis_runtime("teareduce_master_bias_workflow")

import ccdproc
import numpy as np
warnings.filterwarnings(
    "ignore",
    message=r"XDG_CONFIG_HOME is set to '.*', but the default location, .* already exists, and takes precedence.*",
    category=Warning,
)
from astropy.io import fits
from astropy.nddata import CCDData
from astropy.stats import mad_std
from astropy.wcs import FITSFixedWarning

warnings.filterwarnings("ignore", category=FITSFixedWarning)

from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from teareduce_healthcheck import bootstrap_runtime_dirs, inspect_teareduce_environment, scan_notebook
from teareduce_notebook_runner import block_notebook_output_collisions, execute_copy, require_trusted_notebook_code


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", help="Path to the TEAREDUCE notebook to execute in copy.")
    parser.add_argument("--output-dir", required=True, help="Directory for copied notebook outputs and comparison products.")
    parser.add_argument("--kernel-name", default="python3", help="Jupyter kernel name for copied notebook execution.")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="Per-cell timeout for notebook execution.")
    parser.add_argument("--trust-notebook-code", action="store_true", help="Confirm that the notebook code is explicitly trusted.")
    parser.add_argument(
        "--limit-science-products",
        type=int,
        default=0,
        help="If > 0, only write this many native bias-subtracted science products. Useful for smoke tests.",
    )
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--report-md", help="Optional Markdown report path.")
    parser.add_argument("--manifest-json", help="Optional manifest path.")
    return parser.parse_args()


def select_dataset_dir(run: dict) -> Path:
    staged = run.get("staged_path_map") or {}
    if not staged:
        raise RuntimeError("Notebook preflight did not expose a staged dataset directory.")
    dataset_dir = Path(next(iter(staged.values())))
    if not dataset_dir.is_dir():
        raise RuntimeError(f"Staged dataset directory is missing: {dataset_dir}")
    return dataset_dir


def classify_frames(dataset_dir: Path) -> tuple[list[Path], list[Path]]:
    bias_frames: list[Path] = []
    science_frames: list[Path] = []
    for path in sorted(dataset_dir.glob("t_AL*.fits")):
        imagetyp = str(fits.getheader(path).get("IMAGETYP", "")).strip().upper()
        if imagetyp == "BIAS":
            bias_frames.append(path)
        else:
            science_frames.append(path)
    if not bias_frames:
        raise RuntimeError(f"No BIAS frames found in {dataset_dir}")
    return bias_frames, science_frames


def build_native_master_bias(bias_frames: list[Path], output_path: Path) -> dict:
    started = time.perf_counter()
    list_bias = [CCDData.read(path) for path in bias_frames]
    master_bias = ccdproc.combine(
        img_list=list_bias,
        method="average",
        sigma_clip=True,
        sigma_clip_low_thres=5,
        sigma_clip_high_thresh=5,
        sigma_clip_func=np.ma.median,
        sigma_clip_dev_func=mad_std,
    )
    master_bias.header["FILENAME"] = output_path.name
    master_bias.header["HISTORY"] = "native scientific-data-analysis master bias"
    master_bias.write(output_path, overwrite=True)
    duration = round(time.perf_counter() - started, 2)
    return {"path": output_path, "duration_sec": duration}


def subtract_bias_native(science_frames: list[Path], master_bias_path: Path, output_dir: Path) -> dict:
    started = time.perf_counter()
    master_bias = CCDData.read(master_bias_path)
    created = []
    for frame in science_frames:
        ccdimage = CCDData.read(frame)
        corrected = ccdproc.subtract_bias(ccdimage, master_bias)
        output_name = f"z{frame.name}"
        target = output_dir / output_name
        corrected.header["FILENAME"] = output_name
        corrected.header["HISTORY"] = f"master BIAS file: {master_bias_path.name}"
        corrected.write(target, overwrite=True)
        created.append(target)
    duration = round(time.perf_counter() - started, 2)
    return {"paths": created, "duration_sec": duration}


def array_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    delta = a.astype(float) - b.astype(float)
    return {
        "shape": list(a.shape),
        "mean_abs_diff": float(np.mean(np.abs(delta))),
        "max_abs_diff": float(np.max(np.abs(delta))),
        "std_diff": float(np.std(delta)),
        "allclose_atol_1e-6": bool(np.allclose(a, b, atol=1e-6, rtol=0)),
    }


def compare_products(dataset_dir: Path, native_master_bias: Path, science_frames: list[Path], native_products: list[Path]) -> dict:
    teareduce_master_bias = dataset_dir / "N1_master_bias.fits"
    comparison = {
        "teareduce_master_bias": public_path(teareduce_master_bias),
        "native_master_bias": public_path(native_master_bias),
        "teareduce_master_bias_exists": teareduce_master_bias.exists(),
        "native_master_bias_exists": native_master_bias.exists(),
    }
    if teareduce_master_bias.exists():
        with fits.open(teareduce_master_bias) as hdul_a, fits.open(native_master_bias) as hdul_b:
            comparison["master_bias_metrics"] = array_metrics(hdul_a[0].data, hdul_b[0].data)
    teareduce_products = sorted(dataset_dir.glob("zt_AL*.fits"))
    comparison["teareduce_product_count"] = len(teareduce_products)
    comparison["native_product_count"] = len(native_products)
    if science_frames and native_products:
        sample_in = science_frames[0]
        sample_teareduce = dataset_dir / f"z{sample_in.name}"
        sample_native = native_products[0]
        comparison["sample_product"] = {
            "source_trimmed": public_path(sample_in),
            "teareduce_output": public_path(sample_teareduce),
            "native_output": public_path(sample_native),
            "teareduce_exists": sample_teareduce.exists(),
            "native_exists": sample_native.exists(),
        }
        if sample_teareduce.exists():
            with fits.open(sample_teareduce) as hdul_a, fits.open(sample_native) as hdul_b:
                comparison["sample_product"]["metrics"] = array_metrics(hdul_a[0].data, hdul_b[0].data)
    return comparison


def build_report(payload: dict) -> str:
    run = payload["teareduce_run"]
    native = payload["native_stack"]
    comp = payload["comparison"]
    notebook = payload["notebook_scan"]
    master_metrics = comp.get("master_bias_metrics", {})
    sample_metrics = comp.get("sample_product", {}).get("metrics", {})
    lines = [
        "# Canonical TEAREDUCE Workflow: Master Bias",
        "",
        "## Selected case",
        f"- Notebook: `{payload['notebook']}`",
        f"- Workflow: copied execution of the TEAREDUCE bias-correction notebook plus a native-stack replay of the same calibration step.",
        f"- TEAREDUCE in launcher Python: `{payload['teareduce'].get('version') or 'not detected'}`; selected notebook kernel version not verified.",
        f"- Notebook-observed TEAREDUCE version: `{', '.join(notebook.get('observed_versions') or ['unknown'])}`",
        "",
        "## TEAREDUCE result",
        f"- Notebook execution status: `{run['assessment']['status']}`",
        f"- Notebook copied execution time: `{run['duration_sec']}` s",
        f"- Bias frames used: `{native['bias_frame_count']}`",
        f"- Corrected non-bias frames written by the notebook: `{comp['teareduce_product_count']}`",
        f"- Master bias path: `{comp['teareduce_master_bias']}`",
        "",
        "## Native-stack replay",
        f"- Native master-bias build time: `{native['master_bias_duration_sec']}` s",
        f"- Native bias-subtraction time over non-bias frames: `{native['science_subtraction_duration_sec']}` s",
        f"- Native corrected non-bias frames written: `{native['native_science_products_written']}`",
        f"- Total non-bias frames available in the dataset: `{native['science_frame_count']}`",
        f"- Native master bias path: `{comp['native_master_bias']}`",
        "",
        "## Numerical comparison",
    ]
    if master_metrics:
        lines.extend(
            [
                f"- Master-bias mean abs diff: `{master_metrics['mean_abs_diff']:.6g}`",
                f"- Master-bias max abs diff: `{master_metrics['max_abs_diff']:.6g}`",
                f"- Master-bias exact-style allclose (`atol=1e-6`): `{master_metrics['allclose_atol_1e-6']}`",
            ]
        )
    if sample_metrics:
        lines.extend(
            [
                f"- Sample corrected-frame mean abs diff: `{sample_metrics['mean_abs_diff']:.6g}`",
                f"- Sample corrected-frame max abs diff: `{sample_metrics['max_abs_diff']:.6g}`",
                f"- Sample corrected-frame allclose (`atol=1e-6`): `{sample_metrics['allclose_atol_1e-6']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## When TEAREDUCE is the better choice",
            "- When the goal is to reproduce or teach the exact notebook workflow.",
            "- When the user wants the same stepwise exploratory context, quicklook style, and classroom-facing narrative as the original notebook.",
            "- When version-skew against older TEAREDUCE notebooks needs to be surfaced explicitly while keeping the notebook as the execution truth.",
            "",
            "## When the native stack is the better choice",
            "- When you want a shorter script-first path with fewer notebook-specific moving parts.",
            "- When you want cleaner manifests, easier automation, or broader reuse outside the TEAREDUCE ecosystem.",
            "- When the task is just to build the calibration product, not to preserve the original notebook pedagogy.",
            "",
            "## Recommendation",
            "- Keep TEAREDUCE as the faithful path for notebook reproduction and teaching-aligned calibration workflows.",
            "- Prefer the native stack for concise batch automation and for mixed-field work where the notebook context is not itself the deliverable.",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    bootstrap = bootstrap_runtime_dirs()
    args = parse_args()
    require_trusted_notebook_code("teareduce_master_bias_workflow", args.trust_notebook_code)
    notebook_path = Path(args.notebook).resolve()
    output_dir = Path(args.output_dir)
    report_path = Path(args.report_md) if args.report_md else output_dir / "report.md"
    block_notebook_output_collisions(
        "teareduce_master_bias_workflow",
        notebook_paths=[notebook_path],
        extra_paths=[],
        outputs=[
            ("--summary-json", args.summary_json),
            ("--report-md/default", report_path),
            ("--manifest-json", args.manifest_json),
        ],
        output_dirs=[("--output-dir", output_dir)],
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    teareduce_run_dir = output_dir / "teareduce_copy"
    run = execute_copy(notebook_path, teareduce_run_dir, kernel_name=args.kernel_name, timeout_sec=args.timeout_sec)
    if not run["success"]:
        message = run["assessment"]["reason"]
        raise SystemExit(f"TEAREDUCE notebook execution failed: {message}")

    dataset_dir = select_dataset_dir(run)
    bias_frames, science_frames = classify_frames(dataset_dir)

    native_dir = output_dir / "native_stack"
    native_dir.mkdir(parents=True, exist_ok=True)
    native_master_bias_path = native_dir / "N1_master_bias_native.fits"
    native_master = build_native_master_bias(bias_frames, native_master_bias_path)
    native_science_frames = science_frames[: args.limit_science_products] if args.limit_science_products > 0 else science_frames
    native_products = subtract_bias_native(native_science_frames, native_master_bias_path, native_dir)

    comparison = compare_products(dataset_dir, native_master_bias_path, science_frames, native_products["paths"])
    teareduce_info = inspect_teareduce_environment()
    notebook_info = scan_notebook(notebook_path)

    payload = {
        "tool": "teareduce_master_bias_workflow",
        "environment": environment_summary(extra={"runtime_overrides": bootstrap}),
        "notebook": public_path(notebook_path),
        "notebook_scan": notebook_info,
        "teareduce": teareduce_info,
        "teareduce_run": run,
        "native_stack": {
            "bias_frame_count": len(bias_frames),
            "science_frame_count": len(science_frames),
            "native_science_products_written": len(native_products["paths"]),
            "master_bias_duration_sec": native_master["duration_sec"],
            "science_subtraction_duration_sec": native_products["duration_sec"],
            "native_master_bias_path": public_path(native_master_bias_path),
        },
        "comparison": comparison,
    }
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")

    report_path.write_text(build_report(sanitize_payload(payload)), encoding="utf-8")

    if args.summary_json:
        Path(args.summary_json).write_text(rendered, encoding="utf-8")
    if args.manifest_json:
        outputs = [
            Path(run["executed_copy"]),
            native_master_bias_path,
            report_path,
            *native_products["paths"],
        ]
        if args.summary_json:
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[notebook_path, *bias_frames, *science_frames],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "limit_science_products": args.limit_science_products,
            },
            command="teareduce_master_bias_workflow.py",
            notes=[
                "Runs the TEAREDUCE notebook in copy, then replays the same master-bias logic through the native stack for comparison.",
                "Original notebook and original FITS files are not modified.",
            ],
            extra={"comparison": comparison, "teareduce_version": teareduce_info.get("version"), "teareduce_version_scope": "launcher_python_only"},
        )


if __name__ == "__main__":
    main()
