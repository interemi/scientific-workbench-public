#!/usr/bin/env python3
"""Regression tests for apt_workbench.py optional-backend safety."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from _internal.public_contract import validate_standard_envelope


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
WRAPPER = SCRIPTS / "datanalysis_env.py"
TOOL = SCRIPTS / "apt_workbench.py"


def run_cmd(args: list[str], *, expect_ok: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command unexpectedly passed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}")
    if "Traceback" in completed.stdout or "Traceback" in completed.stderr:
        raise AssertionError(f"Command leaked a traceback:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    return completed


def apt_cmd(*args: str | Path) -> list[str]:
    return [sys.executable, str(WRAPPER), "python", str(TOOL), *[str(item) for item in args]]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stdout_json(completed: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(completed.stdout)
    except Exception as exc:
        raise AssertionError(f"Expected JSON stdout, got:\n{completed.stdout}\nSTDERR:\n{completed.stderr}") from exc


def assert_standard(payload: dict, expected_status: str) -> None:
    issues = validate_standard_envelope(payload)
    if issues:
        raise AssertionError(f"Invalid standard envelope: {issues}\n{payload}")
    if payload["status"] != expected_status:
        raise AssertionError(f"Expected status={expected_status}, got {payload['status']}: {payload}")


def make_executable(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def fake_apt(path: Path) -> Path:
    return make_executable(
        path,
        """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if "-h" in args or "--help" in args:
    print("fake APT help")
    sys.exit(0)
try:
    out = args[args.index("-o") + 1]
except ValueError:
    out = "APT.tbl"
path = pathlib.Path(out)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    "Number  Image  X  Y  SourceIntensity\\n"
    "1  image.fits  10.0  20.0  1234.5\\n"
    "2  image.fits  30.0  40.0  567.8\\n",
    encoding="utf-8",
)
print("fake APT wrote", out)
sys.exit(0)
""",
    )


def make_apt_table(path: Path) -> Path:
    path.write_text(
        "Number Image X Y SourceIntensity\n"
        "1 image.fits 10.0 20.0 1234.5\n"
        "2 image.fits 30.0 40.0 567.8\n",
        encoding="utf-8",
    )
    return path


def check_prepare_success(tmp: Path) -> None:
    source_csv = tmp / "sources.csv"
    source_csv.write_text("id,x,y\nA,10,20\nB,30,40\n", encoding="utf-8")
    source_list = tmp / "sources.lst"
    summary = tmp / "prepare.json"
    run_cmd(apt_cmd("prepare-source-list", source_csv, source_list, "--x-col", "x", "--y-col", "y", "--id-col", "id", "--summary-json", summary))
    payload = read_json(summary)
    assert_standard(payload, "ok")
    if source_list.read_text(encoding="utf-8").splitlines() != ["10.00000000 20.00000000 A", "30.00000000 40.00000000 B"]:
        raise AssertionError("Source list was not formatted as expected.")


def check_fake_batch_success(tmp: Path) -> None:
    apt = fake_apt(tmp / "fake APT.csh")
    prefs = tmp / "APT.pref"
    prefs.write_text("fake prefs\n", encoding="utf-8")
    image = tmp / "image.fits"
    image.write_text("fake image\n", encoding="utf-8")
    sources = tmp / "sources.lst"
    sources.write_text("10 20 A\n", encoding="utf-8")
    output = tmp / "APT.tbl"
    summary = tmp / "batch.json"
    run_cmd(
        apt_cmd(
            "run-batch",
            "--apt-command",
            apt,
            "--apt-preferences",
            prefs,
            "--image",
            image,
            "--source-list",
            sources,
            "--output-table",
            output,
            "--summary-json",
            summary,
            "--log-dir",
            tmp / "logs",
        )
    )
    payload = read_json(summary)
    assert_standard(payload, "ok")
    if not output.exists() or not (tmp / "logs" / "apt_command.sh").exists():
        raise AssertionError("Fake APT batch did not produce expected output/logs.")


def check_prepare_missing_column_blocks(tmp: Path) -> None:
    source_csv = tmp / "missing_y.csv"
    source_csv.write_text("id,x\nA,10\n", encoding="utf-8")
    output = tmp / "missing_y.lst"
    summary = tmp / "missing_y.json"
    run_cmd(apt_cmd("prepare-source-list", source_csv, output, "--x-col", "x", "--y-col", "y", "--summary-json", summary), expect_ok=False)
    payload = read_json(summary)
    assert_standard(payload, "blocked")
    if output.exists():
        raise AssertionError("Blocked source-list preparation created an output.")


def check_prepare_does_not_overwrite_input(tmp: Path) -> None:
    source_csv = tmp / "self.csv"
    original = "id,x,y\nA,10,20\n"
    source_csv.write_text(original, encoding="utf-8")
    summary = tmp / "self.json"
    run_cmd(apt_cmd("prepare-source-list", source_csv, source_csv, "--x-col", "x", "--y-col", "y", "--id-col", "id", "--summary-json", summary), expect_ok=False)
    payload = read_json(summary)
    assert_standard(payload, "blocked")
    if source_csv.read_text(encoding="utf-8") != original:
        raise AssertionError("Source-list preparation overwrote its input.")


def check_parse_single_space_apt_table(tmp: Path) -> None:
    apt_table = make_apt_table(tmp / "APT_single_space.tbl")
    output = tmp / "parsed.csv"
    summary = tmp / "parse.json"
    run_cmd(apt_cmd("parse-results", apt_table, output, "--summary-json", summary))
    payload = read_json(summary)
    assert_standard(payload, "ok")
    if payload["qa"]["metrics"]["column_count"] < 5:
        raise AssertionError(f"APT table collapsed into too few columns: {payload}")
    if "SourceIntensity" not in output.read_text(encoding="utf-8"):
        raise AssertionError("Parsed CSV missed the SourceIntensity column.")


def check_parse_output_parent_file_blocks(tmp: Path) -> None:
    apt_table = make_apt_table(tmp / "APT.tbl")
    parent_file = tmp / "parent_is_file"
    parent_file.write_text("not a directory\n", encoding="utf-8")
    output = parent_file / "parsed.csv"
    summary = tmp / "bad_parent.json"
    run_cmd(apt_cmd("parse-results", apt_table, output, "--summary-json", summary), expect_ok=False)
    payload = read_json(summary)
    assert_standard(payload, "blocked")
    if output.exists():
        raise AssertionError("Blocked parse left an output through a file parent.")


def check_parse_summary_cannot_overwrite_output(tmp: Path) -> None:
    apt_table = make_apt_table(tmp / "APT_for_collision.tbl")
    output = tmp / "parsed_collision.csv"
    completed = run_cmd(apt_cmd("parse-results", apt_table, output, "--summary-json", output), expect_ok=False)
    payload = stdout_json(completed)
    assert_standard(payload, "blocked")
    if output.exists():
        raise AssertionError("--summary-json collision left a parsed table or summary at the output path.")


def check_run_batch_missing_image_blocks_even_dry_run(tmp: Path) -> None:
    apt = fake_apt(tmp / "fake APT missing image.csh")
    prefs = tmp / "APT_missing_image.pref"
    prefs.write_text("fake prefs\n", encoding="utf-8")
    sources = tmp / "sources_missing_image.lst"
    sources.write_text("10 20 A\n", encoding="utf-8")
    summary = tmp / "missing_image.json"
    run_cmd(
        apt_cmd(
            "run-batch",
            "--apt-command",
            apt,
            "--apt-preferences",
            prefs,
            "--image",
            tmp / "missing.fits",
            "--source-list",
            sources,
            "--output-table",
            tmp / "would_not_run.tbl",
            "--summary-json",
            summary,
            "--dry-run",
        ),
        expect_ok=False,
    )
    payload = read_json(summary)
    assert_standard(payload, "blocked")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_apt_workbench_") as raw_tmp:
        tmp = Path(raw_tmp)
        check_prepare_success(tmp)
        print("PASS check_prepare_success")
        check_fake_batch_success(tmp)
        print("PASS check_fake_batch_success")
        check_prepare_missing_column_blocks(tmp)
        print("PASS check_prepare_missing_column_blocks")
        check_prepare_does_not_overwrite_input(tmp)
        print("PASS check_prepare_does_not_overwrite_input")
        check_parse_single_space_apt_table(tmp)
        print("PASS check_parse_single_space_apt_table")
        check_parse_output_parent_file_blocks(tmp)
        print("PASS check_parse_output_parent_file_blocks")
        check_parse_summary_cannot_overwrite_output(tmp)
        print("PASS check_parse_summary_cannot_overwrite_output")
        check_run_batch_missing_image_blocks_even_dry_run(tmp)
        print("PASS check_run_batch_missing_image_blocks_even_dry_run")
    print("All apt_workbench regressions passed.")


if __name__ == "__main__":
    main()
