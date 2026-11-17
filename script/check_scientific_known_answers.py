#!/usr/bin/env python3
"""Check small synthetic astronomy results against independent known answers.

The generated inputs and all evidence live in a new directory outside Git.
Run this with the prepared Python 3.11 Core environment.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FITS_SHA256 = "c40732799d2792ed9131899c2ad5a3b13317004a96e4d40a0d6aa959afc740de"
LEFT_CSV = "source_id,ra_deg,dec_deg\nL1,150,-30\nL2,10,0\n"
RIGHT_CSV = "source_id,ra_deg,dec_deg\nR1,150,-29.9999\nR2,200,0\n"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_external_directory(path: Path) -> Path:
    target = path.expanduser().resolve()
    require(not path.exists() and not path.is_symlink(), "evidence directory already exists")
    require(not target.is_relative_to(ROOT.resolve()), "evidence must be outside the checkout")
    target.mkdir(parents=True, exist_ok=False)
    return target


def card(key: str, value: str) -> bytes:
    return (key.ljust(8) + "= " + value.rjust(20)).ljust(80).encode("ascii")


def make_fits() -> bytes:
    # Independently encode the published FirstRunExampleService fixture contract.
    values = [
        ("SIMPLE", "T"), ("BITPIX", "-32"), ("NAXIS", "2"),
        ("NAXIS1", "8"), ("NAXIS2", "8"), ("EXTEND", "T"),
        ("OBJECT", "'SYNTHETIC_WCS'"), ("BUNIT", "'adu'"),
        ("CTYPE1", "'RA---TAN'"), ("CTYPE2", "'DEC--TAN'"),
        ("CUNIT1", "'deg'"), ("CUNIT2", "'deg'"),
        ("RADESYS", "'ICRS'"), ("CRPIX1", "4.5"),
        ("CRPIX2", "4.5"), ("CRVAL1", "150.0"),
        ("CRVAL2", "-30.0"), ("CDELT1", "-0.0002777777777778"),
        ("CDELT2", "0.0002777777777778"),
    ]
    header = b"".join(card(key, value) for key, value in values) + b"END".ljust(80)
    header += b" " * (-len(header) % 2880)
    pixels = b"".join(
        struct.pack(">I", 0x7FC00000) if index == 9 else struct.pack(">f", float(index))
        for index in range(64)
    )
    pixels += b"\0" * (-len(pixels) % 2880)
    return header + pixels


def separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    # Standard-library haversine baseline, independent of the backend's SkyCoord.
    lon1, lat1, lon2, lat2 = map(math.radians, (ra1, dec1, ra2, dec2))
    half = math.sin((lat2 - lat1) / 2) ** 2
    half += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * math.atan2(math.sqrt(half), math.sqrt(max(0.0, 1 - half))) * 180 / math.pi * 3600


def run(command: list[str], directory: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    directory.mkdir(parents=True, exist_ok=False)
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, text=True, capture_output=True,
        check=False, timeout=120,
    )
    (directory / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (directory / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    return completed


def read_json(path: Path) -> dict:
    require(path.is_file(), f"missing expected JSON: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_manifest(path: Path, inputs: list[Path], outputs: list[Path]) -> None:
    manifest = read_json(path)
    recorded_inputs = manifest.get("inputs") or []
    require(len(recorded_inputs) == len(inputs), "manifest input count differs")
    for recorded, source in zip(recorded_inputs, inputs):
        require(recorded.get("exists") is True, "manifest input is not present")
        require(recorded.get("sha256") == sha256(source), "manifest input hash differs")
    recorded_outputs = manifest.get("outputs") or []
    require(len(recorded_outputs) == len(outputs), "manifest output count differs")
    for recorded, artifact in zip(recorded_outputs, outputs):
        require(recorded.get("exists") is True, "manifest output is not present")
        require(recorded.get("sha256") == sha256(artifact), "manifest output hash differs")


def check_fits_crop(source: Path, case: Path, original_wcs, environment: dict[str, str]) -> float:
    from astropy.wcs import WCS

    case.mkdir()
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    preview = case / "cropped_wcs.png"
    script = ROOT / "skills/scientific-data-astro/scripts/inspect_fits.py"
    x, y = 2, 1
    expected = original_wcs.pixel_to_world(x, y)
    arguments = [str(script), str(source), "--crop", f"{x},{y},4,4", "--pixel", f"{x},{y}",
                 "--preview", str(preview), "--summary-json", str(summary),
                 "--manifest-json", str(manifest)]

    with patch.dict(os.environ, {**environment, "DATAANALYSIS_PYTHON": sys.executable}):
        from matplotlib.figure import Figure

        add_subplot = Figure.add_subplot
        errors = []

        def record_subplot(figure, *args, **kwargs):
            projection = kwargs.get("projection")
            axis = add_subplot(figure, *args, **kwargs)
            if isinstance(projection, WCS):
                errors.append(float(projection.pixel_to_world(0, 0).separation(expected).arcsec))
            return axis

        # Inspect the projection used for the actual PNG rather than the full-HDU header.
        with ((case / "stdout.log").open("x") as stdout, (case / "stderr.log").open("x") as stderr,
              redirect_stdout(stdout), redirect_stderr(stderr),
              patch.object(Figure, "add_subplot", record_subplot),
              patch.object(sys, "argv", arguments),
              patch.object(sys, "path", [str(script.parent), *sys.path])):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exit_status:
                require(exit_status.code == 0, "FITS crop command failed; inspect retained logs")

    require(len(errors) == 1 and errors[0] < 1e-8, "FITS crop WCS origin differs")
    outcome = read_json(summary)
    require(outcome.get("app_status") == "PASS", "FITS crop did not pass its app contract")
    lookup = outcome["results"]["pixel_lookup"]
    require(lookup["hdu_index"] == 0 and lookup["image_xy"] == [x, y]
            and lookup["pixel_value"] == 10 and lookup["pixel_unit"] == "adu",
            "FITS pixel lookup did not use original, zero-based coordinates")
    axes = lookup["world_axes"]
    require(lookup["reference_frame"] == "ICRS" and [axis["unit"] for axis in axes] == ["deg", "deg"]
            and separation_arcsec(axes[0]["value"], axes[1]["value"], expected.ra.deg, expected.dec.deg) < 1e-8,
            "FITS pixel lookup world coordinates differ")
    check_manifest(manifest, [source], [summary, preview])
    require(read_json(manifest)["parameters"]["pixel"] == f"{x},{y}", "FITS manifest lost lookup coordinates")
    return errors[0]


def inspect_fits_case(root: Path, environment: dict[str, str]) -> dict:
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales
    import numpy as np

    source = root / "input" / "synthetic_wcs_8x8.fits"
    source.write_bytes(make_fits())
    original_hash = sha256(source)
    require(original_hash == FITS_SHA256, "FITS bytes differ from the app-generated fixture")
    with fits.open(source, memmap=False) as hdus:
        require(len(hdus) == 1 and hdus[0].data.shape == (8, 8), "unexpected FITS structure")
        require(np.isfinite(hdus[0].data).sum() == 63, "expected exactly 63 finite pixels")
        require(hdus[0].header.get("BUNIT") == "adu", "FITS pixel unit changed")
        require(hdus[0].header.get("RADESYS") == "ICRS", "FITS reference frame changed")
        require(hdus[0].header.get("CUNIT1") == "deg"
                and hdus[0].header.get("CUNIT2") == "deg", "FITS WCS angular units changed")
        require(abs(hdus[0].header.get("CDELT1") + 1 / 3600) < 1e-12
                and abs(hdus[0].header.get("CDELT2") - 1 / 3600) < 1e-12,
                "FITS WCS axis direction or scale changed")
        wcs = WCS(hdus[0].header)
        ra, dec = wcs.all_pix2world([[3.5, 3.5]], 0)[0]
        scales = proj_plane_pixel_scales(wcs) * 3600
        require(abs(ra - 150) < 1e-9 and abs(dec + 30) < 1e-9,
                "reference-pixel sky coordinate differs")
        require(all(abs(scale - 1) < 1e-6 for scale in scales),
                "pixel scale differs from 1 arcsec/pixel")

    case = root / "fits"
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    preview = case / "synthetic_wcs.png"
    command = [
        sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/inspect_fits.py"),
        str(source), "--preview", str(preview), "--summary-json", str(summary),
        "--manifest-json", str(manifest), "--header-key", "CUNIT1",
        "--header-key", "CUNIT2", "--header-key", "RADESYS",
        "--header-key", "CDELT1", "--header-key", "CDELT2",
    ]
    completed = run(command, case, environment)
    require(completed.returncode == 0, "FITS backend failed; inspect retained logs")
    result = read_json(summary)
    require(result.get("tool") == "inspect_fits" and result.get("app_status") == "PASS",
            "FITS result did not pass its app contract")
    hdus = result.get("results", {}).get("hdus") or []
    require(len(hdus) == 1, "FITS backend HDU count differs")
    image = hdus[0].get("data_summary") or {}
    header = hdus[0].get("header") or {}
    backend_wcs = hdus[0].get("wcs") or {}
    require(image.get("shape") == [8, 8] and image.get("finite_pixels") == 63,
            "FITS backend image values differ")
    require(image.get("nonfinite_sampled_pixels") == 1, "FITS NaN count differs")
    require(header.get("BUNIT") == "adu" and header.get("RADESYS") == "ICRS"
            and header.get("CUNIT1") == "deg" and header.get("CUNIT2") == "deg",
            "FITS backend lost declared units or frame")
    require(backend_wcs.get("crval") == [150, -30] and backend_wcs.get("crpix") == [4.5, 4.5],
            "FITS backend WCS reference differs")
    require(backend_wcs.get("reference_frame") == "ICRS" and backend_wcs.get("axis_units") == ["deg", "deg"],
            "FITS backend WCS frame or axis units differ")
    measured_scales = backend_wcs.get("projection_plane_scale_arcsec", [])
    require(len(measured_scales) == 2 and all(abs(scale - 1) < 1e-6 for scale in measured_scales),
            "FITS backend projection-plane scales differ")
    require(preview.is_file() and preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
            "FITS display-only preview is absent or invalid")
    check_manifest(manifest, [source], [summary, preview])
    crop_origin_error = check_fits_crop(source, root / "fits-crop", wcs, environment)
    require(sha256(source) == original_hash, "FITS input changed")
    return {
        "input_sha256": original_hash, "shape_pixels": [8, 8],
        "finite_pixels": 63, "nonfinite_pixels": 1,
        "reference_deg": [float(ra), float(dec)],
        "pixel_scale_arcsec": [float(scale) for scale in scales],
        "crop_origin_error_arcsec": crop_origin_error,
        "preview": "display_only",
    }


def check_bounded_fits(root: Path, environment: dict[str, str]) -> dict:
    from astropy.io import fits
    import numpy as np

    values = np.full((1028, 1030), 3, dtype=np.int16)
    values[0, 0] = -32768
    image = fits.ImageHDU(values, name="SCI")
    image.header.update({"BSCALE": 0.5, "BZERO": 4.0, "BLANK": -32768, "BUNIT": "adu"})
    table = fits.BinTableHDU.from_columns([fits.Column(name="ID", format="J", array=[1, 2])], name="CAT")
    sources = {
        "scaled_image": [fits.PrimaryHDU(), image, table],
        "table_only": [fits.PrimaryHDU(), table],
    }
    verified = {}
    for name, hdus in sources.items():
        source = root / "input" / f"{name}.fits"
        fits.HDUList(hdus).writeto(source)
        original_hash = sha256(source)
        case = root / name
        summary, manifest, preview = (case / name for name in ("summary.json", "manifest.json", "quicklook.png"))
        command = [
            sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/inspect_fits.py"),
            str(source), "--summary-json", str(summary), "--manifest-json", str(manifest),
            "--preview", str(preview), "--preview-if-available", "--sample-size", "4096",
        ]
        if name == "scaled_image":
            command += ["--extension", "SCI", "--pixel", "0,0"]
        completed = run(command, case, environment)
        require(completed.returncode == 0, f"{name} FITS check failed; inspect retained logs")
        payload = read_json(summary)
        result = payload["results"]
        require(result["hdus"][-1]["data_summary"] == {"rows": 2, "columns": 1, "column_names": ["ID"]},
                "FITS table header summary differs")
        details = result["preview"]
        require(details["display_only"] is True, "FITS quicklook lost its visual-only classification")
        if name == "scaled_image":
            stats = result["hdus"][1]["data_summary"]
            require(result["hdus"][1]["header"]["BUNIT"] == "adu", "FITS scaled image lost its BUNIT")
            require(stats["shape"] == [1028, 1030] and stats["sampling"] == "distributed_sections"
                    and 1 < stats["sampled_pixels"] <= 4096, "FITS sampling scope differs")
            require(stats["nonfinite_sampled_pixels"] == 1 and stats["min"] == stats["max"] == 5.5,
                    "FITS section scaling or BLANK handling differs")
            lookup = result["pixel_lookup"]
            require(lookup["pixel_value"] is None and lookup["pixel_status"] == "nonfinite"
                    and lookup["world_axes"] == [] and lookup["world_reason"],
                    "FITS undefined pixel or missing WCS was not reported")
            require(details["status"] == "rendered" and details["hdu_index"] == 1
                    and details["region_xywh"] == [3, 2, 1024, 1024] and details["coordinates"] == "pixel",
                    "FITS automatic quicklook crop differs")
            require(preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "FITS quicklook PNG is invalid")
            check_manifest(manifest, [source], [summary, preview])
            verified["scaled_image"] = {"sampled_pixels": stats["sampled_pixels"],
                                        "region_xywh": details["region_xywh"]}
        else:
            require(payload["app_status"] == "WARNING" and details["status"] == "unavailable"
                    and not preview.exists() and not payload["artifacts"].get("preview_png"),
                    "FITS table-only inspection should retain the summary without a quicklook")
            check_manifest(manifest, [source], [summary])
            verified["table_only"] = "summary_retained"
        require(sha256(source) == original_hash, f"{name} FITS input changed")
    return verified


def crossmatch_command(left: Path, right: Path, output: Path, summary: Path,
                       manifest: Path, radius: str = "1", *options: str,
                       right_columns: tuple[str, str] = ("ra_deg", "dec_deg")) -> list[str]:
    return [
        sys.executable, str(ROOT / "skills/scientific-data-analysis/scripts/catalog_workbench.py"),
        "crossmatch-sky", str(left), str(right), str(output),
        "--left-ra", "ra_deg", "--left-dec", "dec_deg",
        "--right-ra", right_columns[0], "--right-dec", right_columns[1],
        "--radius-arcsec", radius, "--summary-json", str(summary),
        "--manifest-json", str(manifest),
        *options,
    ]


def crossmatch_convention_cases(root: Path, environment: dict[str, str]) -> dict:
    from astropy.table import Table

    left = root / "input" / "mixed_left.tsv"
    right = root / "input" / "mixed_right.ecsv"
    left.write_text("source_id\tra_deg\tdec_deg\nL-wrap\t359.99995\t0\n", encoding="ascii")
    table = Table({"source_id": ["R-wrap"], "ra": [math.radians(0.00005)], "dec": [0.0]})
    table["ra"].unit = table["dec"].unit = "rad"
    table.meta.update(coordinate_frame="ICRS", coordinate_epoch_jyear=2016.25)
    table.write(right, format="ascii.ecsv")
    inputs = [left, right]
    original_hashes = {path.name: sha256(path) for path in inputs}

    for name, ra_unit, epoch, message in [
        ("mixed_units", "rad", "2016.25", None),
        ("metadata_unit_conflict", "deg", "2016.25", "declares unit rad"),
        ("metadata_epoch_conflict", "rad", "2000", "declares coordinate epoch 2016.25"),
    ]:
        case = root / name
        output = case / "matches.ecsv"
        summary = case / "summary.json"
        manifest = case / "manifest.json"
        completed = run(
            crossmatch_command(
                left, right, output, summary, manifest, "0.5",
                "--right-ra-unit", ra_unit, "--right-dec-unit", "rad",
                "--left-format", "tab", "--right-format", "ecsv",
                "--coordinate-frame", "icrs", "--coordinate-epoch-jyear", epoch,
                right_columns=("ra", "dec"),
            ),
            case, environment,
        )
        payload = read_json(summary)
        if message is not None:
            require(completed.returncode == 2 and payload.get("app_status") == "BLOCKED_CONTROLADO"
                    and message in payload["results"]["message"], f"{name} was not controlled-blocked")
            require(not output.exists() and not manifest.exists(), f"{name} wrote scientific output")
            continue

        require(completed.returncode == 0 and payload.get("app_status") == "PASS", f"{name} failed")
        matches = Table.read(output, format="ascii.ecsv")
        require(len(matches) == 1 and matches["source_id"][0] == "L-wrap"
                and matches["right_source_id"][0] == "R-wrap", "crossmatch across RA zero differs")
        actual_sep = float(matches["match_sep_arcsec"][0])
        expected_sep = separation_arcsec(359.99995, 0.0, 0.00005, 0.0)
        require(abs(actual_sep - expected_sep) < 1e-6, "mixed-unit separation differs")
        check_manifest(manifest, inputs, [output, summary])
        parameters = read_json(manifest)["parameters"]
        expected = {
            "left_ra": "ra_deg", "left_dec": "dec_deg", "right_ra": "ra", "right_dec": "dec",
            "left_ra_unit": "deg", "left_dec_unit": "deg", "right_ra_unit": "rad", "right_dec_unit": "rad",
            "left_format": "tab", "right_format": "ecsv",
            "coordinate_frame": "icrs", "coordinate_epoch_jyear": 2016.25, "radius_arcsec": 0.5,
            "proper_motion_applied": False,
        }
        for key, value in expected.items():
            require(parameters.get(key) == value and payload["results"].get(key) == value,
                    f"crossmatch evidence lost {key}")

    require({path.name: sha256(path) for path in inputs} == original_hashes, "mixed catalogs changed")
    return {
        "input_sha256": original_hashes, "actual_sep_arcsec": actual_sep,
        "unit_conflict": "BLOCKED_CONTROLADO", "epoch_conflict": "BLOCKED_CONTROLADO",
    }


def crossmatch_cases(root: Path, environment: dict[str, str]) -> dict:
    from astropy.table import Table

    left = root / "input" / "left.csv"
    right = root / "input" / "right.csv"
    left.write_text(LEFT_CSV, encoding="ascii")
    right.write_text(RIGHT_CSV, encoding="ascii")
    original_hashes = {path.name: sha256(path) for path in (left, right)}
    expected_sep = separation_arcsec(150, -30, 150, -29.9999)
    require(abs(expected_sep - 0.36) < 1e-9, "independent angular baseline differs")
    require(separation_arcsec(10, 0, 200, 0) > 1, "far pair unexpectedly inside radius")

    case = root / "crossmatch"
    output = case / "matches.ecsv"
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    completed = run(crossmatch_command(left, right, output, summary, manifest), case, environment)
    require(completed.returncode == 0, "crossmatch backend failed; inspect retained logs")
    result = read_json(summary)
    require(result.get("tool") == "catalog_workbench.crossmatch-sky"
            and result.get("app_status") == "PASS", "crossmatch contract did not pass")
    counts = result.get("results") or {}
    require(counts.get("matched_rows") == 1 and counts.get("unmatched_left_rows") == 1,
            "crossmatch counts differ")
    require(counts.get("left_rows") == 2 and counts.get("right_rows") == 2,
            "crossmatch input counts differ")
    table = Table.read(output, format="ascii.ecsv")
    require(len(table) == 1 and str(table["source_id"][0]) == "L1"
            and str(table["right_source_id"][0]) == "R1", "crossmatch pair differs")
    actual_sep = float(table["match_sep_arcsec"][0])
    require(abs(actual_sep - expected_sep) < 1e-6,
            "crossmatch separation differs beyond 1e-6 arcsec")
    check_manifest(manifest, [left, right], [output, summary])

    rejected = {}
    variants = {
        "zero_radius": (right, "0"),
        "radius_over_half_circle": (right, "648000.01"),
        "missing_dec": (root / "input" / "missing_dec.csv", "1"),
        "nonfinite_ra": (root / "input" / "nonfinite_ra.csv", "1"),
        "out_of_range_ra": (root / "input" / "out_of_range_ra.csv", "1"),
    }
    variants["missing_dec"][0].write_text("source_id,ra_deg\nR1,150\n", encoding="ascii")
    variants["nonfinite_ra"][0].write_text(
        "source_id,ra_deg,dec_deg\nR1,NaN,-30\n", encoding="ascii"
    )
    variants["out_of_range_ra"][0].write_text(
        "source_id,ra_deg,dec_deg\nR1,360,-30\n", encoding="ascii"
    )
    for name, (candidate, radius) in variants.items():
        directory = root / name
        result_path = directory / "matches.ecsv"
        result_summary = directory / "summary.json"
        result_manifest = directory / "manifest.json"
        before = {path.name: sha256(path) for path in (left, candidate)}
        completed = run(
            crossmatch_command(left, candidate, result_path, result_summary, result_manifest, radius),
            directory, environment,
        )
        payload = read_json(result_summary)
        require(completed.returncode == 2 and payload.get("status") == "blocked"
                and payload.get("app_status") == "BLOCKED_CONTROLADO",
                f"{name} was not controlled-blocked")
        require(not result_path.exists() and not result_manifest.exists(),
                f"{name} wrote a scientific output after rejection")
        require({path.name: sha256(path) for path in (left, candidate)} == before,
                f"{name} changed an input")
        rejected[name] = "BLOCKED_CONTROLADO"

    collision = root / "input_collision"
    completed = run(
        crossmatch_command(left, right, left, collision / "summary.json",
                           collision / "manifest.json"),
        collision, environment,
    )
    collision_payload = json.loads(completed.stdout)
    require(completed.returncode == 2
            and collision_payload.get("results", {}).get("error_type") == "output_input_collision"
            and collision_payload.get("app_status") == "BLOCKED_CONTROLADO",
            "input/output collision was not controlled-blocked")
    require(not (collision / "summary.json").exists()
            and not (collision / "manifest.json").exists(),
            "input/output collision wrote an artifact")
    rejected["input_output_collision"] = "BLOCKED_CONTROLADO"

    no_match = root / "no_match"
    no_match_summary = no_match / "summary.json"
    no_match_output = no_match / "matches.ecsv"
    completed = run(
        crossmatch_command(left, right, no_match_output, no_match_summary,
                           no_match / "manifest.json", "0.1"),
        no_match, environment,
    )
    no_match_payload = read_json(no_match_summary)
    require(completed.returncode == 0 and no_match_payload.get("app_status") == "WARNING"
            and no_match_payload.get("results", {}).get("matched_rows") == 0
            and no_match_output.is_file(), "zero-match warning contract differs")
    require({path.name: sha256(path) for path in (left, right)} == original_hashes,
            "catalog inputs changed")
    return {
        "input_sha256": original_hashes, "coordinate_units": "decimal degrees",
        "radius_arcsec": 1, "expected_pair": ["L1", "R1"],
        "matched_rows": 1, "unmatched_left_rows": 1,
        "baseline_sep_arcsec": expected_sep, "actual_sep_arcsec": actual_sep,
        "tolerance_arcsec": 1e-6, "rejections": rejected,
        "no_match_status": "WARNING",
        "reviewed_conventions": crossmatch_convention_cases(root, environment),
    }


def photometric_cases(root: Path, environment: dict[str, str]) -> dict:
    import csv

    source = root / "input" / "photometry_standards.csv"
    source.write_text(
        "inst_mag,std_mag,airmass,color,error_mag,catalog_magnitude_system,calibration_passband\n"
        "12,13,1,0,0.02,AB,r\n12,13,2,1,0.02,AB,r\n12,12.6,3,0,0.02,AB,r\n",
        encoding="ascii",
    )
    original = sha256(source)
    expected_values = [1.2, -0.2, 0.2]
    # With this design, the coefficient variances are 2.5, 0.5 and 1.5 times sigma squared.
    expected_errors = [0.02 * math.sqrt(factor) for factor in (2.5, 0.5, 1.5)]
    results = {}
    for weighted in (False, True):
        case = root / ("photometry_weighted" if weighted else "photometry_unweighted")
        summary = case / "summary.json"
        manifest = case / "manifest.json"
        coefficients = case / "coefficients.csv"
        command = [
            sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/photometric_solution.py"),
            str(source), "--include-color-term", "--color-col", "color", "--summary-json", str(summary),
            "--coefficients-csv", str(coefficients), "--manifest-json", str(manifest),
        ]
        if weighted:
            command.extend(["--error-col", "error_mag"])
        completed = run(command, case, environment)
        require(completed.returncode == 0, "photometric calibration failed; inspect retained logs")
        payload = read_json(summary)
        require(payload["tool"] == "photometric_solution" and payload["app_status"] == "WARNING",
                "exactly determined photometric fit must warn about its residuals")
        result = payload["results"]
        require(result["residual_degrees_of_freedom"] == 0 and result["reduced_chi2"] is None,
                "reduced chi-square is undefined at zero residual degrees of freedom")
        measurements = result["measurement_summary"]["measurements"]
        require(len(measurements) == 3, "expected three photometric coefficients")
        with coefficients.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        require(len(rows) == len(measurements), "photometric CSV omitted coefficients")
        for measurement, row, value, uncertainty in zip(measurements, rows, expected_values, expected_errors):
            require(abs(measurement["value"] - value) < 1e-12, "photometric coefficient differs")
            require(row["unit"] == measurement["unit"] and abs(float(row["value"]) - value) < 1e-12,
                    "photometric CSV value or unit differs")
            if weighted:
                require(abs(measurement["uncertainty"] - uncertainty) < 1e-12,
                        "absolute-sigma coefficient uncertainty differs")
            else:
                require(measurement["uncertainty"] is None and row["uncertainty"] == "",
                        "unweighted fit invented uncertainty at zero residual degrees of freedom")
        check_manifest(manifest, [source], [summary, coefficients])
        results[case.name] = [measurement["uncertainty"] for measurement in measurements]
    require(sha256(source) == original, "photometry input changed")
    return {"input_sha256": original, "residual_degrees_of_freedom": 0, "coefficient_uncertainties": results}


def lithium_equivalent_width_cases(root: Path, environment: dict[str, str]) -> dict:
    import numpy as np
    from astropy.io import fits

    source = root / "input" / "lithium_ascii.dat"
    source.write_text(
        "# wavelength in angstroms, normalized flux\n"
        "6705.4 1.01\n6705.6 0.98\n6705.8 1.01\n"
        "6707.0 1.0\n6707.1 0.9\n6707.4 0.8\n6707.8 1.0\n"
        "6708.3 1.01\n6708.4 0.98\n6708.5 1.01\n",
        encoding="ascii",
    )
    wrong_unit = root / "input" / "lithium_nm.fits"
    fits.PrimaryHDU(np.ones(10), header=fits.Header({"CUNIT1": "nm"})).writeto(wrong_unit)
    originals = {item.name: sha256(item) for item in (source, wrong_unit)}
    # Trapezoids over widths 0.1, 0.3, 0.4 Å give 90 mÅ for these depths.
    expected_ew = 90.0
    expected_noise = 1000 * math.sqrt(0.0002) * math.sqrt(0.05**2 + 0.20**2 + 0.35**2 + 0.20**2)
    checks = {}
    for name, spectrum, continuum_left, skip_grid, failure in (
        ("lithium_no_grid", source, ("6705.15", "6706.0"), True, None),
        ("lithium_with_grid", source, ("6705.15", "6706.0"), False, None),
        ("lithium_no_continuum", source, ("6704", "6705"), True, "contains no samples"),
        ("lithium_wrong_unit", wrong_unit, ("6705.15", "6706.0"), True, "wavelength unit"),
    ):
        case = root / name
        products = case / "products"
        summary = case / "summary.json"
        manifest = case / "manifest.json"
        command = [
            sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/li6708_equivalent_width_workbench.py"),
            "measure", str(spectrum), "--output-dir", str(products), "--summary-json", str(summary),
            "--manifest-json", str(manifest), "--continuum-degree", "0",
            "--continuum-window", *continuum_left, "--continuum-window", "6708.1", "6708.8",
            "--integration-window", "6706.8", "6708.0",
        ]
        if skip_grid:
            command.append("--skip-systematic-grid")
        completed = run(command, case, environment)
        payload = read_json(summary)
        result = payload["results"]
        measurement = result["measurement_summary"]
        if failure:
            require(completed.returncode == 2 and payload["app_status"] == "BLOCKED_CONTROLADO"
                    and any(failure in finding for finding in payload["qa"]["findings"]),
                    f"{name} was not controlled-blocked")
            require(measurement["measurements"] == [] and not manifest.exists(), f"{name} reported derived values")
            checks[name] = "BLOCKED_CONTROLADO"
            continue
        require(completed.returncode == 0 and payload["app_status"] == "PASS", f"{name} failed")
        ew = measurement["measurements"][0]
        require(ew["unit"] == "mÅ" and abs(ew["value"] - expected_ew) < 1e-7,
                "lithium equivalent width differs from the trapezoid reference")
        require(abs(result["random_like_uncertainty_milliangstrom"] - expected_noise) < 1e-7,
                "lithium noise proxy did not propagate the nonuniform trapezoid weights")
        if skip_grid:
            require(ew["uncertainty"] is None and result["uncertainty_milliangstrom"] is None,
                    "lithium reported an unmeasured combined uncertainty")
        else:
            grid = result["grid_systematics"]
            require(grid["grid_count"] >= 2 and grid["ew_ma_std"] < 1e-7,
                    "window shifts should leave this fixture's sample selections unchanged")
            require(abs(ew["uncertainty"] - expected_noise) < 1e-7,
                    "lithium combined uncertainty differs without a systematic floor")
        check_manifest(manifest, [spectrum], [
            summary, products / "li6708_summary.csv", products / "li6708_summary.md",
            products / "figures/li6708_equivalent_width.png",
        ])
        checks[name] = {"ew_milliangstrom": ew["value"], "combined_uncertainty_milliangstrom": ew["uncertainty"]}
    require({item.name: sha256(item) for item in (source, wrong_unit)} == originals, "lithium inputs changed")
    return {"input_sha256": originals, "noise_proxy_milliangstrom": expected_noise, "cases": checks}


def sb2_cases(root: Path, environment: dict[str, str]) -> dict:
    import csv

    inputs = []
    specifications = [
        ("observation_a", 1, -42.0, 38.0, 241),
        ("observation_a", 2, -41.7, 38.4, 241),
        ("observation_b", 1, -15.0, 64.0, 241),
        ("observation_b", 2, -15.0, 64.0, 8),
    ]
    for name, aperture, left, right, count in specifications:
        source = root / "input" / f"sb2_{name}_{aperture}.csv"
        with source.open("w", encoding="ascii", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["case_id", "aperture", "velocity_kms", "ccf_value"])
            for index in range(count):
                velocity = -120 + 240 * index / (count - 1)
                signal = (
                    0.15 + 0.9 * math.exp(-0.5 * ((velocity - left) / 9.0)**2)
                    + 0.75 * math.exp(-0.5 * ((velocity - right) / 11.0)**2)
                    + 0.001 * aperture * math.sin(velocity)
                )
                writer.writerow([name, aperture, velocity, signal])
        inputs.append(source)
    originals = {source.name: sha256(source) for source in inputs}
    case = root / "sb2"
    products = case / "products"
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    completed = run(
        [sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/sb2_double_gaussian_workbench.py"),
         "fit", *map(str, inputs), "--output-dir", str(products), "--summary-json", str(summary),
         "--manifest-json", str(manifest)],
        case, environment,
    )
    payload = read_json(summary)
    result = payload["results"]
    require(completed.returncode == 0 and payload["app_status"] == "WARNING",
            "partially rejected SB2 runs must report a warning")
    require(result["accepted_count"] == 3 and result["rejected_count"] == 1, "SB2 acceptance counts differ")
    require(result["component_a_summary"] is None and result["component_b_summary"] is None,
            "SB2 pooled different cases")
    cases = {item["case_id"]: item for item in result["case_summaries"]}
    require(list(cases) == ["observation_a", "observation_b"], "SB2 case grouping differs")
    rows = result["order_rows"]
    for row, (_, _, left, right, _) in zip(rows[:3], specifications):
        require(abs(row["center_left_kms"] - left) < 0.03 and abs(row["center_right_kms"] - right) < 0.03,
                "SB2 fit failed to recover synthetic centers")
    for name, row_slice in [("observation_a", rows[:2]), ("observation_b", rows[2:3])]:
        for side, component in [("left", "component_a_summary"), ("right", "component_b_summary")]:
            reported = cases[name][component]
            weights = [row[f"center_{side}_err_kms"]**-2 for row in row_slice]
            mean = sum(weight * row[f"center_{side}_kms"] for row, weight in zip(row_slice, weights)) / sum(weights)
            require(reported["n_orders"] == len(row_slice) and abs(reported["mean_kms"] - mean) < 1e-10
                    and abs(reported["err_kms"] - math.sqrt(1 / sum(weights))) < 1e-10,
                    "SB2 per-case weighting differs")
    require(rows[-1]["acceptance_flags"] == "fit_failed" and rows[-1]["center_left_kms"] is None
            and "12 distinct samples" in rows[-1]["fit_error"]
            and any("12 distinct samples" in finding["message"] for finding in payload["qa"]["findings"]),
            "SB2 failure must retain a reason and omit derived velocities")
    details = result["measurement_summary"]
    require(len(details["measurements"]) == 4 and all(row["unit"] == "km/s" for row in details["measurements"]),
            "SB2 did not retain structured units and case measurements")
    figures = sorted((products / "figures").glob("*.png"))
    require([path.name for path in figures] == [Path(row["figure_path"]).name for row in rows[:3]],
            "SB2 figures differ from the reported successful fits")
    check_manifest(manifest, inputs, [
        products / "sb2_double_gaussian_orders.csv", products / "summary.md", *figures, summary,
    ])
    require({source.name: sha256(source) for source in inputs} == originals, "SB2 inputs changed")
    return {"accepted_count": 3, "rejected_count": 1, "cases": cases, "input_sha256": originals}


def existing_wcs_cases(root: Path, environment: dict[str, str]) -> dict:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    # The celestial axes are deliberately swapped. The extension center lands on CRVAL.
    header = fits.Header({
        "WCSAXES": 2, "CTYPE1": "DEC--TAN", "CTYPE2": "RA---TAN",
        "CUNIT1": "deg", "CUNIT2": "deg", "CRPIX1": 5.5, "CRPIX2": 3.5,
        "CRVAL1": 0.0, "CRVAL2": 0.01, "CDELT1": 1 / 3600, "CDELT2": -1 / 3600,
        "RADESYS": "ICRS", "RA": 359.99, "DEC": 0.0,
    })
    plane = np.arange(60, dtype=np.float32).reshape(6, 10)
    fixtures = {}
    for name, image, pointing, inverse_fails in [
        ("wcs_later_image_extension", plane, True, False),
        ("wcs_header_in_separate_extension", None, True, False),
        ("wcs_without_pointing_keywords", plane, False, False),
        ("wcs_noninvertible_sip", plane, False, True),
    ]:
        selected = header.copy()
        if not pointing:
            del selected["RA"]
            del selected["DEC"]
        if inverse_fails:
            selected.update({
                "CTYPE1": "RA---TAN-SIP", "CTYPE2": "DEC--TAN-SIP", "CRVAL1": 0.01, "CRVAL2": 0.0,
                "CDELT1": -1 / 3600, "CDELT2": 1 / 3600,
                "A_ORDER": 2, "A_2_0": 0.5, "B_ORDER": 2, "B_0_2": 0.0,
            })
        source = root / "input" / f"{name}.fits"
        unrelated = fits.PrimaryHDU(data=np.full((8, 8), 1000, dtype=np.float32))
        fits.HDUList([unrelated, fits.ImageHDU(data=image, header=selected)]).writeto(source)
        fixtures[name] = (source, image is not None, pointing, inverse_fails, sha256(source))

    checks = {}
    for name, (source, has_image, has_pointing, inverse_fails, original) in fixtures.items():
        case = root / name
        products = case / "products"
        preview = products / "existing_wcs_quicklook.png"
        summary = case / "summary.json"
        manifest = case / "manifest.json"
        completed = run(
            [sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/astrometry_net_workbench.py"),
             "verify-existing-wcs", str(source), "--output-dir", str(products),
             "--summary-json", str(summary), "--manifest-json", str(manifest)],
            case, environment,
        )
        payload = read_json(summary)
        result = payload["results"]
        expected_status = "PASS" if has_image and not inverse_fails else "WARNING"
        require(completed.returncode == 0 and payload["app_status"] == expected_status,
                "local WCS verification status differs")
        require(result["wcs_hdu_index"] == 1 and result["has_image_data"] == has_image,
                "WCS check used an unrelated FITS extension")
        center = result["wcs_center"]
        require(abs(center["ra_deg"] - 0.01) < 1e-10 and abs(center["dec_deg"]) < 1e-10,
                "WCS center did not respect celestial axis order")
        residual = result["pixel_round_trip"]
        if inverse_fails:
            require(residual["max_residual_pixel"] is None and residual["finite_points"] == 0
                    and any("did not converge" in item for item in payload["qa"]["findings"]),
                    "noninvertible SIP must expose the inverse failure and omit a residual")
        else:
            require(residual["finite_points"] == (5 if has_image else 1) and residual["max_residual_pixel"] < 1e-7,
                    "WCS round trip differs from the TAN reference")
        require(result["catalog_accuracy_checked"] is False and
                all(row.get("uncertainty") is None for row in result["measurement_summary"]["measurements"]),
                "local WCS check reported independent coordinate uncertainties")
        offset = result["center_offset_arcsec"]
        if has_image and has_pointing:
            require(abs(offset - 72) < 1e-7, "pointing separation did not wrap RA at zero")
        else:
            require(offset is None, "WCS check invented a pointing-to-center separation")
        if has_image:
            corners = {(item["x"], item["y"]) for item in result["field_corners"]}
            require(corners == {(0, 0), (9, 0), (0, 5), (9, 5)}, "WCS checks used the wrong image footprint")
            require(result["image_quality_proxy"]["median"] == 29.5, "image QA used the wrong FITS extension")
            with Image.open(preview) as image:
                require(image.info.get("Description") == "Source FITS HDU 1 (zero-based)",
                        "WCS quicklook did not use the selected extension")
        else:
            require(center["source"] == "WCS reference pixel" and not result["field_corners"] and not preview.exists(),
                    "header-only WCS borrowed image data")
        check_manifest(manifest, [source], [summary, preview] if has_image else [summary])
        require(sha256(source) == original, "WCS verification changed the input")
        checks[name] = {"status": payload["app_status"], "round_trip": residual, "pointing_separation_arcsec": offset}
    return checks


def photometry_noise_cases(root: Path, environment: dict[str, str]) -> dict:
    cases = [
        ("noise_finite_background", True, "100", "10", "1", "3", "PASS", 710),
        ("noise_background_omitted", False, "100", "10", "1", "3", "WARNING", 648),
        ("noise_zero_variance", True, "0", "0", "0", "0", "WARNING", 0),
        ("noise_overflow", True, "100", "10", "1", "1e308", "BLOCKED_CONTROLADO", None),
    ]
    evidence = {}
    for name, background, source, sky, dark, read_noise, status, total_variance in cases:
        case = root / name
        summary, report, manifest = (case / filename for filename in ("summary.json", "report.md", "manifest.json"))
        options = ["--sky-estimate-pixels", "16"] if background else []
        completed = run(
            [sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/photometry_noise_budget.py"),
             "--source", source, "--sky-per-pixel", sky, "--dark-per-pixel", dark, "--read-noise", read_noise,
             "--units", "adu", "--gain", "2", "--n-pixels", "4", "--n-frames", "2", *options,
             "--summary-json", str(summary), "--report-md", str(report), "--manifest-json", str(manifest)],
            case, environment,
        )
        payload = read_json(summary)
        result = payload["results"]
        measurement = result["measurement_summary"]
        require(payload["app_status"] == status, f"{name} QA status differs")
        if total_variance is None:
            require(completed.returncode == 2 and "overflow" in result["blocked_reason"],
                    "large read-noise values should block with a numerical explanation")
            require(not measurement["measurements"] and not report.exists() and not manifest.exists(),
                    "blocked noise calculation published a result")
            evidence[name] = {"status": status}
            continue
        require(completed.returncode == 0, f"{name} did not finish")
        # For 100 ADU, 10 ADU sky, 1 ADU dark and 3 electrons read noise:
        # source 400, sky 160, dark 16, read 72. Estimating the mean over 16 pixels adds 62.
        offset = result["variance_terms_e2"]["background_estimate_variance_e2"]
        expected_offset = 62 if background and total_variance > 0 else 0
        require(offset == expected_offset and sum(result["variance_terms_e2"].values()) == total_variance,
                "variance terms differ from the independent electron-count calculation")
        diagnostics = {row["label"]: row for row in measurement["diagnostics"]}
        require(("Background-estimate variance" in diagnostics) == background, "background term display differs")
        if background:
            require(diagnostics["Background-estimate variance"]["unit"] == "(e⁻)²", "variance unit missing")
        source_measurement = measurement["measurements"][0]
        if total_variance > 0:
            expected_noise = math.sqrt(total_variance)
            expected_snr = 400 / expected_noise
            require(source_measurement["unit"] == "e⁻" and source_measurement["value"] == 400
                    and abs(source_measurement["uncertainty"] - expected_noise) < 1e-12
                    and abs(measurement["measurements"][1]["value"] - expected_snr) < 1e-12,
                    "source uncertainty or SNR differs from the reference")
        else:
            require(result["snr"] is None and result["dominant_noise_term"] is None
                    and source_measurement["uncertainty"] is None and len(measurement["measurements"]) == 1,
                    "zero variance reported a numerical SNR or uncertainty")
        check_manifest(manifest, [], [summary, report])
        evidence[name] = {"status": status, "snr": result["snr"], "background_variance_e2": offset}
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 11), "use the prepared Python 3.11 Core environment")
    output = new_external_directory(args.output_dir)
    (output / "input").mkdir()
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(output / "matplotlib")
    evidence: dict[str, object] = {
        "status": "FAIL", "source_commit": None,
        "fixture_origin": "project-authored synthetic; generated from published constants",
        "scientific_limit": (
            "FITS preview is display-only. The crossmatch uses supplied positions and applies no epoch "
            "transformation, proper motion, uncertainty, duplicate resolution, or physical-association validation."
        ),
    }
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            capture_output=True, check=True,
        ).stdout.strip()
        evidence["source_commit"] = commit
        evidence["working_tree_clean"] = not bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=ROOT, text=True, capture_output=True, check=True,
        ).stdout.strip())
        evidence["fits"] = inspect_fits_case(output, environment)
        evidence["fits_bounded"] = check_bounded_fits(output, environment)
        evidence["crossmatch"] = crossmatch_cases(output, environment)
        evidence["photometry"] = photometric_cases(output, environment)
        evidence["lithium_equivalent_width"] = lithium_equivalent_width_cases(output, environment)
        evidence["sb2"] = sb2_cases(output, environment)
        evidence["existing_wcs"] = existing_wcs_cases(output, environment)
        evidence["photometry_noise"] = photometry_noise_cases(output, environment)
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["failure"] = str(error)
        raise
    finally:
        (output / "verification.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"Scientific known-answer PASS: FITS/WCS, sky crossmatch, photometric calibration, lithium EW, and SB2. Evidence: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Scientific known-answer validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
