#!/usr/bin/env python3
"""v1.8 app-like regression for science, astro, optional, and legacy routes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
import os
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tmp" / "v1_8_phase7_app_like_science_astro"
INPUTS = TMP / "inputs"
RUNS = TMP / "runs"
REPORT = TMP / "phase7_app_like_science_astro_report.md"
SUMMARY = TMP / "phase7_app_like_science_astro_summary.json"
PYTHON = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_file():
        return {path.name: sha256(path)}
    hashes: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            hashes[str(item.relative_to(path))] = sha256(item)
    return hashes


def clean_tmp() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    INPUTS.mkdir(parents=True)
    RUNS.mkdir(parents=True)


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def make_wcs_fits(path: Path) -> None:
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    size = 64
    y, x = np.mgrid[0:size, 0:size]
    star = 450.0 * np.exp(-((x - 32.0) ** 2 + (y - 30.0) ** 2) / (2 * 4.0**2))
    background = 90.0 + 0.25 * x + 0.1 * y
    data = (background + star).astype("float32")

    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [150.0, 2.0]
    wcs.wcs.crpix = [32.0, 32.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    header = wcs.to_header()
    header["OBJECT"] = "Synthetic AppReady Field"
    header["FILTER"] = "V"
    header["EXPTIME"] = 30.0
    header["AIRMASS"] = 1.2
    header["DATE-OBS"] = "2026-01-01T00:00:00"
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def make_ambiguous_fits(path: Path) -> None:
    import numpy as np
    from astropy.io import fits

    data = np.full((24, 24), np.nan, dtype="float32")
    data[0, 0] = math.inf
    data[1, 1] = -10.0
    header = fits.Header()
    header["OBJECT"] = "Ambiguous Header"
    header["EXPTIME"] = -5.0
    header["AIRMASS"] = 0.4
    header["DATE-OBS"] = "not-a-date"
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)


def make_png(path: Path, *, invert: bool = False) -> None:
    import numpy as np
    from PIL import Image

    y, x = np.mgrid[0:48, 0:48]
    red = np.clip(40 + x * 4, 0, 255)
    green = np.clip(50 + y * 4, 0, 255)
    blue = np.clip(180 - ((x - 24) ** 2 + (y - 24) ** 2) ** 0.5 * 4, 0, 255)
    rgb = np.dstack([red, green, blue]).astype("uint8")
    if invert:
        rgb = 255 - rgb
    Image.fromarray(rgb, mode="RGB").save(path)


def make_li_spectrum(path: Path) -> None:
    import numpy as np

    wave = np.linspace(6698.0, 6718.0, 500)
    continuum = 1.0 + 0.002 * (wave - 6708.0)
    absorption = 0.17 * np.exp(-0.5 * ((wave - 6707.8) / 0.22) ** 2)
    flux = continuum - absorption
    rows = [[f"{w:.5f}", f"{f:.8f}"] for w, f in zip(wave, flux)]
    write_csv(path, ["wavelength", "flux"], rows)


def base_rv_manifest() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "tool": "radial_velocity_workbench",
        "language": "es",
        "title": "RV app-like regression",
        "backend": "generic-rv",
        "system_name": "HD AppReady",
        "source_files": ["input.vels"],
        "star_metadata": {"name": "HD AppReady"},
        "rv_datasets": [
            {
                "label": "mock",
                "source": "input.vels",
                "sample_count": 5,
                "value_units": "m/s",
                "jd_span_days": 4.0,
            }
        ],
        "objective": "Validate a copied manual RV manifest before report building.",
        "initial_search": {
            "raw_rv_figure": "figures/raw_rv.png",
            "initial_periodogram_figure": "figures/initial_periodogram.png",
            "dominant_periods_days": [42.0],
            "false_alarm_probabilities": [0.01],
            "notes": "ok",
        },
        "fitted_model": {
            "planet_count": 1,
            "fitted_rv_figure": "figures/fitted_rv.png",
            "statistics_figure": "figures/statistics.png",
            "residual_periodogram_figure": "figures/residual_periodogram.png",
            "chi2_before": 2.0,
            "chi2_after": 1.1,
            "rms_before": 3.0,
            "rms_after": 1.5,
            "optimization_notes": "ok",
        },
        "dynamics": {
            "integration_horizon": "1000 yr",
            "dynamics_figure": "figures/dynamics.png",
            "notes": "ok",
        },
        "conclusions": "Synthetic manifest for app-like validation.",
        "caveats": "No scientific claim; regression fixture only.",
        "workflow_notes": [],
        "report_readiness_notes": [],
        "validation": {},
        "planets": [
            {
                "label": "Planet 1",
                "period_days": 42.0,
                "phased_rv_figure": "figures/phased_planet1.png",
                "notes": "ok",
            }
        ],
    }


def prepare_rv_session(root: Path) -> Path:
    session = root / "rv_session"
    figures = session / "figures"
    figures.mkdir(parents=True)
    (session / "input.vels").write_text(
        "# value_units = m/s\n"
        "2450000 1.0 0.2\n"
        "2450001 1.8 0.2\n"
        "2450002 -0.2 0.3\n"
        "2450003 -1.4 0.3\n"
        "2450004 0.4 0.2\n",
        encoding="utf-8",
    )
    manifest = base_rv_manifest()
    figure_paths = [
        manifest["initial_search"]["raw_rv_figure"],
        manifest["initial_search"]["initial_periodogram_figure"],
        manifest["fitted_model"]["fitted_rv_figure"],
        manifest["fitted_model"]["statistics_figure"],
        manifest["fitted_model"]["residual_periodogram_figure"],
        manifest["dynamics"]["dynamics_figure"],
        manifest["planets"][0]["phased_rv_figure"],
    ]
    for raw in figure_paths:
        (session / raw).write_bytes(b"placeholder")
    manifest_path = session / "session_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest_path


def make_fixtures() -> dict[str, Path]:
    fixtures: dict[str, Path] = {}

    fits_dir = INPUTS / "fits"
    fits_dir.mkdir(parents=True)
    good_fits = fits_dir / "science_wcs.fits"
    ambiguous_fits = fits_dir / "ambiguous_header.fits"
    broken_fits = fits_dir / "broken_header.fits"
    make_wcs_fits(good_fits)
    make_ambiguous_fits(ambiguous_fits)
    broken_fits.write_text("This file has a .fits suffix but no FITS blocks.\n", encoding="utf-8")
    fixtures["science_fits"] = good_fits
    fixtures["ambiguous_fits"] = ambiguous_fits
    fixtures["broken_fits"] = broken_fits

    standards = INPUTS / "photometry" / "standards.csv"
    rows = []
    for idx, (airmass, color) in enumerate([(1.0, 0.2), (1.1, 0.5), (1.25, 0.8), (1.4, 1.0), (1.6, 0.3), (1.8, 0.9)]):
        inst_mag = 12.0 + idx * 0.15
        std_mag = inst_mag + 24.5 - 0.18 * airmass + 0.05 * color + (idx - 2) * 0.002
        rows.append([f"{inst_mag:.5f}", f"{std_mag:.5f}", f"{airmass:.3f}", f"{color:.3f}", "0.015"])
    write_csv(standards, ["inst_mag", "std_mag", "airmass", "color", "error"], rows)
    fixtures["standards"] = standards

    left = INPUTS / "catalogs" / "left_catalog.csv"
    right = INPUTS / "catalogs" / "right_catalog.csv"
    write_csv(left, ["source_id", "ra_deg", "dec_deg", "flux"], [["L1", 150.0000, 2.0000, 100], ["L2", 150.0100, 2.0100, 80]])
    write_csv(right, ["catalog_id", "ra_deg", "dec_deg", "mag"], [["R1", 150.00008, 2.00002, 15.1], ["R2", 151.0, 3.0, 19.5]])
    fixtures["left_catalog"] = left
    fixtures["right_catalog"] = right

    png_dir = INPUTS / "rgb"
    png_dir.mkdir(parents=True)
    current_png = png_dir / "current_rgb.png"
    previous_png = png_dir / "previous_rgb.png"
    make_png(current_png)
    make_png(previous_png, invert=True)
    fixtures["current_png"] = current_png
    fixtures["previous_png"] = previous_png

    spectrum = INPUTS / "spectra" / "li_spectrum.csv"
    make_li_spectrum(spectrum)
    fixtures["li_spectrum"] = spectrum

    rv_manifest = prepare_rv_session(INPUTS / "rv")
    fixtures["rv_vels"] = rv_manifest.parent / "input.vels"
    fixtures["rv_manifest"] = rv_manifest

    generic = INPUTS / "general" / "expenses.csv"
    write_csv(generic, ["date", "category", "amount_eur"], [["2026-01-01", "groceries", 52.4], ["2026-01-02", "transport", 13.2]])
    fixtures["generic_table"] = generic

    legacy_root = INPUTS / "legacy_empty_root"
    legacy_root.mkdir(parents=True)
    fixtures["legacy_empty_root"] = legacy_root
    fixtures["legacy_missing_root"] = INPUTS / "missing_legacy_root"

    return fixtures


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def app_status(payload: dict[str, Any]) -> str:
    return payload.get("app_status") or {
        "ok": "PASS",
        "warning": "WARNING",
        "blocked": "BLOCKED_CONTROLADO",
        "fail": "FAIL",
    }.get(str(payload.get("status", "")).lower(), "FAIL")


def path_from_payload(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def discover_artifacts(summary_path: Path, payload: dict[str, Any], explicit_outputs: list[Path] | None = None) -> list[str]:
    discovered: list[str] = []
    if summary_path.exists():
        discovered.append(str(summary_path))
    for item in payload.get("typed_artifacts", []) or []:
        raw_path = item.get("path") if isinstance(item, dict) else None
        if not raw_path:
            continue
        candidate = path_from_payload(str(raw_path))
        if candidate.exists():
            discovered.append(str(candidate))
    for candidate in explicit_outputs or []:
        if candidate.exists():
            discovered.append(str(candidate))
    return sorted(set(discovered))


def validate_envelope(payload: dict[str, Any], case: str) -> None:
    for key in ("contract_version", "tool", "status", "qa", "next_actions", "original_modified"):
        require(key in payload, f"{case}: missing envelope field {key}")
    require(payload["contract_version"] == "1.8", f"{case}: unexpected contract_version")
    require(payload["original_modified"] is False, f"{case}: original_modified must be false")
    require(isinstance(payload.get("next_actions"), list) and payload["next_actions"], f"{case}: empty next_actions")
    require(app_status(payload) in {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"}, f"{case}: invalid app_status")


def capability_cases(fixtures: dict[str, Path]) -> list[dict[str, Any]]:
    missing_stilts = str(INPUTS / "missing_backends" / "stilts")
    missing_apt = str(INPUTS / "missing_backends" / "APT.csh")
    return [
        {
            "target": "inspect_fits.py",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["science_fits"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "FITS valido con WCS: deberia generar summary, manifest y preview para modo astro.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "inspect_fits.py"),
                str(fixtures["science_fits"]),
                "--preview",
                str(run / "preview.png"),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "preview.png", run / "manifest.json"],
        },
        {
            "target": "physical_qa.py",
            "case_type": "header/datos ambiguos con WARNING",
            "input": fixtures["ambiguous_fits"],
            "expected": {"WARNING"},
            "exposure": "normal_ciencia",
            "diagnostic": "FITS con EXPTIME/AIRMASS/DATE-OBS sospechosos y baja fraccion finita debe avisar sin exito silencioso.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "physical_qa.py"),
                str(fixtures["ambiguous_fits"]),
                "--summary-json",
                str(run / "summary.json"),
            ],
            "summary": lambda run: run / "summary.json",
        },
        {
            "target": "photometry_noise_budget.py",
            "case_type": "ciencia/astro feliz sintetico",
            "input": None,
            "expected": {"PASS"},
            "exposure": "normal_ciencia",
            "diagnostic": "Presupuesto de ruido numerico: patron transferible de SNR con report y manifest.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "photometry_noise_budget.py"),
                "--source",
                "1200",
                "--sky-per-pixel",
                "6",
                "--dark-per-pixel",
                "0.2",
                "--read-noise",
                "3.5",
                "--n-pixels",
                "22",
                "--sky-estimate-pixels",
                "200",
                "--n-frames",
                "3",
                "--summary-json",
                str(run / "summary.json"),
                "--report-md",
                str(run / "report.md"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "report.md", run / "manifest.json"],
        },
        {
            "target": "photometric_solution.py",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["standards"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto_ciencia",
            "diagnostic": "Calibracion lineal reproducible desde estandares; util en app si la UI mapea columnas.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "photometric_solution.py"),
                str(fixtures["standards"]),
                "--inst-mag-col",
                "inst_mag",
                "--std-mag-col",
                "std_mag",
                "--airmass-col",
                "airmass",
                "--color-col",
                "color",
                "--error-col",
                "error",
                "--include-color-term",
                "--summary-json",
                str(run / "summary.json"),
                "--coefficients-csv",
                str(run / "coefficients.csv"),
                "--residual-csv",
                str(run / "residuals.csv"),
                "--residual-plot",
                str(run / "residuals.png"),
                "--report-md",
                str(run / "report.md"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "coefficients.csv", run / "residuals.csv", run / "residuals.png", run / "report.md", run / "manifest.json"],
        },
        {
            "target": "catalog_workbench.py crossmatch-sky",
            "case_type": "ciencia/astro feliz sintetico",
            "input": [fixtures["left_catalog"], fixtures["right_catalog"]],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "Crossmatch celeste con radio pequeno: patron util, pero contrato sigue sky-only.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "catalog_workbench.py"),
                "crossmatch-sky",
                str(fixtures["left_catalog"]),
                str(fixtures["right_catalog"]),
                str(run / "matches.csv"),
                "--left-ra",
                "ra_deg",
                "--left-dec",
                "dec_deg",
                "--right-ra",
                "ra_deg",
                "--right-dec",
                "dec_deg",
                "--radius-arcsec",
                "1.0",
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "matches.csv", run / "manifest.json"],
        },
        {
            "target": "rgb_visual_fits_export.py",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["current_png"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "Exporta un PNG RGB ya renderizado a FITS display-only con manifest y comparacion.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "rgb_visual_fits_export.py"),
                str(fixtures["current_png"]),
                str(run / "visual_rgb.fits"),
                "--previous-png",
                str(fixtures["previous_png"]),
                "--comparison-png",
                str(run / "comparison.png"),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
                "--object-name",
                "Synthetic RGB",
                "--reason",
                "phase7 app-like display export",
                "--force",
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "visual_rgb.fits", run / "comparison.png", run / "manifest.json"],
        },
        {
            "target": "astrometry_net_workbench.py preflight",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["science_fits"],
            "expected": {"PASS", "WARNING", "BLOCKED_CONTROLADO"},
            "exposure": "experto",
            "diagnostic": "Preflight de astrometria: debe inferir hints o bloquear/avisar con honestidad sin resolver.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "astrometry_net_workbench.py"),
                "preflight",
                str(fixtures["science_fits"]),
                "--summary-json",
                str(run / "summary.json"),
                "--report-md",
                str(run / "report.md"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "report.md", run / "manifest.json"],
        },
        {
            "target": "astrometry_net_workbench.py verify-existing-wcs",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["science_fits"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "Verifica WCS existente sin re-solve, con QA y artefactos trazables.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "astrometry_net_workbench.py"),
                "verify-existing-wcs",
                str(fixtures["science_fits"]),
                "--output-dir",
                str(run / "wcs_qa"),
                "--summary-json",
                str(run / "summary.json"),
                "--report-md",
                str(run / "report.md"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "report.md", run / "manifest.json", run / "wcs_qa"],
        },
        {
            "target": "radial_velocity_workbench.py inspect",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["rv_vels"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "Inspecciona RV con incertidumbres; app debe tratarlo como modo experto astro/RV.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "radial_velocity_workbench.py"),
                "inspect",
                str(fixtures["rv_vels"]),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "radial_velocity_workbench.py validate-manifest",
            "case_type": "ciencia/astro feliz sintetico",
            "input": fixtures["rv_manifest"],
            "expected": {"PASS", "WARNING"},
            "exposure": "experto",
            "diagnostic": "Valida manifest manual Systemic/RV y deja hallazgos listos para UI experta.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "radial_velocity_workbench.py"),
                "validate-manifest",
                str(fixtures["rv_manifest"]),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "li6708_equivalent_width_workbench.py measure",
            "case_type": "domain_specific experto",
            "input": fixtures["li_spectrum"],
            "expected": {"PASS", "WARNING"},
            "exposure": "no_exponer_normal",
            "diagnostic": "Medida Li I es estrecha: util solo en modo experto espectroscopia, sin analogias generales.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "li6708_equivalent_width_workbench.py"),
                "measure",
                str(fixtures["li_spectrum"]),
                "--output-dir",
                str(run / "li_bundle"),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
                "--continuum-window",
                "6699",
                "6704",
                "--continuum-window",
                "6711",
                "6717",
                "--integration-window",
                "6707.2",
                "6708.4",
                "--skip-systematic-grid",
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json", run / "li_bundle"],
        },
        {
            "target": "stilts_workbench.py preflight",
            "case_type": "backend opcional ausente",
            "input": None,
            "expected": {"BLOCKED_CONTROLADO"},
            "exposure": "panel_opcional",
            "diagnostic": "STILTS ausente forzado debe bloquear de forma controlada y sugerir alternativa nativa.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "stilts_workbench.py"),
                "preflight",
                "--stilts-command",
                missing_stilts,
                "--summary-json",
                str(run / "summary.json"),
            ],
            "summary": lambda run: run / "summary.json",
        },
        {
            "target": "apt_workbench.py preflight",
            "case_type": "backend opcional ausente",
            "input": None,
            "expected": {"BLOCKED_CONTROLADO"},
            "exposure": "panel_opcional",
            "diagnostic": "APT ausente forzado debe bloquear limpio y no fingir batch mode.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "apt_workbench.py"),
                "preflight",
                "--apt-command",
                missing_apt,
                "--summary-json",
                str(run / "summary.json"),
            ],
            "summary": lambda run: run / "summary.json",
        },
        {
            "target": "teareduce_router.py",
            "case_type": "domain_specific rechazado para uso general",
            "input": fixtures["generic_table"],
            "expected": {"PASS", "WARNING"},
            "exposure": "panel_opcional_experto",
            "diagnostic": "Para una tabla administrativa debe preferir stack nativo, no TEAREDUCE.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "teareduce_router.py"),
                "--intent",
                "analizar tabla administrativa general, no reduccion espectroscopica",
                str(fixtures["generic_table"]),
                "--summary-json",
                str(run / "summary.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "extra_check": lambda payload: require(
                (payload.get("results") or {}).get("recommended_backend") == "native",
                "teareduce_router.py: debe recomendar native para tabla general",
            ),
        },
        {
            "target": "legacy_spectroscopy_envcheck.py",
            "case_type": "legacy no disponible",
            "input": fixtures["legacy_missing_root"],
            "expected": {"BLOCKED_CONTROLADO"},
            "exposure": "experto_legacy",
            "diagnostic": "Ruta legacy inexistente debe bloquear limpio, sin crear productos que parezcan validos.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "legacy_spectroscopy_envcheck.py"),
                str(fixtures["legacy_missing_root"]),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "fxcor_iraf_workbench.py prepare-session",
            "case_type": "legacy no disponible",
            "input": fixtures["legacy_missing_root"],
            "expected": {"BLOCKED_CONTROLADO"},
            "exposure": "experto_legacy",
            "diagnostic": "Preparacion fxcor sobre practica inexistente debe bloquear antes de crear workspace enganoso.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "fxcor_iraf_workbench.py"),
                "prepare-session",
                str(fixtures["legacy_missing_root"]),
                "--output-dir",
                str(run / "fxcor_workspace"),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "istarmod_workbench.py inspect-tree",
            "case_type": "legacy no disponible",
            "input": fixtures["legacy_missing_root"],
            "expected": {"BLOCKED_CONTROLADO"},
            "exposure": "experto_legacy",
            "diagnostic": "Inspect-tree sobre ruta inexistente debe bloquear como legacy experto no disponible.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "istarmod_workbench.py"),
                "inspect-tree",
                str(fixtures["legacy_missing_root"]),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "inspect_fits.py",
            "case_type": "entrada rota con FAIL/BLOCKED limpio",
            "input": fixtures["broken_fits"],
            "expected": {"BLOCKED_CONTROLADO", "FAIL"},
            "exposure": "experto",
            "diagnostic": "Archivo con extension FITS falsa debe fallar o bloquear limpio, sin traceback.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "inspect_fits.py"),
                str(fixtures["broken_fits"]),
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
        },
        {
            "target": "scientific_workflow_router.py",
            "case_type": "domain_specific rechazado para uso general",
            "input": fixtures["generic_table"],
            "expected": {"PASS"},
            "exposure": "normal",
            "diagnostic": "El router debe rechazar rutas astro/legacy para una tabla personal/profesional general.",
            "command": lambda run: [
                str(PYTHON),
                str(SCRIPTS / "scientific_workflow_router.py"),
                "plan",
                str(fixtures["generic_table"]),
                "--task",
                "analizar gastos personales anonimizados",
                "--summary-json",
                str(run / "summary.json"),
                "--manifest-json",
                str(run / "manifest.json"),
            ],
            "summary": lambda run: run / "summary.json",
            "outputs": lambda run: [run / "manifest.json"],
            "extra_check": validate_router_rejections,
        },
    ]


def validate_router_rejections(payload: dict[str, Any]) -> None:
    recommended_labels = {item.get("label") for item in payload.get("recommended_capabilities", [])}
    rejected_labels = {item.get("label") for item in payload.get("rejected_capabilities", [])}
    forbidden = {
        "inspect_fits.py",
        "fits_rgb_batch.py",
        "astrometry_net_workbench.py",
        "legacy/astro narrow routes",
    }
    require(not (recommended_labels & forbidden), f"router recommended domain-specific labels for general use: {recommended_labels & forbidden}")
    require("legacy/astro narrow routes" in rejected_labels or "inspect_fits.py" in rejected_labels, "router did not explicitly reject astro/legacy routes")


def input_hashes_for(value: Any) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if isinstance(value, list):
        return {str(path): hash_tree(path) for path in value}
    path = Path(value)
    return {str(path): hash_tree(path)}


def run_case(item: dict[str, Any]) -> dict[str, Any]:
    slug_source = f"{item['target']}_{item['case_type']}"
    slug = "".join(char if char.isalnum() else "_" for char in slug_source.lower()).strip("_")
    run_dir = RUNS / slug
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = item["command"](run_dir)
    summary_json = item["summary"](run_dir)
    before = input_hashes_for(item.get("input"))
    result = run_command(cmd)
    after = input_hashes_for(item.get("input"))
    require(before == after, f"{item['target']}: capability modified input")
    require("Traceback" not in result.stdout + result.stderr, f"{item['target']}: raw traceback in output")
    require(summary_json.exists(), f"{item['target']}: missing summary_json")
    payload = load_json(summary_json)
    validate_envelope(payload, item["target"])
    if "extra_check" in item:
        item["extra_check"](payload)
    status = app_status(payload)
    require(status in item["expected"], f"{item['target']}: app_status {status} not in expected {sorted(item['expected'])}")
    accepted_returncodes = {0}
    if status in {"WARNING", "BLOCKED_CONTROLADO", "FAIL"}:
        accepted_returncodes.add(1)
        accepted_returncodes.add(2)
    require(result.returncode in accepted_returncodes, f"{item['target']}: returncode {result.returncode} does not match status {status}")
    artifacts = discover_artifacts(summary_json, payload, item.get("outputs", lambda run: [])(run_dir) if callable(item.get("outputs")) else [])
    require(artifacts, f"{item['target']}: no artifacts discovered")
    return {
        "target": item["target"],
        "case_type": item["case_type"],
        "input": str(item.get("input")),
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "state": status,
        "exposure": item["exposure"],
        "diagnostic": item["diagnostic"],
        "summary_json": str(summary_json),
        "artifact_count": len(artifacts),
        "artifacts": artifacts[:14],
        "warnings": payload.get("warnings") or [],
        "errors": payload.get("errors") or [],
        "helpful_for_real_person": status in {"PASS", "WARNING", "BLOCKED_CONTROLADO"} and bool(payload.get("next_actions")),
    }


def main() -> int:
    clean_tmp()
    fixtures = make_fixtures()
    rows = [run_case(item) for item in capability_cases(fixtures)]

    overall = "PASS" if all(row["state"] in {"PASS", "WARNING", "BLOCKED_CONTROLADO", "FAIL"} for row in rows) else "FAIL"
    SUMMARY.write_text(json.dumps({"status": overall, "rows": rows}, indent=2, ensure_ascii=True), encoding="utf-8")

    lines = [
        "# v1.8 Phase 7 App-Like Science/Astro Regression",
        "",
        f"Status: {overall}",
        "",
        "| target | tipo | estado | exposicion app | artefactos | diagnostico |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['target']}` | {row['case_type']} | `{row['state']}` | `{row['exposure']}` | {row['artifact_count']} | {row['diagnostic']} |"
        )
    lines.extend(["", f"Machine summary: `{SUMMARY}`", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": overall, "report": str(REPORT), "summary": str(SUMMARY), "case_count": len(rows)}, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
