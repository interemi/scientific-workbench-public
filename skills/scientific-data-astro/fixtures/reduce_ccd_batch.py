#!/usr/bin/env python3
"""Combine calibration frames and reduce CCD images with explicit bias/dark/flat steps."""

import argparse
import json
from pathlib import Path

from _internal.provenance_utils import write_manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bias", action="append", default=[], help="Raw bias frame. Repeat as needed.")
    parser.add_argument("--dark", action="append", default=[], help="Raw dark frame. Repeat as needed.")
    parser.add_argument("--flat", action="append", default=[], help="Raw flat frame. Repeat as needed.")
    parser.add_argument("--science", action="append", default=[], help="Science image to reduce. Repeat as needed.")
    parser.add_argument("--master-bias", help="Existing master bias FITS.")
    parser.add_argument("--master-dark", help="Existing master dark FITS.")
    parser.add_argument("--master-flat", help="Existing master flat FITS.")
    parser.add_argument("--output-dir", required=True, help="Directory for masters and reduced products.")
    parser.add_argument("--combine-method", choices=["median", "mean"], default="median")
    parser.add_argument("--scale-dark", action="store_true", help="Scale master dark by exposure time ratio.")
    parser.add_argument("--audit-json", help="Optional path for a calibration compatibility audit JSON.")
    parser.add_argument("--manifest-json", help="Optional path for a provenance manifest.")
    return parser.parse_args()


def load_dependencies():
    import numpy as np
    from astropy.io import fits

    return np, fits


def load_image(fits, path):
    with fits.open(path) as hdus:
        data = hdus[0].data.astype(float)
        header = hdus[0].header.copy()
    return data, header


def summarize_frame(path, data, header):
    return {
        "path": str(Path(path).resolve()),
        "shape": list(data.shape),
        "filter_id": str(header.get("INSFLID", "")).strip(),
        "imagetyp": str(header.get("IMAGETYP", "")).strip(),
        "exptime": float(header.get("EXPTIME", 0.0) or 0.0),
    }


def combine_frames(np, fits, paths, method):
    arrays = []
    header = None
    for path in paths:
        data, this_header = load_image(fits, path)
        arrays.append(data)
        if header is None:
            header = this_header
    cube = np.stack(arrays, axis=0)
    if method == "median":
        combined = np.nanmedian(cube, axis=0)
    else:
        combined = np.nanmean(cube, axis=0)
    return combined, header


def normalize_flat(np, data):
    finite = data[np.isfinite(data)]
    median = float(np.nanmedian(finite)) if finite.size else 1.0
    if median == 0:
        median = 1.0
    return data / median


def crop_center(np, data, target_shape):
    y, x = data.shape
    ty, tx = target_shape
    y0 = max(0, (y - ty) // 2)
    x0 = max(0, (x - tx) // 2)
    return data[y0 : y0 + ty, x0 : x0 + tx]


def align_pair(np, science, calibration):
    if science.shape == calibration.shape:
        return science, calibration, None
    raise SystemExit(
        "Science/calibration shape mismatch: "
        f"science={tuple(science.shape)}, calibration={tuple(calibration.shape)}. "
        "Implicit center-cropping is disabled because it would invalidate WCS and detector geometry; "
        "trim the inputs explicitly with a documented detector section before reduction."
    )


def save_fits(fits, path, data, header, history):
    header = header.copy()
    for item in history:
        header.add_history(item)
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def history_label(text):
    safe = text.encode("ascii", "ignore").decode("ascii")
    return safe[:70]


def build_calibration_audit(np, fits, args):
    science = []
    for item in args.science:
        data, header = load_image(fits, item)
        science.append(summarize_frame(item, data, header))
    flats = []
    for item in args.flat:
        data, header = load_image(fits, item)
        flats.append(summarize_frame(item, data, header))
    biases = []
    for item in args.bias:
        data, header = load_image(fits, item)
        biases.append(summarize_frame(item, data, header))
    audit_rows = []
    for row in science:
        compatible_flats = [
            flat
            for flat in flats
            if tuple(flat["shape"]) == tuple(row["shape"])
            and (not row["filter_id"] or not flat["filter_id"] or flat["filter_id"] == row["filter_id"])
        ]
        compatible_bias = [bias for bias in biases if tuple(bias["shape"]) == tuple(row["shape"])]
        audit_rows.append(
            {
                "science_path": row["path"],
                "science_shape": row["shape"],
                "science_filter_id": row["filter_id"],
                "compatible_bias_count": len(compatible_bias),
                "compatible_flat_count": len(compatible_flats),
                "has_bias": len(compatible_bias) > 0 or bool(args.master_bias),
                "has_flat": len(compatible_flats) > 0 or bool(args.master_flat),
            }
        )
    return {
        "combine_method": args.combine_method,
        "scale_dark": bool(args.scale_dark),
        "science_frames": science,
        "flat_frames": flats,
        "bias_frames": biases,
        "science_audit": audit_rows,
    }


def main():
    args = parse_args()
    np, fits = load_dependencies()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = build_calibration_audit(np, fits, args)

    master_bias = None
    master_dark = None
    master_flat = None
    master_history = []

    if args.master_bias:
        master_bias, bias_header = load_image(fits, args.master_bias)
        master_history.append(history_label(f"Loaded master bias: {Path(args.master_bias).name}"))
    elif args.bias:
        master_bias, bias_header = combine_frames(np, fits, args.bias, args.combine_method)
        save_fits(fits, output_dir / "master_bias.fits", master_bias, bias_header, [f"Combined {len(args.bias)} bias frames"])
        master_history.append(f"Created master bias from {len(args.bias)} frames")
    else:
        bias_header = None

    if args.master_dark:
        master_dark, dark_header = load_image(fits, args.master_dark)
        master_history.append(history_label(f"Loaded master dark: {Path(args.master_dark).name}"))
    elif args.dark:
        master_dark, dark_header = combine_frames(np, fits, args.dark, args.combine_method)
        if master_bias is not None:
            master_dark = master_dark - master_bias
        save_fits(fits, output_dir / "master_dark.fits", master_dark, dark_header, [f"Combined {len(args.dark)} dark frames"])
        master_history.append(f"Created master dark from {len(args.dark)} frames")
    else:
        dark_header = None

    if args.master_flat:
        master_flat, flat_header = load_image(fits, args.master_flat)
        master_history.append(history_label(f"Loaded master flat: {Path(args.master_flat).name}"))
    elif args.flat:
        master_flat, flat_header = combine_frames(np, fits, args.flat, args.combine_method)
        if master_bias is not None:
            master_flat = master_flat - master_bias
        if master_dark is not None:
            master_flat = master_flat - master_dark
        master_flat = normalize_flat(np, master_flat)
        save_fits(fits, output_dir / "master_flat.fits", master_flat, flat_header, [f"Combined {len(args.flat)} flat frames"])
        master_history.append(f"Created master flat from {len(args.flat)} frames")
    else:
        flat_header = None

    if not args.science:
        print("No science frames provided. Masters only.")
        return

    for science_path in args.science:
        data, header = load_image(fits, science_path)
        reduced = data.copy()
        history = list(master_history)
        if master_bias is not None:
            reduced, bias_to_apply, note = align_pair(np, reduced, master_bias)
            if note:
                history.append(note)
            reduced -= bias_to_apply
            history.append("Bias subtraction applied")
        if master_dark is not None:
            dark_to_apply = master_dark
            if args.scale_dark:
                science_exp = float(header.get("EXPTIME", 0.0) or 0.0)
                dark_exp = float((dark_header or {}).get("EXPTIME", 0.0) or 0.0)
                if dark_exp > 0:
                    dark_to_apply = master_dark * (science_exp / dark_exp)
                    history.append(f"Dark scaled by exposure ratio {science_exp / dark_exp:.6g}")
            reduced, dark_to_apply, note = align_pair(np, reduced, dark_to_apply)
            if note:
                history.append(note)
            reduced -= dark_to_apply
            history.append("Dark subtraction applied")
        if master_flat is not None:
            reduced, flat_to_apply, note = align_pair(np, reduced, master_flat)
            if note:
                history.append(note)
            safe_flat = np.where(flat_to_apply == 0, 1.0, flat_to_apply)
            reduced /= safe_flat
            history.append("Flat-field correction applied")

        out = output_dir / f"reduced_{Path(science_path).name}"
        save_fits(fits, out, reduced, header, history)
        print(f"Saved reduced frame: {out.resolve()}")

    if args.audit_json:
        audit_path = Path(args.audit_json)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=True) + "\n")
        print(f"Saved audit: {audit_path.resolve()}")

    if args.manifest_json:
        output_paths = list(output_dir.glob("*.fits"))
        if args.audit_json:
            output_paths.append(Path(args.audit_json))
        write_manifest(
            args.manifest_json,
            inputs=[*map(Path, args.bias), *map(Path, args.dark), *map(Path, args.flat), *map(Path, args.science)],
            outputs=output_paths,
            parameters={
                "combine_method": args.combine_method,
                "scale_dark": args.scale_dark,
                "master_bias": args.master_bias,
                "master_dark": args.master_dark,
                "master_flat": args.master_flat,
            },
            command="reduce_ccd_batch.py",
            notes=["Reduction may crop frames to a common central shape when science and calibration dimensions differ."],
            extra={"calibration_audit": audit},
        )
        print(f"Saved manifest: {Path(args.manifest_json).resolve()}")


if __name__ == "__main__":
    main()
