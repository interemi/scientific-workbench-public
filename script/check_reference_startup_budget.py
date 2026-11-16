#!/usr/bin/env python3
"""Measure Swift entry to the visible key window in fresh synthetic sessions."""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import plistlib
import shlex
import shutil
import signal
import statistics
import subprocess
import tempfile
import uuid


REPO = Path(__file__).resolve().parent.parent
WARMUPS = 2
SAMPLES = 24
MEDIAN_LIMIT_MS = 500
P95_LIMIT_MS = 550


def command(*args):
    return subprocess.check_output(args, cwd=REPO, text=True).strip()


def fixture(output):
    jobs = []
    start = datetime(2023, 11, 14, tzinfo=timezone.utc)
    for number in reversed(range(250)):
        run = output / f"synthetic-{number:03d}"
        run.mkdir(parents=True)
        for name, contents in {
            "command.txt": "synthetic profile_table\n",
            "next_steps.md": "# Next steps\n\n- Review the synthetic table.\n",
            "result.csv": "source_id,flux\n1,4.2\n",
            "stdout.txt": "Synthetic profiling result\n" * 80,
            "summary.json": '{"tool":"profile_table","status":"ok","app_status":"PASS","original_modified":"false"}\n',
        }.items():
            (run / name).write_text(contents, encoding="utf-8")
        jobs.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"scientific-workbench-startup-{number}")),
            "capabilityID": "profile_table", "capabilityLabel": "profile_table.py",
            "status": "succeeded", "runDirectory": str(run), "createdAt":
                (start + timedelta(seconds=number)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exitCode": 0, "command": "", "stdout": "", "stderr": "", "artifacts": [],
            "requestInputPaths": [], "requestRawArguments": "", "nextActions": [],
            "previewArtifactTypes": [], "structuredErrors": [], "tags": [], "warnings": [],
        })
    index = output / ".scientificworkbench/jobs.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"version": 2, "jobs": jobs}), encoding="utf-8")
    return jobs[0]["id"]


def inventory(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def record(path, payload):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def build(evidence, sdk):
    source = evidence / "source"
    source.mkdir()
    archive = subprocess.check_output(["git", "archive", "HEAD", "Package.swift", "Sources", "Tests"], cwd=REPO)
    subprocess.run(["/usr/bin/tar", "-xf", "-", "-C", str(source)], input=archive, check=True)
    options = ["--package-path", str(source), "-Xswiftc", "-DSWB_STARTUP_BUDGET"]
    if backend := os.environ.get("SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM"):
        options.extend(["--build-system", backend])
    environment = {**os.environ, "SDKROOT": str(sdk)}
    with (evidence / "build.log").open("x", encoding="utf-8") as log:
        subprocess.run(["swift", "build", *options], env=environment, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    binary_dir = subprocess.check_output(["swift", "build", *options, "--show-bin-path"],
                                         env=environment, text=True).strip()
    return Path(binary_dir) / "ScientificWorkbench"


def make_bundle(evidence, source, output, python):
    identifier = uuid.uuid4().hex
    bundle = evidence / "Scientific Workbench Startup Check.app"
    binary = bundle / "Contents/MacOS/Scientific Workbench"
    binary.parent.mkdir(parents=True)
    shutil.copy2(source, binary)
    args = [str(binary), "--agent-persistent-isolated-session", f"SWB_STARTUP_{identifier}",
            "--agent-output-root", str(output), "--agent-skill-root",
            str(REPO / "skills/scientific-data-analysis"), "--agent-python-executable", str(python)]
    launcher = binary.with_name("launch-isolated")
    launcher.write_text(
        "#!/bin/bash\nset -eu\numask 077\n"
        "unset OPENAI_API_KEY XAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY\n"
        "export SWB_STARTUP_BUDGET=1\n"
        "trace=$(cat " + shlex.quote(str(evidence / "next-log")) + ")\n"
        "exec " + shlex.join(args) + ' > "$trace" 2>&1\n',
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleExecutable": launcher.name,
        "CFBundleIdentifier": f"com.interemi.scientific-workbench.startup.{identifier}",
        "CFBundleName": "Scientific Workbench",
        "CFBundleDisplayName": "Scientific Workbench Startup Check",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "14.0",
        "NSPrincipalClass": "NSApplication",
    }))
    return bundle, binary


def events(trace):
    result = {}
    if trace.is_file():
        for line in trace.read_text(encoding="utf-8").splitlines():
            if line.startswith("SWB_STARTUP\t"):
                _, elapsed, name, value = line.split("\t", maxsplit=3)
                if name in result:
                    raise SystemExit(f"Duplicate event {name} in {trace}")
                result[name] = (int(elapsed), value)
    return result


def trial(evidence, bundle, binary, selection, index):
    trace = evidence / f"trial-{index + 1:02d}.log"
    (evidence / "next-log").write_text(str(trace) + "\n", encoding="utf-8")
    try:
        subprocess.run(["/usr/bin/open", "-n", "-W", str(bundle)], timeout=30, check=True)
    except subprocess.TimeoutExpired:
        entry = events(trace).get("swift_entry")
        if entry and entry[1].isdigit():
            pid = int(entry[1])
            actual = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "command="],
                                    capture_output=True, text=True)
            if actual.stdout.strip().startswith(str(binary) + " --agent-persistent-isolated-session SWB_STARTUP_"):
                os.kill(pid, signal.SIGTERM)
        raise SystemExit(f"Isolated app timed out. See {trace}")
    observed = events(trace)
    expected = {"swift_entry", "key_window", "environment", "history", "finished"}
    if set(observed) != expected:
        raise SystemExit(f"Incomplete startup trace. See {trace}")
    if (observed["key_window"][1] != "Chat" or observed["history"][1].lower() != f"250|{selection}"
            or observed["environment"][1] != "ok"
            or not observed["swift_entry"][0] <= observed["key_window"][0] < observed["environment"][0]):
        raise SystemExit(f"Startup behavior did not match the benchmark. See {trace}")
    return (observed["key_window"][0] - observed["swift_entry"][0]) / 1e6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="Interpreter from the installed Core environment")
    parser.add_argument("--sdk", type=Path, help="macOS SDK to use for the debug build")
    parser.add_argument("--evidence-parent", type=Path, help="Existing directory for a new private evidence folder")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("This check opens an isolated macOS app in the current graphical session.")
    python = args.python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        parser.error("--python must name the executable in an installed Core environment.")
    if command("git", "status", "--porcelain"):
        parser.error("Run from a clean checkout so the evidence can identify the tested commit.")
    revision = command("git", "rev-parse", "HEAD")
    sdk = args.sdk or Path(command("xcrun", "--sdk", "macosx", "--show-sdk-path"))
    sdk_version = json.loads((sdk / "SDKSettings.json").read_text(encoding="utf-8"))["Version"]
    host = {
        "model": command("/usr/sbin/sysctl", "-n", "hw.model"),
        "cpu": command("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"),
        "memory_bytes": int(command("/usr/sbin/sysctl", "-n", "hw.memsize")),
        "macos": command("/usr/bin/sw_vers", "-productVersion"),
        "macos_build": command("/usr/bin/sw_vers", "-buildVersion"),
        "sdk": sdk_version,
        "swift": command("swift", "--version"),
    }
    reference = (host["model"] == "MacBookPro18,3" and host["cpu"] == "Apple M1 Pro"
                 and host["memory_bytes"] == 16 * 1024**3 and host["macos_build"] == "26A434"
                 and host["sdk"] == "26.5" and "Apple Swift version 6.4" in host["swift"])

    os.umask(0o077)
    evidence = Path(tempfile.mkdtemp(prefix="scientific-workbench-startup-", dir=args.evidence_parent)).resolve()
    print(f"Evidence: {evidence}", flush=True)
    output = evidence / "history"
    selection = fixture(output)
    before = inventory(output)
    record(evidence / "history-before.json", before)
    source = build(evidence, sdk)
    bundle, binary = make_bundle(evidence, source, output, python)
    runs = []
    for index in range(WARMUPS + SAMPLES):
        elapsed = trial(evidence, bundle, binary, selection, index)
        runs.append(elapsed)
        print(f"Trial {index + 1:02d}: {elapsed:.1f} ms", flush=True)
    after = inventory(output)
    record(evidence / "history-after.json", after)
    if after != before or command("git", "rev-parse", "HEAD") != revision or command("git", "status", "--porcelain"):
        raise SystemExit("The fixture or source changed during the check. Keep the evidence and investigate.")
    measured = sorted(runs[WARMUPS:])
    median = statistics.median(measured)
    p95 = measured[math.ceil(0.95 * SAMPLES) - 1]
    passed = median <= MEDIAN_LIMIT_MS and p95 <= P95_LIMIT_MS
    result = {
        "revision": revision, "host": host, "binary_sha256": sha256(binary.read_bytes()).hexdigest(),
        "warmups": WARMUPS, "samples": SAMPLES, "launches_ms": runs,
        "median_ms": median, "p95_ms": p95, "median_limit_ms": MEDIAN_LIMIT_MS, "p95_limit_ms": P95_LIMIT_MS,
        "fixture_files_unchanged": len(after),
        "status": ("pass" if passed else "fail") if reference else "observation",
    }
    record(evidence / "summary.json", result)
    print(f"{result['status']}: median {median:.1f} ms, p95 {p95:.1f} ms")
    return int(reference and not passed)


if __name__ == "__main__":
    raise SystemExit(main())
