#!/usr/bin/env python3
"""Regression checks for sb2_double_gaussian_workbench fit guardrails."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sb2_double_gaussian_workbench.py"


def write_ccf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "aperture", "velocity_kms", "ccf_value"])
        for index in range(241):
            velocity = -120.0 + index
            value = 0.15 + 0.9 * math.exp(-0.5 * ((velocity + 42.0) / 9.0) ** 2) + 0.75 * math.exp(
                -0.5 * ((velocity - 38.0) / 11.0) ** 2
            )
            writer.writerow(["sb2_regression", 1, f"{velocity:.3f}", f"{value:.8f}"])


def run_fit(inputs: list[Path], output_dir: Path, summary_json: Path, manifest_json: Path | None = None) -> dict:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "fit",
        *[str(path) for path in inputs],
        "--output-dir",
        str(output_dir),
        "--summary-json",
        str(summary_json),
    ]
    if manifest_json:
        cmd.extend(["--manifest-json", str(manifest_json)])
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=80,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    payload = None
    texts = []
    if summary_json.exists() and summary_json.is_file():
        texts.append(summary_json.read_text(encoding="utf-8"))
    texts.append(completed.stdout)
    for text in texts:
        stripped = text.strip()
        marker = stripped.find('{\n  "tool"')
        candidate = stripped[marker:] if marker >= 0 else stripped
        if candidate.startswith("{"):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
    return {"rc": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "payload": payload}


def assert_blocked_clean(result: dict, output_dir: Path) -> None:
    assert result["rc"] == 2, result
    assert isinstance(result["payload"], dict), result
    assert result["payload"]["status"] == "blocked", result["payload"]
    assert "Traceback (most recent call last)" not in result["stderr"], result["stderr"]
    for name in ["sb2_double_gaussian_orders.csv", "summary.md"]:
        assert not (output_dir / name).exists(), f"Producto parcial inesperado: {output_dir / name}"
    assert not (output_dir / "figures").exists(), f"Directorio parcial inesperado: {output_dir / 'figures'}"


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="sb2-double-gaussian-regression-"))
    try:
        fixtures = base / "fixtures"
        outputs = base / "outputs"
        summaries = base / "summaries"
        ccf = fixtures / "good.csv"
        write_ccf(ccf)

        happy = run_fit([ccf], outputs / "happy", summaries / "happy.json", summaries / "happy_manifest.json")
        assert happy["rc"] == 0, happy
        assert happy["payload"]["status"] == "ok", happy["payload"]
        assert (outputs / "happy" / "sb2_double_gaussian_orders.csv").exists()

        missing_columns = fixtures / "missing_columns.csv"
        missing_columns.write_text("velocity_kms,value\n-1,0.1\n1,0.2\n", encoding="utf-8")
        assert_blocked_clean(run_fit([missing_columns], outputs / "missing_columns", summaries / "missing_columns.json"), outputs / "missing_columns")

        assert_blocked_clean(run_fit([fixtures / "missing.csv"], outputs / "missing_input", summaries / "missing_input.json"), outputs / "missing_input")

        bad_summary_parent = outputs / "summary_parent_is_file"
        bad_summary_parent.parent.mkdir(parents=True, exist_ok=True)
        bad_summary_parent.write_text("not a directory\n", encoding="utf-8")
        assert_blocked_clean(
            run_fit([ccf], outputs / "bad_summary", bad_summary_parent / "summary.json", summaries / "bad_summary_manifest.json"),
            outputs / "bad_summary",
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
