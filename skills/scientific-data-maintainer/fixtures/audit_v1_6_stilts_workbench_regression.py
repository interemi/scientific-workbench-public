#!/usr/bin/env python3
"""Narrow v1.6 regression checks for stilts_workbench.py."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stilts_workbench.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def fake_stilts(path: Path, *, write_output: bool = True, sleep_forever: bool = False) -> Path:
    if sleep_forever:
        body = """#!/usr/bin/env python3
import time
time.sleep(10)
"""
    elif write_output:
        body = """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if not args:
    print("fake stilts ready")
    sys.exit(0)
task = args[0]

def value(prefix):
    for item in args[1:]:
        if item.startswith(prefix + "="):
            return item.split("=", 1)[1]
    return None

if task in {"tcopy", "tpipe", "tskymatch2"}:
    out = value("out")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text("id,ra,dec\\n1,10.0,20.0\\n", encoding="utf-8")
    print("wrote", out)
    sys.exit(0)
if task == "votlint":
    out = value("out") or "-"
    if out == "-":
        print("fake votlint: no issues")
    else:
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out).write_text("fake votlint: no issues\\n", encoding="utf-8")
    sys.exit(0)
print("unsupported task", task, file=sys.stderr)
sys.exit(3)
"""
    else:
        body = """#!/usr/bin/env python3
import sys
print("claimed success without writing output")
sys.exit(0)
"""
    return make_executable(path, body)


def run_stilts(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True, check=False)


def assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stilts-workbench-v1-6-") as tmp_raw:
        tmp = Path(tmp_raw)
        tools = tmp / "tools with spaces"
        stilts = fake_stilts(tools / "fake STILTS.py")
        no_output_stilts = fake_stilts(tools / "fake STILTS no output.py", write_output=False)
        slow_stilts = fake_stilts(tools / "fake STILTS slow.py", sleep_forever=True)

        source = tmp / "input catalog.csv"
        source.write_text("id,ra,dec,mag\n1,10,20,15\n2,11,21,16\n", encoding="utf-8")
        left = tmp / "left.csv"
        right = tmp / "right.csv"
        left.write_text("id,ra,dec\nA,10,20\n", encoding="utf-8")
        right.write_text("id,ra,dec\nB,10.0001,20.0001\n", encoding="utf-8")
        votable = tmp / "table.vot"
        votable.write_text("<VOTABLE version='1.4'></VOTABLE>\n", encoding="utf-8")

        convert_summary = tmp / "convert summary.json"
        convert_out = tmp / "converted.csv"
        convert = run_stilts(
            [
                "convert",
                str(source),
                str(convert_out),
                "--stilts-command",
                str(stilts),
                "--ofmt",
                "csv",
                "--summary-json",
                str(convert_summary),
                "--manifest-json",
                str(tmp / "convert manifest.json"),
                "--log-dir",
                str(tmp / "convert logs"),
            ]
        )
        assert convert.returncode == 0, convert.stderr
        assert_no_traceback(convert)
        assert read_json(convert_summary)["status"] == "ok"
        assert convert_out.exists()

        lint_summary = tmp / "lint summary.json"
        lint_report = tmp / "lint report.txt"
        lint = run_stilts(
            [
                "votlint",
                str(votable),
                str(lint_report),
                "--stilts-command",
                str(stilts),
                "--summary-json",
                str(lint_summary),
            ]
        )
        assert lint.returncode == 0, lint.stderr
        assert_no_traceback(lint)
        assert read_json(lint_summary)["status"] == "ok"
        assert lint_report.exists()

        bad_radius_summary = tmp / "bad radius.json"
        bad_radius = run_stilts(
            [
                "crossmatch-sky",
                str(left),
                str(right),
                str(tmp / "bad radius.csv"),
                "--left-ra",
                "ra",
                "--left-dec",
                "dec",
                "--right-ra",
                "ra",
                "--right-dec",
                "dec",
                "--radius-arcsec",
                "0",
                "--stilts-command",
                str(stilts),
                "--summary-json",
                str(bad_radius_summary),
            ]
        )
        assert bad_radius.returncode == 2, bad_radius.stderr
        assert_no_traceback(bad_radius)
        assert read_json(bad_radius_summary)["status"] == "blocked"

        stale_out = tmp / "stale matched.csv"
        stale_out.write_text("stale\n", encoding="utf-8")
        stale_summary = tmp / "stale summary.json"
        stale = run_stilts(
            [
                "crossmatch-sky",
                str(left),
                str(right),
                str(stale_out),
                "--left-ra",
                "ra",
                "--left-dec",
                "dec",
                "--right-ra",
                "ra",
                "--right-dec",
                "dec",
                "--radius-arcsec",
                "1",
                "--stilts-command",
                str(no_output_stilts),
                "--summary-json",
                str(stale_summary),
            ]
        )
        assert stale.returncode == 1, stale.stderr
        assert_no_traceback(stale)
        stale_payload = read_json(stale_summary)
        assert stale_payload["status"] == "fail", stale_payload
        assert stale_payload["qa"]["metrics"]["unchanged_outputs"] == 1, stale_payload

        log_file = tmp / "log-dir-is-file"
        log_file.write_text("not a directory\n", encoding="utf-8")
        log_summary = tmp / "log blocked.json"
        log_blocked = run_stilts(
            [
                "convert",
                str(source),
                str(tmp / "log blocked output.csv"),
                "--stilts-command",
                str(stilts),
                "--log-dir",
                str(log_file),
                "--summary-json",
                str(log_summary),
            ]
        )
        assert log_blocked.returncode == 2, log_blocked.stderr
        assert_no_traceback(log_blocked)
        assert read_json(log_summary)["status"] == "blocked"

        timeout_summary = tmp / "timeout summary.json"
        timeout = run_stilts(
            [
                "convert",
                str(source),
                str(tmp / "timeout output.csv"),
                "--stilts-command",
                str(slow_stilts),
                "--timeout-sec",
                "1",
                "--summary-json",
                str(timeout_summary),
            ]
        )
        assert timeout.returncode == 1, timeout.stderr
        assert_no_traceback(timeout)
        assert read_json(timeout_summary)["status"] == "fail"

        parent_file = tmp / "summary parent file"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        bad_summary = parent_file / "summary.json"
        bad_summary_result = run_stilts(["preflight", "--stilts-command", str(stilts), "--summary-json", str(bad_summary)])
        assert bad_summary_result.returncode == 2, bad_summary_result.stderr
        assert_no_traceback(bad_summary_result)
        assert "Could not write summary JSON" in bad_summary_result.stderr

    print("stilts_workbench v1.6 regression: ok")


if __name__ == "__main__":
    main()
