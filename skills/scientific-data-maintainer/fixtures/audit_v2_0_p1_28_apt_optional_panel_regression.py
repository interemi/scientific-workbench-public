#!/usr/bin/env python3
"""Regression for the v2.0 P1-28 APT optional panel."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime


ROOT = Path(__file__).resolve().parents[1]
APT = ROOT / "scripts" / "apt_workbench.py"
PREFLIGHT = ROOT / "scripts" / "external_astro_tools_preflight.py"
REFERENCE = ROOT / "references" / "v2-0-p1-28-apt-optional-panel.md"
DEFAULT_APP_ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "tmp" / "v2_0_p1_28_apt_optional_panel"),
    )
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--summary-json")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(command: list[str], *, expected: int | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=env,
    )
    if expected is not None:
        require(
            completed.returncode == expected,
            f"Expected exit {expected}, found {completed.returncode}: {completed.stderr}",
        )
    require("Traceback" not in completed.stdout + completed.stderr, "Raw traceback escaped")
    return completed


def read_json(path: Path) -> dict:
    require(path.exists(), f"Missing JSON artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def make_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def fake_apt(path: Path) -> Path:
    return make_executable(
        path,
        """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if "-h" in args or "--help" in args:
    print("fake APT batch backend")
    raise SystemExit(0)
out = pathlib.Path(args[args.index("-o") + 1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    "Number  Image  X  Y  SourceIntensity\\n"
    "1  copied_image.fits  10.0  20.0  1234.5\\n"
    "2  copied_image.fits  30.0  40.0  567.8\\n",
    encoding="utf-8",
)
print("fake APT wrote", out)
""",
    )


def validate_app_surface(app_root: Path) -> None:
    required = {
        app_root / "Sources/ScientificWorkbench/Models/OptionalAstronomyBackendModels.swift": [
            "aptOverallStatus",
            "aptPreferences",
            "aptBatch",
        ],
        app_root / "Sources/ScientificWorkbench/Services/OptionalAstronomyBackendService.swift": [
            "--apt-command",
            "--apt-preferences",
            "BLOCKED_CONTROLADO",
        ],
        app_root / "Sources/ScientificWorkbench/Views/OptionalAstronomyBackendsView.swift": [
            "Aperture Photometry Tool (APT)",
            "Run APT Preflight",
            "Inspect FITS Instead",
            "Use Native Noise Budget",
            "Logs are preserved in Jobs",
        ],
        app_root / "Sources/ScientificWorkbench/Stores/WorkbenchStore.swift": [
            "func runAPTPreflight()",
            "func useNativeAPTAlternative",
            "latestAPTJob",
        ],
        app_root / "Sources/ScientificWorkbench/Models/RunModels.swift": [
            "BLOCKED_CONTROLADO",
            "static func resolved",
        ],
        app_root / "Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift": [
            'case "apt_workbench"',
            '"preflight"',
        ],
        app_root / "Tests/ScientificWorkbenchTests/OptionalAstronomyBackendTests.swift": [
            "controlledBackendEnvelopeResolvesToBlockedJobState",
            "optionalAstronomyBackendNativeAPTAlternativeSelectsFitsInspection",
        ],
        app_root / "Guides/Scientific_Workbench_User_Guide.md": [
            "Panel opcional APT",
            "Run APT Preflight",
        ],
    }
    for path, markers in required.items():
        require(path.exists(), f"Missing app file: {path}")
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in text, f"Missing marker {marker!r} in {path.name}")


def main() -> int:
    args = parse_args()
    ensure_datanalysis_runtime("audit_v2_0_p1_28_apt_optional_panel_regression")
    root = Path(args.output_dir).resolve()
    if root.exists():
        shutil.rmtree(root)
    inputs = root / "inputs"
    originals = root / "originals"
    runs = root / "runs"
    tools = root / "tools"
    for directory in (inputs, originals, runs, tools):
        directory.mkdir(parents=True, exist_ok=True)

    real_summary = runs / "real_preflight" / "summary.json"
    real = run(
        [
            sys.executable,
            str(PREFLIGHT),
            "--require-apt",
            "--probe",
            "--summary-json",
            str(real_summary),
        ]
    )
    real_payload = read_json(real_summary)
    require(real_payload.get("app_status") in {"PASS", "WARNING", "BLOCKED_CONTROLADO"}, "Unexpected real preflight state")
    require(real_payload.get("original_modified") is False, "Real preflight modified originals")

    source_original = originals / "sources.csv"
    image_original = originals / "image.fits"
    prefs_original = originals / "APT.pref"
    source_original.write_text("id,x,y\nA,10,20\nB,30,40\n", encoding="utf-8")
    image_original.write_text("Synthetic copied FITS placeholder for fake APT.\n", encoding="utf-8")
    prefs_original.write_text("aperture=5\nannulus_inner=8\nannulus_outer=12\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (source_original, image_original, prefs_original)}

    source_copy = inputs / "sources copied.csv"
    image_copy = inputs / "image copied.fits"
    prefs_copy = inputs / "APT copied.pref"
    shutil.copy2(source_original, source_copy)
    shutil.copy2(image_original, image_copy)
    shutil.copy2(prefs_original, prefs_copy)
    apt_command = fake_apt(tools / "fake APT.csh")

    source_list = runs / "synthetic" / "inputs" / "sources.lst"
    prepare_summary = runs / "synthetic" / "prepare_summary.json"
    prepare_manifest = runs / "synthetic" / "prepare_manifest.json"
    run(
        [
            sys.executable,
            str(APT),
            "prepare-source-list",
            str(source_copy),
            str(source_list),
            "--x-col",
            "x",
            "--y-col",
            "y",
            "--id-col",
            "id",
            "--summary-json",
            str(prepare_summary),
            "--manifest-json",
            str(prepare_manifest),
        ],
        expected=0,
    )

    apt_table = runs / "synthetic" / "tables" / "APT.tbl"
    batch_summary = runs / "synthetic" / "batch_summary.json"
    batch_manifest = runs / "synthetic" / "batch_manifest.json"
    log_dir = runs / "synthetic" / "logs"
    run(
        [
            sys.executable,
            str(APT),
            "run-batch",
            "--apt-command",
            str(apt_command),
            "--apt-preferences",
            str(prefs_copy),
            "--image",
            str(image_copy),
            "--source-list",
            str(source_list),
            "--output-table",
            str(apt_table),
            "--summary-json",
            str(batch_summary),
            "--manifest-json",
            str(batch_manifest),
            "--log-dir",
            str(log_dir),
        ],
        expected=0,
    )

    parsed_csv = runs / "synthetic" / "tables" / "apt_results.csv"
    parse_summary = runs / "synthetic" / "parse_summary.json"
    parse_manifest = runs / "synthetic" / "parse_manifest.json"
    run(
        [
            sys.executable,
            str(APT),
            "parse-results",
            str(apt_table),
            str(parsed_csv),
            "--summary-json",
            str(parse_summary),
            "--manifest-json",
            str(parse_manifest),
        ],
        expected=0,
    )

    batch_payload = read_json(batch_summary)
    parse_payload = read_json(parse_summary)
    require(batch_payload.get("app_status") == "PASS", "Synthetic APT batch did not pass")
    require(parse_payload.get("app_status") == "PASS", "Synthetic APT parse did not pass")
    require((parse_payload.get("results") or {}).get("row_count") == 2, "Expected two parsed APT rows")
    for artifact in (
        source_list,
        apt_table,
        parsed_csv,
        log_dir / "apt_command.sh",
        log_dir / "apt_stdout.txt",
        log_dir / "apt_stderr.txt",
        batch_manifest,
        parse_manifest,
    ):
        require(artifact.exists(), f"Missing synthetic artifact: {artifact}")

    blocked_summary = runs / "missing_backend" / "summary.json"
    blocked_output = runs / "missing_backend" / "APT.tbl"
    blocked = run(
        [
            sys.executable,
            str(APT),
            "run-batch",
            "--apt-command",
            str(root / "missing" / "APT.csh"),
            "--apt-preferences",
            str(root / "missing" / "APT.pref"),
            "--image",
            str(image_copy),
            "--source-list",
            str(source_list),
            "--output-table",
            str(blocked_output),
            "--summary-json",
            str(blocked_summary),
        ],
        expected=2,
    )
    blocked_payload = read_json(blocked_summary)
    require(blocked_payload.get("app_status") == "BLOCKED_CONTROLADO", "Missing backend did not block")
    require(
        all(item.get("kind") == "missing_optional_backend" for item in blocked_payload.get("errors") or []),
        "Missing APT backend/preferences did not use missing_optional_backend",
    )
    require(
        any("APT.pref" in item.get("label", "") for item in blocked_payload.get("next_actions") or []),
        "Blocked APT payload lacks specific next actions",
    )
    require(not blocked_output.exists(), "Blocked APT run left a misleading output table")
    require("Traceback" not in blocked.stdout + blocked.stderr, "Blocked APT run leaked traceback")

    for path, original in before.items():
        require(path.read_bytes() == original, f"Original modified: {path.name}")

    validate_app_surface(Path(args.app_root))
    require(REFERENCE.exists(), "P1-28 reference is missing")
    reference = REFERENCE.read_text(encoding="utf-8")
    for marker in ("optional_panel", "BLOCKED_CONTROLADO", "missing_optional_backend", "photometry_noise_budget.py"):
        require(marker in reference, f"Reference missing marker: {marker}")

    capabilities = (real_payload.get("results") or {}).get("capabilities") or {}
    summary = {
        "tool": "audit_v2_0_p1_28_apt_optional_panel_regression",
        "status": "PASS",
        "real_machine": {
            "returncode": real.returncode,
            "app_status": real_payload.get("app_status"),
            "java_ready": capabilities.get("java_ready"),
            "apt_command_ready": capabilities.get("apt_command_ready"),
            "apt_batch_ready": capabilities.get("apt_batch_ready"),
            "preferences": (real_payload.get("results") or {}).get("apt_preferences"),
        },
        "synthetic": {
            "source_rows": 2,
            "batch_status": batch_payload.get("app_status"),
            "parse_status": parse_payload.get("app_status"),
            "parsed_rows": (parse_payload.get("results") or {}).get("row_count"),
            "artifacts": [
                str(source_list),
                str(apt_table),
                str(parsed_csv),
                str(log_dir / "apt_command.sh"),
                str(log_dir / "apt_stdout.txt"),
                str(log_dir / "apt_stderr.txt"),
                str(batch_manifest),
                str(parse_manifest),
            ],
        },
        "missing_backend": {
            "returncode": blocked.returncode,
            "app_status": blocked_payload.get("app_status"),
            "errors": blocked_payload.get("errors"),
            "next_actions": blocked_payload.get("next_actions"),
            "output_created": blocked_output.exists(),
        },
        "native_alternatives": ["inspect_fits", "photometry_noise_budget"],
        "exposure": "optional_panel",
        "original_modified": False,
        "app_root": str(Path(args.app_root)),
        "reference": str(REFERENCE),
        "warnings": [],
        "failures": [],
    }
    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    summary_path = Path(args.summary_json) if args.summary_json else root / "p1_28_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
