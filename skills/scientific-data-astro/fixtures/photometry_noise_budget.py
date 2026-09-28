#!/usr/bin/env python3
"""Estimate a practical imaging/photometry noise budget and resulting SNR."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload, resolve_output_path
from _internal.provenance_utils import public_path, write_manifest
from _internal.runtime_common import configure_runtime


configure_runtime("photometry_noise_budget")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=float, required=True, help="Source signal per frame inside the aperture.")
    parser.add_argument("--sky-per-pixel", type=float, default=0.0, help="Sky background per pixel per frame.")
    parser.add_argument("--dark-per-pixel", type=float, default=0.0, help="Dark current per pixel per frame.")
    parser.add_argument("--read-noise", type=float, required=True, help="Read noise per pixel per frame in electrons.")
    parser.add_argument("--n-pixels", type=float, required=True, help="Effective number of pixels in the aperture.")
    parser.add_argument(
        "--sky-estimate-pixels",
        type=float,
        help="Optional number of pixels used to estimate the background. Adds the sky-estimation variance term.",
    )
    parser.add_argument("--n-frames", type=int, default=1, help="Number of frames combined in the final measurement.")
    parser.add_argument("--units", choices=["electrons", "adu"], default="electrons", help="Units used for source/sky/dark counts.")
    parser.add_argument("--gain", type=float, default=1.0, help="Gain in electrons per ADU when --units=adu.")
    parser.add_argument("--summary-json", help="Optional summary JSON using the standard top-level envelope.")
    parser.add_argument("--output-json", help="Optional summary JSON.")
    parser.add_argument("--report-md", help="Optional markdown summary report.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    return parser.parse_args()


def to_electrons(value: float, units: str, gain: float) -> float:
    return value * gain if units == "adu" else value


def finite_float(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite.")
    return value


def nonnegative_float(value: float, label: str) -> float:
    finite_float(value, label)
    if value < 0:
        raise ValueError(f"{label} must be non-negative.")
    return value


def positive_float(value: float, label: str) -> float:
    finite_float(value, label)
    if value <= 0:
        raise ValueError(f"{label} must be positive.")
    return value


def json_safe_number(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def validate_args(args):
    nonnegative_float(args.source, "--source")
    nonnegative_float(args.sky_per_pixel, "--sky-per-pixel")
    nonnegative_float(args.dark_per_pixel, "--dark-per-pixel")
    nonnegative_float(args.read_noise, "--read-noise")
    positive_float(args.n_pixels, "--n-pixels")
    positive_float(float(args.n_frames), "--n-frames")
    positive_float(args.gain, "--gain")
    if args.sky_estimate_pixels is not None:
        positive_float(args.sky_estimate_pixels, "--sky-estimate-pixels")
    for label, raw_path in (
        ("--summary-json", args.summary_json),
        ("--output-json", args.output_json),
        ("--report-md", args.report_md),
        ("--manifest-json", args.manifest_json),
    ):
        validate_output_target(raw_path, label)


def validate_output_target(raw_path: str | None, label: str) -> None:
    if not raw_path:
        return
    path = Path(raw_path)
    if path.exists() and path.is_dir():
        raise ValueError(f"{label} must point to a file, not a directory.")
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise ValueError(f"{label} parent is not a directory: {parent}")


def summary_json_path(args) -> Path | None:
    return resolve_output_path(args.summary_json, args.output_json)


def emit_blocked(args, message: str) -> int:
    output_path = summary_json_path(args)
    payload = build_blocked_payload(
        "photometry_noise_budget",
        message,
        notes=[
            "The noise budget was not computed because the supplied inputs are physically invalid or incomplete.",
            "Counts and noise terms must be finite; source, sky, dark, and read noise cannot be negative.",
        ],
        artifacts={
            "summary_json": str(output_path) if output_path else None,
            "report_md": None,
            "manifest_json": None,
        },
        results={
            "blocked_reason": message,
            "parameters": {
                "source": json_safe_number(args.source),
                "sky_per_pixel": json_safe_number(args.sky_per_pixel),
                "dark_per_pixel": json_safe_number(args.dark_per_pixel),
                "read_noise": json_safe_number(args.read_noise),
                "n_pixels": json_safe_number(args.n_pixels),
                "sky_estimate_pixels": json_safe_number(args.sky_estimate_pixels),
                "n_frames": json_safe_number(args.n_frames),
                "units": args.units,
                "gain": json_safe_number(args.gain),
            },
        },
    )
    try:
        emit_payload(payload, output_path)
    except OSError:
        emit_payload(payload, None)
    return 2


def classify_regime(variance_terms: dict[str, float]) -> str:
    total = sum(variance_terms.values())
    if total <= 0:
        return "undefined"
    source_fraction = variance_terms["source_shot_variance_e2"] / total
    sky_like_fraction = (
        variance_terms["sky_variance_e2"]
        + variance_terms["dark_variance_e2"]
        + variance_terms["background_estimate_variance_e2"]
    ) / total
    read_fraction = variance_terms["read_variance_e2"] / total
    if source_fraction >= 0.5:
        return "source-shot-noise-limited"
    if sky_like_fraction >= 0.5:
        return "background-limited"
    if read_fraction >= 0.5:
        return "read-noise-limited"
    return "mixed-regime"


def write_report(path: Path, summary: dict):
    lines = [
        "# Photometry Noise Budget",
        "",
        "## Inputs",
        "",
        f"- Units in: `{summary['units_in']}`",
        f"- Frames combined: `{summary['n_frames']}`",
        f"- Aperture pixels: `{summary['n_pixels']}`",
        f"- Background-estimate pixels: `{summary['sky_estimate_pixels']}`",
        "",
        "## Results",
        "",
        f"- Total source electrons: `{summary['signal_electrons']['source_total_e']:.6f}`",
        f"- Total noise: `{summary['total_noise_e']:.6f}` e-",
        f"- SNR: `{summary['snr']}`",
        f"- Dominant noise term: `{summary['dominant_noise_term']}`",
        f"- Regime: `{summary['operating_regime']}`",
        "",
        "## Variance Fractions",
        "",
    ]
    for name, value in summary["variance_fractions"].items():
        lines.append(f"- `{name}`: `{value:.4f}`")
    lines.extend(["", "## Notes", ""])
    lines.extend([f"- {item}" for item in summary["notes"]])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_noise_budget(args) -> int:
    validate_args(args)

    source_per_frame_e = to_electrons(args.source, args.units, args.gain)
    sky_per_pixel_e = to_electrons(args.sky_per_pixel, args.units, args.gain)
    dark_per_pixel_e = to_electrons(args.dark_per_pixel, args.units, args.gain)

    source_e = source_per_frame_e * args.n_frames
    sky_e = sky_per_pixel_e * args.n_pixels * args.n_frames
    dark_e = dark_per_pixel_e * args.n_pixels * args.n_frames
    read_var_e = (args.read_noise**2) * args.n_pixels * args.n_frames
    source_var_e = max(source_e, 0.0)
    sky_var_e = max(sky_e, 0.0)
    dark_var_e = max(dark_e, 0.0)
    background_per_pixel_variance = (
        sky_per_pixel_e * args.n_frames
        + dark_per_pixel_e * args.n_frames
        + (args.read_noise**2) * args.n_frames
    )
    if args.sky_estimate_pixels:
        background_estimate_var = (args.n_pixels**2 / args.sky_estimate_pixels) * background_per_pixel_variance
    else:
        background_estimate_var = 0.0

    variance_terms = {
        "source_shot_variance_e2": source_var_e,
        "sky_variance_e2": sky_var_e,
        "dark_variance_e2": dark_var_e,
        "read_variance_e2": read_var_e,
        "background_estimate_variance_e2": background_estimate_var,
    }
    total_variance = sum(variance_terms.values())
    total_noise = total_variance**0.5
    snr = source_e / total_noise if total_noise > 0 else None

    noise_terms = {
        "source_shot_noise_e": source_var_e**0.5,
        "sky_noise_e": sky_var_e**0.5,
        "dark_noise_e": dark_var_e**0.5,
        "read_noise_e": read_var_e**0.5,
        "background_estimate_noise_e": background_estimate_var**0.5,
    }
    dominant = max(noise_terms.items(), key=lambda item: item[1])[0]
    total_variance_safe = total_variance if total_variance > 0 else 1.0
    variance_fractions = {name: value / total_variance_safe for name, value in variance_terms.items()}
    operating_regime = classify_regime(variance_terms)

    summary = {
        "units_in": args.units,
        "gain_e_per_adu": args.gain if args.units == "adu" else None,
        "n_frames": args.n_frames,
        "n_pixels": args.n_pixels,
        "sky_estimate_pixels": args.sky_estimate_pixels,
        "signal_electrons": {
            "source_total_e": source_e,
            "sky_total_e": sky_e,
            "dark_total_e": dark_e,
        },
        "variance_terms_e2": variance_terms,
        "noise_terms_e": noise_terms,
        "variance_fractions": variance_fractions,
        "total_noise_e": total_noise,
        "snr": snr,
        "dominant_noise_term": dominant,
        "operating_regime": operating_regime,
        "notes": [
            "This is a standard first-order aperture-photometry/imaging noise budget.",
            "It assumes source, sky, and dark follow Poisson statistics and that read noise adds in quadrature.",
            "If --sky-estimate-pixels is omitted, the calculation assumes the background level is known perfectly.",
            "Use this as a planning or QA calculation, not as a replacement for a full instrument simulator.",
        ],
    }

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    output_summary_path = summary_json_path(args)
    qa_findings = []
    if args.sky_estimate_pixels is None:
        qa_findings.append("The background-estimation term was omitted, so the SNR may be optimistic.")
    if operating_regime == "undefined":
        qa_findings.append("The total variance is undefined or zero for the supplied inputs.")
    payload = build_tool_payload(
        "photometry_noise_budget",
        status="warning" if qa_findings else "ok",
        notes=summary["notes"],
        artifacts={
            "summary_json": str(output_summary_path) if output_summary_path else None,
            "report_md": args.report_md,
            "manifest_json": args.manifest_json,
        },
        results=summary,
        qa={
            "status": "warning" if qa_findings else "ok",
            "findings": qa_findings,
            "metrics": {
                "snr": summary["snr"],
                "total_noise_e": summary["total_noise_e"],
                "n_frames": summary["n_frames"],
            },
        },
        legacy=summary,
    )

    outputs = []
    if output_summary_path:
        output_json = Path(output_summary_path)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        emit_payload(payload, output_json)
        outputs.append(output_json)
        print(f"Saved summary: {public_path(output_json)}")
    if args.report_md:
        report_path = Path(args.report_md)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report_path, summary)
        outputs.append(report_path)
        print(f"Saved report: {public_path(report_path)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[],
            outputs=outputs,
            parameters={
                "source": args.source,
                "sky_per_pixel": args.sky_per_pixel,
                "dark_per_pixel": args.dark_per_pixel,
                "read_noise": args.read_noise,
                "n_pixels": args.n_pixels,
                "sky_estimate_pixels": args.sky_estimate_pixels,
                "n_frames": args.n_frames,
                "units": args.units,
                "gain": args.gain,
            },
            command="photometry_noise_budget.py",
            notes=summary["notes"],
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_noise_budget(args)
    except ValueError as exc:
        return emit_blocked(args, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
