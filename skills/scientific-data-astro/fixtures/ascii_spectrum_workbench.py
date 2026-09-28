#!/usr/bin/env python3
"""Inspect and compare simple 1D ASCII spectra, especially two-column coursework files."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload, emit_payload_best_effort
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.runtime_common import configure_runtime, suppress_fd_output


def lazy_imports():
    configure_runtime("ascii_spectrum_workbench")
    with suppress_fd_output(True):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from scipy.ndimage import median_filter

    return plt, np, median_filter


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="ASCII spectra to inspect.")
    parser.add_argument("--output-dir", required=True, help="Directory for summaries, plots, and reports.")
    parser.add_argument(
        "--line-window",
        nargs=3,
        action="append",
        metavar=("LABEL", "XMIN", "XMAX"),
        default=[],
        help="Optional line window to characterize, e.g. Halpha 6555 6570. Repeat as needed.",
    )
    parser.add_argument("--summary-json")
    parser.add_argument("--manifest-json")
    return parser.parse_args()


def parse_ascii_spectrum(path: Path):
    _, np, _ = lazy_imports()
    wavelengths = []
    fluxes = []
    nonfinite_rows = []
    for line_number, raw in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace(",", " ")
        parts = [item for item in line.split() if item]
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except Exception:
            continue
        if not math.isfinite(x) or not math.isfinite(y):
            nonfinite_rows.append(line_number)
            continue
        wavelengths.append(x)
        fluxes.append(y)
    if nonfinite_rows:
        excerpt = ", ".join(str(item) for item in nonfinite_rows[:8])
        suffix = "..." if len(nonfinite_rows) > 8 else ""
        raise SystemExit(
            f"{path.name} contains {len(nonfinite_rows)} non-finite wavelength/flux row(s) "
            f"at line(s) {excerpt}{suffix}; refusing to publish NaN/Inf diagnostics."
        )
    if len(wavelengths) < 10:
        raise SystemExit(f"{path.name} does not look like a usable 1D ASCII spectrum with at least 10 rows.")
    return np.asarray(wavelengths, dtype=float), np.asarray(fluxes, dtype=float)


def window_characterization(wavelength, flux, label: str, xmin: float, xmax: float):
    _, np, _ = lazy_imports()
    mask = (wavelength >= xmin) & (wavelength <= xmax)
    if np.sum(mask) < 3:
        return {"label": label, "xmin": xmin, "xmax": xmax, "covered": False}
    xs = wavelength[mask]
    ys = flux[mask]
    continuum = float(np.median(ys))
    peak_index = int(np.argmax(ys))
    trough_index = int(np.argmin(ys))
    peak_height = float(ys[peak_index] - continuum)
    trough_depth = float(continuum - ys[trough_index])
    if peak_height > trough_depth:
        kind = "emission-like"
        amplitude = peak_height
        center = float(xs[peak_index])
    else:
        kind = "absorption-like"
        amplitude = trough_depth
        center = float(xs[trough_index])
    local_mad = float(np.median(np.abs(ys - np.median(ys))))
    local_sigma_proxy = 1.4826 * local_mad if local_mad > 0 else float(np.std(ys))
    feature_strength_sigma = amplitude / local_sigma_proxy if local_sigma_proxy > 0 else None
    if feature_strength_sigma is None:
        support_level = "undetermined"
    elif feature_strength_sigma < 3:
        support_level = "weak"
    elif feature_strength_sigma < 6:
        support_level = "tentative"
    else:
        support_level = "moderate"
    return {
        "label": label,
        "xmin": xmin,
        "xmax": xmax,
        "covered": True,
        "continuum_proxy": continuum,
        "line_character": kind,
        "feature_proxy": True,
        "feature_amplitude": amplitude,
        "feature_center": center,
        "local_sigma_proxy": local_sigma_proxy,
        "feature_strength_sigma": feature_strength_sigma,
        "support_level": support_level,
        "peak_flux": float(np.max(ys)),
        "trough_flux": float(np.min(ys)),
        "caution": "Window-level feature labels are heuristic QA aids only and should not be treated as automatic astrophysical identifications.",
    }


def profile_spectrum(path: Path, line_windows: list[list[str]]):
    _, np, median_filter = lazy_imports()
    wavelength, flux = parse_ascii_spectrum(path)
    diffs = np.diff(wavelength)
    monotonic_increasing = bool(np.all(diffs > 0))
    non_decreasing = bool(np.all(diffs >= 0))
    spacing = diffs[np.isfinite(diffs)]
    smooth = median_filter(flux, size=max(5, min(len(flux) // 40 * 2 + 1, 101)))
    residual = flux - smooth
    mad = float(np.median(np.abs(residual - np.median(residual))))
    sigma_proxy = 1.4826 * mad if mad > 0 else float(np.std(residual))
    outlier_threshold = 8.0 * sigma_proxy if sigma_proxy > 0 else None
    if outlier_threshold:
        outlier_mask = np.abs(residual) > outlier_threshold
        outlier_fraction = float(np.mean(outlier_mask))
        outlier_count = int(np.sum(outlier_mask))
    else:
        outlier_fraction = 0.0
        outlier_count = 0
    continuum_norm = np.percentile(flux, 95)
    if continuum_norm == 0:
        normalized_flux = flux
    else:
        normalized_flux = flux / continuum_norm
    windows = [
        window_characterization(wavelength, flux, label, float(xmin), float(xmax))
        for label, xmin, xmax in line_windows
    ]
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "samples": int(len(wavelength)),
        "wavelength_min": float(np.min(wavelength)),
        "wavelength_max": float(np.max(wavelength)),
        "flux_min": float(np.min(flux)),
        "flux_max": float(np.max(flux)),
        "flux_median": float(np.median(flux)),
        "flux_std": float(np.std(flux)),
        "monotonic_increasing": monotonic_increasing,
        "non_decreasing": non_decreasing,
        "has_duplicate_wavelengths": bool(np.any(diffs == 0)),
        "median_spacing": float(np.median(spacing)) if spacing.size else None,
        "mean_spacing": float(np.mean(spacing)) if spacing.size else None,
        "sigma_proxy": sigma_proxy,
        "outlier_fraction": outlier_fraction,
        "outlier_count": outlier_count,
        "continuum_normalization_p95": float(continuum_norm),
        "line_windows": windows,
        "quality_flags": [
            item
            for item in [
                None if monotonic_increasing else "Wavelength axis is not strictly increasing.",
                None if outlier_fraction < 0.02 else "Spectrum contains a noticeable fraction of spike-like outliers.",
                None if len(wavelength) >= 100 else "Spectrum has relatively few samples; classification features may be undersampled.",
                (
                    "Requested line-window summaries are heuristic feature proxies and need manual physical interpretation."
                    if line_windows
                    else None
                ),
            ]
            if item
        ],
        "preview_points": {
            "wavelength": wavelength[:8].tolist(),
            "flux": flux[:8].tolist(),
            "normalized_flux": normalized_flux[:8].tolist(),
        },
    }


def write_inventory_csv(path: Path, profiles: list[dict]):
    fieldnames = [
        "name",
        "samples",
        "wavelength_min",
        "wavelength_max",
        "monotonic_increasing",
        "median_spacing",
        "sigma_proxy",
        "outlier_fraction",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in profiles:
            writer.writerow({key: item.get(key) for key in fieldnames})


def write_overlay_plot(path: Path, profiles: list[dict], normalized: bool):
    plt, np, _ = lazy_imports()
    fig = plt.figure(figsize=(8.6, 5.0))
    ax = fig.add_subplot(111)
    for item in profiles:
        wavelength, flux = parse_ascii_spectrum(Path(item["path"]))
        if normalized:
            scale = item["continuum_normalization_p95"] or 1.0
            flux = flux / scale if scale else flux
        ax.plot(wavelength, flux, lw=1.0, label=Path(item["path"]).stem)
    ax.set_xlabel("Wavelength")
    ax.set_ylabel("Normalized flux" if normalized else "Flux")
    ax.set_title("ASCII spectra comparison" + (" (normalized)" if normalized else ""))
    ax.grid(True, alpha=0.25)
    if len(profiles) <= 8:
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_report(path: Path, profiles: list[dict], outputs: dict[str, Path]):
    lines = ["# ASCII Spectrum Workbench Report", ""]
    lines.extend(
        [
            "This report is a QA and comparison layer for reduced ASCII spectra.",
            "Requested line-window summaries are heuristic feature proxies only; they are not automatic spectral classifications or secure line identifications.",
            "",
        ]
    )
    lines.append("## Spectra")
    lines.append("")
    for item in profiles:
        lines.extend(
            [
                f"- `{item['name']}`: `{item['samples']}` samples, range `{item['wavelength_min']:.3f}` to `{item['wavelength_max']:.3f}`, monotonic=`{item['monotonic_increasing']}`, outlier_fraction=`{item['outlier_fraction']:.4f}`",
            ]
        )
        for flag in item["quality_flags"]:
            lines.append(f"  - flag: {flag}")
        for window in item["line_windows"]:
            if window.get("covered"):
                lines.append(
                    f"  - window `{window['label']}`: tentative `{window['line_character']}` feature proxy near `{window['feature_center']:.4f}` with amplitude `{window['feature_amplitude']:.6g}`, support=`{window['support_level']}`, strength~`{(window['feature_strength_sigma'] or 0):.2f} sigma`"
                )
            else:
                lines.append(f"  - window `{window['label']}`: not sufficiently covered in this spectrum.")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Inventory: `{public_path(outputs['inventory'])}`",
            f"- Raw overlay: `{public_path(outputs['overlay_raw'])}`",
            f"- Normalized overlay: `{public_path(outputs['overlay_norm'])}`",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_workbench(args) -> int:
    output_dir = Path(args.output_dir)
    profiles = [profile_spectrum(Path(raw), args.line_window) for raw in args.inputs]
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_csv = output_dir / "spectrum_inventory.csv"
    overlay_raw = output_dir / "overlay_raw.png"
    overlay_norm = output_dir / "overlay_normalized.png"
    report_md = output_dir / "report.md"
    summary_json = Path(args.summary_json) if args.summary_json else output_dir / "summary.json"

    write_inventory_csv(inventory_csv, profiles)
    write_overlay_plot(overlay_raw, profiles, normalized=False)
    write_overlay_plot(overlay_norm, profiles, normalized=True)
    write_report(
        report_md,
        profiles,
        outputs={"inventory": inventory_csv, "overlay_raw": overlay_raw, "overlay_norm": overlay_norm},
    )

    notes = [
        "This workflow is designed for simple reduced 1D ASCII spectra, especially two-column coursework files.",
        "Use it as a fast QA and comparison layer before classification or write-up work.",
    ]
    findings = [flag for profile in profiles for flag in profile.get("quality_flags", [])]
    legacy = sanitize_payload(
        {
            "tool": "ascii_spectrum_workbench",
            "spectra": profiles,
            "line_windows_requested": args.line_window,
            "outputs": {
                "inventory_csv": str(inventory_csv),
                "overlay_raw": str(overlay_raw),
                "overlay_normalized": str(overlay_norm),
                "report_md": str(report_md),
            },
            "notes": notes,
        }
    )
    payload = build_tool_payload(
        "ascii_spectrum_workbench",
        status="warning" if findings else "ok",
        notes=notes,
        artifacts={
            "summary_json": str(summary_json),
            "inventory_csv": str(inventory_csv),
            "overlay_raw": str(overlay_raw),
            "overlay_normalized": str(overlay_norm),
            "report_md": str(report_md),
        },
        results={"spectra": profiles, "line_windows_requested": args.line_window},
        qa={
            "status": "warning" if findings else "ok",
            "findings": findings,
            "metrics": {"spectrum_count": len(profiles), "finding_count": len(findings)},
        },
        legacy=legacy,
    )
    emit_payload(payload, summary_json)
    outputs = [inventory_csv, overlay_raw, overlay_norm, report_md, summary_json]
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[Path(item) for item in args.inputs],
            outputs=outputs,
            parameters={"line_window": args.line_window},
            command="ascii_spectrum_workbench.py",
            notes=notes,
        )
    return 0


def emit_blocked(args, message: str) -> int:
    summary_json = Path(args.summary_json) if args.summary_json else Path(args.output_dir) / "summary.json"
    payload = build_blocked_payload(
        "ascii_spectrum_workbench",
        message,
        notes=["ASCII spectrum processing stopped before publishing scientific diagnostics."],
        artifacts={"summary_json": str(summary_json), "output_dir": args.output_dir},
        results={"inputs": [public_path(Path(item)) for item in args.inputs]},
        inputs=[Path(item) for item in args.inputs],
    )
    emit_payload_best_effort(payload, summary_json)
    return 2


def main() -> int:
    args = parse_args()
    try:
        return run_workbench(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return emit_blocked(args, str(exc) or "ASCII spectrum processing was blocked.")
    except Exception as exc:
        return emit_blocked(args, f"ASCII spectrum processing was blocked: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
