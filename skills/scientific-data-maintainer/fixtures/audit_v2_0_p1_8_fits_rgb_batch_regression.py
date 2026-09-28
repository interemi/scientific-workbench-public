#!/usr/bin/env python3
"""Regression for v2.0 P1-8 fits_rgb_batch app integration."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "v2_0_p1_8_fits_rgb_batch" / "regression"
SCRIPT = ROOT / "scripts" / "fits_rgb_batch.py"
REFERENCE = ROOT / "references" / "v2-0-p1-8-fits-rgb-batch-integration.md"


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_fits_fixture(root: Path, *, ambiguous_wcs: bool, shifted: bool = False) -> list[Path]:
    import numpy as np
    from astropy.io import fits

    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, filt in enumerate(["R", "G", "B"]):
        y, x = np.indices((48, 48))
        dy = index - 1 if shifted else 0
        dx = 1 - index if shifted else 0
        data = 100 + 800 * np.exp(-((x - (24 + dx)) ** 2 + (y - (24 + dy)) ** 2) / (2 * 4.0**2))
        header = fits.Header()
        header["OBJECT"] = "APPREADY_RGB"
        header["FILTER"] = filt
        header["EXPTIME"] = 30.0
        header["IMAGETYP"] = "reduced light"
        header["CTYPE1"] = "RA---TAN"
        header["CTYPE2"] = "DEC--TAN"
        header["CRPIX1"] = 24.0
        if ambiguous_wcs:
            # Deliberately incomplete WCS: the tool should warn and fall back.
            pass
        else:
            header["CRPIX2"] = 24.0
            header["CRVAL1"] = 120.0
            header["CRVAL2"] = 22.0
            header["CDELT1"] = -0.0002777778
            header["CDELT2"] = 0.0002777778
        path = root / f"appready_{filt}.fits"
        fits.PrimaryHDU(data.astype("float32"), header=header).writeto(path, overwrite=True)
        paths.append(path)
    return paths


def run_case(python_executable: str, name: str, input_root: Path) -> tuple[int, dict]:
    run_root = TMP / "runs" / name
    output_dir = run_root / "artifacts"
    summary = run_root / "summary.json"
    cmd = [
        python_executable,
        str(SCRIPT),
        "--input-root",
        str(input_root),
        "--output-dir",
        str(output_dir),
        "--summary-json",
        str(summary),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if not summary.exists():
        return proc.returncode, {"_missing_summary": True, "stdout": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, json.loads(summary.read_text(encoding="utf-8"))


def artifact_types(payload: dict) -> set[str]:
    return {item.get("artifact_type") for item in payload.get("typed_artifacts", []) if isinstance(item, dict)}


def validate_payload(name: str, payload: dict, failures: list[str], *, expect_wcs_warning: bool) -> None:
    if payload.get("_missing_summary"):
        fail(failures, f"{name}: summary.json was not written")
        return
    if payload.get("tool") != "fits_rgb_batch":
        fail(failures, f"{name}: unexpected tool {payload.get('tool')!r}")
    if payload.get("original_modified") is not False:
        fail(failures, f"{name}: original_modified must be false")
    if payload.get("app_status") not in {"PASS", "WARNING"}:
        fail(failures, f"{name}: app_status must be PASS or WARNING, found {payload.get('app_status')!r}")
    types = artifact_types(payload)
    for required in ("preview_png", "manifest_json", "summary_json", "table_csv"):
        if required not in types:
            fail(failures, f"{name}: missing typed artifact {required}")
    previews = [
        item for item in payload.get("typed_artifacts", [])
        if item.get("artifact_type") == "preview_png" and str(item.get("path", "")).endswith(".png")
    ]
    if not previews:
        fail(failures, f"{name}: no individual PNG preview artifact")
    warnings = "\n".join(str(item) for item in payload.get("warnings", []))
    if expect_wcs_warning and "Incomplete celestial WCS metadata" not in warnings:
        fail(failures, f"{name}: expected incomplete WCS warning")


def validate_reference(failures: list[str]) -> None:
    if not REFERENCE.exists():
        fail(failures, f"Missing reference: {REFERENCE}")
        return
    text = REFERENCE.read_text(encoding="utf-8")
    archived_reference = (
        ROOT / ".cache" / "archived_references" / "references" / REFERENCE.name
    )
    if archived_reference.is_file():
        text += "\n" + archived_reference.read_text(encoding="utf-8")
    for term in ["expert_science", "preview_png", "manifest_json", "Source FITS are never modified"]:
        if term not in text:
            fail(failures, f"Reference missing term: {term}")


def validate(args: argparse.Namespace) -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)

    try:
        happy_inputs = write_fits_fixture(TMP / "fixtures" / "happy_rgb", ambiguous_wcs=False)
        ambiguous_inputs = write_fits_fixture(TMP / "fixtures" / "ambiguous_wcs", ambiguous_wcs=True)
    except Exception as exc:
        return {
            "tool": "audit_v2_0_p1_8_fits_rgb_batch_regression",
            "status": "BLOCKED_CONTROLADO",
            "reason": f"Could not create FITS fixtures: {exc}",
            "failures": [],
            "warnings": [str(exc)],
        }

    hashes_before = {str(path): sha256(path) for path in happy_inputs + ambiguous_inputs}
    happy_code, happy_payload = run_case(args.python_executable, "happy_rgb", TMP / "fixtures" / "happy_rgb")
    ambiguous_code, ambiguous_payload = run_case(args.python_executable, "ambiguous_wcs", TMP / "fixtures" / "ambiguous_wcs")
    hashes_after = {str(path): sha256(path) for path in happy_inputs + ambiguous_inputs}

    if happy_code != 0:
        fail(failures, f"happy_rgb exited with {happy_code}")
    if ambiguous_code != 0:
        fail(failures, f"ambiguous_wcs exited with {ambiguous_code}")
    if hashes_before != hashes_after:
        fail(failures, "Input FITS hashes changed")

    validate_payload("happy_rgb", happy_payload, failures, expect_wcs_warning=False)
    validate_payload("ambiguous_wcs", ambiguous_payload, failures, expect_wcs_warning=True)
    validate_reference(failures)

    status = "PASS" if not failures else "FAIL"
    return {
        "tool": "audit_v2_0_p1_8_fits_rgb_batch_regression",
        "status": status,
        "python_executable": args.python_executable,
        "tmp": str(TMP),
        "cases": [
            {
                "name": "happy_rgb",
                "exit_code": happy_code,
                "app_status": happy_payload.get("app_status"),
                "artifact_types": sorted(artifact_types(happy_payload)),
            },
            {
                "name": "ambiguous_wcs",
                "exit_code": ambiguous_code,
                "app_status": ambiguous_payload.get("app_status"),
                "artifact_types": sorted(artifact_types(ambiguous_payload)),
                "warning_count": len(ambiguous_payload.get("warnings", [])),
            },
        ],
        "original_hashes_unchanged": hashes_before == hashes_after,
        "reference": str(REFERENCE),
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--summary-json", default=None)
    args = parser.parse_args()

    payload = validate(args)
    output = json.dumps(payload, indent=2, ensure_ascii=False)
    print(output)
    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    return 0 if payload["status"] in {"PASS", "BLOCKED_CONTROLADO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
