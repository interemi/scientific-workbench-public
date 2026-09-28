#!/usr/bin/env python3
"""Regression for the v2.0 P1-13 app-side radial-velocity selector."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "radial_velocity_workbench.py"
APP_ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "references" / "v2-0-p1-13-radial-velocity-selector.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python used to run radial_velocity_workbench.py.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "tmp" / "v2_0_p1_13_radial_velocity"),
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
) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = run_dir / "summary.json"
    manifest = run_dir / "manifest.json"
    command = [
        python,
        str(SCRIPT),
        "inspect",
        str(fixture),
        "--summary-json",
        str(summary),
        "--manifest-json",
        str(manifest),
    ]
    before = fixture.read_bytes()
    proc = subprocess.run(command, text=True, capture_output=True)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    require(proc.returncode == expected_returncode, f"{fixture.name}: return code {proc.returncode}")
    require(payload.get("status") == expected_status, f"{fixture.name}: status {payload.get('status')}")
    require("Traceback" not in proc.stdout + proc.stderr, f"{fixture.name}: raw traceback")
    require(fixture.read_bytes() == before, f"{fixture.name}: original modified")
    return {
        "case": fixture.stem,
        "command": command,
        "returncode": proc.returncode,
        "status": payload.get("status"),
        "app_status": payload.get("app_status"),
        "findings": (payload.get("qa") or {}).get("findings") or [],
        "original_modified": False,
        "artifacts": [str(summary), str(manifest)] if manifest.exists() else [str(summary)],
    }


def check_app_surface() -> None:
    required = {
        APP_ROOT / "Sources/ScientificWorkbench/Models/RadialVelocityInspectionModels.swift": [
            "RadialVelocityTimeSystem",
            "RadialVelocityUnit",
            "RadialVelocitySelectionValidation",
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Services/RadialVelocityInspectionService.swift": [
            "func inspect(path:",
            "func validate(",
            "func stage(",
            "Original Modified = false",
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Views/RadialVelocityInspectionView.swift": [
            "RV Column Review",
            "Run Reviewed Inspection",
            "Next actions",
        ],
        APP_ROOT / "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift": [
            'case "radial_velocity_workbench.inspect"',
        ],
        APP_ROOT / "Tests/ScientificWorkbenchTests/RadialVelocityInspectionTests.swift": [
            "radialVelocityInspectorMapsHappyColumnsAndUnits",
            "radialVelocityInspectorSurfacesAmbiguousCandidates",
            "radialVelocityInspectorBlocksBrokenTable",
            "radialVelocityHeadlessReviewInitializesSelection",
        ],
        APP_ROOT / "Guides/Scientific_Workbench_User_Guide.md": [
            "Inspeccion guiada de velocidad radial",
            "Run Reviewed Inspection",
        ],
    }
    for path, markers in required.items():
        require(path.exists(), f"Missing app file: {path}")
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in text, f"Missing marker {marker!r} in {path.name}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    inputs = output_dir / "inputs"
    runs = output_dir / "runs"
    inputs.mkdir(parents=True, exist_ok=True)

    happy = inputs / "happy.vels"
    happy.write_text(
        "# Time Standard = BJD\n"
        "# Value Units = km/s\n"
        "2459000.1 12.4 0.3\n"
        "2459001.2 13.1 0.4\n",
        encoding="utf-8",
    )
    ambiguous = inputs / "ambiguous.vels"
    ambiguous.write_text(
        "2459000.1 12.4\n"
        "2459001.2 13.1\n",
        encoding="utf-8",
    )
    broken = inputs / "broken.vels"
    broken.write_text("# Value Units = km/s\nnot numeric\n", encoding="utf-8")

    rows = [
        run_case(
            args.python_executable,
            happy,
            runs / "happy",
            expected_returncode=0,
            expected_status="ok",
        ),
        run_case(
            args.python_executable,
            ambiguous,
            runs / "ambiguous",
            expected_returncode=0,
            expected_status="warning",
        ),
        run_case(
            args.python_executable,
            broken,
            runs / "broken",
            expected_returncode=2,
            expected_status="blocked",
        ),
    ]
    check_app_surface()
    require(REFERENCE.exists(), "P1-13 reference is missing")
    reference_text = REFERENCE.read_text(encoding="utf-8")
    require("expert_science" in reference_text, "Exposure boundary is not documented")
    normalized_reference = " ".join(reference_text.lower().split())
    require("not a general-purpose" in normalized_reference, "Domain boundary is not documented")

    summary = {
        "tool": "audit_v2_0_p1_13_radial_velocity_selector_regression",
        "status": "PASS",
        "cases": rows,
        "column_mapping": {
            "roles": ["time", "radial_velocity", "uncertainty"],
            "time_systems": ["JD", "BJD", "HJD", "MJD"],
            "velocity_units": ["km/s", "m/s"],
        },
        "exposure": "expert_science",
        "original_modified": False,
        "reference": str(REFERENCE),
        "app_root": str(APP_ROOT),
        "warnings": [],
        "failures": [],
    }
    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
