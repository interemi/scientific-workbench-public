#!/usr/bin/env python3
"""Run the official TEAREDUCE cr2images cookbook notebook in copy and summarize its products."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime

ensure_datanalysis_runtime("teareduce_cookbook_cr2images_workflow")

import numpy as np
from astropy.io import fits

from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from teareduce_healthcheck import bootstrap_runtime_dirs, inspect_teareduce_environment, scan_notebook
from teareduce_notebook_runner import block_notebook_output_collisions, execute_copy, require_trusted_notebook_code

OFFICIAL_NOTEBOOK_URL = (
    "https://raw.githubusercontent.com/nicocardiel/teareduce-cookbook/main/notebooks/cr2images/cr2images.ipynb"
)
OFFICIAL_SAMPLE_URLS = {
    "ftdz_45243.fits": (
        "https://raw.githubusercontent.com/nicocardiel/teareduce-cookbook/main/notebooks/cr2images/ftdz_45243.fits"
    ),
    "ftdz_45244.fits": (
        "https://raw.githubusercontent.com/nicocardiel/teareduce-cookbook/main/notebooks/cr2images/ftdz_45244.fits"
    ),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", help="Path to a local cr2images cookbook notebook. If omitted, download the official one.")
    parser.add_argument("--sample", action="append", default=[], help="Local sample FITS to stage next to the copied notebook.")
    parser.add_argument(
        "--fetch-official-samples",
        action="store_true",
        help="Download the official sample FITS from the TEAREDUCE cookbook when local samples are not supplied.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for copied notebook outputs and reports.")
    parser.add_argument("--kernel-name", default="python3", help="Jupyter kernel name for copied notebook execution.")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="Per-cell execution timeout.")
    parser.add_argument("--trust-notebook-code", action="store_true", help="Confirm that the notebook code is explicitly trusted.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--report-md", help="Optional Markdown report path.")
    parser.add_argument("--manifest-json", help="Optional manifest path.")
    return parser.parse_args()


def ensure_local_file(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        urllib.request.urlretrieve(url, target)
    return target


def prepare_notebook(args, output_dir: Path) -> Path:
    if args.notebook:
        return Path(args.notebook).expanduser().resolve()
    return ensure_local_file(OFFICIAL_NOTEBOOK_URL, output_dir / "official_inputs" / "cr2images.ipynb")


def prepare_samples(args, output_dir: Path) -> list[Path]:
    samples: list[Path] = []
    for raw in args.sample:
        path = Path(raw).expanduser().resolve()
        if path.exists():
            samples.append(path)
    if args.fetch_official_samples:
        for name, url in OFFICIAL_SAMPLE_URLS.items():
            samples.append(ensure_local_file(url, output_dir / "official_inputs" / name))
    deduped: list[Path] = []
    seen = set()
    for item in samples:
        key = str(item)
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def array_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    delta = a.astype(float) - b.astype(float)
    return {
        "shape": list(a.shape),
        "mean_abs_diff": float(np.mean(np.abs(delta))),
        "max_abs_diff": float(np.max(np.abs(delta))),
        "std_diff": float(np.std(delta)),
        "allclose_atol_1e-6": bool(np.allclose(a, b, atol=1e-6, rtol=0)),
    }


def file_metrics(original: Path, cleaned: Path) -> dict:
    with fits.open(original) as hdul_orig, fits.open(cleaned) as hdul_clean:
        data_orig = hdul_orig[0].data.astype(float)
        data_clean = hdul_clean[0].data.astype(float)
    delta = data_clean - data_orig
    changed = delta != 0
    return {
        "original": public_path(original),
        "cleaned": public_path(cleaned),
        "changed_pixel_count": int(np.count_nonzero(changed)),
        "changed_fraction": float(np.count_nonzero(changed) / changed.size),
        "max_abs_change": float(np.max(np.abs(delta))),
        "median_abs_change": float(np.median(np.abs(delta[changed]))) if np.any(changed) else 0.0,
    }


def compare_outputs(workspace_dir: Path) -> dict:
    comparisons = {}
    for stem in ["45243", "45244"]:
        manual = workspace_dir / f"cftdz_{stem}.fits"
        helper = workspace_dir / f"ccftdz_{stem}.fits"
        original = workspace_dir / f"ftdz_{stem}.fits"
        single = workspace_dir / f"cccftdz_{stem}.fits"
        if manual.exists() and helper.exists():
            with fits.open(manual) as hdul_a, fits.open(helper) as hdul_b:
                manual_vs_helper = array_metrics(hdul_a[0].data, hdul_b[0].data)
        else:
            manual_vs_helper = None
        comparisons[stem] = {
            "manual_vs_helper": manual_vs_helper,
            "manual_output": public_path(manual) if manual.exists() else None,
            "helper_output": public_path(helper) if helper.exists() else None,
            "single_image_output": public_path(single) if single.exists() else None,
            "manual_change_stats": file_metrics(original, manual) if original.exists() and manual.exists() else None,
            "single_change_stats": file_metrics(original, single) if original.exists() and single.exists() else None,
        }
    return comparisons


def build_report(payload: dict) -> str:
    lines = [
        "# TEAREDUCE Cookbook Fallback: cr2images",
        "",
        "## Selected fallback path",
        f"- Notebook: `{payload['notebook']}`",
        f"- Source mode: `{payload['source_mode']}`",
        f"- TEAREDUCE in launcher Python: `{payload['teareduce'].get('version') or 'not detected'}`; selected notebook kernel version not verified.",
        f"- Notebook execution status: `{payload['teareduce_run']['assessment']['status']}`",
        "",
        "## Why this fallback exists",
        "- It replaces the missing local `TEA_procesado_INT` tree with the official TEAREDUCE cookbook sample pair for cosmic-ray cleaning.",
        "- It keeps the notebook-first pedagogy but no longer depends on the absent practice directory tree.",
        "",
        "## Output comparison",
    ]
    for stem, info in payload["comparisons"].items():
        metrics = info.get("manual_vs_helper") or {}
        manual_change = info.get("manual_change_stats") or {}
        lines.extend(
            [
                f"### Pair member {stem}",
                f"- Manual notebook output: `{info.get('manual_output')}`",
                f"- Helper-function output: `{info.get('helper_output')}`",
                f"- Manual vs helper mean abs diff: `{metrics.get('mean_abs_diff', 0):.6g}`",
                f"- Manual vs helper max abs diff: `{metrics.get('max_abs_diff', 0):.6g}`",
                f"- Manual vs helper allclose (`atol=1e-6`): `{metrics.get('allclose_atol_1e-6')}`",
                f"- Changed pixels in the manual cleaned image: `{manual_change.get('changed_pixel_count')}`",
                f"- Fraction of changed pixels: `{manual_change.get('changed_fraction', 0):.6g}`",
                f"- Maximum absolute correction: `{manual_change.get('max_abs_change', 0):.6g}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommendation",
            "- Use the official cookbook fallback when the local `TEA_procesado_INT` tree is missing but you still want a real TEAREDUCE cosmic-ray workflow.",
            "- Use the local practice notebooks only when the full processed practice tree is available and you want the exact classroom dataset.",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    bootstrap = bootstrap_runtime_dirs()
    args = parse_args()
    require_trusted_notebook_code("teareduce_cookbook_cr2images_workflow", args.trust_notebook_code)
    output_dir = Path(args.output_dir)
    report_path = Path(args.report_md) if args.report_md else output_dir / "report.md"
    block_notebook_output_collisions(
        "teareduce_cookbook_cr2images_workflow",
        notebook_paths=[Path(args.notebook)] if args.notebook else [],
        extra_paths=args.sample,
        outputs=[
            ("--summary-json", args.summary_json),
            ("--report-md/default", report_path),
            ("--manifest-json", args.manifest_json),
        ],
        output_dirs=[("--output-dir", output_dir)],
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    notebook_path = prepare_notebook(args, output_dir)
    samples = prepare_samples(args, output_dir)
    if len(samples) < 2:
        raise SystemExit("At least the two sample FITS files for cr2images are required.")

    run = execute_copy(
        notebook_path,
        output_dir / "teareduce_copy",
        kernel_name=args.kernel_name,
        timeout_sec=args.timeout_sec,
        extra_stage_paths=[str(path) for path in samples],
    )
    if not run["success"]:
        raise SystemExit(f"cr2images fallback notebook execution failed: {run['assessment']['reason']}")

    workspace_dir = Path(run["workspace_dir"])
    comparisons = compare_outputs(workspace_dir)

    payload = {
        "tool": "teareduce_cookbook_cr2images_workflow",
        "environment": environment_summary(extra={"runtime_overrides": bootstrap}),
        "notebook": public_path(notebook_path),
        "source_mode": "local_notebook" if args.notebook else "official_download",
        "notebook_scan": scan_notebook(notebook_path),
        "teareduce": inspect_teareduce_environment(),
        "samples": [public_path(path) for path in samples],
        "teareduce_run": run,
        "comparisons": comparisons,
    }
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")

    report_path.write_text(build_report(sanitize_payload(payload)), encoding="utf-8")

    outputs = [Path(run["executed_copy"]), report_path]
    if args.summary_json:
        Path(args.summary_json).write_text(rendered, encoding="utf-8")
        outputs.append(Path(args.summary_json))
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[notebook_path, *samples],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "fetch_official_samples": args.fetch_official_samples,
            },
            command="teareduce_cookbook_cr2images_workflow.py",
            notes=[
                "Runs the official TEAREDUCE cr2images cookbook notebook in a copied workspace.",
                "Quantifies the agreement between the manual notebook write path and apply_cr2images_ccddata outputs.",
            ],
            extra={"comparisons": comparisons, "teareduce_version": payload["teareduce"].get("version"), "teareduce_version_scope": "launcher_python_only"},
        )


if __name__ == "__main__":
    main()
