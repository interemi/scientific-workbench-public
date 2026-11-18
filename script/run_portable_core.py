#!/usr/bin/env python3
"""Validate a bundled scientific profile with synthetic inputs in a new external directory."""

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from check_distribution_snapshot import ROOT, verify
from capability_io_contracts import validate_summary_contract
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


def check_core_io_contracts(output, doctor, environment):
    """Exercise the published environment and advisory result shapes."""
    validate_summary_contract(doctor, capability="env_doctor")
    family = ROOT / "skills"
    analysis = family / "scientific-data-analysis/scripts"
    astro = family / "scientific-data-astro/scripts"
    evidence = output / "core-io"
    evidence.mkdir()
    original = evidence / "synthetic-file-hint.pdf"
    marker = b"synthetic file hint only\n"
    original.write_bytes(marker)

    advisory = analysis / "companion_route_check.py"
    external = astro / "external_astro_tools_preflight.py"
    cases = [
        ("discovery", "datanalysis_env.status", analysis / "datanalysis_env.py",
         ["status"], {0: {"PASS", "WARNING"}}),
        ("healthcheck", "datanalysis_healthcheck", analysis / "datanalysis_healthcheck.py",
         ["--skip-notebook-exec"], {0: {"PASS", "WARNING"}, 1: {"BLOCKED_CONTROLADO"}}),
        ("doctor-invalid-output", "env_doctor", analysis / "env_doctor.py",
         ["--manifest-json", str(evidence)], {2: {"BLOCKED_CONTROLADO"}}),
        ("advisory", "companion_route_check", advisory,
         ["--task", "Inspect a scientific report", "--file", str(original)], {0: {"PASS"}}),
        ("advisory-overlap", "companion_route_check", advisory,
         ["--file", str(original)], {2: {"BLOCKED_CONTROLADO"}}),
        ("external-discovery", "external_astro_tools_preflight", external,
         [], {0: {"PASS", "WARNING"}, 2: {"BLOCKED_CONTROLADO"}}),
        ("external-missing-required", "external_astro_tools_preflight", external,
         ["--require-apt", "--apt-command", str(evidence / "missing-apt"),
          "--apt-preferences", str(evidence / "missing.pref")], {2: {"BLOCKED_CONTROLADO"}}),
    ]
    records = {"doctor": {"returncode": 0, "app_status": doctor["app_status"]}}
    for name, capability, script, args, expected in cases:
        overlap = name == "advisory-overlap"
        summary = original if overlap else evidence / f"{name}.json"
        command = [sys.executable, str(script), *args, "--summary-json", str(summary)]
        process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120)
        (evidence / f"{name}.stdout.log").write_text(process.stdout, encoding="utf-8")
        (evidence / f"{name}.stderr.log").write_text(process.stderr, encoding="utf-8")
        if overlap and original.read_bytes() != marker:
            raise ValueError("companion routing modified the synthetic file hint")
        payload = json.loads(process.stdout if overlap else summary.read_text(encoding="utf-8"))
        validate_summary_contract(payload, capability=capability)
        status = payload["app_status"]
        if status not in expected.get(process.returncode, set()):
            raise ValueError(f"{capability} {name}: unexpected exit {process.returncode} with {status}")
        records[name] = {"returncode": process.returncode, "app_status": status}
    return records


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
        [sys.executable, str(ROOT / "script/check_scientific_known_answers.py"),
         "--output-dir", str(output / "known-answer")],
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
                doctor = json.loads((output / "env-doctor.json").read_text())
                validate_profile_readiness(doctor, args.profile)
                evidence["core_io_contracts"] = check_core_io_contracts(output, doctor, environment)
        summary = json.loads((output / "smoke-summary.json").read_text())
        evidence["passed_features"] = validate_summary(summary, args.profile)
        known_answer = json.loads((output / "known-answer/verification.json").read_text())
        if known_answer.get("status") != "PASS":
            raise ValueError("scientific known-answer checks did not pass")
        evidence["known_answer_status"] = known_answer["status"]
        evidence["known_answer_fits_sha256"] = known_answer["fits"]["input_sha256"]
        evidence["known_answer_crossmatch_sep_arcsec"] = known_answer["crossmatch"]["actual_sep_arcsec"]
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
