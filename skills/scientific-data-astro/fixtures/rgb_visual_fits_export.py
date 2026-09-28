#!/usr/bin/env python3
"""Export a rendered RGB PNG as a display-only FITS RGB product.

This helper is intentionally narrow. It does not rebuild RGBs from raw FITS,
perform CCD calibration, or clean images. Use it after a visual RGB has already
been rendered and needs a traceable FITS container and optional before/after
comparison for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from _internal.provenance_utils import build_manifest, public_path, sha256_file, standard_qa_payload
from _internal.public_contract import build_tool_payload, emit_payload

TOOL_NAME = "rgb_visual_fits_export"
BUNIT = "normalized_display_intensity"
DISPLAY_WARNING = "Display-only normalized RGB product; not flux calibrated."
PNG_EXTENSIONS = {".png"}
FITS_EXTENSIONS = {".fits", ".fit", ".fts"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_png", help="Rendered RGB PNG to export.")
    parser.add_argument("output_fits", help="Output FITS path.")
    parser.add_argument("--previous-png", help="Optional previous RGB PNG to compare against.")
    parser.add_argument("--comparison-png", help="Optional side-by-side before/after PNG path.")
    parser.add_argument("--manifest-json", help="Optional manifest path. Defaults next to the output FITS.")
    parser.add_argument("--summary-json", help="Optional standard JSON envelope path.")
    parser.add_argument("--object-name", help="Optional object/target name for FITS metadata.")
    parser.add_argument("--reason", help="Short reason for the visual RGB export or redo.")
    parser.add_argument("--previous-label", default="previous", help="Label for the previous image in comparison PNG.")
    parser.add_argument("--new-label", default="new visual RGB", help="Label for the new image in comparison PNG.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
    return parser.parse_args(argv)


def safe_emit_payload(payload: dict[str, Any], summary_json: str | Path | None) -> None:
    """Emit a payload while avoiding traceback on a bad summary path."""
    if summary_json:
        summary_path = Path(summary_json)
        try:
            if summary_path.parent.exists() and not summary_path.parent.is_dir():
                print(
                    f"Could not write summary JSON because parent is not a directory: {summary_path.parent}",
                    file=sys.stderr,
                )
                emit_payload(payload, None)
                return
        except OSError as exc:
            print(f"Could not validate summary JSON path: {exc}", file=sys.stderr)
            emit_payload(payload, None)
            return
    emit_payload(payload, summary_json)


def fail_payload(message: str, args: argparse.Namespace | None = None, status: str = "blocked") -> int:
    artifacts = {}
    if args is not None:
        artifacts = {
            "input_png": args.input_png,
            "output_fits": args.output_fits,
            "summary_json": args.summary_json,
        }
        if getattr(args, "previous_png", None):
            artifacts["previous_png"] = args.previous_png
        if getattr(args, "comparison_png", None):
            artifacts["comparison_png"] = args.comparison_png
    payload = build_tool_payload(
        TOOL_NAME,
        status=status,
        notes=[message],
        artifacts=artifacts,
        results={},
        qa=standard_qa_payload(status=status, findings=[message], metrics={"blocking_count": 1 if status == "blocked" else 0}),
    )
    safe_emit_payload(payload, getattr(args, "summary_json", None) if args else None)
    return 2 if status == "blocked" else 1


def require_dependencies(args: argparse.Namespace):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None, None, fail_payload("Missing Pillow. Install pillow to read PNGs and write comparisons.", args, "blocked")

    try:
        from astropy.io import fits
    except ImportError:
        return None, None, fail_payload("Missing astropy. Use the datanalysis environment before writing FITS.", args, "blocked")

    return (Image, ImageDraw), fits, None


def read_rgb_png(path: Path, image_module: Any) -> tuple[np.ndarray, dict[str, Any], list[str]]:
    with image_module.open(path) as image:
        original_mode = image.mode
        source_size = [int(image.width), int(image.height)]
        warnings_list = []
        if path.suffix.lower() not in PNG_EXTENSIONS:
            warnings_list.append(f"Input file extension is {path.suffix or '<none>'}; expected .png.")
        if original_mode != "RGB":
            warnings_list.append(f"Input image mode is {original_mode}; it was converted to RGB for FITS export.")
        if "A" in original_mode:
            warnings_list.append("Input image has an alpha channel; transparency is not represented in the RGB FITS product.")
        rgb = image.convert("RGB")
        arr = np.asarray(rgb, dtype=np.float32) / 255.0
    return arr, {"mode": original_mode, "size": source_size}, warnings_list


def inspect_png_for_warnings(path: Path, image_module: Any, label: str) -> list[str]:
    warnings_list = []
    if path.suffix.lower() not in PNG_EXTENSIONS:
        warnings_list.append(f"{label} extension is {path.suffix or '<none>'}; expected .png.")
    with image_module.open(path) as image:
        if image.mode != "RGB":
            warnings_list.append(f"{label} image mode is {image.mode}; comparison rendering will convert it to RGB.")
        if "A" in image.mode:
            warnings_list.append(f"{label} image has an alpha channel; transparency is not represented in comparison output.")
    return warnings_list


def validate_output_path(path: Path, description: str, force: bool, *, allow_existing: bool = False) -> str | None:
    if path.exists() and not force and not allow_existing:
        return f"{description} already exists; pass --force to overwrite: {path}"
    if path.parent.exists() and not path.parent.is_dir():
        return f"{description} parent is not a directory: {path.parent}"
    return None


def write_visual_fits(
    output_fits: Path,
    rgb: np.ndarray,
    fits_module: Any,
    input_png: Path,
    previous_png: Path | None,
    object_name: str | None,
    reason: str | None,
    force: bool,
) -> None:
    output_fits.parent.mkdir(parents=True, exist_ok=True)
    cube = np.transpose(rgb, (2, 0, 1)).astype("float32")

    primary = fits_module.PrimaryHDU()
    primary.header["IMAGETYP"] = "VISUAL_RGB"
    primary.header["CALIB"] = "DISPLAY_ONLY"
    primary.header["BUNIT"] = BUNIT
    primary.header["DATE"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    primary.header["SRCIMG"] = input_png.name[:68]
    if previous_png:
        primary.header["PREVIMG"] = previous_png.name[:68]
    if object_name:
        primary.header["OBJECT"] = str(object_name)[:68]
    if reason:
        primary.header["HISTORY"] = str(reason)[:70]
    primary.header["COMMENT"] = DISPLAY_WARNING

    cube_hdu = fits_module.ImageHDU(data=cube, name="RGB_CUBE")
    cube_hdu.header["BUNIT"] = BUNIT
    cube_hdu.header["CORDER"] = "R,G,B"
    cube_hdu.header["CALIB"] = "DISPLAY_ONLY"
    cube_hdu.header["COMMENT"] = DISPLAY_WARNING

    channel_hdus = []
    for index, name in enumerate(("RED", "GREEN", "BLUE")):
        hdu = fits_module.ImageHDU(data=cube[index], name=name)
        hdu.header["BUNIT"] = BUNIT
        hdu.header["CALIB"] = "DISPLAY_ONLY"
        hdu.header["COMMENT"] = DISPLAY_WARNING
        channel_hdus.append(hdu)

    fits_module.HDUList([primary, cube_hdu, *channel_hdus]).writeto(output_fits, overwrite=force)


def write_comparison_png(
    previous_png: Path,
    new_png: Path,
    comparison_png: Path,
    image_module: Any,
    image_draw_module: Any,
    previous_label: str,
    new_label: str,
    force: bool,
) -> None:
    if comparison_png.exists() and not force:
        raise FileExistsError(f"Comparison already exists: {comparison_png}")
    comparison_png.parent.mkdir(parents=True, exist_ok=True)

    with image_module.open(previous_png).convert("RGB") as previous_img, image_module.open(new_png).convert("RGB") as new_img:
        label_height = 28
        padding = 12
        target_height = max(previous_img.height, new_img.height)

        def padded(image):
            canvas = image_module.new("RGB", (image.width, target_height), "white")
            canvas.paste(image, (0, 0))
            return canvas

        previous_canvas = padded(previous_img)
        new_canvas = padded(new_img)
        width = previous_canvas.width + new_canvas.width + padding * 3
        height = target_height + label_height + padding * 2
        out = image_module.new("RGB", (width, height), "white")
        draw = image_draw_module.Draw(out)
        draw.text((padding, padding // 2), previous_label, fill="black")
        new_x = previous_canvas.width + padding * 2
        draw.text((new_x, padding // 2), new_label, fill="black")
        out.paste(previous_canvas, (padding, label_height + padding))
        out.paste(new_canvas, (new_x, label_height + padding))
        out.save(comparison_png)


def build_extra(
    rgb: np.ndarray,
    input_png: Path,
    output_fits: Path,
    previous_png: Path | None,
    comparison_png: Path | None,
    object_name: str | None,
    reason: str | None,
) -> dict[str, Any]:
    payload = {
        "product_type": "visual_rgb_fits",
        "calibration_scope": "display_only_not_flux_calibrated",
        "bunit": BUNIT,
        "rgb_cube_shape": [3, int(rgb.shape[0]), int(rgb.shape[1])],
        "channel_extensions": ["RED", "GREEN", "BLUE"],
        "input_png_sha256": sha256_file(input_png),
        "output_fits_sha256": sha256_file(output_fits) if output_fits.exists() else None,
        "warning": DISPLAY_WARNING,
    }
    if object_name:
        payload["object_name"] = object_name
    if reason:
        payload["reason"] = reason
    if previous_png:
        payload["previous_png_sha256"] = sha256_file(previous_png)
    if comparison_png and comparison_png.exists():
        payload["comparison_png_sha256"] = sha256_file(comparison_png)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_png = Path(args.input_png)
    output_fits = Path(args.output_fits)
    previous_png = Path(args.previous_png) if args.previous_png else None
    comparison_png = Path(args.comparison_png) if args.comparison_png else None
    manifest_json = Path(args.manifest_json) if args.manifest_json else output_fits.with_suffix(".manifest.json")

    if not input_png.exists() or not input_png.is_file():
        return fail_payload(f"Input PNG does not exist: {input_png}", args)
    if previous_png and (not previous_png.exists() or not previous_png.is_file()):
        return fail_payload(f"Previous PNG does not exist: {previous_png}", args)
    if previous_png and comparison_png is None:
        comparison_png = output_fits.with_name(output_fits.stem + "_before_after.png")
        args.comparison_png = str(comparison_png)
    if input_png.resolve() == output_fits.resolve():
        return fail_payload("Input PNG and output FITS resolve to the same path.", args)
    if previous_png and previous_png.resolve() == output_fits.resolve():
        return fail_payload("Previous PNG and output FITS resolve to the same path.", args)
    if output_fits.suffix.lower() not in FITS_EXTENSIONS:
        return fail_payload(f"Output path should use a FITS extension (.fits/.fit/.fts): {output_fits}", args)
    for path, description in (
        (output_fits, "Output FITS"),
        (manifest_json, "Manifest JSON"),
        (Path(args.summary_json), "Summary JSON") if args.summary_json else (None, None),
        (comparison_png, "Comparison PNG") if comparison_png else (None, None),
    ):
        if path is None:
            continue
        issue = validate_output_path(path, description, args.force, allow_existing=(description == "Summary JSON"))
        if issue:
            return fail_payload(issue, args)

    pillow_modules, fits_module, dependency_exit = require_dependencies(args)
    if dependency_exit is not None:
        return dependency_exit
    image_module, image_draw_module = pillow_modules

    try:
        rgb, input_image_info, qa_findings = read_rgb_png(input_png, image_module)
        if previous_png:
            qa_findings.extend(inspect_png_for_warnings(previous_png, image_module, "Previous PNG"))
        write_visual_fits(
            output_fits,
            rgb,
            fits_module,
            input_png,
            previous_png,
            args.object_name,
            args.reason,
            args.force,
        )
        if previous_png and comparison_png:
            write_comparison_png(
                previous_png,
                input_png,
                comparison_png,
                image_module,
                image_draw_module,
                args.previous_label,
                args.new_label,
                args.force,
            )
    except (OSError, ValueError) as exc:
        return fail_payload(f"Visual RGB FITS export was blocked by invalid input/output: {exc}", args, "blocked")
    except Exception as exc:
        return fail_payload(f"Visual RGB FITS export failed unexpectedly: {exc}", args, "fail")

    outputs = [output_fits, manifest_json]
    if comparison_png:
        outputs.append(comparison_png)
    extra = build_extra(rgb, input_png, output_fits, previous_png, comparison_png, args.object_name, args.reason)
    extra["input_image"] = input_image_info
    manifest = build_manifest(
        inputs=[input_png] + ([previous_png] if previous_png else []),
        outputs=outputs,
        parameters={
            "object_name": args.object_name,
            "reason": args.reason,
            "previous_label": args.previous_label if previous_png else None,
            "new_label": args.new_label if previous_png else None,
            "force": args.force,
        },
        command=" ".join(sys.argv),
        notes=[DISPLAY_WARNING],
        extra=extra,
    )
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    qa_status = "warning" if qa_findings else "ok"
    qa_findings = [DISPLAY_WARNING] + qa_findings
    payload = build_tool_payload(
        TOOL_NAME,
        status=qa_status,
        notes=qa_findings,
        artifacts={
            "output_fits": output_fits,
            "manifest_json": manifest_json,
            "comparison_png": comparison_png,
        },
        results={
            "rgb_cube_shape": extra["rgb_cube_shape"],
            "bunit": BUNIT,
            "calibration_scope": "display_only_not_flux_calibrated",
            "channel_extensions": ["RED", "GREEN", "BLUE"],
            "object_name": args.object_name,
            "reason": args.reason,
            "input_image": input_image_info,
        },
        qa=standard_qa_payload(
            status=qa_status,
            findings=qa_findings,
            metrics={
                "height_px": int(rgb.shape[0]),
                "width_px": int(rgb.shape[1]),
                "channels": 3,
                "warning_count": len(qa_findings) - 1,
            },
        ),
        include_environment=True,
    )
    safe_emit_payload(payload, args.summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
