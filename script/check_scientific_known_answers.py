#!/usr/bin/env python3
"""Check small synthetic astronomy results against independent known answers.

The generated inputs and all evidence live in a new directory outside Git.
Run this with the prepared Python 3.11 Core environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys


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
    require(preview.is_file() and preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
            "FITS display-only preview is absent or invalid")
    check_manifest(manifest, [source], [summary, preview])
    require(sha256(source) == original_hash, "FITS input changed")
    return {
        "input_sha256": original_hash, "shape_pixels": [8, 8],
        "finite_pixels": 63, "nonfinite_pixels": 1,
        "reference_deg": [float(ra), float(dec)],
        "pixel_scale_arcsec": [float(scale) for scale in scales],
        "preview": "display_only",
    }


def crossmatch_command(left: Path, right: Path, output: Path, summary: Path,
                       manifest: Path, radius: str = "1") -> list[str]:
    return [
        sys.executable, str(ROOT / "skills/scientific-data-analysis/scripts/catalog_workbench.py"),
        "crossmatch-sky", str(left), str(right), str(output),
        "--left-ra", "ra_deg", "--left-dec", "dec_deg",
        "--right-ra", "ra_deg", "--right-dec", "dec_deg",
        "--radius-arcsec", radius, "--summary-json", str(summary),
        "--manifest-json", str(manifest),
    ]


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
    }


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
            "FITS preview is display-only; the crossmatch has no epoch, proper motion, "
            "uncertainty, duplicate resolution, or physical-association validation."
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
        evidence["crossmatch"] = crossmatch_cases(output, environment)
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["failure"] = str(error)
        raise
    finally:
        (output / "verification.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"Scientific known-answer PASS: FITS/WCS and sky crossmatch. Evidence: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Scientific known-answer validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
