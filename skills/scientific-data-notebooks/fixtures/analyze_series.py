#!/usr/bin/env python3
"""Analyze generic, spectral, or time-series data from table-like files."""

import argparse
import json
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import public_path, sanitize_payload, standard_tool_payload
from _internal.runtime_common import configure_runtime
from _internal.tabular_io import read_table_any


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input table-like file.")
    parser.add_argument("--x-col", help="Column name for x/time/wavelength. Defaults to first numeric column.")
    parser.add_argument("--y-col", help="Column name for y/flux. Defaults to second numeric column.")
    parser.add_argument("--kind", choices=["generic", "time", "spectrum"], default="generic")
    parser.add_argument("--plot", help="Optional output PNG plot.")
    parser.add_argument("--periodogram", action="store_true", help="Run a Lomb-Scargle period search for time series.")
    parser.add_argument("--fit-gaussian", nargs=2, type=float, metavar=("XMIN", "XMAX"), help="Fit a gaussian in the selected x range.")
    parser.add_argument("--summary-json", help="Optional output JSON summary.")
    return parser.parse_args()


def emit_collision_only(input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing series-analysis outputs that overlap the input table."
    payload = standard_tool_payload(
        "analyze_series",
        status="blocked",
        notes=[message, "No plot or summary was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "input": public_path(input_path),
            "collisions": collisions,
        },
        qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": len(collisions)}},
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def load_dependencies():
    configure_runtime("analyze_series")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.table import Table
    from astropy.timeseries import LombScargle
    from scipy.optimize import curve_fit

    return plt, np, Table, LombScargle, curve_fit


def read_table(Table, path):
    return read_table_any(Table, path)


def pick_numeric_columns(table, x_col, y_col):
    numeric = []
    for name in table.colnames:
        try:
            table[name].astype(float)
            numeric.append(name)
        except Exception:
            continue
    if x_col is None:
        if not numeric:
            raise SystemExit("No numeric columns available.")
        x_col = numeric[0]
    if y_col is None:
        choices = [name for name in numeric if name != x_col]
        if not choices:
            raise SystemExit("Could not infer y column.")
        y_col = choices[0]
    return x_col, y_col


def gaussian(x, amp, mu, sigma, offset):
    import numpy as np

    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + offset


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    collisions = find_output_input_collisions(
        [("input", input_path)],
        [("--plot", args.plot), ("--summary-json", args.summary_json)],
    )
    if collisions:
        raise SystemExit(emit_collision_only(input_path, collisions))
    plt, np, Table, LombScargle, curve_fit = load_dependencies()
    table = read_table(Table, args.input)
    x_col, y_col = pick_numeric_columns(table, args.x_col, args.y_col)
    x = np.asarray(table[x_col], dtype=float)
    y = np.asarray(table[y_col], dtype=float)

    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if x.size == 0:
        raise SystemExit("No finite samples available.")

    summary = {
        "path": str(Path(args.input).resolve()),
        "kind": args.kind,
        "x_col": x_col,
        "y_col": y_col,
        "count": int(x.size),
        "x_min": float(np.min(x)),
        "x_max": float(np.max(x)),
        "y_min": float(np.min(y)),
        "y_max": float(np.max(y)),
        "y_mean": float(np.mean(y)),
        "y_std": float(np.std(y)),
    }

    if args.periodogram:
        frequency, power = LombScargle(x, y).autopower()
        best_index = int(np.argmax(power))
        best_frequency = float(frequency[best_index])
        summary["periodogram"] = {
            "best_frequency": best_frequency,
            "best_period": float(1.0 / best_frequency) if best_frequency != 0 else None,
            "max_power": float(power[best_index]),
        }

    if args.fit_gaussian:
        xmin, xmax = args.fit_gaussian
        mask = (x >= xmin) & (x <= xmax)
        if np.sum(mask) < 5:
            raise SystemExit("Not enough points in the requested fit window.")
        xf = x[mask]
        yf = y[mask]
        p0 = [float(np.max(yf) - np.min(yf)), float(xf[np.argmax(yf)]), float(np.std(xf) or 1.0), float(np.min(yf))]
        popt, _ = curve_fit(gaussian, xf, yf, p0=p0, maxfev=10000)
        summary["gaussian_fit"] = {
            "amplitude": float(popt[0]),
            "center": float(popt[1]),
            "sigma": float(abs(popt[2])),
            "offset": float(popt[3]),
        }

    print(f"Series file: {summary['path']}")
    print(f"Columns: x={x_col}, y={y_col}")
    print(f"Samples: {summary['count']}")
    print(f"x range: {summary['x_min']:.6g} -> {summary['x_max']:.6g}")
    print(f"y range: {summary['y_min']:.6g} -> {summary['y_max']:.6g}")
    if "periodogram" in summary:
        print(f"Best period: {summary['periodogram']['best_period']:.6g}")
    if "gaussian_fit" in summary:
        print(f"Gaussian center: {summary['gaussian_fit']['center']:.6g}")

    if args.plot:
        out = Path(args.plot)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig = plt.figure(figsize=(7, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(x, y, lw=1.0, marker="o", ms=2 if x.size < 1000 else 0)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(f"{Path(args.input).name} [{args.kind}]")
        if "gaussian_fit" in summary:
            xmin, xmax = args.fit_gaussian
            xx = np.linspace(xmin, xmax, 500)
            fit = summary["gaussian_fit"]
            ax.plot(xx, gaussian(xx, fit["amplitude"], fit["center"], fit["sigma"], fit["offset"]), color="tab:red", lw=1.5)
        fig.tight_layout()
        fig.savefig(out, dpi=160)
        plt.close(fig)
        print(f"Saved plot: {out.resolve()}")

    if args.summary_json:
        out = Path(args.summary_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
        print(f"Saved summary: {out.resolve()}")


if __name__ == "__main__":
    main()
