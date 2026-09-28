#!/usr/bin/env python3
"""Short local Astrometry smoke test for real coursework-style FITS inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _internal.provenance_utils import standard_tool_payload

try:
    from astropy.io import fits
except Exception:  # pragma: no cover - runtime dependency check only
    fits = None


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Directory for smoke-test outputs.")
    parser.add_argument("--backend-config", help="Optional solve-field backend config.")
    parser.add_argument("--index-dir", action="append", default=[], help="Optional Astrometry index directory. Repeat as needed.")
    parser.add_argument("--direct-fits", help="A normal direct-imaging FITS that should solve locally.")
    parser.add_argument("--compact-fits", help="A compact imaging FITS that may need stack-first local recovery.")
    parser.add_argument("--existing-wcs-fits", help="A FITS that already carries a celestial WCS and should be verified, not re-solved.")
    parser.add_argument("--spectroscopy-fits", help="A spectroscopy-like FITS that should be classified as unsuitable for blind solving.")
    parser.add_argument("--scale-est", type=float, help="Optional plate-scale estimate in arcsec/pixel.")
    parser.add_argument("--scale-err", type=float, default=12.0, help="Percentage error on --scale-est.")
    parser.add_argument("--summary-json", help="Optional machine-readable summary path.")
    return parser.parse_args()


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_fits_candidate(path: str | None, require_image: bool) -> tuple[bool, str | None]:
    if not path:
        return False, "missing_path"
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return False, f"input_not_found:{candidate}"
    if fits is None:
        return False, "astropy_not_available"
    try:
        with fits.open(candidate, memmap=False) as hdus:
            found_image = False
            for hdu in hdus:
                data = getattr(hdu, "data", None)
                if data is None:
                    continue
                ndim = getattr(data, "ndim", None)
                if ndim is not None and ndim >= 2:
                    found_image = True
                    break
    except Exception as exc:
        return False, f"invalid_fits:{exc.__class__.__name__}"
    if require_image and not found_image:
        return False, "no_2d_image_hdu"
    return True, None


def main():
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.is_symlink() or (output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir()))):
        finding = (
            "The astrometry smoke output directory must be absent or empty; refusing to "
            "replace pre-existing case artifacts."
        )
        payload = standard_tool_payload(
            "astrometry_local_smoke_test",
            status="blocked",
            artifacts={},
            results={"blocked_output_dir": str(output_dir)},
            qa={"status": "blocked", "findings": [finding]},
            notes=[finding],
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve().with_name("astrometry_net_workbench.py")
    python_bin = sys.executable

    common_flags = []
    if args.backend_config:
        common_flags.extend(["--backend-config", args.backend_config])
    for item in args.index_dir or []:
        common_flags.extend(["--index-dir", item])
    if args.scale_est is not None:
        common_flags.extend(["--scale-est", str(args.scale_est), "--scale-err", str(args.scale_err)])

    cases = []

    def append_case(case_id: str, label: str, cmd: list[str], summary_path: Path, require_image: bool):
        case_dir = summary_path.parent
        case_dir.mkdir(parents=True, exist_ok=False)
        input_ok, input_issue = inspect_fits_candidate(cmd[3] if len(cmd) > 3 else None, require_image=require_image)
        if not input_ok:
            cases.append(
                {
                    "case_id": case_id,
                    "label": label,
                    "status": "invalid_fixture",
                    "fixture_issue": input_issue,
                    "command": cmd,
                    "returncode": None,
                    "summary_path": str(summary_path),
                    "result_status": None,
                    "fit_assessment": {},
                }
            )
            return
        completed = run_cmd(cmd)
        summary = load_json(summary_path) if summary_path.exists() else {}
        fit_assessment = summary.get("fit_assessment")
        if not isinstance(fit_assessment, dict):
            fit_assessment = summary.get("preflight", {}).get("fit_assessment")
        if not isinstance(fit_assessment, dict):
            fit_assessment = {}
        case_status = "tool_failure"
        result_status = summary.get("result_status")
        if case_id == "direct" and result_status == "solved":
            case_status = "pass"
        elif case_id == "compact" and result_status in {"solved", "skipped_existing_wcs"}:
            case_status = "pass"
        elif case_id == "existing_wcs" and result_status in {"verified_existing_wcs", "wcs_header_only"}:
            case_status = "pass" if result_status == "verified_existing_wcs" else "expected_skip"
        elif case_id == "spectroscopy" and fit_assessment.get("recommended_action") == "avoid_plate_solve":
            case_status = "expected_skip"
        cases.append(
            {
                "case_id": case_id,
                "label": label,
                "status": case_status,
                "command": cmd,
                "returncode": completed.returncode,
                "summary_path": str(summary_path),
                "result_status": result_status,
                "fit_assessment": fit_assessment,
            }
        )

    if args.direct_fits:
        summary_path = output_dir / "direct" / "summary.json"
        cmd = [
            python_bin,
            str(script_path),
            "solve-local-best-effort",
            args.direct_fits,
            "--output-dir",
            str(output_dir / "direct"),
            "--summary-json",
            str(summary_path),
            *common_flags,
        ]
        append_case("direct", "direct imaging", cmd, summary_path, require_image=True)

    if args.compact_fits:
        summary_path = output_dir / "compact" / "summary.json"
        cmd = [
            python_bin,
            str(script_path),
            "solve-local-best-effort",
            args.compact_fits,
            "--output-dir",
            str(output_dir / "compact"),
            "--summary-json",
            str(summary_path),
            "--peer-count",
            "13",
            *common_flags,
        ]
        append_case("compact", "compact imaging", cmd, summary_path, require_image=True)

    if args.existing_wcs_fits:
        summary_path = output_dir / "existing_wcs" / "summary.json"
        cmd = [
            python_bin,
            str(script_path),
            "verify-existing-wcs",
            args.existing_wcs_fits,
            "--output-dir",
            str(output_dir / "existing_wcs"),
            "--summary-json",
            str(summary_path),
        ]
        append_case("existing_wcs", "existing WCS", cmd, summary_path, require_image=False)

    if args.spectroscopy_fits:
        summary_path = output_dir / "spectroscopy" / "summary.json"
        cmd = [
            python_bin,
            str(script_path),
            "preflight",
            args.spectroscopy_fits,
            "--summary-json",
            str(summary_path),
        ]
        append_case("spectroscopy", "spectroscopy control", cmd, summary_path, require_image=True)

    status = "PASS"
    notes = [
        "This smoke now distinguishes bad fixtures from real astrometry tool failures.",
        "Existing-WCS verification is reported separately from fresh local blind solves.",
    ]
    for item in cases:
        if item.get("status") in {"invalid_fixture", "tool_failure"}:
            status = "FAIL"
    qa = {
        "status": "ok" if status == "PASS" else "fail",
        "findings": [
            item["case_id"] + ": " + item["status"]
            for item in cases
            if item.get("status") not in {"pass", "expected_skip"}
        ],
        "metrics": {
            "case_count": len(cases),
            "pass_count": sum(1 for item in cases if item.get("status") == "pass"),
            "expected_skip_count": sum(1 for item in cases if item.get("status") == "expected_skip"),
            "invalid_fixture_count": sum(1 for item in cases if item.get("status") == "invalid_fixture"),
            "tool_failure_count": sum(1 for item in cases if item.get("status") == "tool_failure"),
        },
    }
    legacy_payload = {
        "tool": "astrometry_local_smoke_test",
        "status": status,
        "case_count": len(cases),
        "cases": cases,
    }
    payload = standard_tool_payload(
        "astrometry_local_smoke_test",
        status="ok" if status == "PASS" else "fail",
        notes=notes,
        artifacts={"summary_json": args.summary_json},
        results=legacy_payload,
        qa=qa,
        legacy=legacy_payload,
    )
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
