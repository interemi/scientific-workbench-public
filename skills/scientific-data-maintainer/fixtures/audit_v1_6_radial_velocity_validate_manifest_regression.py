#!/usr/bin/env python3
"""Regression checks for radial_velocity_workbench.py validate-manifest v1.6 edge behavior."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().with_name("radial_velocity_workbench.py")


FIGURE_KEYS = [
    ("initial_search", "raw_rv_figure"),
    ("initial_search", "initial_periodogram_figure"),
    ("fitted_model", "fitted_rv_figure"),
    ("fitted_model", "statistics_figure"),
    ("fitted_model", "residual_periodogram_figure"),
    ("dynamics", "dynamics_figure"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def base_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "tool": "radial_velocity_workbench",
        "language": "es",
        "title": "RV regression",
        "backend": "generic-rv",
        "system_name": "HD Test",
        "source_files": ["input.vels"],
        "star_metadata": {"name": "HD Test"},
        "rv_datasets": [
            {
                "label": "mock",
                "source": "input.vels",
                "sample_count": 3,
                "value_units": "m/s",
                "jd_span_days": 2.0,
            }
        ],
        "objective": "Validar el manifiesto antes del informe.",
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
            "integration_horizon": "1000 anos",
            "dynamics_figure": "figures/dynamics.png",
            "notes": "ok",
        },
        "conclusions": "El ajuste manual queda documentado.",
        "caveats": "Fixture sintetico.",
        "workflow_notes": [],
        "report_readiness_notes": [],
        "validation": {},
        "planets": [
            {
                "label": "Planeta 1",
                "period_days": 42.0,
                "phased_rv_figure": "figures/phased_planet1.png",
                "notes": "ok",
            }
        ],
    }


def prepare_session(root: Path, name: str, manifest: dict) -> Path:
    session = root / name
    figures = session / "figures"
    figures.mkdir(parents=True)
    (session / "input.vels").write_text("2450000 1.0 0.1\n2450001 2.0 0.1\n", encoding="utf-8")
    for section, key in FIGURE_KEYS:
        raw = manifest.get(section, {}).get(key)
        if raw:
            (session / raw).parent.mkdir(parents=True, exist_ok=True)
            (session / raw).write_bytes(b"placeholder")
    for planet in manifest.get("planets", []):
        raw = planet.get("phased_rv_figure")
        if raw:
            (session / raw).parent.mkdir(parents=True, exist_ok=True)
            (session / raw).write_bytes(b"placeholder")
    manifest_path = session / "session_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest_path


def run_validate(manifest_path: Path, out_dir: Path) -> tuple[int, dict | None, str]:
    summary = out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "validate-manifest",
        str(manifest_path),
        "--summary-json",
        str(summary),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    payload = None
    if summary.exists():
        payload = json.loads(summary.read_text(encoding="utf-8"))
    elif proc.stdout.strip().startswith("{"):
        payload = json.loads(proc.stdout)
    return proc.returncode, payload, (proc.stdout or "") + "\n" + (proc.stderr or "")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rv_validate_manifest_regression_") as tmp:
        root = Path(tmp)

        happy_path = prepare_session(root, "happy", base_manifest())
        rc, payload, text = run_validate(happy_path, root / "happy_out")
        require(rc == 0, f"happy manifest should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "happy manifest should be ok")
        require((payload.get("qa") or {}).get("status") == "ok", "happy QA should be ok")
        print("PASS check_happy_manifest_ok")

        edge = base_manifest()
        edge["initial_search"]["raw_rv_figure"] = ""
        edge["initial_search"]["initial_periodogram_figure"] = None
        edge["fitted_model"]["fitted_rv_figure"] = "figures/missing_fit.png"
        edge["planets"][0]["phased_rv_figure"] = ""
        edge["fitted_model"]["chi2_after"] = None
        edge["fitted_model"]["planet_count"] = 2
        edge_path = prepare_session(root, "edge", edge)
        (edge_path.parent / "figures" / "missing_fit.png").unlink()
        rc, payload, text = run_validate(edge_path, root / "edge_out")
        require(rc == 0, f"edge manifest should exit 0 warning: {text}")
        require(payload is not None and payload.get("status") == "warning", "edge manifest should warn")
        validation = payload.get("results") or {}
        missing_figures = validation.get("completeness", {}).get("missing_figures") or []
        findings = " ".join((payload.get("qa") or {}).get("findings") or [])
        require(len(missing_figures) >= 4, f"empty and missing figures should be counted: {missing_figures}")
        require("fitted_model.chi2_after" in findings, f"missing metric should be in findings: {findings}")
        require("planets.count_mismatch" in findings, f"planet mismatch should be in findings: {findings}")
        print("PASS check_empty_missing_figures_warn")

        nonfinite = base_manifest()
        nonfinite["fitted_model"]["chi2_after"] = math.nan
        nonfinite["fitted_model"]["rms_after"] = math.inf
        nonfinite["planets"][0]["period_days"] = -math.inf
        nonfinite_path = prepare_session(root, "nonfinite", nonfinite)
        rc, payload, text = run_validate(nonfinite_path, root / "nonfinite_out")
        require(rc == 0, f"nonfinite manifest should exit 0 warning: {text}")
        require(payload is not None and payload.get("status") == "warning", "nonfinite manifest should warn")
        validation = payload.get("results") or {}
        require(len(validation.get("nonfinite_numeric_values") or []) == 3, "non-finite values should be listed")
        json.dumps(payload, allow_nan=False)
        print("PASS check_nonfinite_values_warn_strict_json")

        corrupt = root / "corrupt_manifest.json"
        corrupt.write_text('{"system_name": "bad",', encoding="utf-8")
        rc, payload, text = run_validate(corrupt, root / "corrupt_out")
        require(rc != 0, "corrupt manifest should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "corrupt manifest should emit blocked payload")
        require("Traceback" not in text, "corrupt manifest should not traceback")
        print("PASS check_corrupt_json_blocks_cleanly")

        missing = root / "missing_manifest.json"
        rc, payload, text = run_validate(missing, root / "missing_out")
        require(rc != 0, "missing manifest should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "missing manifest should emit blocked payload")
        require("Traceback" not in text, "missing manifest should not traceback")
        print("PASS check_missing_manifest_blocks_cleanly")

    print("All radial_velocity_workbench validate-manifest v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
