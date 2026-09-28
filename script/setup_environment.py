#!/usr/bin/env python3
"""Plan or install dependencies in a new, isolated Scientific Workbench environment."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from check_distribution_snapshot import ROOT, verify
from check_core_lock import verify_core_lock
from check_full_lock import FULL_BUILD_LOCK, FULL_RUNTIME_LOCK, verify_full_lock


def installation_environment(source=None):
    source = os.environ if source is None else source
    environment = {
        key: value for key, value in source.items()
        if not key.startswith(("PIP_", "PYTHON", "CONDA_", "DATAANALYSIS_"))
        and key != "VIRTUAL_ENV"
    }
    # os.devnull disables all pip config files, including global and site config.
    environment.update(PIP_CONFIG_FILE=os.devnull, PIP_REQUIRE_VIRTUALENV="1",
                       PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1")
    return environment


def validate_destination(destination, root=ROOT):
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; choose a new parent directory")
    if destination.name != "datanalysis":
        raise ValueError("the final directory must be named datanalysis for runtime discovery")
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("keep the Python environment outside the source checkout")
    return destination


def locked_requirements(profile, runtime, root=ROOT):
    if profile not in {"core", "full"}:
        raise ValueError("a reviewed lock is available only for core and full profiles")
    minimum_macos = 15 if profile == "full" else 14
    if (runtime.get("system") != "Darwin" or runtime.get("machine") != "arm64"
            or int(runtime.get("macos", "0").split(".")[0] or "0") < minimum_macos):
        raise ValueError(f"the {profile} lock requires native arm64 Python 3.11 on macOS {minimum_macos} or later")
    if profile == "full":
        verify_full_lock(root)
        return root / FULL_RUNTIME_LOCK
    path = root / "distribution/locks/core-macos-arm64-py311.txt"
    if not path.is_file():
        raise ValueError("the reviewed requirements lock is missing")
    verify_core_lock(root)
    return path


def validate_profile_readiness(payload, profile):
    capabilities = payload.get("capabilities", {})
    required = ["core_ready"]
    if profile == "full":
        required.append("full_ready")
    missing = [name for name in required if capabilities.get(name) is not True]
    if missing:
        raise ValueError(f"requested {profile} profile is not ready: {', '.join(missing)}; inspect env-doctor.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="existing Python 3.11 executable")
    parser.add_argument("--destination", required=True, type=Path,
                        help="new external directory ending in datanalysis")
    parser.add_argument("--profile", choices=("core", "full"), default="core")
    parser.add_argument("--locked", action="store_true",
                        help="use reviewed macOS arm64/Python 3.11 distribution hashes (core: macOS 14+, full: 15+)")
    parser.add_argument("--install", action="store_true",
                        help="create the environment and download dependencies; otherwise only preview")
    args = parser.parse_args(argv)
    verify()
    destination = validate_destination(args.destination)
    python = shutil.which(args.python)
    if not python:
        raise ValueError("Python executable was not found")
    environment = installation_environment()
    version = subprocess.check_output(
        [python, "-I", "-c", "import json,sys;print(json.dumps(list(sys.version_info[:3])))"],
        text=True, timeout=15, env=environment)
    if json.loads(version)[:2] != [3, 11]:
        raise ValueError("use Python 3.11; other Python versions have not been validated")
    skill = ROOT / "skills/scientific-data-analysis"
    requirements = skill / f"requirements-{args.profile}.txt"
    pip_options = []
    if args.locked:
        runtime = json.loads(subprocess.check_output(
            [python, "-I", "-c", "import json,platform;print(json.dumps(dict(system=platform.system(),machine=platform.machine(),macos=platform.mac_ver()[0])))"],
            text=True, timeout=15, env=environment))
        requirements = locked_requirements(args.profile, runtime)
        pip_options = ["--require-hashes", "--only-binary=:all:"]
        if args.profile == "full":
            # PIMS is the only reviewed source distribution. Build it with the
            # pinned tools inside this new venv; never download implicit build dependencies.
            pip_options += ["--no-binary=pims", "--no-build-isolation", "--no-cache-dir"]
    environment_python = destination / "bin/python"
    commands = [
        [python, "-I", "-m", "venv", "--copies", str(destination)],
        [str(environment_python), "-I", "-m", "pip", "install", "--no-user",
         *pip_options, "-r", str(requirements)],
    ]
    if args.locked and args.profile == "full":
        commands.insert(1, [str(environment_python), "-I", "-m", "pip", "install", "--no-user",
                            "--require-hashes", "--only-binary=:all:", "--force-reinstall",
                            "-r", str(ROOT / FULL_BUILD_LOCK)])
    print("Scientific Workbench environment setup")
    print("Dependencies are downloaded only with --install. Existing environments are never updated.")
    print("Resolution: reviewed distribution hashes" if args.locked else "Resolution: current package index (versions may change)")
    for command in commands:
        print(shlex.join(command))
    if not args.install:
        print("Preview complete; no environment was created and no packages were installed.")
        return 0
    # Reserve the destination before invoking venv; never let venv reuse an existing environment.
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    evidence = destination / "scientific-workbench-setup"
    evidence.mkdir()
    (evidence / "installation-plan.json").write_text(json.dumps({
        "profile": args.profile, "locked": args.locked,
        "requirements": requirements.relative_to(ROOT).as_posix(),
        "requirements_sha256": hashlib.sha256(requirements.read_bytes()).hexdigest(),
        "build_requirements_sha256": hashlib.sha256((ROOT / FULL_BUILD_LOCK).read_bytes()).hexdigest()
        if args.locked and args.profile == "full" else None,
        "commands": commands,
    }, indent=2) + "\n")
    for command in commands:
        subprocess.run(command, check=True, env=environment)
    subprocess.run([str(environment_python), "-I", "-m", "pip", "check"],
                   env=environment, check=True)
    freeze = subprocess.check_output([str(environment_python), "-I", "-m", "pip", "freeze", "--all"],
                                     text=True, env=environment)
    (evidence / "installed-packages.txt").write_text(freeze)
    environment["DATAANALYSIS_PYTHON"] = str(environment_python)
    subprocess.run([str(environment_python), str(skill / "scripts/env_doctor.py"),
                    "--strict-core", "--summary-json", str(evidence / "env-doctor.json")],
                   env=environment, check=True)
    validate_profile_readiness(json.loads((evidence / "env-doctor.json").read_text()), args.profile)
    subprocess.run([str(environment_python), str(skill / "scripts/datanalysis_env.py"), "status"],
                   env=environment, check=True)
    print(f"Settings > Skill root: {skill}")
    print(f"Settings > Python: {environment_python}")
    print(f"Installation evidence: {evidence}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        print("Any newly created environment is preserved for diagnosis; nothing was deleted.", file=sys.stderr)
        raise SystemExit(1)
