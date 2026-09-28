#!/usr/bin/env python3
"""v1.7 phase 2 real-world measurement/noise/QA regression."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "sda_v1_7_phase2_measurement_noise_qa"


TARGETS = {
    "photometry_noise_budget.py": SCRIPT_DIR / "photometry_noise_budget.py",
    "photometric_solution.py": SCRIPT_DIR / "photometric_solution.py",
    "physical_qa.py": SCRIPT_DIR / "physical_qa.py",
    "radial_velocity_workbench.py": SCRIPT_DIR / "radial_velocity_workbench.py",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated fixtures, command logs, and reports.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_strict(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(
        text,
        parse_constant=lambda token: fail(f"non-strict JSON constant emitted: {token}"),
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def copy_to_temp(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def run_command(case_dir: Path, command: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    case_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        cwd=SKILL_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    (case_dir / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")
    (case_dir / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (case_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    (case_dir / "returncode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    return proc


def require_status(payload: dict, expected: set[str], label: str) -> str:
    status = payload.get("status")
    qa_status = (payload.get("qa") or {}).get("status")
    if status not in expected:
        fail(f"{label}: expected status in {sorted(expected)}, got {status}")
    if qa_status != status:
        fail(f"{label}: qa.status {qa_status} did not match status {status}")
    return str(status)


def make_source_fixtures(source_dir: Path) -> dict[str, Path]:
    source_dir.mkdir(parents=True, exist_ok=True)

    calibration = source_dir / "instrument_calibration_standards.csv"
    cal_rows = []
    loads = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1]
    temps = [-0.6, -0.3, 0.0, 0.2, 0.5, 0.8, 1.1, 1.4]
    residuals = [0.0, 0.003, -0.002, 0.001, -0.001, 0.002, -0.003, 0.0]
    for idx, (load, temp, residual) in enumerate(zip(loads, temps, residuals), start=1):
        raw = 100.0 + idx * 7.5
        reference = raw + 2.5 + 0.4 * load - 0.15 * temp + residual
        cal_rows.append(
            {
                "standard_id": f"STD-{idx:02d}",
                "raw_reading": f"{raw:.6f}",
                "reference_value": f"{reference:.6f}",
                "load_level": f"{load:.6f}",
                "temperature_code": f"{temp:.6f}",
                "cal_uncert": "0.020",
            }
        )
    write_csv(
        calibration,
        ["standard_id", "raw_reading", "reference_value", "load_level", "temperature_code", "cal_uncert"],
        cal_rows,
    )

    lab_qa = source_dir / "lab_sensor_series_with_suspect_ranges.csv"
    write_csv(
        lab_qa,
        ["time", "signal", "signal_error", "background_counts", "wavelength"],
        [
            {"time": "2026-05-20T09:00:00", "signal": "10.2", "signal_error": "0.3", "background_counts": "2.1", "wavelength": "500"},
            {"time": "2026-05-20T09:01:00", "signal": "inf", "signal_error": "0.3", "background_counts": "2.0", "wavelength": "501"},
            {"time": "2026-05-20T09:01:00", "signal": "-4.1", "signal_error": "-0.2", "background_counts": "2.2", "wavelength": "500"},
            {"time": "2026-05-20T08:59:00", "signal": "11.0", "signal_error": "0.4", "background_counts": "2.3", "wavelength": "499"},
            {"time": "not-a-time", "signal": "12.0", "signal_error": "0.4", "background_counts": "2.1", "wavelength": "502"},
        ],
    )

    measurement_vels = source_dir / "production_probe_measurements.vels"
    measurement_vels.write_text(
        "\n".join(
            [
                "# value_units = micrometers",
                "# dataset = anonymized production probe QA",
                "2450000.0000 10.0 0.30",
                "2450000.2500 10.4 0.28",
                "bad-row",
                "2450000.5000 inf 0.25",
                "2450000.7500 11.2 -0.10",
                "2450001.0000 10.8",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "calibration": calibration,
        "lab_qa": lab_qa,
        "measurement_vels": measurement_vels,
    }


def case_noise_budget(output_dir: Path) -> dict:
    case_dir = output_dir / "runs" / "photometry_noise_budget"
    summary = case_dir / "sensor_roi_summary.json"
    report = case_dir / "sensor_roi_report.md"
    manifest = case_dir / "sensor_roi_manifest.json"
    command = [
        sys.executable,
        str(TARGETS["photometry_noise_budget.py"]),
        "--source",
        "4200",
        "--sky-per-pixel",
        "12",
        "--dark-per-pixel",
        "0.3",
        "--read-noise",
        "2.1",
        "--n-pixels",
        "64",
        "--sky-estimate-pixels",
        "800",
        "--n-frames",
        "5",
        "--units",
        "electrons",
        "--summary-json",
        str(summary),
        "--report-md",
        str(report),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    if proc.returncode != 0:
        fail(f"photometry_noise_budget failed: {proc.stderr or proc.stdout}")
    payload = read_json_strict(summary)
    status = require_status(payload, {"ok"}, "photometry_noise_budget.py")
    results = payload["results"]
    snr = results.get("snr")
    if not isinstance(snr, (float, int)) or not math.isfinite(float(snr)) or float(snr) <= 0:
        fail("photometry_noise_budget.py emitted invalid SNR")
    if results.get("operating_regime") != "source-shot-noise-limited":
        fail(f"unexpected ROI operating regime: {results.get('operating_regime')}")
    if not report.exists() or not manifest.exists():
        fail("photometry_noise_budget.py did not write report/manifest")
    return {
        "capability": "photometry_noise_budget.py",
        "domain_core": "aperture-photometry/imaging SNR from source, background, dark/leakage, read noise, ROI pixels, and frame count",
        "reusable_pattern": "first-order signal-to-noise budget for a measured sensor ROI",
        "input": "parameterized anonymized machine-vision ROI",
        "command": " ".join(command),
        "status": status.upper(),
        "warning_error": "none",
        "diagnostic": f"SNR={float(snr):.3f}; dominant={results.get('dominant_noise_term')}; regime={results.get('operating_regime')}",
        "modifies_originals": "NO: parameter-only input; outputs isolated under temp run dir",
        "useful_for_real_person": "YES: helps decide whether the ROI measurement is signal, background, or read-noise limited",
        "limits": "Not a full camera/instrument simulator; terms must be mapped honestly.",
        "artifact": str(summary),
    }


def case_photometric_solution(output_dir: Path, source: Path) -> dict:
    case_dir = output_dir / "runs" / "photometric_solution"
    input_copy = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_copy)
    summary = case_dir / "calibration_summary.json"
    coeffs = case_dir / "coefficients.csv"
    residuals = case_dir / "residuals.csv"
    plot = case_dir / "residuals.png"
    report = case_dir / "calibration_report.md"
    manifest = case_dir / "calibration_manifest.json"
    command = [
        sys.executable,
        str(TARGETS["photometric_solution.py"]),
        str(input_copy),
        "--inst-mag-col",
        "raw_reading",
        "--std-mag-col",
        "reference_value",
        "--airmass-col",
        "load_level",
        "--color-col",
        "temperature_code",
        "--include-color-term",
        "--error-col",
        "cal_uncert",
        "--summary-json",
        str(summary),
        "--coefficients-csv",
        str(coeffs),
        "--residual-csv",
        str(residuals),
        "--residual-plot",
        str(plot),
        "--report-md",
        str(report),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command, timeout=120)
    after = sha256(input_copy)
    if before != after:
        fail("photometric_solution.py modified its copied input")
    if proc.returncode != 0:
        fail(f"photometric_solution.py failed: {proc.stderr or proc.stdout}")
    payload = read_json_strict(summary)
    status = require_status(payload, {"ok", "warning"}, "photometric_solution.py")
    results = payload["results"]
    params = results.get("parameters", {})
    zero = params.get("zero_point", {}).get("value")
    load = params.get("extinction", {}).get("value")
    temp = params.get("color_term", {}).get("value")
    if zero is None or abs(float(zero) - 2.5) > 0.02:
        fail(f"unexpected calibration zero_point: {zero}")
    if load is None or abs(float(load) - 0.4) > 0.03:
        fail(f"unexpected calibration load coefficient: {load}")
    if temp is None or abs(float(temp) + 0.15) > 0.03:
        fail(f"unexpected calibration temperature coefficient: {temp}")
    for required in (coeffs, residuals, plot, report, manifest):
        if not required.exists():
            fail(f"photometric_solution.py missing artifact: {required}")
    return {
        "capability": "photometric_solution.py",
        "domain_core": "first-order standard-star calibration with residuals and coefficient uncertainties",
        "reusable_pattern": "linear instrument calibration against standards, with context terms and residual QA",
        "input": str(input_copy),
        "command": " ".join(command),
        "status": status.upper(),
        "warning_error": "; ".join(payload.get("qa", {}).get("findings", [])) or "none",
        "diagnostic": f"zero={float(zero):.4f}; load={float(load):.4f}; temperature={float(temp):.4f}; rms={results.get('rms_residual_mag'):.6f}",
        "modifies_originals": "NO: copied input hash preserved",
        "useful_for_real_person": "YES: gives a traceable first-order calibration and residual files for a lab/instrument table",
        "limits": "Output terminology remains photometric/magnitude-oriented; use only when the linear offset model is appropriate.",
        "artifact": str(summary),
    }


def case_physical_qa(output_dir: Path, source: Path) -> dict:
    case_dir = output_dir / "runs" / "physical_qa"
    input_copy = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_copy)
    summary = case_dir / "physical_qa_summary.json"
    command = [
        sys.executable,
        str(TARGETS["physical_qa.py"]),
        str(input_copy),
        "--summary-json",
        str(summary),
    ]
    proc = run_command(case_dir, command)
    after = sha256(input_copy)
    if before != after:
        fail("physical_qa.py modified its copied input")
    if proc.returncode != 0:
        fail(f"physical_qa.py failed unexpectedly: {proc.stderr or proc.stdout}")
    payload = read_json_strict(summary)
    status = require_status(payload, {"warning"}, "physical_qa.py")
    findings = payload.get("qa", {}).get("findings", [])
    finding_text = " ".join(str(item.get("message", item)) for item in findings)
    expected_fragments = ["non-finite", "negative", "duplicate", "not monotonic"]
    missing = [fragment for fragment in expected_fragments if fragment not in finding_text]
    if missing:
        fail(f"physical_qa.py did not flag expected lab-series issues: {missing}; findings={finding_text}")
    return {
        "capability": "physical_qa.py",
        "domain_core": "light physical sanity checks over FITS, spectra, and scientific tables",
        "reusable_pattern": "table QA for finite values, negative uncertainties, duplicate/nonmonotonic time, and suspicious measurement ranges",
        "input": str(input_copy),
        "command": " ".join(command),
        "status": status.upper(),
        "warning_error": finding_text,
        "diagnostic": f"{len(findings)} finding(s); warning_count={payload.get('qa', {}).get('metrics', {}).get('warning_count')}",
        "modifies_originals": "NO: copied input hash preserved",
        "useful_for_real_person": "YES: flags impossible/suspicious lab sensor rows before modeling or reporting",
        "limits": "Conservative name-based QA; it does not know every domain-specific valid range.",
        "artifact": str(summary),
    }


def case_radial_velocity_inspect(output_dir: Path, source: Path) -> dict:
    case_dir = output_dir / "runs" / "radial_velocity_workbench_inspect"
    input_copy = copy_to_temp(source, case_dir / "input_copy" / source.name)
    before = sha256(input_copy)
    summary = case_dir / "measurement_inspect_summary.json"
    manifest = case_dir / "measurement_inspect_manifest.json"
    command = [
        sys.executable,
        str(TARGETS["radial_velocity_workbench.py"]),
        "inspect",
        str(input_copy),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    proc = run_command(case_dir, command)
    after = sha256(input_copy)
    if before != after:
        fail("radial_velocity_workbench.py inspect modified its copied input")
    if proc.returncode != 0:
        fail(f"radial_velocity_workbench.py inspect should warn, not block: {proc.stderr or proc.stdout}")
    payload = read_json_strict(summary)
    status = require_status(payload, {"warning"}, "radial_velocity_workbench.py inspect")
    metrics = payload.get("qa", {}).get("metrics", {})
    if metrics.get("sample_count_total", 0) <= 0:
        fail("radial_velocity_workbench.py inspect found no reusable measurement samples")
    for key in ("malformed_row_count", "nonfinite_value_row_count", "nonpositive_error_row_count", "missing_error_row_count"):
        if int(metrics.get(key) or 0) <= 0:
            fail(f"radial_velocity_workbench.py inspect did not count {key}")
    findings = payload.get("qa", {}).get("findings", [])
    return {
        "capability": "radial_velocity_workbench.py inspect",
        "domain_core": "Systemic-style radial-velocity time/value/uncertainty input inspection",
        "reusable_pattern": "pre-fit measurement-series intake with time span, uncertainty checks, malformed row counts, and nonfinite/outlier hygiene",
        "input": str(input_copy),
        "command": " ".join(command),
        "status": status.upper(),
        "warning_error": "; ".join(findings),
        "diagnostic": f"samples={metrics.get('sample_count_total')}; malformed={metrics.get('malformed_row_count')}; nonfinite={metrics.get('nonfinite_value_row_count')}",
        "modifies_originals": "NO: copied input hash preserved",
        "useful_for_real_person": "YES: catches bad rows before a manual fit or handoff of measurement-series data",
        "limits": "Still uses .vels/RV terminology; do not present it as a general time-series modeler.",
        "artifact": str(summary),
    }


def write_report(output_dir: Path, cases: list[dict]) -> Path:
    report = output_dir / "phase2_measurement_noise_qa_report.md"
    lines = [
        "# AUDITORIA v1.7 - Fase 2: medicion, ruido y QA real-world",
        "",
        "## Alcance",
        "",
        "Se probaron cuatro capabilities nacidas en ciencia/astro con casos no astrofisicos anonimizados y copiados a temporal.",
        "",
        "## Resultados",
        "",
        "| Capability | Patron reutilizable | Input | Comando | Estado | Warning/error | Diagnostico | Modifica originales | Utilidad real | Artefacto |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        lines.append(
            "| {capability} | {pattern} | `{input}` | `{command}` | {status} | {warning} | {diagnostic} | {modifies} | {useful} | `{artifact}` |".format(
                capability=case["capability"],
                pattern=case["reusable_pattern"],
                input=case["input"],
                command=case["command"].replace("|", "\\|"),
                status=case["status"],
                warning=case["warning_error"].replace("|", "\\|"),
                diagnostic=case["diagnostic"].replace("|", "\\|"),
                modifies=case["modifies_originals"],
                useful=case["useful_for_real_person"],
                artifact=case["artifact"],
            )
        )
    lines.extend(
        [
            "",
            "## Nucleo de dominio y limites",
            "",
        ]
    )
    for case in cases:
        lines.extend(
            [
                f"### {case['capability']}",
                "",
                f"- Nucleo de dominio: {case['domain_core']}",
                f"- Patron reusable: {case['reusable_pattern']}",
                f"- Limite honesto: {case['limits']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision",
            "",
            "La fase queda cubierta por una regresion integrada. No se cambiaron contratos cientificos ni se crearon capabilities nuevas.",
        ]
    )
    report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report


def run_phase(output_dir: Path) -> dict:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_fixtures = make_source_fixtures(output_dir / "generated" / "source_inputs")
    cases = [
        case_noise_budget(output_dir),
        case_photometric_solution(output_dir, source_fixtures["calibration"]),
        case_physical_qa(output_dir, source_fixtures["lab_qa"]),
        case_radial_velocity_inspect(output_dir, source_fixtures["measurement_vels"]),
    ]
    report = write_report(output_dir, cases)
    summary = {
        "phase": "v1.7 phase 2",
        "status": "ok",
        "capability_count": len(cases),
        "case_status_counts": {status: sum(1 for case in cases if case["status"] == status) for status in sorted({case["status"] for case in cases})},
        "output_dir": str(output_dir),
        "report_md": str(report),
        "cases": cases,
    }
    (output_dir / "phase2_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    summary = run_phase(Path(args.output_dir))
    print(json.dumps({key: summary[key] for key in ("phase", "status", "capability_count", "case_status_counts", "report_md")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
