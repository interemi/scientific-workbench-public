#!/usr/bin/env python3
"""Validate a bundled scientific profile with synthetic inputs in a new external directory."""

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from check_distribution_snapshot import ROOT, verify
from setup_environment import installation_environment, validate_profile_readiness


def validate_output(path, root=ROOT):
    path = path.expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("output already exists; choose a new directory to preserve evidence")
    if path.resolve().is_relative_to(root.resolve()):
        raise ValueError("output must be outside the source checkout")
    return path


def validate_summary(summary, profile="core"):
    runs = summary.get("feature_runs", {})
    coverage = summary.get("public_surface_coverage", {})
    required_tiers = {"core", "full"} if profile == "full" else {"core"}
    if (summary.get("overall_status") != "PASS" or summary.get("profile") != profile or not runs
            or any(run.get("returncode") != 0 for run in runs.values())
            or coverage.get("missing_coverage") != []
            or not required_tiers.issubset(coverage.get("tiers_enforced", []))):
        raise ValueError(f"{profile} smoke failed, returned no feature runs or has incomplete coverage")
    return len(runs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=("core", "full"), default="core")
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 11):
        raise ValueError("run this script with the prepared Python 3.11 environment")
    output = validate_output(args.output_dir)
    entries = verify()
    output.mkdir(parents=True, exist_ok=False)
    environment = installation_environment()
    environment["DATAANALYSIS_PYTHON"] = sys.executable
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(output / "matplotlib")
    scripts = ROOT / "skills/scientific-data-analysis/scripts"
    commands = [
        [sys.executable, str(scripts / "env_doctor.py"), "--strict-core",
         "--summary-json", str(output / "env-doctor.json")],
        [sys.executable, str(scripts / "portable_smoke_test.py"), "--profile", args.profile,
         "--output-dir", str(output / "artifacts"),
         "--summary-json", str(output / "smoke-summary.json"),
         "--manifest-json", str(output / "smoke-manifest.json")],
    ]
    evidence = {"status": "FAIL", "profile": args.profile, "python": sys.version, "platform": platform.platform(),
                "architecture": platform.machine(), "snapshot_entries_before": entries,
                "commands": commands}
    try:
        for index, command in enumerate(commands):
            with (output / f"step-{index + 1}.log").open("w") as log:
                subprocess.run(command, env=environment, cwd=ROOT, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=600)
            if index == 0:
                validate_profile_readiness(json.loads((output / "env-doctor.json").read_text()), args.profile)
        summary = json.loads((output / "smoke-summary.json").read_text())
        evidence["passed_features"] = validate_summary(summary, args.profile)
        evidence["status"] = "PASS"
    finally:
        # A changed backend is a failure even when all child commands succeeded.
        try:
            evidence["snapshot_entries_after"] = verify()
        except (OSError, ValueError, KeyError) as error:
            evidence.update(status="FAIL", snapshot_error=str(error))
            raise
        finally:
            (output / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Portable {args.profile} PASS: {evidence['passed_features']} features. Evidence: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Portable validation stopped: {error}. New evidence is preserved.", file=sys.stderr)
        raise SystemExit(1)
