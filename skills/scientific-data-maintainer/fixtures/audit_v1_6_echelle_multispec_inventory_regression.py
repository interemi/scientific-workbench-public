#!/usr/bin/env python3
"""Regression checks for echelle_multispec_inventory.py v1.6 edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits


SCRIPT = Path(__file__).resolve().with_name("echelle_multispec_inventory.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_multispec(path: Path, object_name: str, starts: list[float], *, suffix_case: bool = False, malformed: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = 24
    data = np.ones((len(starts), pixels), dtype=np.float32)
    hdu = fits.PrimaryHDU(data)
    header = hdu.header
    header["OBJECT"] = object_name
    header["CTYPE1"] = "MULTISPE"
    header["WAT0_001"] = "system=equispec"
    header["WAT1_001"] = "wtype=multispec label=Wavelength units=angstroms"
    parts = ["wtype=multispec"]
    if malformed:
        parts.extend([f'spec{index}="broken payload"' for index in range(1, len(starts) + 1)])
    else:
        for index, start in enumerate(starts, start=1):
            delta = 0.2 + 0.01 * index
            last = start + delta * (pixels - 1)
            parts.append(f'spec{index}="{index} {index} 2 {start:.3f} {delta:.4f} {pixels} 0 0 {start:.3f} {last:.3f}"')
    blob = " ".join(parts)
    for chunk_index, chunk_start in enumerate(range(0, len(blob), 68), start=1):
        header[f"WAT2_{chunk_index:03d}"] = blob[chunk_start : chunk_start + 68]
    target = path.with_suffix(".FITS") if suffix_case else path
    hdu.writeto(target, overwrite=True)
    return target


def run_inventory(input_path: Path, out_dir: Path) -> tuple[int, dict | None, str]:
    summary = out_dir / "summary.json"
    cmd = [
        sys.executable,
        str(SCRIPT),
        str(input_path),
        "--output-dir",
        str(out_dir / "inventory"),
        "--report-md",
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
    with tempfile.TemporaryDirectory(prefix="echelle_multispec_inventory_v16_") as raw_tmp:
        root = Path(raw_tmp)

        happy = make_multispec(root / "happy.fits", "SYN_HAPPY", [6500.0, 6560.0])
        rc, payload, text = run_inventory(happy, root / "happy_out")
        require(rc == 0, f"happy inventory should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "happy inventory should be ok")
        require(payload.get("results", {}).get("order_count") == 2, "happy inventory should count two orders")
        require(payload.get("qa", {}).get("status") == "ok", "happy QA should be ok")
        print("PASS check_happy_multispec_ok")

        mixed_dir = root / "Mixed Directory With Spaces"
        make_multispec(mixed_dir / "upper_case.fit", "SYN_UPPER", [5000.0], suffix_case=True)
        make_multispec(mixed_dir / "normal.fits", "SYN_NORMAL", [5100.0, 5200.0])
        rc, payload, text = run_inventory(mixed_dir, root / "mixed_out")
        require(rc == 0, f"mixed directory should exit 0: {text}")
        require(payload is not None and payload.get("status") == "ok", "mixed directory should be ok")
        require(payload.get("results", {}).get("file_count") == 2, "directory discovery should include uppercase FITS suffixes")
        require(payload.get("results", {}).get("order_count") == 3, "mixed directory should count all orders")
        print("PASS check_directory_case_insensitive_suffixes")

        edge = make_multispec(root / "bad_wat.fits", "SYN_EDGE", [6500.0, 6560.0], malformed=True)
        rc, payload, text = run_inventory(edge, root / "edge_out")
        require(rc == 0, f"bad WAT should exit 0 warning: {text}")
        require(payload is not None and payload.get("status") == "warning", "bad WAT should warn")
        require(payload.get("results", {}).get("order_count") == 0, "bad WAT should not fake orders")
        print("PASS check_malformed_wat_warns")

        corrupt = root / "not_a_fits.fits"
        corrupt.write_text("not a fits file\n", encoding="utf-8")
        rc, payload, text = run_inventory(corrupt, root / "corrupt_out")
        require(rc != 0, "corrupt FITS should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "corrupt FITS should emit blocked payload")
        require("Traceback" not in text, "corrupt FITS should not traceback")
        print("PASS check_corrupt_fits_blocks_cleanly")

        missing = root / "missing.fits"
        rc, payload, text = run_inventory(missing, root / "missing_out")
        require(rc != 0, "missing input should return non-zero")
        require(payload is not None and payload.get("status") == "blocked", "missing input should emit blocked payload")
        require("Traceback" not in text, "missing input should not traceback")
        print("PASS check_missing_input_blocks_cleanly")

        partial = root / "partial"
        make_multispec(partial / "good.fits", "SYN_PARTIAL", [6400.0])
        bad = partial / "bad.fits"
        bad.write_bytes(b"broken")
        rc, payload, text = run_inventory(partial, root / "partial_out")
        require(rc == 0, f"partial directory should keep valid FITS and warn: {text}")
        require(payload is not None and payload.get("status") == "warning", "partial directory should warn")
        metrics = payload.get("qa", {}).get("metrics", {})
        require(metrics.get("readable_file_count") == 1, "partial directory should report one readable file")
        require(metrics.get("failed_file_count") == 1, "partial directory should report one failed file")
        require(payload.get("results", {}).get("order_count") == 1, "partial directory should keep valid order rows")
        print("PASS check_partial_directory_warns_without_losing_good_file")

        json.dumps(payload, allow_nan=False)

    print("All echelle_multispec_inventory v1.6 regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
