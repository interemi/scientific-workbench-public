#!/usr/bin/env python3
"""Create DS9-like quicklooks, cutouts, and simple region overlays from FITS files."""

import argparse
import math
import warnings
from pathlib import Path

from _internal.runtime_common import configure_runtime


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fits_path", help="Input FITS file.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    parser.add_argument("--extension", help="Extension index or EXTNAME.")
    parser.add_argument("--center", nargs=2, type=float, metavar=("X", "Y"), help="Cutout center in pixel coordinates.")
    parser.add_argument("--size", type=int, help="Cutout size in pixels. If omitted, render the full frame.")
    parser.add_argument("--region-file", help="Optional DS9 region file with simple physical coordinates.")
    parser.add_argument("--title", help="Optional plot title.")
    return parser.parse_args()


def load_dependencies():
    configure_runtime("fits_quicklook")
    warnings.filterwarnings("ignore", message=".*FITSFixedWarning.*")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import FITSFixedWarning
    from astropy.wcs import WCS
    from matplotlib import patches
    from matplotlib import transforms

    warnings.filterwarnings("ignore", category=FITSFixedWarning)

    return plt, np, fits, Cutout2D, WCS, patches, transforms


def choose_hdu(hdus, extension):
    if extension is None:
        for idx, hdu in enumerate(hdus):
            if getattr(hdu, "data", None) is not None and getattr(hdu.data, "ndim", 0) >= 2:
                return idx
        raise SystemExit("No image HDU found.")
    if extension.isdigit():
        return int(extension)
    for idx, hdu in enumerate(hdus):
        if str(hdu.name).strip().lower() == extension.strip().lower():
            return idx
    raise SystemExit(f"Could not find extension '{extension}'.")


def first_2d_plane(data, np):
    arr = np.asarray(data)
    while arr.ndim > 2:
        arr = arr[0]
    if arr.ndim != 2:
        raise SystemExit("Selected HDU does not contain a 2D image plane.")
    return arr


def parse_region_file(path):
    entries = []
    if path is None:
        return entries
    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("global") or line == "physical":
                continue
            shape, _, meta = line.partition("#")
            shape = shape.strip()
            meta = meta.strip()
            color = "yellow"
            if "color=" in meta:
                color = meta.split("color=", 1)[1].split()[0]
            if shape.startswith("circle(") and shape.endswith(")"):
                values = [float(v) for v in shape[7:-1].split(",")]
                if len(values) >= 3:
                    entries.append({"kind": "circle", "x": values[0], "y": values[1], "r": values[2], "color": color})
            elif shape.startswith("box(") and shape.endswith(")"):
                values = [float(v) for v in shape[4:-1].split(",")]
                if len(values) >= 5:
                    entries.append(
                        {
                            "kind": "box",
                            "x": values[0],
                            "y": values[1],
                            "w": values[2],
                            "h": values[3],
                            "angle": values[4],
                            "color": color,
                        }
                    )
            elif shape.startswith("line(") and shape.endswith(")"):
                values = [float(v) for v in shape[5:-1].split(",")]
                if len(values) >= 4:
                    entries.append({"kind": "line", "x1": values[0], "y1": values[1], "x2": values[2], "y2": values[3], "color": color})
    return entries


def apply_region_overlays(axis, entries, patches, transforms, x0=0.0, y0=0.0):
    for entry in entries:
        if entry["kind"] == "circle":
            patch = patches.Circle((entry["x"] - x0, entry["y"] - y0), entry["r"], fill=False, lw=1.2, ec=entry["color"])
            axis.add_patch(patch)
        elif entry["kind"] == "box":
            cx = entry["x"] - x0
            cy = entry["y"] - y0
            patch = patches.Rectangle(
                (cx - entry["w"] / 2.0, cy - entry["h"] / 2.0),
                entry["w"],
                entry["h"],
                fill=False,
                lw=1.2,
                ec=entry["color"],
            )
            transform = transforms.Affine2D().rotate_deg_around(cx, cy, entry["angle"]) + axis.transData
            patch.set_transform(transform)
            axis.add_patch(patch)
        elif entry["kind"] == "line":
            axis.plot([entry["x1"] - x0, entry["x2"] - x0], [entry["y1"] - y0, entry["y2"] - y0], color=entry["color"], lw=1.0)


def main():
    args = parse_args()
    plt, np, fits, Cutout2D, WCS, patches, transforms = load_dependencies()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with fits.open(args.fits_path) as hdus:
        idx = choose_hdu(hdus, args.extension)
        hdu = hdus[idx]
        data = first_2d_plane(hdu.data, np)
        header = hdu.header

        cutout = None
        x0 = 0.0
        y0 = 0.0
        wcs = None
        if args.center and args.size:
            try:
                full_wcs = WCS(header)
            except Exception:
                full_wcs = None
            cutout = Cutout2D(data, position=(args.center[0], args.center[1]), size=(args.size, args.size), wcs=full_wcs, mode="trim")
            image = cutout.data
            x0, y0 = cutout.origin_original
            wcs = cutout.wcs
        else:
            image = data
            try:
                maybe_wcs = WCS(header)
                wcs = maybe_wcs if maybe_wcs.has_celestial else None
            except Exception:
                wcs = None

        finite = image[np.isfinite(image)]
        if finite.size == 0:
            raise SystemExit("No finite pixels available for rendering.")
        vmin, vmax = np.percentile(finite, [1, 99])
        if not math.isfinite(vmin) or not math.isfinite(vmax) or vmin == vmax:
            vmin = float(np.nanmin(finite))
            vmax = float(np.nanmax(finite))
            if vmin == vmax:
                vmax = vmin + 1.0

        figure = plt.figure(figsize=(7, 6))
        if wcs is not None and getattr(wcs, "has_celestial", False):
            axis = figure.add_subplot(111, projection=wcs)
            axis.set_xlabel("RA")
            axis.set_ylabel("Dec")
        else:
            axis = figure.add_subplot(111)
            axis.set_xlabel("X (pixel)")
            axis.set_ylabel("Y (pixel)")
        artist = axis.imshow(image, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
        apply_region_overlays(axis, parse_region_file(args.region_file), patches, transforms, x0=x0, y0=y0)
        figure.colorbar(artist, ax=axis, fraction=0.046, pad=0.04)
        axis.set_title(args.title or f"{Path(args.fits_path).name} [HDU {idx}]")
        figure.tight_layout()
        figure.savefig(output_path, dpi=160)
        plt.close(figure)
        print(f"Saved quicklook: {output_path.resolve()}")


if __name__ == "__main__":
    main()
