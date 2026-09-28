#!/usr/bin/env python3
"""Shared helpers for narrow legacy spectroscopy coursework routes."""

from __future__ import annotations

import csv
import math
import re
import shutil
import unicodedata
import warnings
from dataclasses import dataclass
from pathlib import Path

from _internal.provenance_utils import public_path
from _internal.runtime_common import find_executable


DEFAULT_RECOMMENDED_ORDERS = [21, 24, 33, 34, 36, 37, 40, 42, 43, 50, 52]
C_KMS = 299792.458

OBSERVATORY_LOCATIONS = {
    # DSAZ appears in the supplied FITS headers and in IRAF obsdb.dat for Calar Alto.
    "DSAZ": {"lon_deg": -(2 + 32 / 60 + 46.5 / 3600), "lat_deg": (37 + 13 / 60 + 25 / 3600), "height_m": 2168.0},
}


def ascii_safe_slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "legacy_spectroscopy"


def path_risk_report(path: str | Path) -> dict:
    rendered = str(Path(path))
    normalized = unicodedata.normalize("NFC", rendered)
    non_ascii_chars = [char for char in normalized if ord(char) > 127]
    return {
        "path": public_path(rendered),
        "contains_spaces": " " in normalized,
        "contains_non_ascii": bool(non_ascii_chars),
        "non_ascii_characters": sorted(set(non_ascii_chars)),
        "legacy_safe_workspace_needed": (" " in normalized) or bool(non_ascii_chars),
    }


def detect_practice_assets(root: str | Path) -> dict:
    root = Path(root)
    fits_dir = root / "fits_p1"
    istarmod_root = root / "iSTARMOD"
    code_iraf = root / "CODEX" / "01_iraf_safe"
    code_analysis = root / "CODEX" / "02_analysis"
    code_istarmod = root / "CODEX" / "03_istarmod_work"
    detected_pdfs = sorted(str(item.resolve()) for item in root.glob("*.pdf"))
    fits_files = sorted(str(item.resolve()) for item in fits_dir.glob("*.fits")) if fits_dir.exists() else []
    return {
        "practice_root": public_path(root),
        "fits_dir": public_path(fits_dir) if fits_dir.exists() else None,
        "fits_count": len(fits_files),
        "fits_files": [public_path(item) for item in fits_files],
        "calibration_csv": public_path(root / "FWHM_vsini_datafit.csv") if (root / "FWHM_vsini_datafit.csv").exists() else None,
        "istarmod_root": public_path(istarmod_root) if istarmod_root.exists() else None,
        "practice_pdfs": [public_path(item) for item in detected_pdfs],
        "codex_iraf_safe_root": public_path(code_iraf) if code_iraf.exists() else None,
        "codex_analysis_root": public_path(code_analysis) if code_analysis.exists() else None,
        "codex_istarmod_root": public_path(code_istarmod) if code_istarmod.exists() else None,
    }


def recommended_workspace_root(root: str | Path) -> str:
    root = Path(root)
    slug = ascii_safe_slug(root.name)
    return public_path(Path("/tmp") / f"{slug}_legacy_safe")


def load_fits_dependencies():
    from astropy import units as u
    from astropy.coordinates import EarthLocation, SkyCoord
    from astropy.io import fits
    from astropy.time import Time

    return fits, Time, SkyCoord, EarthLocation, u


def read_header_with_warnings(path: str | Path):
    fits, _, _, _, _ = load_fits_dependencies()
    path = Path(path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with fits.open(path, memmap=False, ignore_missing_end=True) as hdul:
            hdul.verify("silentfix")
            header = hdul[0].header.copy()
            data_shape = tuple(getattr(hdul[0].data, "shape", ()) or ())
    return header, data_shape, [str(item.message) for item in caught]


def parse_multispec_entries(header: dict, *, fallback_pixels: int | None = None) -> list[dict]:
    wat_keys = sorted(
        [key for key in header if str(key).upper().startswith("WAT2_")],
        key=lambda item: int(str(item).split("_", 1)[1]),
    )
    wat_blob = "".join(str(header[key]) for key in wat_keys)
    spec_matches = re.findall(r'spec(\d+)\s*=\s*"([^"]+)"', wat_blob)
    results = []
    default_bandid = header.get("BANDID1")
    for spec_index, payload in spec_matches:
        fields = _normalize_multispec_payload(int(spec_index), payload)
        if len(fields) < 9:
            continue
        aperture_1based = int(spec_index)
        beam_index = int(float(fields[1])) if len(fields) > 1 else None
        dispersion_type = int(float(fields[2])) if len(fields) > 2 else None
        lambda_zero = float(fields[3])
        delta_lambda = float(fields[4])
        pixels = int(float(fields[5])) if len(fields) > 5 else int(fallback_pixels or 0)
        lambda_last = lambda_zero + delta_lambda * max(0, pixels - 1)
        results.append(
            {
                "spec_index": int(spec_index),
                "aperture_1based": aperture_1based,
                "aperture_0based": max(0, aperture_1based - 1),
                "beam_index": beam_index,
                "dispersion_type": dispersion_type,
                "pixels": pixels,
                "lambda_zero": lambda_zero,
                "delta_lambda": delta_lambda,
                "lambda_min": min(lambda_zero, lambda_last),
                "lambda_max": max(lambda_zero, lambda_last),
                "lambda_center": 0.5 * (lambda_zero + lambda_last),
                "aperture_low": parse_float(fields[7]) if len(fields) > 7 else None,
                "aperture_high": parse_float(fields[8]) if len(fields) > 8 else None,
                "bandid": default_bandid,
            }
        )
    return results


def _split_float_int_tail(token: str, *, integer_min: int = 1000, integer_max: int = 5000) -> tuple[str, str] | None:
    for length in range(3, 6):
        if len(token) <= length:
            continue
        left = token[:-length]
        right = token[-length:]
        if not right.isdigit():
            continue
        integer_value = int(right)
        if integer_value < integer_min or integer_value > integer_max:
            continue
        try:
            float(left)
        except ValueError:
            continue
        return left, right
    return None


def _split_int_float(token: str, *, integer_min: int = 1000, integer_max: int = 5000) -> tuple[str, str] | None:
    match = re.match(r"^(\d{3,5})(0(?:\.\d*)?|\.\d+)$", token)
    if not match:
        return None
    integer_value = int(match.group(1))
    if integer_value < integer_min or integer_value > integer_max:
        return None
    return match.group(1), match.group(2)


def _split_two_floats(token: str, *, first_min: float | None = None, first_max: float | None = None, second_min: float | None = None, second_max: float | None = None, prefer_second_ge_first: bool = False) -> tuple[str, str] | None:
    candidates = []
    for position in range(1, len(token)):
        left = token[:position]
        right = token[position:]
        try:
            left_value = float(left)
            right_value = float(right)
        except ValueError:
            continue
        if first_min is not None and left_value < first_min:
            continue
        if first_max is not None and left_value > first_max:
            continue
        if second_min is not None and right_value < second_min:
            continue
        if second_max is not None and right_value > second_max:
            continue
        if prefer_second_ge_first and right_value < left_value:
            continue
        candidates.append((left, right, left_value, right_value))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (abs(item[0].count(".") - 1), abs(item[1].count(".") - 1), -len(item[0])))
    best = candidates[0]
    return best[0], best[1]


def _normalize_multispec_payload(spec_index: int, payload: str) -> list[str]:
    body = re.sub(rf"^{spec_index}\s*", "", payload.strip(), count=1)
    tokens = body.split()
    if len(tokens) < 2:
        return [str(spec_index)]

    first = tokens[0]
    second = tokens[1] if len(tokens) > 1 else ""
    remainder_tokens = tokens[2:]

    if second == "0":
        beam = first
        dtype = "0"
        main_tokens = remainder_tokens
    elif first.endswith("0") and first[:-1].isdigit():
        beam = first[:-1]
        dtype = "0"
        main_tokens = tokens[1:]
    elif second.startswith("0") and len(second) > 1 and second[1].isdigit():
        beam = first
        dtype = "0"
        main_tokens = [second[1:], *remainder_tokens]
    else:
        beam = first
        dtype = second
        main_tokens = remainder_tokens

    while len(main_tokens) < 6 or _multispec_tokens_need_cleanup(main_tokens):
        changed = False
        if len(main_tokens) >= 2 and main_tokens[1].isdigit():
            split = _split_two_floats(main_tokens[0], first_min=1000, first_max=20000, second_min=0, second_max=1)
            if split:
                main_tokens = [split[0], split[1], *main_tokens[1:]]
                changed = True
        if not changed and len(main_tokens) >= 2:
            split = _split_float_int_tail(main_tokens[1])
            if split:
                main_tokens = [main_tokens[0], split[0], split[1], *main_tokens[2:]]
                changed = True
        if not changed and len(main_tokens) >= 3:
            split = _split_int_float(main_tokens[2])
            if split:
                main_tokens = [main_tokens[0], main_tokens[1], split[0], split[1], *main_tokens[3:]]
                changed = True
        if not changed and len(main_tokens) >= 4:
            split = _split_two_floats(main_tokens[3], first_min=-1, first_max=1, second_min=10)
            if split:
                main_tokens = [*main_tokens[:3], split[0], split[1], *main_tokens[4:]]
                changed = True
        if not changed and len(main_tokens) >= 5:
            split = _split_two_floats(main_tokens[4], first_min=0, second_min=10, prefer_second_ge_first=True)
            if split:
                main_tokens = [*main_tokens[:4], split[0], split[1], *main_tokens[5:]]
                changed = True
        if not changed:
            break
    return [str(spec_index), beam, dtype, *main_tokens]


def _multispec_tokens_need_cleanup(tokens: list[str]) -> bool:
    preview = tokens[:6]
    for token in preview:
        if token.count(".") > 1:
            return True
    if len(preview) >= 2 and _split_float_int_tail(preview[1]) is not None:
        return True
    if len(preview) >= 3 and _split_int_float(preview[2]) is not None:
        return True
    return False


def csv_write(path: str | Path, rows: list[dict], fieldnames: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def parse_float(token: str | None) -> float | None:
    if token is None:
        return None
    text = str(token).strip()
    if not text or text in {".", ".."} or text.upper() == "INDEF":
        return None
    return float(text)


@dataclass
class FxcorRow:
    object_name: str
    image_name: str
    aperture: int
    shift_pix: float | None
    height: float | None
    fwhm_kms: float | None
    tdr: float | None
    vrel_kms: float | None
    verr_kms: float | None
    veldisp_kms_per_pix: float | None
    template_image: str | None
    template_vhelio_kms: float | None

    @property
    def fwhm_pix(self) -> float | None:
        if self.fwhm_kms is None or self.veldisp_kms_per_pix in (None, 0):
            return None
        return self.fwhm_kms / self.veldisp_kms_per_pix


def parse_fxcor_txt(path: str | Path) -> list[FxcorRow]:
    path = Path(path)
    rows: list[FxcorRow] = []
    veldisp = None
    template_image = None
    template_vhelio = None
    velocity_re = re.compile(r"Velocity Dispersion =\s*([0-9.+-]+)")
    template_re = re.compile(r"Image\s+=\s+'([^']+)'\s+Vhelio\s+=\s+([A-Za-z0-9.+-]+)")
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        if "Velocity Dispersion" in line:
            match = velocity_re.search(line)
            if match:
                veldisp = float(match.group(1))
            continue
        if line.startswith("#                   Image"):
            match = template_re.search(line)
            if match:
                template_image = match.group(1)
                template_vhelio = parse_float(match.group(2))
            continue
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 13:
            continue
        rows.append(
            FxcorRow(
                object_name=parts[0],
                image_name=parts[1],
                template_image=template_image,
                template_vhelio_kms=template_vhelio,
                aperture=int(parts[4]),
                shift_pix=parse_float(parts[6]),
                height=parse_float(parts[7]),
                fwhm_kms=parse_float(parts[8]),
                tdr=parse_float(parts[9]),
                vrel_kms=parse_float(parts[11]),
                verr_kms=parse_float(parts[13]) if len(parts) > 13 else None,
                veldisp_kms_per_pix=veldisp,
            )
        )
    return rows


def parse_header_skycoord(header):
    _, Time, SkyCoord, _, u = load_fits_dependencies()
    ra = header["RA"]
    dec = header["DEC"]
    equinox = float(header.get("EQUINOX", 2000.0))
    equinox_time = Time(equinox, format="jyear")
    if isinstance(ra, str) and ":" in ra:
        return SkyCoord(ra=ra, dec=dec, unit=(u.hourangle, u.deg), frame="fk5", equinox=equinox_time)
    return SkyCoord(ra=float(ra) * u.deg, dec=float(dec) * u.deg, frame="fk5", equinox=equinox_time)


def observatory_location(header):
    _, _, _, EarthLocation, u = load_fits_dependencies()
    observatory = str(header.get("OBSERVAT", "")).strip().upper()
    site = OBSERVATORY_LOCATIONS.get(observatory)
    if site is None:
        raise ValueError(f"Observatorio no soportado para correccion heliocentrica: {observatory or 'INDEF'}")
    return EarthLocation.from_geodetic(site["lon_deg"] * u.deg, site["lat_deg"] * u.deg, site["height_m"] * u.m)


def heliocentric_correction_kms(path: str | Path) -> float:
    _, Time, _, _, u = load_fits_dependencies()
    header, _, _ = read_header_with_warnings(path)
    coord = parse_header_skycoord(header)
    if header.get("DATE-OBS"):
        start = Time(str(header["DATE-OBS"]), format="isot", scale="utc")
    elif header.get("MJD-OBS") is not None:
        mjd = float(header["MJD-OBS"])
        if mjd < 30000:
            mjd += 40000
        start = Time(mjd, format="mjd", scale="utc")
    else:
        raise ValueError(f"No hay DATE-OBS ni MJD-OBS utilizables en {public_path(path)}")
    exptime = float(header.get("EXPTIME", 0.0) or 0.0)
    obstime = start + (exptime / 2.0) * u.s
    corr = coord.radial_velocity_correction(kind="heliocentric", obstime=obstime, location=observatory_location(header))
    return float(corr.to_value(u.km / u.s))


def compute_vhelio_from_vrel(vrel_kms: float, template_vhelio_kms: float, h_template_kms: float, h_object_kms: float) -> tuple[float, float]:
    ref_vobs = template_vhelio_kms - h_template_kms
    vobs = (((1.0 + ref_vobs / C_KMS) * (1.0 + vrel_kms / C_KMS)) - 1.0) * C_KMS
    return vobs, vobs + h_object_kms


def weighted_mean(values: list[float], errors: list[float]) -> tuple[float, float]:
    if not values or not errors:
        raise ValueError("No hay valores suficientes para la media ponderada.")
    weights = [1.0 / (err * err) for err in errors]
    numerator = sum(weight * value for weight, value in zip(weights, values))
    denominator = sum(weights)
    return numerator / denominator, math.sqrt(1.0 / denominator)


def load_vsini_calibration(csv_path: str | Path):
    import numpy as np
    from scipy.interpolate import PchipInterpolator

    xs = []
    ys = []
    with Path(csv_path).open(encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            try:
                xs.append(float(row[0]))
                ys.append(float(row[1]))
            except ValueError:
                if not xs and not ys:
                    continue
                raise
    if len(xs) < 2:
        raise ValueError(f"La calibracion FWHM-v sin i necesita al menos dos filas numericas: {public_path(csv_path)}")
    x = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    order = np.argsort(x)
    return x[order], y[order], PchipInterpolator(x[order], y[order], extrapolate=False)


def default_fxcor_cases(available_fits: set[str] | None = None) -> list[dict]:
    available_fits = set(available_fits or [])
    cases = [
        {
            "case_id": "pwand_rv",
            "label": "PW And velocidad radial",
            "mode": "single_rv",
            "object": "npwand_n3.fits",
            "template": "nhd161096_n3.fits",
            "template_vhelio_kms": -12.5,
            "apertures": DEFAULT_RECOMMENDED_ORDERS,
        },
        {
            "case_id": "pwand_vsini36",
            "label": "PW And v sin i orden 36",
            "mode": "vsini_fwhm",
            "object": "npwand_n3.fits",
            "template": "nhd166620_n2.fits",
            "apertures": [36],
            "osample": "a6444-6534",
            "rsample": "a6444-6534",
        },
        {
            "case_id": "rej_compA_rv",
            "label": "REJ1101 componente A",
            "mode": "sb2_rv",
            "object": "nrej1101_foces02_n2.fits",
            "template": "nhd100696_n3.fits",
            "template_vhelio_kms": 0.2,
            "apertures": DEFAULT_RECOMMENDED_ORDERS,
            "window": 60,
            "wincenter": -110,
        },
        {
            "case_id": "rej_compB_rv",
            "label": "REJ1101 componente B",
            "mode": "sb2_rv",
            "object": "nrej1101_foces02_n2.fits",
            "template": "nhd100696_n3.fits",
            "template_vhelio_kms": 0.2,
            "apertures": DEFAULT_RECOMMENDED_ORDERS,
            "window": 60,
            "wincenter": 80,
        },
        {
            "case_id": "rej_vsini36_compA_k0",
            "label": "REJ1101 v sin i componente A",
            "mode": "vsini_fwhm",
            "object": "nrej1101_foces02_n2.fits",
            "template": "nhd97004_n4.fits",
            "apertures": [36],
            "window": 60,
            "wincenter": -110,
        },
        {
            "case_id": "rej_vsini36_compB_k1",
            "label": "REJ1101 v sin i componente B",
            "mode": "vsini_fwhm",
            "object": "nrej1101_foces02_n2.fits",
            "template": "nhd92588_n2.fits",
            "apertures": [36],
            "window": 60,
            "wincenter": 80,
        },
    ]
    if not available_fits:
        return cases
    return [
        case
        for case in cases
        if case["object"] in available_fits and case["template"] in available_fits
    ]


def find_legacy_tools() -> dict:
    display = None
    try:
        import os

        display = os.environ.get("DISPLAY")
    except Exception:
        display = None
    return {
        "cl": find_executable(["cl"]),
        "mkiraf": find_executable(["mkiraf"]),
        "xgterm": find_executable(["xgterm"]),
        "ssh": find_executable(["ssh"]),
        "pdflatex": find_executable(["pdflatex", "/Library/TeX/texbin/pdflatex"]),
        "display": display,
        "xquartz_app": str(Path("/Applications/Utilities/XQuartz.app")) if Path("/Applications/Utilities/XQuartz.app").exists() else None,
    }


def copy_selected_files(paths: list[Path], target_dir: Path) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in paths:
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied
