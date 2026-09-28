#!/usr/bin/env python3
"""Regression for the v2.0 P1-26 photometric-calibration selector."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "photometric_solution.py"
APP_ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "references" / "v2-0-p1-26-photometric-calibration-selector.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python used to run photometric_solution.py.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "tmp" / "v2_0_p1_26_photometric_calibration"),
    )
    parser.add_argument("--summary-json")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(
    python: str,
    fixture: Path,
    run_dir: Path,
    *,
    expected_returncode: int,
    expected_status: str,
    extra: list[str] | None = None,
    expect_products: bool = False,
) -> dict:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = run_dir / "summary.json"
    manifest = run_dir / "manifest.json"
    coefficients = run_dir / "artifacts" / "coefficients.csv"
    residuals = run_dir / "tables" / "residuals.csv"
    preview = run_dir / "previews" / "residuals.png"
    report = run_dir / "reports" / "photometric_solution.md"
    command = [
        python,
        str(SCRIPT),
        str(fixture),
        "--summary-json",
        str(summary),
        "--coefficients-csv",
        str(coefficients),
        "--residual-csv",
        str(residuals),
        "--residual-plot",
        str(preview),
        "--report-md",
        str(report),
        "--manifest-json",
        str(manifest),
    ]
    if extra:
        command.extend(extra)
    before = fixture.read_bytes()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(run_dir / "mplconfig")
    proc = subprocess.run(command, text=True, capture_output=True, env=env)
    require(summary.exists(), f"{fixture.name}: summary JSON was not written")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    require(proc.returncode == expected_returncode, f"{fixture.name}: return code {proc.returncode}")
    require(payload.get("status") == expected_status, f"{fixture.name}: status {payload.get('status')}")
    require("Traceback" not in proc.stdout + proc.stderr, f"{fixture.name}: raw traceback")
    require(fixture.read_bytes() == before, f"{fixture.name}: original modified")
    products = [coefficients, residuals, preview, report, manifest]
    if expect_products:
        for product in products:
            require(product.exists(), f"{fixture.name}: missing product {product.name}")
    elif expected_returncode != 0:
        require(
            not any(product.exists() for product in products),
            f"{fixture.name}: blocked input left fit products",
        )
    return {
        "case": fixture.stem,
        "command": command,
        "returncode": proc.returncode,
        "status": payload.get("status"),
        "app_status": payload.get("app_status"),
        "short_summary": payload.get("short_summary"),
        "quality_flags": (payload.get("results") or {}).get("quality_flags") or [],
        "original_modified": False,
        "artifacts": [str(path) for path in [summary, *products] if path.exists()],
    }


def check_app_surface() -> None:
    required = {
        APP_ROOT / "Sources/ScientificWorkbench/Models/PhotometricCalibrationModels.swift": [
            "PhotometricCalibrationSelection",
            "PhotometricCalibrationValidation",
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Services/PhotometricCalibrationService.swift": [
            "func inspect(path:",
            "func validate(",
            "func stage(",
            '"original_modified": false',
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Views/PhotometricCalibrationView.swift": [
            "Photometric Calibration Review",
            "Table Preview",
            "Fit Reviewed Calibration",
            "Include color term",
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift": [
            'case "photometric_solution"',
            "artifacts/coefficients.csv",
            "previews/residuals.png",
        ],
        APP_ROOT / "Tests/ScientificWorkbenchTests/PhotometricCalibrationTests.swift": [
            "photometricCalibrationMapsHappyColumns",
            "photometricCalibrationSurfacesAmbiguousColumns",
            "photometricCalibrationWarnsAndExcludesNonfiniteRows",
            "photometricCalibrationBlocksMissingRequiredColumns",
            "photometricCalibrationStagesCanonicalCopyWithoutTouchingOriginal",
        ],
        APP_ROOT / "Guides/Scientific_Workbench_User_Guide.md": [
            "Calibracion fotometrica guiada",
            "Fit Reviewed Calibration",
        ],
    }
    for path, markers in required.items():
        require(path.exists(), f"Missing app file: {path}")
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in text, f"Missing marker {marker!r} in {path.name}")


def write_fixtures(inputs: Path) -> dict[str, Path]:
    happy = inputs / "happy.csv"
    happy.write_text(
        "inst_mag,std_mag,airmass,color_index,offset_err\n"
        "-14.40,9.561900,1.02,-0.10,0.015\n"
        "-14.20,9.773250,1.25,0.65,0.015\n"
        "-14.00,9.918600,1.48,0.20,0.015\n"
        "-13.80,10.135600,1.73,1.10,0.015\n"
        "-13.60,10.406500,1.10,0.90,0.015\n"
        "-13.40,10.469650,1.92,0.35,0.015\n"
        "-13.20,10.796150,1.37,1.35,0.015\n"
        "-13.00,10.889550,1.64,0.05,0.015\n"
        "-12.80,11.076050,2.04,0.75,0.015\n"
        "-12.60,11.383750,1.55,1.55,0.015\n",
        encoding="utf-8",
    )
    narrow = inputs / "narrow.csv"
    narrow.write_text(
        "inst_mag,std_mag,airmass,color_index,offset_err\n"
        "-14.1,10.1,1.10,0.50,0.02\n"
        "-13.9,10.3,1.12,0.53,0.02\n"
        "-13.7,10.5,1.13,0.55,0.02\n"
        "-13.5,10.7,1.14,0.56,0.02\n",
        encoding="utf-8",
    )
    nonfinite = inputs / "nonfinite.csv"
    nonfinite.write_text(
        "inst_mag,std_mag,airmass\n"
        "-14.0,10.0,1.0\n"
        "-13.9,10.1,Inf\n"
        "-13.8,10.2,1.4\n",
        encoding="utf-8",
    )
    missing = inputs / "missing_columns.csv"
    missing.write_text(
        "instrumental,standard,secz\n"
        "-14.0,10.0,1.0\n"
        "-13.9,10.1,1.2\n"
        "-13.8,10.2,1.4\n",
        encoding="utf-8",
    )
    return {
        "happy": happy,
        "narrow": narrow,
        "nonfinite": nonfinite,
        "missing": missing,
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    inputs = output_dir / "inputs"
    runs = output_dir / "runs"
    inputs.mkdir(parents=True, exist_ok=True)
    fixtures = write_fixtures(inputs)

    color_args = [
        "--color-col",
        "color_index",
        "--include-color-term",
        "--error-col",
        "offset_err",
    ]
    rows = [
        run_case(
            args.python_executable,
            fixtures["happy"],
            runs / "happy",
            expected_returncode=0,
            expected_status="ok",
            extra=color_args,
            expect_products=True,
        ),
        run_case(
            args.python_executable,
            fixtures["narrow"],
            runs / "narrow",
            expected_returncode=0,
            expected_status="warning",
            extra=color_args,
            expect_products=True,
        ),
        run_case(
            args.python_executable,
            fixtures["nonfinite"],
            runs / "nonfinite",
            expected_returncode=2,
            expected_status="blocked",
        ),
        run_case(
            args.python_executable,
            fixtures["missing"],
            runs / "missing",
            expected_returncode=2,
            expected_status="blocked",
        ),
    ]
    check_app_surface()
    require(REFERENCE.exists(), "P1-26 reference is missing")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    require("expert_science" in reference_text, "Exposure boundary is not documented")
    require("keeps its existing scientific fit" in reference_text, "Fit boundary is not documented")

    summary = {
        "tool": "audit_v2_0_p1_26_photometric_calibration_regression",
        "status": "PASS",
        "cases": rows,
        "column_mapping": {
            "required": ["instrumental_mag", "catalog_mag", "airmass"],
            "optional": ["filter", "uncertainty", "color_index"],
            "canonical": [
                "inst_mag",
                "std_mag",
                "airmass",
                "filter",
                "color_index",
                "offset_err",
            ],
        },
        "fit_summary_artifacts": [
            "summary_json",
            "manifest_json",
            "table_csv",
            "preview_png",
            "report_md",
        ],
        "exposure": "expert_science",
        "original_modified": False,
        "reference": str(REFERENCE),
        "app_root": str(APP_ROOT),
        "warnings": [],
        "failures": [],
    }
    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    summary_path = Path(args.summary_json) if args.summary_json else output_dir / "p1_26_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
