#!/usr/bin/env python3
"""Native numeric quicklooks and notebook scans for an external TEAREDUCE route."""

import argparse
import json
from pathlib import Path

from _internal.provenance_utils import environment_summary, write_manifest
from teareduce_healthcheck import bootstrap_runtime_dirs, summarize_notebooks


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    statsummary = subparsers.add_parser("statsummary", help="Summarize a FITS, NumPy, or text array with native NumPy statistics.")
    statsummary.add_argument("input", help="Input file path.")
    statsummary.add_argument("--hdu", type=int, default=0, help="FITS HDU index when the input is FITS-like.")
    statsummary.add_argument("--npz-key", help="Explicit NPZ member key to use.")
    statsummary.add_argument("--rm-nan", action="store_true", help="Ignore non-finite values in the native summary.")
    statsummary.add_argument("--summary-json", help="Optional JSON report path.")
    statsummary.add_argument("--manifest-json", help="Optional provenance manifest path.")

    imshow_fits = subparsers.add_parser("imshow-fits", help="Create a native Matplotlib PNG quicklook from a FITS image.")
    imshow_fits.add_argument("input", help="Input FITS file path.")
    imshow_fits.add_argument("--output", required=True, help="Output PNG path.")
    imshow_fits.add_argument("--hdu", type=int, default=0, help="FITS HDU index.")
    imshow_fits.add_argument("--title", help="Optional plot title.")
    imshow_fits.add_argument("--vmin-sigma", type=float, default=3.0, help="Sigma multiplier below the median.")
    imshow_fits.add_argument("--vmax-sigma", type=float, default=5.0, help="Sigma multiplier above the median.")
    imshow_fits.add_argument("--summary-json", help="Optional JSON report path.")
    imshow_fits.add_argument("--manifest-json", help="Optional provenance manifest path.")

    notebook_scan = subparsers.add_parser("notebook-scan", help="Scan TEAREDUCE notebooks and summarize usage.")
    notebook_scan.add_argument("paths", nargs="+", help="Notebook paths or directories.")
    notebook_scan.add_argument("--max-notebooks", type=int, default=8, help="Maximum notebooks to inspect.")
    notebook_scan.add_argument("--summary-json", help="Optional JSON report path.")
    notebook_scan.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def reduce_array(data):
    import numpy as np

    array = np.asarray(data)
    notes = []
    if array.ndim == 0:
        array = array.reshape(1)
    while array.ndim > 2:
        array = array[0]
        notes.append("Selected the first plane along a leading axis to reduce the input to 2D.")
    return array, notes


def load_numeric_input(path, hdu=0, npz_key=None):
    import numpy as np

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".fits", ".fit", ".fts", ".fz"}:
        from astropy.io import fits

        with fits.open(path) as hdul:
            data = hdul[hdu].data
        reduced, notes = reduce_array(data)
        return reduced, {"loader": "fits", "hdu": hdu, "notes": notes}
    if suffix == ".npy":
        reduced, notes = reduce_array(np.load(path, allow_pickle=False))
        return reduced, {"loader": "npy", "notes": notes}
    if suffix == ".npz":
        with np.load(path, allow_pickle=False) as payload:
            keys = list(payload.files)
            key = npz_key or keys[0]
            reduced, notes = reduce_array(payload[key])
        return reduced, {"loader": "npz", "npz_key": key, "available_keys": keys, "notes": notes}
    reduced, notes = reduce_array(np.loadtxt(path))
    return reduced, {"loader": "text", "notes": notes}


def save_payload(payload, summary_json=None):
    rendered = json.dumps(payload, indent=2, ensure_ascii=True, default=json_default)
    print(rendered)
    if summary_json:
        summary_path = Path(summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered + "\n")


def json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def native_summary(data, *, rm_nan=False):
    import numpy as np

    values = np.asarray(data, dtype=float).ravel()
    if rm_nan:
        values = values[np.isfinite(values)]
    elif not np.isfinite(values).all():
        raise ValueError("Input contains non-finite values; use --rm-nan to exclude them.")
    if values.size == 0:
        raise ValueError("Input has no finite numeric values to summarize.")
    median = float(np.median(values))
    median_absolute_deviation = float(np.median(np.abs(values - median)))
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": median,
        "std": float(np.std(values, ddof=0)),
        "robust_std": 1.4826 * median_absolute_deviation,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "method": "numpy_population_std_and_scaled_median_absolute_deviation",
    }


def command_statsummary(args):
    bootstrap_runtime_dirs()

    data, meta = load_numeric_input(args.input, hdu=args.hdu, npz_key=args.npz_key)
    summary = native_summary(data, rm_nan=args.rm_nan)
    payload = {
        "tool": "teareduce_bridge",
        "command": "statsummary",
        "input": str(Path(args.input).resolve()),
        "backend": "native_numpy",
        "teareduce_executed": False,
        "environment": environment_summary(),
        "input_meta": meta,
        "array_shape": list(getattr(data, "shape", [])),
        "array_dtype": str(getattr(data, "dtype", "unknown")),
        "statsummary": summary,
    }
    save_payload(payload, summary_json=args.summary_json)
    if args.manifest_json:
        outputs = [Path(args.summary_json)] if args.summary_json and Path(args.summary_json).exists() else []
        write_manifest(
            args.manifest_json,
            inputs=[Path(args.input)],
            outputs=outputs,
            parameters={"hdu": args.hdu, "npz_key": args.npz_key, "rm_nan": args.rm_nan},
            command="teareduce_bridge.py statsummary",
            notes=[*meta.get("notes", []), "Native statistics; not a TEAREDUCE statsummary result."],
        )


def command_imshow_fits(args):
    bootstrap_runtime_dirs()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from astropy.io import fits

    input_path = Path(args.input)
    with fits.open(input_path) as hdul:
        data = hdul[args.hdu].data
    reduced, notes = reduce_array(data)
    stats = native_summary(reduced, rm_nan=True)
    vmin = stats["median"] - args.vmin_sigma * stats["robust_std"]
    vmax = stats["median"] + args.vmax_sigma * stats["robust_std"]
    if not vmin < vmax:
        vmin, vmax = stats["min"], stats["max"]
        if not vmin < vmax:
            vmin, vmax = vmin - 0.5, vmax + 0.5
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(reduced, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
    ax.set_title(args.title or input_path.name)
    fig.tight_layout()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    payload = {
        "tool": "teareduce_bridge",
        "command": "imshow-fits",
        "input": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "backend": "native_matplotlib",
        "teareduce_executed": False,
        "environment": environment_summary(),
        "hdu": args.hdu,
        "array_shape": list(getattr(reduced, "shape", [])),
        "array_dtype": str(getattr(reduced, "dtype", "unknown")),
        "statsummary": stats,
        "display_limits": {"vmin": vmin, "vmax": vmax},
        "notes": notes,
    }
    save_payload(payload, summary_json=args.summary_json)
    if args.manifest_json:
        outputs = [output_path]
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=outputs,
            parameters={"hdu": args.hdu, "vmin_sigma": args.vmin_sigma, "vmax_sigma": args.vmax_sigma},
            command="teareduce_bridge.py imshow-fits",
            notes=[*notes, "Native quicklook; not a TEAREDUCE imshow result."],
        )


def command_notebook_scan(args):
    bootstrap_runtime_dirs()
    payload = {
        "tool": "teareduce_bridge",
        "command": "notebook-scan",
        "environment": environment_summary(),
        "notebooks": summarize_notebooks(args.paths, max_notebooks=args.max_notebooks),
    }
    save_payload(payload, summary_json=args.summary_json)
    if args.manifest_json:
        outputs = [Path(args.summary_json)] if args.summary_json and Path(args.summary_json).exists() else []
        write_manifest(
            args.manifest_json,
            inputs=[Path(item) for item in args.paths if Path(item).exists()],
            outputs=outputs,
            parameters={"max_notebooks": args.max_notebooks},
            command="teareduce_bridge.py notebook-scan",
        )


def main():
    args = parse_args()
    if args.command == "statsummary":
        command_statsummary(args)
        return
    if args.command == "imshow-fits":
        command_imshow_fits(args)
        return
    if args.command == "notebook-scan":
        command_notebook_scan(args)
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
