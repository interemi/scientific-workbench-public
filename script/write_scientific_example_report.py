"""Publish a compact, path-neutral index of the generated synthetic examples."""

import csv
import hashlib
import math
from pathlib import Path
import shutil


def write_report(output: Path, evidence: dict) -> dict:
    fits = evidence["fits"]
    crossmatch = evidence["crossmatch"]
    photometry = evidence["photometry"]
    lithium = evidence["lithium_equivalent_width"]
    metrics = [
        ("FITS/WCS", "Finite pixels", "pixel", 63, fits["finite_pixels"], 0),
        ("FITS/WCS", "ICRS reference RA", "deg", 150, fits["reported_reference_deg"][0], 1e-9),
        ("FITS/WCS", "ICRS reference Dec", "deg", -30, fits["reported_reference_deg"][1], 1e-9),
        ("FITS/WCS", "Signed CDELT1", "deg/pixel", -1 / 3600, fits["reported_signed_scale_deg_per_pixel"][0], 1e-12),
        ("FITS/WCS", "Signed CDELT2", "deg/pixel", 1 / 3600, fits["reported_signed_scale_deg_per_pixel"][1], 1e-12),
        ("Sky crossmatch", "Matched pairs", "pair", 1, crossmatch["matched_rows"], 0),
        ("Sky crossmatch", "L1-R1 separation", "arcsec", crossmatch["baseline_sep_arcsec"],
         crossmatch["actual_sep_arcsec"], crossmatch["tolerance_arcsec"]),
    ]
    for (coefficient, unit), reference, result in zip(
        (("Zero point", "mag"), ("Extinction", "mag/airmass"), ("Color term", "mag/mag")),
        photometry["reference_coefficients"], photometry["coefficient_values"]["photometry_weighted"], strict=True,
    ):
        metrics.append(("Photometric calibration", coefficient, unit, reference, result, 1e-12))
    metrics.append(("Li I equivalent width", "Equivalent width", "mÅ", lithium["reference_ew_milliangstrom"],
                    lithium["cases"]["lithium_with_grid"]["ew_milliangstrom"], 1e-7))

    if not all(math.isfinite(result) and abs(result - reference) <= tolerance
               for _, _, _, reference, result, tolerance in metrics):
        raise ValueError("the example report would include a metric outside its reference tolerance")
    report = output / "example-report"
    report.mkdir()
    table_path = report / "synthetic-metrics.csv"
    with table_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["case", "metric", "unit", "reference", "synthetic_result", "absolute_tolerance"])
        writer.writerows(metrics)

    figures = {
        "synthetic-fits-wcs.png": (
            "fits/synthetic_wcs.png", "FITS/WCS quicklook with coordinate ticks. Display stretch only.",
        ),
        "synthetic-li-equivalent-width.png": (
            "lithium_with_grid/products/figures/li6708_equivalent_width.png",
            "Li I equivalent width with the selected continuum and integration windows.",
        ),
    }
    sections = []
    for name, (relative_path, caption) in figures.items():
        original = output / relative_path
        if not original.is_file() or not original.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"missing synthetic result figure: {name}")
        shutil.copyfile(original, report / name)
        sections.extend([f"**Synthetic figure.** {caption}", "", f"![Synthetic figure. {caption}]({name})", ""])

    index = report / "README.md"
    index.write_text(
        "# Scientific Workbench synthetic examples\n\n"
        "All inputs and results in this report are **Synthetic**. **Reference** values come from "
        "known fixture constants or independent calculations. This set contains no **Observed** data.\n\n"
        "Run the documented scientific known-answer check against a fresh output directory to rebuild "
        "the inputs, results, figures, and this index. The tool summaries and manifests remain "
        "available in the full evidence directory.\n\n"
        "**Synthetic table with reference columns.** [Quantitative comparison](synthetic-metrics.csv).\n\n"
        + "\n".join(sections),
        encoding="utf-8",
    )
    return {
        "data_origin": "synthetic",
        "reference_origin": "fixture constants and independent numerical baselines",
        "observed_data_included": False,
        "case_count": len({metric[0] for metric in metrics}),
        "metric_count": len(metrics),
        "files": [
            {"path": path.relative_to(output).as_posix(), "byte_count": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(report.iterdir())
        ],
    }
