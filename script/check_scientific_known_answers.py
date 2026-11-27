#!/usr/bin/env python3
"""Check small synthetic astronomy results against independent known answers.

The generated inputs and all evidence live in a new directory outside Git.
Run this with the prepared Python 3.11 Core environment.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import csv
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

from capability_io_contracts import validate_summary_contract
from write_scientific_example_report import write_report


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


def read_json(path: Path, *, capability: str | None = None) -> dict:
    require(path.is_file(), f"missing expected JSON: {path.name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_summary_contract(payload, capability=capability)
    return payload


def check_manifest(path: Path, inputs: list[Path], outputs: list[Path]) -> None:
    manifest = read_json(path)
    for role, files in (("input", inputs), ("output", outputs)):
        records = manifest.get(role + "s") or []
        require(len(records) == len(files), f"manifest {role} count differs")
        for recorded, file in zip(records, files, strict=True):
            name = recorded.get("path")
            require(isinstance(name, str) and Path(name).expanduser().is_absolute()
                    and Path(name).expanduser().resolve() == file.resolve(),
                    f"manifest {role} path differs for {file.name}")
            require(recorded.get("exists") is True and file.is_file(), f"manifest {role} is not present: {file.name}")
            require(recorded.get("size_bytes") == file.stat().st_size, f"manifest {role} size differs for {file.name}")
            require(recorded.get("sha256") == sha256(file), f"manifest {role} hash differs for {file.name}")


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
    signed_scales = [header.get("CDELT1"), header.get("CDELT2")]
    require(all(type(scale) in (float, int) and math.isfinite(scale)
                and abs(scale - reference) < 1e-12
                for scale, reference in zip(signed_scales, (-1 / 3600, 1 / 3600), strict=True)),
            "FITS backend signed WCS axes differ")
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
    rejected_dir = root / "fits-invalid-pixel"
    rejected_summary = rejected_dir / "summary.json"
    rejected_manifest = rejected_dir / "manifest.json"
    rejected = run([
        sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/inspect_fits.py"),
        str(source), "--pixel", "8,0", "--summary-json", str(rejected_summary),
        "--manifest-json", str(rejected_manifest),
    ], rejected_dir, environment)
    require(rejected.returncode == 2 and read_json(rejected_summary)["app_status"] == "BLOCKED_CONTROLADO",
            "out-of-range FITS pixel did not retain a blocked diagnostic")
    require(not rejected_manifest.exists(), "out-of-range FITS pixel wrote a success manifest")
    require(sha256(source) == original_hash, "FITS input changed")
    return {
        "input_sha256": original_hash, "shape_pixels": [8, 8],
        "finite_pixels": 63, "nonfinite_pixels": 1,
        "reference_deg": [float(ra), float(dec)],
        "reported_reference_deg": backend_wcs["crval"],
        "reported_signed_scale_deg_per_pixel": signed_scales,
        "pixel_scale_arcsec": [float(scale) for scale in scales],
        "crop_origin_error_arcsec": crop_origin_error,
        "preview": "display_only",
        "invalid_pixel_status": "BLOCKED_CONTROLADO",
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
    measured_values = {}
    for weighted in (False, True):
        case = root / ("photometry_weighted" if weighted else "photometry_unweighted")
        summary = case / "summary.json"
        manifest = case / "manifest.json"
        coefficients = case / "coefficients.csv"
        residual_plot = case / "residuals.png"
        command = [
            sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/photometric_solution.py"),
            str(source), "--include-color-term", "--color-col", "color", "--summary-json", str(summary),
            "--coefficients-csv", str(coefficients), "--manifest-json", str(manifest),
        ]
        if weighted:
            command.extend(["--error-col", "error_mag", "--residual-plot", str(residual_plot)])
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
        check_manifest(manifest, [source], [summary, coefficients, residual_plot] if weighted else [summary, coefficients])
        results[case.name] = [measurement["uncertainty"] for measurement in measurements]
        measured_values[case.name] = [measurement["value"] for measurement in measurements]
    rejected_dir = root / "photometry_missing_column"
    rejected_summary = rejected_dir / "summary.json"
    rejected_coefficients = rejected_dir / "coefficients.csv"
    rejected = run([
        sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/photometric_solution.py"),
        str(source), "--std-mag-col", "missing", "--summary-json", str(rejected_summary),
        "--coefficients-csv", str(rejected_coefficients),
    ], rejected_dir, environment)
    diagnostic = read_json(rejected_summary)
    require(rejected.returncode == 2 and diagnostic["app_status"] == "BLOCKED_CONTROLADO"
            and diagnostic["results"]["parameters"] == {} and not rejected_coefficients.exists(),
            "missing standard magnitude column produced an incorrect calibration outcome")
    require(sha256(source) == original, "photometry input changed")
    return {
        "input_sha256": original, "residual_degrees_of_freedom": 0, "coefficient_uncertainties": results,
        "reference_coefficients": expected_values, "coefficient_values": measured_values,
        "missing_column_status": diagnostic["app_status"],
    }


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
    return {"input_sha256": originals, "reference_ew_milliangstrom": expected_ew,
            "noise_proxy_milliangstrom": expected_noise, "cases": checks}


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
    rejected_dir = root / "sb2-invalid-separation"
    rejected_summary = rejected_dir / "summary.json"
    rejected_products = rejected_dir / "products"
    rejected = run([
        sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/sb2_double_gaussian_workbench.py"),
        "fit", str(inputs[0]), "--output-dir", str(rejected_products), "--min-separation", "0",
        "--summary-json", str(rejected_summary),
    ], rejected_dir, environment)
    require(rejected.returncode == 2 and read_json(rejected_summary)["app_status"] == "BLOCKED_CONTROLADO"
            and not rejected_products.exists(), "invalid SB2 separation produced fit artifacts")
    require({source.name: sha256(source) for source in inputs} == originals, "SB2 inputs changed")
    return {"accepted_count": 3, "rejected_count": 1, "cases": cases, "input_sha256": originals}


def existing_wcs_cases(root: Path, environment: dict[str, str]) -> dict:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    capability = "astrometry_net_workbench.verify-existing-wcs"

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
        payload = read_json(summary, capability=capability)
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
    no_wcs = root / "input" / "without_celestial_wcs.fits"
    fits.PrimaryHDU(plane).writeto(no_wcs)
    original = sha256(no_wcs)
    case = root / "wcs-missing-celestial-axes"
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    rejected = run(
        [sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/astrometry_net_workbench.py"),
         "verify-existing-wcs", str(no_wcs), "--output-dir", str(case / "products"),
         "--summary-json", str(summary), "--manifest-json", str(manifest)],
        case, environment,
    )
    diagnostic = read_json(summary, capability=capability)
    require(rejected.returncode == 2 and diagnostic["app_status"] == "BLOCKED_CONTROLADO"
            and not diagnostic["results"]["measurement_summary"]["measurements"] and not manifest.exists(),
            "no-WCS input produced a completed verification")
    require(sha256(no_wcs) == original, "WCS verification changed the no-WCS input")
    checks[case.name] = {"status": diagnostic["app_status"], "input_sha256": original}
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


def legacy_spectroscopy_cases(root: Path, environment: dict[str, str]) -> dict:
    import csv
    import statistics

    from astropy.io import fits

    fits_root = root / "input" / "legacy_spectra"
    fits_root.mkdir()
    header = fits.Header({
        "RA": 150.0, "DEC": 20.0, "EQUINOX": 2000.0, "OBSERVAT": "DSAZ",
        "DATE-OBS": "2024-01-01T00:00:00", "EXPTIME": 120.0,
    })
    for name in ("object.fits", "template.fits"):
        fits.PrimaryHDU(header=header).writeto(fits_root / name)
    calibration = root / "input" / "fwhm_calibration.csv"
    calibration.write_text("FWHM_pix,vsini_kms\n5,10\n10,20\n15,30\n", encoding="ascii")
    orders = root / "input" / "legacy_orders.csv"
    fields = [
        "image_name", "template_image", "template_vhelio_kms", "case_id", "mode",
        "aperture", "vrel_kms", "verr_kms", "tdr", "fwhm_pix",
    ]
    with orders.open("w", encoding="ascii", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for case_id, mode, aperture, rv, uncertainty, tdr, fwhm in [
            ("single", "single_rv", 1, 10, 2, 10, 7.5),
            ("single", "single_rv", 2, 14, 4, 11, 7.5),
            ("single", "single_rv", 3, 80, 1, 2, 7.5),
            ("single", "single_rv", 4, 70, 0, 12, 7.5),
            ("binary", "sb2_rv", 1, 20, 2, 10, 7.5),
            ("missing", "single_rv", 1, 10, "-1", 10, 7.5),
            ("rotation", "vsini_fwhm", 1, "", "", 12, 7.5),
            ("rotation", "vsini_fwhm", 2, "", "", 12, 16),
            ("rotation", "vsini_fwhm", 3, "", "", 12, ""),
        ]:
            writer.writerow(["object.fits", "template.fits", 0, case_id, mode, aperture, rv, uncertainty, tdr, fwhm])
    inputs = [orders, calibration, *sorted(fits_root.glob("*.fits"))]
    original = {source.name: sha256(source) for source in inputs}
    case = root / "legacy_spectroscopy"
    products, summary = case / "products", case / "summary.json"
    completed = run(
        [sys.executable, str(ROOT / "skills/scientific-data-astro/scripts/legacy_rv_coursework_workbench.py"),
         "analyze", str(orders), "--fits-root", str(fits_root), "--calibration-csv", str(calibration),
         "--output-dir", str(products), "--summary-json", str(summary), "--manifest-json", str(case / "manifest.json")],
        case, environment,
    )
    require(completed.returncode == 0, f"legacy spectroscopy exited {completed.returncode}: {completed.stderr[-1000:]}")
    payload = read_json(summary)
    require(payload["app_status"] == "WARNING", "provisional legacy estimates must report quality warnings")
    result = payload["results"]
    with (products / "rv_orders_filtered.csv").open(encoding="utf-8") as handle:
        selected = [row for row in csv.DictReader(handle) if row["case_id"] == "single"]
    require([row["aperture"] for row in selected] == ["1", "2"], "legacy RV retained invalid or low-quality orders")
    velocities = [float(row["vhelio_calc_kms"]) for row in selected]
    weighted_velocity = (4 * velocities[0] + velocities[1]) / 5
    formal_uncertainty = 4 / math.sqrt(5)
    details = result["measurement_summary"]
    measurements = {item["label"]: item for item in details["measurements"]}
    rv = measurements["single: heliocentric RV"]
    require(rv["unit"] == "km/s" and math.isclose(rv["value"], weighted_velocity, abs_tol=1e-10)
            and math.isclose(rv["uncertainty"], formal_uncertainty, abs_tol=1e-10),
            "legacy RV central value, unit, or formal error differs")
    diagnostics = {item["label"]: item for item in details["diagnostics"]}
    require(math.isclose(diagnostics["single: sample scatter"]["value"], statistics.stdev(velocities), abs_tol=1e-10)
            and diagnostics["single: orders with missing or invalid errors"]["value"] == 1,
            "legacy RV order scatter or exclusions differ")
    rotation = measurements["rotation, order 1: v sin i estimate"]
    require(rotation["value"] == 15 and rotation["unit"] == "km/s" and rotation.get("uncertainty") is None
            and len(measurements) == 3, "legacy rotation added an extrapolated value or invented an uncertainty")
    findings = {finding["finding"] for finding in payload["qa"]["findings"] if finding.get("message")}
    require({"calibration_range_warning", "missing_fwhm", "sb2_manual_ccf_review_required", "no_usable_orders"} <= findings,
            "legacy spectroscopy did not expose provisional or unavailable results")
    require(all(item["measurement_state"] == "unavailable" and "first_pass_fwhm_proxy" not in item["quality_flags"]
                for item in result["vsini_rows"] if item["vsini_interp_kms"] is None),
            "unavailable rotation must not be labeled as a provisional measurement")
    report = (products / "summary.md").read_text(encoding="utf-8")
    require("15 km/s (uncertainty unavailable)" in report and "orders with missing or invalid errors" in report,
            "the written report lost the uncertainty and exclusion information")
    require({source.name: sha256(source) for source in inputs} == original, "legacy spectroscopy inputs changed")
    return {"rv_kms": rv["value"], "formal_uncertainty_kms": rv["uncertainty"],
            "selected_orders": len(selected), "vsini_kms": rotation["value"], "input_sha256": original}


def general_spectrum_cases(root: Path, environment: dict[str, str]) -> dict:
    import numpy as np
    from astropy import units as u
    from astropy.io import fits
    from astropy.table import Table

    # Calibration is linear in the zero-based index. The original FITS header uses angstroms.
    pixels = np.arange(1001)
    wavelength = 650 + 0.01 * pixels
    center, sigma, depth = 655, 0.035, 0.35
    noise = np.random.default_rng(17).normal(0, 0.002, len(pixels))
    flux = 1 - depth * np.exp(-0.5 * ((wavelength - center) / sigma)**2) + noise
    spectrum = root / "input" / "general_spectrum.fits"
    header = fits.Header({"CTYPE1": "WAVE", "CUNIT1": "Angstrom", "CRPIX1": 1, "CRVAL1": 6500,
                          "CDELT1": 0.1, "BUNIT": "electron/s"})
    fits.PrimaryHDU(flux, header).writeto(spectrum)
    anchors = root / "input" / "wavelength_anchors.ecsv"
    Table({"pixel": [100, 900], "wavelength": [651, 659] * u.nm}).write(anchors)
    originals = {path.name: sha256(path) for path in [spectrum, anchors]}
    case = root / "general_spectroscopy"
    summary, manifest = case / "summary.json", case / "manifest.json"
    script = ROOT / "skills/scientific-data-astro/scripts/spectral_workbench.py"
    base = [sys.executable, str(script), str(spectrum), "--calibration-table", str(anchors), "--calibration-degree", "3"]
    completed = run(
        [*base, "--line-window", str(center), "0.5", "--summary-json", str(summary), "--manifest-json", str(manifest)],
        case, environment,
    )
    require(completed.returncode == 0, f"general spectroscopy exited {completed.returncode}: {completed.stderr[-700:]}")
    result = read_json(summary)
    line = result["results"]["line_fit"]
    calibration = result["results"]["calibration"]
    expected_fwhm = 2 * math.sqrt(2 * math.log(2)) * sigma
    expected_ew = depth * sigma * math.sqrt(2 * math.pi)
    require(abs(line["center"] - center) < 0.002 and abs(line["fwhm"] - expected_fwhm) < 0.002
            and abs(line["equivalent_width_fit"] - expected_ew) < 0.002, "Gaussian line differs from the synthetic reference")
    errors = line["formal_uncertainties"]
    require(all(0 < errors[key] < 0.003 for key in ["center", "fwhm", "equivalent_width"])
            and line["equivalent_width_integral_uncertainty"] is None,
            "formal Gaussian uncertainties or direct integral uncertainty semantics differ")
    fit_x = np.asarray(line["fit_x"])
    fitted_pixels = np.rint((fit_x - 650) * 100).astype(int)
    actual_rms = float(np.sqrt(np.mean((flux[fitted_pixels] - line["fit_model"])**2)))
    require(abs(line["residual_rms"] - actual_rms) < 1e-12 and line["residual_degrees_of_freedom"] == len(fit_x) - 4,
            "Gaussian residual RMS or degrees of freedom differ")
    require(line["axis_unit"] == calibration["wavelength_unit"] == "nm"
            and line["flux_unit"] == "electron/s" and result["results"]["axis_label"] == "Wavelength [nm]",
            "wavelength calibration retained a stale input unit")
    require(result["app_status"] == "WARNING" and calibration["degree"] == 1
            and calibration["requested_degree"] == 3 and calibration["residual_degrees_of_freedom"] == 0
            and calibration["residual_rms"] < 1e-10 and calibration["extrapolated_sample_count"] == 200
            and any("extrapolates" in finding for finding in result["qa"]["findings"]),
            "calibration degree, residuals or quality flags differ")
    check_manifest(manifest, [spectrum, anchors], [summary])
    failure_case = root / "general_spectroscopy_empty_line"
    blocked_summary = failure_case / "summary.json"
    plot = failure_case / "plot.png"
    failure = run([*base, "--line-window", "900", "0.5", "--summary-json", str(blocked_summary), "--plot", str(plot)],
                  failure_case, environment)
    blocked = read_json(blocked_summary)
    require(failure.returncode == 2 and blocked["app_status"] == "BLOCKED_CONTROLADO" and not plot.exists()
            and blocked["results"]["line_fit"] is None and "five distinct samples" in blocked["results"]["blocked_reason"],
            "invalid line window must block with a reason and without producing a plot")
    require({path.name: sha256(path) for path in [spectrum, anchors]} == originals, "spectral inputs changed")
    return {"line_center_nm": line["center"], "formal_center_error_nm": errors["center"],
            "fwhm_nm": line["fwhm"], "equivalent_width_nm": line["equivalent_width_fit"],
            "residual_rms_electron_per_second": actual_rms, "input_sha256": originals}


def spectroscopy_pipeline_cases(root: Path, environment: dict[str, str]) -> dict:
    import csv

    import numpy as np
    from astropy.io import fits

    spectrum = root / "input" / "general_spectrum.fits"
    anchors = root / "input" / "wavelength_anchors.ecsv"
    flux, header = fits.getdata(spectrum, header=True)
    profile = np.exp(-0.5 * ((np.arange(41) - 20) / 1.8)**2)
    gaussian, flat = (root / "input" / name for name in ("gaussian_order.fits", "flat_order.fits"))
    fits.PrimaryHDU(100 + 1000 * profile[:, None] * flux[None, :], header).writeto(gaussian)
    fits.PrimaryHDU(100 + 1000 * profile[:, None] * np.ones((1, flux.size)), header).writeto(flat)
    originals = {path.name: sha256(path) for path in (gaussian, flat, anchors)}

    script = ROOT / "skills/scientific-data-astro/scripts/spectroscopy_pipeline_workbench.py"
    case = root / "spectroscopy_pipeline"
    products = case / "products"
    summary = case / "summary.json"
    manifest = case / "manifest.json"
    options = ["--calibration-table", str(anchors), "--line-window", "655", "0.5"]
    partial = run(
        [sys.executable, str(script), str(gaussian), str(flat), *options,
         "--output-dir", str(products), "--summary-json", str(summary), "--manifest-json", str(manifest)],
        case, environment,
    )
    require(partial.returncode == 1, f"partial spectroscopy batch must return code 1: {partial.stderr[-700:]}")
    payload = read_json(summary)
    result = payload["results"]
    require(payload["app_status"] == "FAIL" and result["completed_science_count"] == 1
            and result["blocked_science_count"] == 1 and result["failed_science_count"] == 0,
            "spectroscopy batch concealed a blocked frame or dropped a completed frame")
    good, blocked = result["science_products"]
    require(good["status"] == "warning" and good["axis_unit"] == "nm" and good["flux_unit"] == "electron/s"
            and abs(good["line_fit_center"] - 655) < 0.002 and good["line_fit_center_uncertainty"] > 0
            and good["line_fit_residual_rms"] > 0 and "Gaussian" in good["line_fit_method"]
            and any("extrapolates" in message for message in good["qa_findings"]),
            "the spectroscopy batch lost calibrated fit values, formal errors, or calibration warnings")
    require(blocked["status"] == "blocked" and blocked["returncode"] == 2
            and "no measurable flux variation" in blocked["failure_reason"]
            and blocked["line_fit_center"] is None and blocked["output_table"] is None,
            "the blocked frame acquired a measurement or lost its failure reason")
    report = (products / "reports/report.md").read_text(encoding="utf-8")
    require("no measurable flux variation" in report and "655.000086 ± 0.000108 nm" in report
            and "extrapolates" in report and "Absolute wavelength uncertainty is unavailable" in report,
            "the spectroscopy batch report lost uncertainty, units, or quality information")
    with (products / "reports/science_products.csv").open(encoding="utf-8") as handle:
        csv_good, csv_blocked = list(csv.DictReader(handle))
    require(csv_good["axis_unit"] == "nm" and csv_good["line_fit_center_uncertainty"] != ""
            and json.loads(csv_good["qa_findings"]) == good["qa_findings"]
            and csv_blocked["status"] == "blocked" and csv_blocked["line_fit_center"] == "",
            "the spectroscopy batch CSV does not match the per-frame evidence")
    good_dir = products / "products/gaussian_order"
    blocked_dir = products / "products/flat_order"
    spectral_outputs = [good_dir / name for name in ("summary.json", "manifest.json", "spectrum.ecsv", "spectrum.png", "trace.png", "spectrum.html")]
    check_manifest(manifest, [gaussian, flat, anchors], [
        products / "reports/science_products.csv", products / "reports/report.md", summary,
        *[path for path in spectral_outputs if path.exists()], blocked_dir / "summary.json",
    ])

    complete = root / "spectroscopy_pipeline_complete"
    complete_summary = complete / "summary.json"
    complete_run = run(
        [sys.executable, str(script), str(gaussian), *options,
         "--output-dir", str(complete / "products"), "--summary-json", str(complete_summary)],
        complete, environment,
    )
    require(complete_run.returncode == 0 and read_json(complete_summary)["app_status"] == "WARNING",
            "a completed batch with calibration warnings should still return code 0")
    previous_table = complete / "products/products/gaussian_order/spectrum.ecsv"
    previous_table_hash = sha256(previous_table)
    retry = root / "spectroscopy_pipeline_blocked_retry"
    retry_summary = retry / "summary.json"
    blocked_run = run(
        [sys.executable, str(script), str(gaussian), "--calibration-table", str(anchors),
         "--line-window", "900", "0.5", "--output-dir", str(complete / "products"), "--summary-json", str(retry_summary)],
        retry, environment,
    )
    failure = read_json(retry_summary)
    failed_row = failure["results"]["science_products"][0]
    require(blocked_run.returncode == 2 and failure["app_status"] == "BLOCKED_CONTROLADO"
            and failed_row["output_table"] is None and failed_row["manifest_json"] is None
            and sha256(previous_table) == previous_table_hash,
            "a blocked retry adopted or modified the previous derived spectrum table")
    incompatible_bias = root / "input" / "incompatible_master_bias.fits"
    fits.PrimaryHDU(np.zeros((8, 8))).writeto(incompatible_bias)
    originals[incompatible_bias.name] = sha256(incompatible_bias)
    rejected = root / "spectroscopy_pipeline_failed_reduction"
    rejected_summary = rejected / "summary.json"
    rejected_manifest = rejected / "manifest.json"
    rejected_products = rejected / "products"
    reduction = run(
        [sys.executable, str(script), str(gaussian), "--master-bias", str(incompatible_bias),
         "--output-dir", str(rejected_products), "--summary-json", str(rejected_summary),
         "--manifest-json", str(rejected_manifest)],
        rejected, environment,
    )
    result = read_json(rejected_summary)
    require(reduction.returncode == 1 and result["app_status"] == "FAIL"
            and result["results"]["skipped_science_count"] == 1 and not result["results"]["science_products"]
            and "CCD reduction failed" in result["results"]["calibration"]["failure_reason"],
            "a CCD reduction failure must skip extraction and remain visible")
    check_manifest(rejected_manifest, [gaussian, incompatible_bias], [
        rejected_products / "reports/science_products.csv", rejected_products / "reports/report.md", rejected_summary,
    ])
    require({path.name: sha256(path) for path in (gaussian, flat, anchors, incompatible_bias)} == originals,
            "pipeline inputs changed")
    return {
        "partial_exit": partial.returncode, "warning_exit": complete_run.returncode, "blocked_exit": blocked_run.returncode,
        "line_center_nm": good["line_fit_center"], "formal_center_error_nm": good["line_fit_center_uncertainty"],
        "input_sha256": originals,
    }


def aperture_photometry_cases(root: Path, environment: dict[str, str]) -> dict:
    import csv

    import numpy as np
    from astropy.io import fits

    data = np.full((33, 33), 100.0)
    annulus_offsets = sorted((x, y) for x in range(-8, 9) for y in range(-8, 9) if 36 <= x*x + y*y <= 64)
    for x, y in annulus_offsets[:20]:
        data[16+y, 16+x] -= 2
    for x, y in annulus_offsets[-20:]:
        data[16+y, 16+x] += 2
    data[16, 16] += 400
    adu = root / "input" / "aperture_adu.fits"
    fits.PrimaryHDU(data, header=fits.Header({"BUNIT": "ADU"})).writeto(adu)
    no_unit = root / "input" / "aperture_no_unit.fits"
    fits.PrimaryHDU(data).writeto(no_unit)
    data[16, 16] -= 410
    electrons = root / "input" / "aperture_negative_electrons.fits"
    fits.PrimaryHDU(data, header=fits.Header({"BUNIT": "electron"})).writeto(electrons)
    hashes = {path.name: sha256(path) for path in [adu, no_unit, electrons]}
    # The 13 aperture pixels contain one source pixel and 12 sky pixels. In the annulus
    # 40 pixels have offsets of magnitude 2 and the other 48 are at the median.
    sky_variance = 160 / 87
    aperture_variance = 13 * sky_variance
    median_variance = 169 * (math.pi / 2) * sky_variance / 88
    script = ROOT / "skills/scientific-data-astro/scripts/aperture_photometry.py"
    cases = [
        ("aperture_adu_gain", adu, ["--gain", "2"], 400, "ADU", 200, "PASS", None),
        ("aperture_adu_no_gain", adu, [], 400, "ADU", None, "WARNING", "uncertainty_gain_unavailable"),
        ("aperture_no_units", no_unit, [], 400, None, None, "WARNING", "uncertainty_units_unavailable"),
        ("aperture_declared_adu", no_unit, ["--units", "adu", "--gain", "2"], 400, "ADU", 200, "PASS", None),
        ("aperture_electrons_negative", electrons, [], -10, "electron", 0, "WARNING", "non_positive_net_flux"),
    ]
    results = {}
    for name, source, options, flux, unit, source_variance, status, flag in cases:
        case = root / name
        summary, table = case / "summary.json", case / "apertures.csv"
        completed = run(
            [sys.executable, str(script), str(source), "--center", "16", "16",
             "--radius", "2", "--annulus-inner", "6", "--annulus-outer", "8",
             "--summary-json", str(summary), "--output-csv", str(table), *options],
            case, environment,
        )
        require(completed.returncode == 0, f"{name} did not finish: {completed.stderr[-600:]}")
        payload = read_json(summary)
        row = payload["results"]["apertures"][0]
        require(payload["app_status"] == status and row["quality_flags"] == ([flag] if flag else []),
                f"{name} quality status differs")
        require(row["net_flux"] == flux and row["flux_unit"] == unit and row["source_poisson_variance"] == source_variance
                and row["n_aperture_pixels"] == 13 and row["n_annulus_pixels"] == 88,
                f"{name} aperture size, units, or source variance differs")
        require(abs(row["background_aperture_variance"] - aperture_variance) < 1e-12
                and abs(row["background_median_variance"] - median_variance) < 1e-12,
                f"{name} background uncertainty differs from the reference")
        if source_variance is None:
            require(row["uncertainty"] is None and "uncertainty=unavailable" in completed.stdout,
                    f"{name} published a total uncertainty without detector information")
        else:
            expected = math.sqrt(source_variance + aperture_variance + median_variance)
            require(abs(row["uncertainty"] - expected) < 1e-12, f"{name} total uncertainty differs")
        with table.open(encoding="utf-8") as handle:
            exported = next(csv.DictReader(handle))
        require((not exported["uncertainty"]) == (row["uncertainty"] is None), "CSV total uncertainty differs")
        results[name] = {"status": status, "flux": flux, "unit": unit, "uncertainty": row["uncertainty"]}
    masked = root / "input" / "aperture_masked_extension.fits"
    data[16, 16] += 410
    data[16, 17] = np.nan
    fits.HDUList([fits.PrimaryHDU(header=fits.Header({"BUNIT": "electron"})),
                  fits.ImageHDU(data, header=fits.Header({"BUNIT": "ADU"}))]).writeto(masked)
    hashes[masked.name] = sha256(masked)
    case = root / "aperture_masked"
    summary = case / "summary.json"
    completed = run(
        [sys.executable, str(script), str(masked), "--extension", "1", "--center", "16", "16",
         "--radius", "2", "--annulus-inner", "6", "--annulus-outer", "8", "--gain", "2", "--summary-json", str(summary)],
        case, environment,
    )
    payload = read_json(summary)
    row = payload["results"]["apertures"][0]
    require(completed.returncode == 0 and payload["app_status"] == "WARNING"
            and payload["results"]["hdu_index"] == 1 and row["flux_unit"] == "ADU"
            and row["x_centroid"] == row["y_centroid"] == 16 and row["aperture_finite_fraction"] == 12/13
            and row["quality_flags"] == ["aperture_nonfinite"],
            "masked aperture or selected-HDU BUNIT behavior differs")
    require({path.name: sha256(path) for path in [adu, no_unit, electrons, masked]} == hashes, "aperture FITS inputs changed")
    return {"cases": results, "input_sha256": hashes}


def additional_astro_contract_cases(root: Path, environment: dict[str, str]) -> dict:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    scripts = ROOT / "skills/scientific-data-astro/scripts"
    products = root / "additional-astro"
    sources = products / "input"
    sources.mkdir(parents=True)
    image = sources / "synthetic.fits"
    image.write_bytes(make_fits())
    vels = sources / "synthetic.vels"
    vels.write_text("# value_units = km/s\n2459000.5 0.001 0.0002\n2459001.5 0.002 0.0002\n", encoding="ascii")
    session = sources / "session.json"
    session.write_text('{"schema_version":"1.0","language":"en","fitted_model":{"planet_count":0},"planets":[]}', encoding="ascii")
    broken = sources / "malformed.json"
    broken.write_text("{", encoding="ascii")
    spectrum = sources / "linear-multispec.fits"
    header = fits.Header({
        "OBJECT": "SYNTHETIC_MULTISPEC",
        "CTYPE1": "MULTISPE",
        "WAT0_001": "system=equispec",
        "WAT1_001": "wtype=multispec label=Wavelength units=angstroms",
        "WAT2_001": 'wtype=multispec spec1="1 1 0 6500 1 24 0 0 0"',
    })
    fits.PrimaryHDU(np.ones((1, 24), dtype="float32"), header=header).writeto(spectrum)
    png = sources / "synthetic.png"
    Image.new("RGB", (4, 3), (30, 70, 120)).save(png)
    digests = {path: sha256(path) for path in sources.iterdir()}

    preflight = "astrometry_net_workbench.preflight"
    inspect = "radial_velocity_workbench.inspect"
    validate = "radial_velocity_workbench.validate-manifest"
    inventory = "echelle_multispec_inventory"
    visual = "rgb_visual_fits_export"
    completed = {0: {"PASS", "WARNING"}}
    blocked = {2: {"BLOCKED_CONTROLADO"}}
    inventory_dir = products / "inventory" / "orders"
    visual_path = products / "visual" / "display.fits"
    missing = sources / "missing.fits"
    cases = [
        ("preflight", preflight, [image], completed),
        ("preflight-missing", preflight, [missing], blocked),
        ("vels", inspect, [vels], completed),
        ("vels-missing", inspect, [sources / "missing.vels"], blocked),
        ("session", validate, [session], {0: {"WARNING"}}),
        ("session-malformed", validate, [broken], blocked),
        ("inventory", inventory, [spectrum, "--output-dir", inventory_dir, "--report-md"], completed),
        ("inventory-missing", inventory, [missing, "--output-dir", products / "inventory-missing" / "orders"], blocked),
        ("visual", visual, [png, visual_path], completed),
        ("visual-missing", visual, [sources / "missing.png", products / "visual-missing" / "display.fits"], blocked),
        ("legacy-missing", "legacy_rv_coursework_workbench.analyze",
         [sources / "missing.csv", "--output-dir", products / "legacy-missing" / "rv"], blocked),
    ]
    records = {}
    for name, capability, arguments, expected in cases:
        tool, _, subcommand = capability.partition(".")
        route = [subcommand] if subcommand else []
        folder = products / name
        summary = folder / "summary.json"
        result = run(
            [sys.executable, str(scripts / f"{tool}.py"), *route, *map(str, arguments), "--summary-json", str(summary)],
            folder, environment,
        )
        payload = read_json(summary, capability=capability)
        status = payload["app_status"]
        require(status in expected.get(result.returncode, set()),
                f"{capability} {name}: unexpected exit {result.returncode} with {status}")
        records[name] = {"returncode": result.returncode, "app_status": status}
        data = payload["results"]
        if name == "vels":
            require(data["sample_count"] == 2 and data["jd_span_days"] == 1 and data["value_units"] == "km/s",
                    "radial velocity inspection lost count, span or input units")
        elif name == "inventory":
            require(data["order_count"] == 1 and (inventory_dir / "orders_inventory.csv").is_file(),
                    "MULTISPE inventory did not retain the single linear order")
        elif name == "visual":
            require(data["calibration_scope"] == "display_only_not_flux_calibrated",
                    "visual FITS export must declare its display calibration scope")
            with fits.open(visual_path) as hdus:
                require([hdu.name for hdu in hdus] == ["PRIMARY", "RGB_CUBE", "RED", "GREEN", "BLUE"]
                        and all(hdu.header["BUNIT"] == "normalized_display_intensity" for hdu in hdus),
                        "visual FITS lost its display unit or channel extensions")
                expected_pixel = np.array([30, 70, 120]) / 255
                np.testing.assert_allclose(hdus["RGB_CUBE"].data[:, 0, 0], expected_pixel, rtol=1e-6)
                np.testing.assert_allclose([hdu.data[0, 0] for hdu in hdus[2:]], expected_pixel, rtol=1e-6)
    require(all(sha256(path) == digest for path, digest in digests.items()),
            "an astronomy contract check modified a protected synthetic input")
    return records


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
        evidence["legacy_spectroscopy"] = legacy_spectroscopy_cases(output, environment)
        evidence["general_spectroscopy"] = general_spectrum_cases(output, environment)
        evidence["spectroscopy_pipeline"] = spectroscopy_pipeline_cases(output, environment)
        evidence["aperture_photometry"] = aperture_photometry_cases(output, environment)
        evidence["additional_astro_contracts"] = additional_astro_contract_cases(output, environment)
        evidence["example_report"] = write_report(output, evidence)
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["failure"] = str(error)
        raise
    finally:
        (output / "verification.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"Scientific known-answer PASS: FITS/WCS, crossmatch, photometry, and spectroscopy. Evidence: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Scientific known-answer validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
