#!/usr/bin/env python3
"""Regression checks for Li 6708 EW measurement v1.6 edge behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().with_name("li6708_equivalent_width_workbench.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_ascii_spectrum(path: Path, *, emission: bool = False, zero_flux: bool = False) -> None:
    wavelength = np.linspace(6704.5, 6710.0, 300)
    sign = 1.0 if emission else -1.0
    flux = 1.0 + sign * 0.12 * np.exp(-0.5 * ((wavelength - 6707.8) / 0.12) ** 2)
    if zero_flux:
        flux[:] = 0.0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# wavelength flux\n" + "\n".join(f"{w:.6f} {f:.8f}" for w, f in zip(wavelength, flux)) + "\n",
        encoding="utf-8",
    )


def run_measure(input_path: Path, out_dir: Path, *, extra: list[str] | None = None, summary: Path | None = None) -> tuple[int, dict | None, str]:
    summary = summary or out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "measure",
        str(input_path),
        "--output-dir",
        str(out_dir / "products"),
        "--summary-json",
        str(summary),
        "--continuum-window",
        "6704.8",
        "6705.8",
        "--continuum-window",
        "6708.6",
        "6709.6",
        "--integration-window",
        "6707.2",
        "6708.2",
        "--skip-systematic-grid",
    ]
    if extra:
        cmd.extend(extra)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(out_dir / "mplconfig")
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    payload = None
    if summary.exists():
        payload = json.loads(summary.read_text(encoding="utf-8"))
    elif proc.stdout.strip().startswith("{"):
        payload = json.loads(proc.stdout)
    return proc.returncode, payload, (proc.stdout or "") + "\n" + (proc.stderr or "")


def assert_strict_json(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="li6708_equivalent_width_v16_") as raw_tmp:
        root = Path(raw_tmp)

        happy = root / "li_absorption.dat"
        write_ascii_spectrum(happy)
        nested_summary = root / "nested" / "summary" / "li.json"
        rc, payload, text = run_measure(happy, root / "happy_out", summary=nested_summary)
        require(rc == 0, f"happy ASCII should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "happy ASCII should emit ok payload")
        require(payload.get("results", {}).get("input_format") == "ascii", "happy ASCII should report input_format ascii")
        require(payload.get("results", {}).get("ew_milliangstrom", 0) > 0, "happy ASCII EW should be positive")
        require(nested_summary.exists(), "summary-json parent directories should be created")
        assert_strict_json(payload)
        print("PASS check_happy_ascii_absorption")

        emission = root / "li_emission.dat"
        write_ascii_spectrum(emission, emission=True)
        rc, payload, text = run_measure(emission, root / "emission_out")
        require(rc == 0, f"emission line should exit 0 with warning payload: {text}")
        require(payload is not None and payload.get("status") == "warning", "emission line should warn")
        require("linea_no_absorbida" in payload.get("qa", {}).get("findings", []), "emission warning should be explicit")
        assert_strict_json(payload)
        print("PASS check_emission_warns_without_faking_absorption")

        too_short = root / "too_short.dat"
        too_short.write_text("6707.7 1.0\n6707.8 0.9\n", encoding="utf-8")
        rc, payload, text = run_measure(too_short, root / "short_out")
        require(rc != 0, "too-short ASCII should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "too-short ASCII should emit blocked payload")
        require("Traceback" not in text, "too-short ASCII should not traceback")
        assert_strict_json(payload)
        print("PASS check_too_short_ascii_blocks_cleanly")

        nonfinite = root / "nonfinite.dat"
        nonfinite.write_text("6707.0 1.0\n6707.1 nan\n6707.2 0.9\n", encoding="utf-8")
        rc, payload, text = run_measure(nonfinite, root / "nonfinite_out")
        require(rc != 0, "non-finite ASCII should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "non-finite ASCII should emit blocked payload")
        require("Traceback" not in text, "non-finite ASCII should not traceback")
        assert_strict_json(payload)
        print("PASS check_nonfinite_ascii_blocks_cleanly")

        zero_flux = root / "zero_flux.dat"
        write_ascii_spectrum(zero_flux, zero_flux=True)
        rc, payload, text = run_measure(zero_flux, root / "zero_flux_out")
        require(rc != 0, "zero-continuum ASCII should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "zero-continuum ASCII should emit blocked payload")
        require("Traceback" not in text, "zero-continuum ASCII should not traceback")
        assert_strict_json(payload)
        print("PASS check_nonpositive_continuum_blocks_cleanly")

        corrupt_fits = root / "not_a_spectrum.fits"
        corrupt_fits.write_bytes(b"not a fits file")
        rc, payload, text = run_measure(corrupt_fits, root / "corrupt_fits_out")
        require(rc != 0, "corrupt FITS should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "corrupt FITS should emit blocked payload")
        require("Traceback" not in text, "corrupt FITS should not traceback")
        assert_strict_json(payload)
        print("PASS check_corrupt_fits_blocks_cleanly")

    print("All Li 6708 EW v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
