#!/usr/bin/env python3
"""Inspect FITS files and optionally save a quicklook preview."""

import argparse
import json
import os
import struct
import sys
import zlib
import warnings
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, write_manifest
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.runtime_common import configure_runtime


FITS_EXTENSIONS = {".fits", ".fit", ".fts", ".fz"}
DEFAULT_HEADER_KEYS = [
    "OBJECT",
    "DATE-OBS",
    "MJD-OBS",
    "EXPTIME",
    "FILTER",
    "BUNIT",
    "CTYPE1",
    "CTYPE2",
    "CRVAL1",
    "CRVAL2",
]


def load_dependencies():
    try:
        import numpy as np
        from astropy.io import fits
        from astropy.wcs import FITSFixedWarning
        from astropy.wcs import WCS
    except ImportError as exc:
        raise ImportError("Missing astropy/numpy dependencies for full FITS inspection.") from exc
    warnings.filterwarnings("ignore", category=FITSFixedWarning)
    return np, fits, WCS


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to a FITS file.")
    parser.add_argument(
        "--extension",
        help="Extension index or EXTNAME to use for preview output. Default: first image HDU.",
    )
    parser.add_argument(
        "--preview",
        help="Optional output PNG path for a quicklook preview of an image extension.",
    )
    parser.add_argument(
        "--crop",
        help="Optional preview crop as x0,y0,width,height in pixel coordinates.",
    )
    parser.add_argument(
        "--force-simple-fallback",
        action="store_true",
        help="Use the minimal primary-image FITS reader even if astropy is installed.",
    )
    parser.add_argument(
        "--summary-json",
        help="Optional output path for the machine-readable summary JSON.",
    )
    parser.add_argument(
        "--manifest-json",
        help="Optional provenance manifest path.",
    )
    parser.add_argument(
        "--header-key",
        action="append",
        default=[],
        help="Additional header key to print. Repeat as needed.",
    )
    parser.add_argument(
        "--max-columns",
        type=int,
        default=12,
        help="Maximum number of table columns to print per HDU summary.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200000,
        help="Approximate number of elements to sample for image statistics.",
    )
    return parser.parse_args()


def parse_crop(crop_text):
    if not crop_text:
        return None
    try:
        parts = [int(item.strip()) for item in crop_text.split(",")]
    except Exception as exc:
        raise SystemExit("--crop must be four integers: x0,y0,width,height") from exc
    if len(parts) != 4:
        raise SystemExit("--crop must be four integers: x0,y0,width,height")
    x0, y0, width, height = parts
    if width <= 0 or height <= 0:
        raise SystemExit("--crop width and height must be positive")
    return x0, y0, width, height


def apply_crop(np, image, crop):
    if crop is None:
        return image
    x0, y0, width, height = crop
    array = np.asarray(image)
    x1 = min(array.shape[1], x0 + width)
    y1 = min(array.shape[0], y0 + height)
    if x0 < 0 or y0 < 0 or x0 >= array.shape[1] or y0 >= array.shape[0] or x1 <= x0 or y1 <= y0:
        raise SystemExit("--crop is outside the selected image bounds")
    return array[y0:y1, x0:x1]


def safe_scalar(value):
    try:
        if hasattr(value, "item"):
            return value.item()
    except Exception:
        pass
    return value


def sampled_finite_values(np, data, sample_size):
    flat = np.asarray(data).reshape(-1)
    if flat.size == 0:
        return flat.astype(float)
    if flat.size > sample_size:
        step = max(1, flat.size // sample_size)
        flat = flat[::step]
    finite = flat[np.isfinite(flat)]
    return finite.astype(float, copy=False)


def summarize_image(np, data, sample_size):
    flat = np.asarray(data).reshape(-1)
    total_pixels = int(flat.size)
    if flat.size and flat.size > sample_size:
        step = max(1, flat.size // sample_size)
        sampled = flat[::step]
    else:
        sampled = flat
    finite = sampled[np.isfinite(sampled)].astype(float, copy=False)
    sampled_pixels = int(sampled.size)
    summary = {
        "shape": list(np.asarray(data).shape),
        "dtype": str(np.asarray(data).dtype),
        "total_pixels": total_pixels,
        "sampled_pixels": sampled_pixels,
        "finite_pixels": int(finite.size),
        "nonfinite_sampled_pixels": int(max(0, sampled_pixels - finite.size)),
        "finite_fraction_sampled": float(finite.size / sampled_pixels) if sampled_pixels else 0.0,
    }
    if finite.size:
        percentiles = np.percentile(finite, [1, 5, 50, 95, 99])
        summary.update(
            {
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "median": float(np.median(finite)),
                "std": float(np.std(finite)),
                "p01": float(percentiles[0]),
                "p05": float(percentiles[1]),
                "p50": float(percentiles[2]),
                "p95": float(percentiles[3]),
                "p99": float(percentiles[4]),
            }
        )
    return summary


def summarize_table_data(data, max_columns):
    names = list(getattr(data, "names", []) or [])
    return {
        "rows": int(len(data)),
        "columns": len(names),
        "column_names": names[:max_columns],
    }


def extract_header_subset(header, extra_keys):
    keys = DEFAULT_HEADER_KEYS + extra_keys
    subset = {}
    for key in keys:
        if key in header:
            subset[key] = safe_scalar(header[key])
    return subset


def wcs_summary(WCS, header):
    if "CTYPE1" not in header and "CTYPE2" not in header:
        return None
    try:
        wcs = WCS(header)
        return {
            "ctype": [str(item) for item in getattr(wcs.wcs, "ctype", []) if item],
            "crval": [float(item) for item in getattr(wcs.wcs, "crval", [])[:2]],
            "crpix": [float(item) for item in getattr(wcs.wcs, "crpix", [])[:2]],
        }
    except Exception:
        return {"status": "present but could not parse"}


def choose_preview_hdu(hdus, extension):
    if extension is not None:
        if extension.isdigit():
            return int(extension)
        for index, hdu in enumerate(hdus):
            if str(hdu.name).strip().lower() == extension.strip().lower():
                return index
        raise SystemExit(f"Could not find extension named '{extension}'.")
    for index, hdu in enumerate(hdus):
        data = getattr(hdu, "data", None)
        if data is not None and getattr(data, "ndim", 0) >= 2:
            return index
    raise SystemExit("No image-like HDU available for preview.")


def first_2d_plane(np, data):
    array = np.asarray(data)
    while array.ndim > 2:
        array = array[0]
    if array.ndim != 2:
        raise ValueError("Selected HDU is not 2D after slicing leading axes.")
    return array


def save_preview(np, WCS, hdus, extension, output_path, crop=None):
    configure_runtime("inspect_fits")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    preview_index = choose_preview_hdu(hdus, extension)
    hdu = hdus[preview_index]
    image = first_2d_plane(np, hdu.data)
    image = apply_crop(np, image, crop)
    finite = sampled_finite_values(np, image, 200000)
    if finite.size == 0:
        raise SystemExit("Cannot render preview because the selected image has no finite pixels.")

    vmin, vmax = np.percentile(finite, [1, 99])
    if vmin == vmax:
        vmax = vmin + 1.0

    figure = None
    try:
        header = hdu.header
        if "CTYPE1" in header or "CTYPE2" in header:
            try:
                projection = WCS(header)
                figure = plt.figure(figsize=(7, 6))
                axis = figure.add_subplot(111, projection=projection)
                axis.set_xlabel("World axis 1")
                axis.set_ylabel("World axis 2")
            except Exception:
                figure = plt.figure(figsize=(7, 6))
                axis = figure.add_subplot(111)
        else:
            figure = plt.figure(figsize=(7, 6))
            axis = figure.add_subplot(111)

        image_artist = axis.imshow(image, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
        axis.set_title(f"HDU {preview_index}: {hdu.name}")
        figure.colorbar(image_artist, ax=axis, fraction=0.046, pad=0.04)
        figure.tight_layout()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=160)
    finally:
        if figure is not None:
            plt.close(figure)
    return preview_index


def parse_fits_card_value(raw_value):
    value = raw_value.split("/", 1)[0].strip()
    if not value:
        return None
    if value.startswith("'"):
        end = value.find("'", 1)
        return value[1:end].strip() if end != -1 else value.strip("'").strip()
    if value in {"T", "F"}:
        return value == "T"
    try:
        if any(char in value for char in [".", "E", "e"]):
            return float(value.replace("D", "E"))
        return int(value)
    except Exception:
        return value


def read_simple_primary_header(handle):
    header = {}
    raw_cards = []
    while True:
        block = handle.read(2880)
        if not block:
            raise ValueError("FITS END card not found")
        for offset in range(0, len(block), 80):
            card = block[offset : offset + 80].decode("ascii", errors="replace")
            raw_cards.append(card)
            keyword = card[:8].strip()
            if keyword == "END":
                return header
            if card[8:10] == "= " and keyword:
                header[keyword] = parse_fits_card_value(card[10:])


def simple_fits_dtype(bitpix):
    import numpy as np

    mapping = {
        8: np.dtype("u1"),
        16: np.dtype(">i2"),
        32: np.dtype(">i4"),
        64: np.dtype(">i8"),
        -32: np.dtype(">f4"),
        -64: np.dtype(">f8"),
    }
    if bitpix not in mapping:
        raise ValueError(f"Unsupported BITPIX for simple fallback: {bitpix}")
    return mapping[bitpix]


def read_simple_primary_image(path):
    import numpy as np

    with Path(path).open("rb") as handle:
        header = read_simple_primary_header(handle)
        if header.get("SIMPLE") is not True:
            raise ValueError("Primary header is not a simple FITS image")
        naxis = int(header.get("NAXIS") or 0)
        if naxis < 1:
            raise ValueError("Simple fallback only supports FITS files with image data")
        axes = [int(header.get(f"NAXIS{idx}") or 0) for idx in range(1, naxis + 1)]
        if any(axis <= 0 for axis in axes):
            raise ValueError("Invalid NAXIS dimensions for simple FITS image")
        dtype = simple_fits_dtype(int(header.get("BITPIX")))
        count = 1
        for axis in axes:
            count *= axis
        raw = handle.read(count * dtype.itemsize)
        if len(raw) < count * dtype.itemsize:
            raise ValueError("FITS data block is truncated")
        data = np.frombuffer(raw, dtype=dtype, count=count).astype(float, copy=False)
        shape = tuple(reversed(axes))
        data = data.reshape(shape)
        bscale = float(header.get("BSCALE") or 1.0)
        bzero = float(header.get("BZERO") or 0.0)
        if bscale != 1.0 or bzero != 0.0:
            data = data * bscale + bzero
        return header, data


def write_grayscale_png(np, image, output_path, vmin, vmax):
    if vmin == vmax:
        vmax = vmin + 1.0
    scaled = (image - vmin) / (vmax - vmin)
    scaled = np.nan_to_num(scaled, nan=0.0, posinf=1.0, neginf=0.0)
    scaled = np.clip(scaled, 0.0, 1.0)
    pixels = (np.flipud(scaled) * 255).astype(np.uint8)
    height, width = pixels.shape

    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + pixels[row].tobytes() for row in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(png)


def build_simple_summary(np, path, extra_keys, sample_size):
    header, data = read_simple_primary_image(path)
    image = first_2d_plane(np, data)
    summary = {
        "path": str(Path(path).resolve()),
        "fallback_mode": "simple_primary_image",
        "hdus": [
            {
                "index": 0,
                "name": "PRIMARY",
                "type": "SimplePrimaryImage",
                "has_data": True,
                "header": {key: safe_scalar(header[key]) for key in DEFAULT_HEADER_KEYS + extra_keys if key in header},
                "wcs": None,
                "data_summary": summarize_image(np, image, sample_size),
                "data_kind": "image",
            }
        ],
    }
    return summary


def save_simple_preview(np, path, output_path, crop=None):
    configure_runtime("inspect_fits")
    _, data = read_simple_primary_image(path)
    image = first_2d_plane(np, data)
    image = apply_crop(np, image, crop)
    finite = sampled_finite_values(np, image, 200000)
    if finite.size == 0:
        raise SystemExit("Cannot render preview because the selected image has no finite pixels.")
    vmin, vmax = np.percentile(finite, [1, 99])
    if vmin == vmax:
        vmax = vmin + 1.0

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        write_grayscale_png(np, image, output_path, vmin, vmax)
        return 0

    figure = plt.figure(figsize=(7, 6))
    try:
        axis = figure.add_subplot(111)
        image_artist = axis.imshow(image, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
        axis.set_title("PRIMARY simple FITS fallback")
        figure.colorbar(image_artist, ax=axis, fraction=0.046, pad=0.04)
        figure.tight_layout()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=160)
    finally:
        plt.close(figure)
    return 0


def build_summary(np, fits, WCS, path, extra_keys, max_columns, sample_size):
    summary = {
        "path": str(Path(path).resolve()),
        "hdus": [],
    }
    with fits.open(path, memmap=False) as hdus:
        for index, hdu in enumerate(hdus):
            entry = {
                "index": index,
                "name": str(hdu.name),
                "type": hdu.__class__.__name__,
                "has_data": hdu.data is not None,
                "header": extract_header_subset(hdu.header, extra_keys),
            }
            entry["wcs"] = wcs_summary(WCS, hdu.header)
            if hdu.data is not None:
                if getattr(hdu.data, "names", None):
                    entry["data_summary"] = summarize_table_data(hdu.data, max_columns)
                    entry["data_kind"] = "table"
                else:
                    entry["data_summary"] = summarize_image(np, hdu.data, sample_size)
                    entry["data_kind"] = "image"
            summary["hdus"].append(entry)
    return summary


def print_summary(summary):
    print(f"FITS file: {summary['path']}")
    print(f"HDU count: {len(summary['hdus'])}")
    for hdu in summary["hdus"]:
        print("")
        print(f"[HDU {hdu['index']}] {hdu['name']} ({hdu['type']})")
        if not hdu["has_data"]:
            print("  data: none")
        elif hdu.get("data_kind") == "table":
            table_summary = hdu["data_summary"]
            print(
                "  table: "
                f"{table_summary['rows']} rows, {table_summary['columns']} columns"
            )
            if table_summary["column_names"]:
                print("  columns: " + ", ".join(table_summary["column_names"]))
        else:
            image_summary = hdu["data_summary"]
            print(
                "  image: "
                f"shape={tuple(image_summary['shape'])}, dtype={image_summary['dtype']}"
            )
            if "median" in image_summary:
                print(
                    "  stats: "
                    f"min={image_summary['min']:.6g}, "
                    f"median={image_summary['median']:.6g}, "
                    f"max={image_summary['max']:.6g}, "
                    f"std={image_summary['std']:.6g}"
                )
            elif image_summary.get("finite_pixels") == 0:
                print("  stats: no finite pixels detected in the sampled data")
        if hdu["header"]:
            pairs = ", ".join(f"{key}={value}" for key, value in hdu["header"].items())
            print("  header: " + pairs)
        if hdu.get("wcs"):
            print("  wcs: " + json.dumps(hdu["wcs"], ensure_ascii=True))


def main():
    args = parse_args()
    path = Path(args.path)
    summary_json = args.summary_json

    def emit_blocked(message, *, status="blocked", kind="fits", metrics=None):
        print(message, file=sys.stderr)
        summary = {
            "path": str(path.resolve()) if path.exists() else str(path),
            "kind": kind,
            "issue_count": 1,
            "issues": [{"severity": "error", "message": message}],
            "metrics": metrics or {},
        }
        payload = build_tool_payload(
            "inspect_fits",
            status=status,
            notes=[
                "Use this inspection as a first FITS pass before reduction, calibration, or scientific interpretation.",
                "The input could not be inspected far enough to produce a normal FITS summary.",
            ],
            artifacts={"summary_json": summary_json, "preview_png": args.preview},
            results=summary,
            qa={"status": status, "findings": [message], "metrics": {"issue_count": 1, **(metrics or {})}},
            legacy=summary,
        )
        if summary_json:
            emit_payload(payload, summary_json)
        return 2

    if summary_json:
        summary_parent = Path(summary_json).expanduser().parent
        if summary_parent.exists() and not summary_parent.is_dir():
            print(f"summary-json parent is not a directory: {summary_parent}", file=sys.stderr)
            return 2
    if args.preview:
        preview_parent = Path(args.preview).expanduser().parent
        if preview_parent.exists() and not preview_parent.is_dir():
            return emit_blocked(f"preview parent is not a directory: {preview_parent}", status="fail")
    if args.manifest_json:
        manifest_parent = Path(args.manifest_json).expanduser().parent
        if manifest_parent.exists() and not manifest_parent.is_dir():
            return emit_blocked(f"manifest-json parent is not a directory: {manifest_parent}", status="fail")
    if not path.exists():
        return emit_blocked(f"File not found: {path}")
    if path.suffix.lower() not in FITS_EXTENSIONS:
        print(
            "Warning: file extension is not a common FITS suffix. Proceeding anyway.",
            file=sys.stderr,
        )

    try:
        crop = parse_crop(args.crop)
    except SystemExit as exc:
        return emit_blocked(str(exc) or "Invalid crop argument")
    force_simple = args.force_simple_fallback or os.environ.get("SDA_INSPECT_FITS_FORCE_SIMPLE") == "1"
    used_simple_fallback = False
    fallback_reason = None
    if not force_simple:
        ensure_datanalysis_runtime("inspect_fits", strict=False)
    try:
        if force_simple:
            raise ImportError("simple fallback requested")
        np, fits, WCS = load_dependencies()
        summary = build_summary(
            np=np,
            fits=fits,
            WCS=WCS,
            path=path,
            extra_keys=args.header_key,
            max_columns=args.max_columns,
            sample_size=args.sample_size,
        )
    except ImportError as exc:
        try:
            import numpy as np
        except ImportError as np_exc:
            raise SystemExit(
                "Missing FITS dependencies. Full inspection needs astropy; the simple fallback also needs numpy."
            ) from np_exc
        used_simple_fallback = True
        fallback_reason = str(exc)
        try:
            summary = build_simple_summary(
                np=np,
                path=path,
                extra_keys=args.header_key,
                sample_size=args.sample_size,
            )
        except Exception as fallback_exc:
            return emit_blocked(f"Could not inspect FITS with simple fallback: {fallback_exc}")
    except Exception as exc:
        return emit_blocked(f"Could not inspect FITS input: {exc.__class__.__name__}: {exc}")
    print_summary(summary)

    if args.preview:
        try:
            if used_simple_fallback:
                if args.extension not in {None, "0", "PRIMARY", "primary"}:
                    raise ValueError("Simple FITS fallback only supports preview of the primary image.")
                preview_index = save_simple_preview(np, path, args.preview, crop=crop)
            else:
                with fits.open(path, memmap=False) as hdus:
                    preview_index = save_preview(np, WCS, hdus, args.extension, args.preview, crop=crop)
        except (SystemExit, Exception) as exc:
            return emit_blocked(str(exc) or "Could not render FITS preview")
        summary["preview_extension"] = preview_index
        print("")
        print(f"Saved preview: {args.preview} (HDU {preview_index})")

    image_hdus = sum(1 for hdu in summary["hdus"] if hdu.get("data_kind") == "image")
    table_hdus = sum(1 for hdu in summary["hdus"] if hdu.get("data_kind") == "table")
    notes = [
        "Use this inspection as a first FITS pass before reduction, calibration, or scientific interpretation.",
    ]
    if used_simple_fallback:
        notes.append(
            "Simple primary-image FITS fallback was used; install astropy for full HDU, table, and WCS inspection."
        )
        summary["fallback_reason"] = fallback_reason
    if args.preview:
        notes.append("A quicklook preview was rendered for the selected image-like HDU.")
    qa_findings = []
    if (image_hdus + table_hdus) == 0:
        qa_findings.append("No image or table HDUs were detected with readable data.")
    for hdu in summary["hdus"]:
        if hdu.get("data_kind") != "image":
            continue
        data_summary = hdu.get("data_summary") or {}
        finite_pixels = int(data_summary.get("finite_pixels") or 0)
        finite_fraction = float(data_summary.get("finite_fraction_sampled") or 0.0)
        if finite_pixels == 0:
            qa_findings.append(f"HDU {hdu['index']} has no finite image pixels in the sampled data.")
        elif finite_fraction < 0.5:
            qa_findings.append(f"HDU {hdu['index']} has low finite-pixel fraction in the sampled data ({finite_fraction:.3f}).")
    qa_status = "warning" if qa_findings else "ok"
    payload = build_tool_payload(
        "inspect_fits",
        status=qa_status,
        notes=notes,
        artifacts={"summary_json": args.summary_json, "preview_png": args.preview},
        results=summary,
        qa={
            "status": qa_status,
            "findings": qa_findings,
            "metrics": {
                "hdu_count": len(summary["hdus"]),
                "image_hdu_count": image_hdus,
                "table_hdu_count": table_hdus,
                "simple_fallback_used": used_simple_fallback,
            },
        },
        legacy=summary,
    )
    if args.summary_json:
        emit_payload(payload, args.summary_json)
        print(f"Saved JSON summary: {public_path(args.summary_json)}")
    if getattr(args, "manifest_json", None):
        outputs = [args.summary_json] if args.summary_json else []
        if args.preview:
            outputs.append(args.preview)
        write_manifest(
            args.manifest_json,
            inputs=[path],
            outputs=outputs,
            parameters={"extension": args.extension, "sample_size": args.sample_size, "crop": args.crop, "simple_fallback": used_simple_fallback},
            command="inspect_fits.py",
            notes=notes,
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
