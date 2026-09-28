#!/usr/bin/env python3
"""Run the short canonical TEAREDUCE smoke test across bias, flat, cr2images, and wavecal."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from _internal.public_contract import build_blocked_payload
from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


BIAS_NOTEBOOK = "P2_03_correccion_bias.ipynb"
FLAT_NOTEBOOK = "P2_04_correccion_flat.ipynb"
CR2_NOTEBOOK = "cr2images.ipynb"
WAVECAL_NOTEBOOK = "wavecalib.ipynb"

FILTER_SIDECAR_NAMES = {
    "49": ["filter_NOT_49.txt", "49.txt"],
    "76": ["filter_NOT_76.txt", "76.txt"],
    "78": ["filter_NOT_78.txt", "78.txt"],
}

CR2_SAMPLE_NAMES = ["ftdz_45243.fits", "ftdz_45244.fits"]
WAVECAL_SAMPLE_NAMES = ["ftdz_45324.fits"]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Directory for route outputs and the final summary.")
    parser.add_argument("--search-root", action="append", default=[], help="Root to search recursively for local notebooks.")
    parser.add_argument("--bias-notebook", help="Optional explicit path to P2_03_correccion_bias.ipynb.")
    parser.add_argument("--flat-notebook", help="Optional explicit path to P2_04_correccion_flat.ipynb.")
    parser.add_argument("--cr2-notebook", help="Optional explicit path to cr2images.ipynb.")
    parser.add_argument("--wavecal-notebook", help="Optional explicit path to wavecalib.ipynb.")
    parser.add_argument("--kernel-name", default="python3", help="Kernel name for copied notebook execution.")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="Per-cell execution timeout.")
    parser.add_argument("--trust-notebook-code", action="store_true", help="Confirm that every auto-discovered or explicit notebook is trusted.")
    parser.add_argument("--summary-json", help="Optional JSON summary path.")
    parser.add_argument("--manifest-json", help="Optional manifest path.")
    return parser.parse_args()


def default_search_roots() -> list[Path]:
    home = Path.home()
    return [home / "Desktop", home / "Documents"]


def iter_search_roots(explicit: list[str]) -> list[Path]:
    if explicit:
        roots = [Path(raw).expanduser().resolve() for raw in explicit]
    else:
        roots = default_search_roots()
    deduped: list[Path] = []
    seen = set()
    for item in roots:
        if not item.exists():
            continue
        key = str(item)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def resolve_notebook(explicit: str | None, filename: str, search_roots: list[Path]) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.exists() else None
    for root in search_roots:
        match = safe_find_first(root, filename)
        if match is not None:
            return match
    return None


def safe_walk_files(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                directories: list[Path] = []
                files: list[Path] = []
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            files.append(Path(entry.path))
                    except (InterruptedError, PermissionError, OSError):
                        continue
        except (InterruptedError, PermissionError, OSError):
            continue
        for file_path in sorted(files):
            yield file_path
        stack.extend(sorted(directories, reverse=True))


def safe_find_first(root: Path, filename: str) -> Path | None:
    for file_path in safe_walk_files(root):
        if file_path.name == filename:
            return file_path.resolve()
    return None


def resolve_sample_paths(names: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for name in names:
        tmp_path = Path("/tmp") / name
        if tmp_path.exists():
            resolved.append(tmp_path.resolve())
    return resolved


def resolve_sidecars(search_roots: list[Path]) -> list[Path]:
    resolved: list[Path] = []
    for candidates in FILTER_SIDECAR_NAMES.values():
        found = None
        for name in candidates:
            tmp_path = Path("/tmp") / name
            if tmp_path.exists():
                found = tmp_path.resolve()
                break
            for root in search_roots:
                found = safe_find_first(root, name)
                if found is not None:
                    break
            if found:
                break
        if found:
            resolved.append(found)
    deduped: list[Path] = []
    seen = set()
    for item in resolved:
        key = str(item)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def compact_metrics(payload: dict, route_name: str) -> dict:
    if route_name == "bias":
        metrics = (((payload.get("comparison") or {}).get("master_bias_metrics")) or {})
        return {
            "mean_abs_diff": metrics.get("mean_abs_diff"),
            "max_abs_diff": metrics.get("max_abs_diff"),
            "allclose_atol_1e-6": metrics.get("allclose_atol_1e-6"),
        }
    if route_name == "flat":
        filters = payload.get("filters") or {}
        return {
            filter_id: {
                "mean_abs_diff": info.get("master_metrics", {}).get("mean_abs_diff"),
                "max_abs_diff": info.get("master_metrics", {}).get("max_abs_diff"),
                "allclose_atol_1e-6": info.get("sample_metrics", {}).get("allclose_atol_1e-6"),
            }
            for filter_id, info in filters.items()
        }
    if route_name == "cr2images":
        comparisons = payload.get("comparisons") or {}
        return {
            stem: {
                "mean_abs_diff": info.get("manual_vs_helper", {}).get("mean_abs_diff") if info.get("manual_vs_helper") else None,
                "max_abs_diff": info.get("manual_vs_helper", {}).get("max_abs_diff") if info.get("manual_vs_helper") else None,
                "allclose_atol_1e-6": info.get("manual_vs_helper", {}).get("allclose_atol_1e-6") if info.get("manual_vs_helper") else None,
            }
            for stem, info in comparisons.items()
        }
    if route_name == "wavecal":
        metrics = (((payload.get("comparison") or {}).get("manual_vs_helper")) or {})
        axis = (((payload.get("comparison") or {}).get("header_axis_comparison")) or {})
        return {
            "mean_abs_diff": metrics.get("mean_abs_diff"),
            "max_abs_diff": metrics.get("max_abs_diff"),
            "allclose_atol_1e-6": metrics.get("allclose_atol_1e-6"),
            "physically_equivalent_axis": axis.get("physically_equivalent_axis"),
        }
    return {}


def run_route(route_name: str, cmd: list[str], route_dir: Path, summary_path: Path, report_path: Path) -> dict:
    route_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    stderr = clean_known_stderr(completed.stderr or "")
    stdout = clean_known_stderr(completed.stdout or "")
    payload = None
    if summary_path.exists():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
    status = "pass" if completed.returncode == 0 and payload is not None else "fail"
    result = {
        "route": route_name,
        "status": status,
        "returncode": completed.returncode,
        "summary_json": public_path(summary_path) if summary_path.exists() else None,
        "report_md": public_path(report_path) if report_path.exists() else None,
        "stderr": stderr,
    }
    if payload is not None:
        result["metrics"] = compact_metrics(payload, route_name)
    elif stdout:
        result["stdout_excerpt"] = stdout[-1200:]
    return result


def missing_route(route_name: str, reason: str, recommendation: str) -> dict:
    return {
        "route": route_name,
        "status": "missing_input",
        "reason": reason,
        "recommendation": recommendation,
    }


def main():
    runtime_dir = configure_runtime("teareduce_smoke_test")
    args = parse_args()
    if not args.trust_notebook_code:
        message = (
            "TEAREDUCE smoke execution can run auto-discovered arbitrary notebook code and is blocked by default. "
            "Review or explicitly select every notebook, then pass --trust-notebook-code."
        )
        payload = build_blocked_payload(
            "teareduce_smoke_test",
            message,
            artifacts={},
            results={"error_type": "untrusted_notebook_code"},
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False))
        raise SystemExit(2)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    search_roots = iter_search_roots(args.search_root)
    bias_notebook = resolve_notebook(args.bias_notebook, BIAS_NOTEBOOK, search_roots)
    flat_notebook = resolve_notebook(args.flat_notebook, FLAT_NOTEBOOK, search_roots)
    cr2_notebook = resolve_notebook(args.cr2_notebook, CR2_NOTEBOOK, search_roots)
    wavecal_notebook = resolve_notebook(args.wavecal_notebook, WAVECAL_NOTEBOOK, search_roots)

    routes: list[dict] = []
    python_exe = sys.executable
    scripts_dir = Path(__file__).resolve().parent

    if bias_notebook:
        route_dir = output_dir / "bias"
        summary_path = route_dir / "summary.json"
        report_path = route_dir / "report.md"
        cmd = [
            python_exe,
            str(scripts_dir / "teareduce_master_bias_workflow.py"),
            str(bias_notebook),
            "--output-dir",
            str(route_dir),
            "--kernel-name",
            args.kernel_name,
            "--timeout-sec",
            str(args.timeout_sec),
            "--trust-notebook-code",
            "--limit-science-products",
            "1",
            "--summary-json",
            str(summary_path),
            "--report-md",
            str(report_path),
            "--manifest-json",
            str(route_dir / "manifest.json"),
        ]
        routes.append(run_route("bias", cmd, route_dir, summary_path, report_path))
    else:
        routes.append(
            missing_route(
                "bias",
                f"Could not locate `{BIAS_NOTEBOOK}`.",
                "Pass --bias-notebook or add the course folder through --search-root.",
            )
        )

    if flat_notebook:
        route_dir = output_dir / "flat"
        summary_path = route_dir / "summary.json"
        report_path = route_dir / "report.md"
        flat_sidecars = resolve_sidecars(search_roots)
        cmd = [
            python_exe,
            str(scripts_dir / "teareduce_flat_workflow.py"),
            str(flat_notebook),
            "--output-dir",
            str(route_dir),
            "--kernel-name",
            args.kernel_name,
            "--timeout-sec",
            str(args.timeout_sec),
            "--trust-notebook-code",
            "--limit-science-products-per-filter",
            "1",
            "--summary-json",
            str(summary_path),
            "--report-md",
            str(report_path),
            "--manifest-json",
            str(route_dir / "manifest.json"),
        ]
        if len(flat_sidecars) == 3:
            for item in flat_sidecars:
                cmd.extend(["--sidecar", str(item)])
        else:
            cmd.append("--fetch-official-sidecars")
        routes.append(run_route("flat", cmd, route_dir, summary_path, report_path))
    else:
        routes.append(
            missing_route(
                "flat",
                f"Could not locate `{FLAT_NOTEBOOK}`.",
                "Pass --flat-notebook or add the course folder through --search-root.",
            )
        )

    cr2_samples = resolve_sample_paths(CR2_SAMPLE_NAMES)
    if cr2_notebook or len(cr2_samples) == len(CR2_SAMPLE_NAMES):
        route_dir = output_dir / "cr2images"
        summary_path = route_dir / "summary.json"
        report_path = route_dir / "report.md"
        cmd = [
            python_exe,
            str(scripts_dir / "teareduce_cookbook_cr2images_workflow.py"),
            "--output-dir",
            str(route_dir),
            "--kernel-name",
            args.kernel_name,
            "--timeout-sec",
            str(args.timeout_sec),
            "--trust-notebook-code",
            "--summary-json",
            str(summary_path),
            "--report-md",
            str(report_path),
            "--manifest-json",
            str(route_dir / "manifest.json"),
        ]
        if cr2_notebook:
            cmd.extend(["--notebook", str(cr2_notebook)])
        if cr2_samples:
            for item in cr2_samples:
                cmd.extend(["--sample", str(item)])
        else:
            cmd.append("--fetch-official-samples")
        routes.append(run_route("cr2images", cmd, route_dir, summary_path, report_path))
    else:
        routes.append(
            missing_route(
                "cr2images",
                f"Could not locate `{CR2_NOTEBOOK}` or the official sample FITS in `/tmp`.",
                "Pass --cr2-notebook and stage the cookbook sample FITS, or let the workflow fetch them when network access is available.",
            )
        )

    wavecal_samples = resolve_sample_paths(WAVECAL_SAMPLE_NAMES)
    if wavecal_notebook or len(wavecal_samples) == len(WAVECAL_SAMPLE_NAMES):
        route_dir = output_dir / "wavecal"
        summary_path = route_dir / "summary.json"
        report_path = route_dir / "report.md"
        cmd = [
            python_exe,
            str(scripts_dir / "teareduce_cookbook_wavecal_workflow.py"),
            "--output-dir",
            str(route_dir),
            "--kernel-name",
            args.kernel_name,
            "--timeout-sec",
            str(args.timeout_sec),
            "--trust-notebook-code",
            "--summary-json",
            str(summary_path),
            "--report-md",
            str(report_path),
            "--manifest-json",
            str(route_dir / "manifest.json"),
        ]
        if wavecal_notebook:
            cmd.extend(["--notebook", str(wavecal_notebook)])
        if wavecal_samples:
            for item in wavecal_samples:
                cmd.extend(["--sample", str(item)])
        else:
            cmd.append("--fetch-official-samples")
        routes.append(run_route("wavecal", cmd, route_dir, summary_path, report_path))
    else:
        routes.append(
            missing_route(
                "wavecal",
                f"Could not locate `{WAVECAL_NOTEBOOK}` or the official sample FITS in `/tmp`.",
                "Pass --wavecal-notebook and stage the cookbook sample FITS, or let the workflow fetch them when network access is available.",
            )
        )

    overall_status = "PASS" if all(route["status"] == "pass" for route in routes) else "CHECK"
    payload = {
        "tool": "teareduce_smoke_test",
        "environment": environment_summary(extra={"runtime_dir": str(runtime_dir)}),
        "search_roots": [public_path(path) for path in search_roots],
        "routes": routes,
        "overall_status": overall_status,
        "notes": [
            "This smoke test checks the four canonical TEAREDUCE routes currently consolidated inside the skill.",
            "Bias and flat depend on the local classroom notebooks; cr2images and wavecal can fall back to cookbook samples.",
        ],
    }
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")

    if args.summary_json:
        summary_path = Path(args.summary_json)
    else:
        summary_path = output_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(rendered, encoding="utf-8")

    if args.manifest_json:
        outputs = [summary_path]
        write_manifest(
            args.manifest_json,
            inputs=[path for path in [bias_notebook, flat_notebook, cr2_notebook, wavecal_notebook] if path],
            outputs=outputs,
            parameters={
                "kernel_name": args.kernel_name,
                "timeout_sec": args.timeout_sec,
                "search_roots": [str(path) for path in search_roots],
            },
            command="teareduce_smoke_test.py",
            notes=payload["notes"],
            extra={"routes": routes, "overall_status": overall_status},
        )

    raise SystemExit(0 if overall_status == "PASS" else 1)


if __name__ == "__main__":
    main()
