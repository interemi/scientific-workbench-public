#!/usr/bin/env python3
"""Regression gate for optional STILTS and APT external-tool wrappers."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str], cwd: Path = ROOT) -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False, env=env)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_executable(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def fake_stilts(path: Path) -> Path:
    return make_executable(
        path,
        """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if not args:
    print("fake stilts")
    sys.exit(0)

task = args[0]

def value(prefix):
    for item in args[1:]:
        if item.startswith(prefix + "="):
            return item.split("=", 1)[1]
    return None

if task in {"tcopy", "tpipe", "tskymatch2"}:
    out = value("out")
    if not out:
        print("missing out=", file=sys.stderr)
        sys.exit(2)
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text("id,ra,dec\\n1,10.0,20.0\\n", encoding="utf-8")
    print("wrote", out)
    sys.exit(0)

if task == "votlint":
    out = value("out") or "-"
    text = "fake votlint: no issues\\n"
    if out == "-":
        print(text, end="")
    else:
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out).write_text(text, encoding="utf-8")
    sys.exit(0)

print("unsupported task", task, file=sys.stderr)
sys.exit(3)
""",
    )


def fake_java(path: Path) -> Path:
    return make_executable(
        path,
        """#!/usr/bin/env python3
import sys
if "-version" in sys.argv:
    print("fake java version 17")
sys.exit(0)
""",
    )


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


def check_preflight(tmp: Path, java: Path, stilts: Path, apt: Path, prefs: Path) -> None:
    summary = tmp / "preflight.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "external_astro_tools_preflight.py"),
            "--java-command",
            str(java),
            "--stilts-command",
            str(stilts),
            "--apt-command",
            str(apt),
            "--apt-preferences",
            str(prefs),
            "--summary-json",
            str(summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    payload = read_json(summary)
    require(payload["tool"] == "external_astro_tools_preflight", "wrong preflight tool")
    require(payload["results"]["capabilities"]["stilts_ready"], "fake STILTS should be ready")
    require(payload["results"]["capabilities"]["apt_batch_ready"], "fake APT should be batch ready")


def check_stilts_convert(tmp: Path, stilts: Path) -> None:
    src = tmp / "catalog.csv"
    src.write_text("id,ra,dec\n1,10.0,20.0\n", encoding="utf-8")
    out = tmp / "converted.csv"
    summary = tmp / "stilts_convert.json"
    manifest = tmp / "stilts_convert_manifest.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "stilts_workbench.py"),
            "convert",
            str(src),
            str(out),
            "--stilts-command",
            str(stilts),
            "--ofmt",
            "csv",
            "--summary-json",
            str(summary),
            "--manifest-json",
            str(manifest),
            "--log-dir",
            str(tmp / "stilts_convert_logs"),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    payload = read_json(summary)
    require(payload["status"] == "ok", "convert should pass")
    require(out.exists(), "converted table not created")
    require(manifest.exists(), "convert manifest not created")


def check_stilts_crossmatch_and_votlint(tmp: Path, stilts: Path) -> None:
    left = tmp / "left.csv"
    right = tmp / "right.csv"
    left.write_text("id,ra,dec\n1,10.0,20.0\n", encoding="utf-8")
    right.write_text("id,ra,dec\n2,10.0001,20.0001\n", encoding="utf-8")
    matched = tmp / "matched.csv"
    cross_summary = tmp / "cross.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "stilts_workbench.py"),
            "crossmatch-sky",
            str(left),
            str(right),
            str(matched),
            "--left-ra",
            "ra",
            "--left-dec",
            "dec",
            "--right-ra",
            "ra",
            "--right-dec",
            "dec",
            "--radius-arcsec",
            "1.0",
            "--stilts-command",
            str(stilts),
            "--ofmt",
            "csv",
            "--summary-json",
            str(cross_summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    require(matched.exists(), "crossmatch output not created")
    require(read_json(cross_summary)["status"] == "ok", "crossmatch should pass")

    votable = tmp / "table.vot"
    votable.write_text("<VOTABLE version='1.4'></VOTABLE>\n", encoding="utf-8")
    report = tmp / "votlint.txt"
    lint_summary = tmp / "lint.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "stilts_workbench.py"),
            "votlint",
            str(votable),
            str(report),
            "--stilts-command",
            str(stilts),
            "--summary-json",
            str(lint_summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    require(report.exists(), "votlint report not created")
    require(read_json(lint_summary)["status"] == "ok", "votlint should pass")


def check_apt_prepare_run_parse(tmp: Path, apt: Path, prefs: Path) -> None:
    source_csv = tmp / "sources.csv"
    source_csv.write_text("id,x,y\nA,10,20\nB,30,40\n", encoding="utf-8")
    source_list = tmp / "sources.lst"
    prep_summary = tmp / "apt_prepare.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "apt_workbench.py"),
            "prepare-source-list",
            str(source_csv),
            str(source_list),
            "--x-col",
            "x",
            "--y-col",
            "y",
            "--id-col",
            "id",
            "--summary-json",
            str(prep_summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    require(source_list.exists(), "source list not created")
    require(read_json(prep_summary)["results"]["row_count"] == 2, "source row count should be 2")

    image = tmp / "image.fits"
    image.write_text("fake fits placeholder\n", encoding="utf-8")
    apt_table = tmp / "APT.tbl"
    batch_summary = tmp / "apt_batch.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "apt_workbench.py"),
            "run-batch",
            "--apt-command",
            str(apt),
            "--apt-preferences",
            str(prefs),
            "--image",
            str(image),
            "--source-list",
            str(source_list),
            "--output-table",
            str(apt_table),
            "--summary-json",
            str(batch_summary),
            "--log-dir",
            str(tmp / "apt_logs"),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    require(apt_table.exists(), "APT table not created")
    require(read_json(batch_summary)["status"] == "ok", "APT batch should pass")

    parsed = tmp / "apt_parsed.csv"
    parse_summary = tmp / "apt_parse.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "apt_workbench.py"),
            "parse-results",
            str(apt_table),
            str(parsed),
            "--summary-json",
            str(parse_summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    payload = read_json(parse_summary)
    require(payload["status"] == "ok", "APT parse should pass")
    require(payload["results"]["row_count"] == 2, "parsed APT row count should be 2")
    require(parsed.exists(), "parsed APT CSV not created")


def check_missing_apt_pref_blocks(tmp: Path, apt: Path) -> None:
    image = tmp / "image2.fits"
    image.write_text("fake fits placeholder\n", encoding="utf-8")
    source_list = tmp / "sources2.lst"
    source_list.write_text("1 2\n", encoding="utf-8")
    summary = tmp / "apt_missing_pref.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "apt_workbench.py"),
            "run-batch",
            "--apt-command",
            str(apt),
            "--apt-preferences",
            str(tmp / "missing.pref"),
            "--image",
            str(image),
            "--source-list",
            str(source_list),
            "--output-table",
            str(tmp / "missing.tbl"),
            "--summary-json",
            str(summary),
        ]
    )
    require(result["returncode"] == 2, "missing APT preferences should block")
    require(read_json(summary)["status"] == "blocked", "missing APT preferences should emit blocked JSON")


def check_local_validation_harness(tmp: Path, java: Path, stilts: Path, apt: Path, prefs: Path) -> None:
    summary = tmp / "local_validation.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "external_astro_tools_local_validation.py"),
            "--output-dir",
            str(tmp / "local_validation"),
            "--java-command",
            str(java),
            "--stilts-command",
            str(stilts),
            "--apt-command",
            str(apt),
            "--apt-preferences",
            str(prefs),
            "--summary-json",
            str(summary),
        ]
    )
    require(result["returncode"] == 0, result["stderr"])
    payload = read_json(summary)
    require(payload["tool"] == "external_astro_tools_local_validation", "wrong local validation tool")
    require(payload["status"] == "ok", f"local validation should pass with fake backends: {payload}")
    statuses = {item["id"]: item["status"] for item in payload["results"]["validations"]}
    require(statuses["stilts_real_crossmatch"] == "PASS", "local validation should exercise fake STILTS")
    require(statuses["apt_batch_validation"] == "PASS", "local validation should dry-run fake APT")


def main() -> None:
    ensure_datanalysis_runtime("audit_external_astro_tools_regression", strict=False)
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-external-astro-") as tmp_raw:
        tmp = Path(tmp_raw)
        java = fake_java(tmp / "fake_java.py")
        stilts = fake_stilts(tmp / "fake_stilts.py")
        apt = fake_apt(tmp / "fake_APT.csh")
        prefs = tmp / "APT.pref"
        prefs.write_text("fake preferences\n", encoding="utf-8")
        checks = [
            lambda: check_preflight(tmp, java, stilts, apt, prefs),
            lambda: check_stilts_convert(tmp, stilts),
            lambda: check_stilts_crossmatch_and_votlint(tmp, stilts),
            lambda: check_apt_prepare_run_parse(tmp, apt, prefs),
            lambda: check_missing_apt_pref_blocks(tmp, apt),
            lambda: check_local_validation_harness(tmp, java, stilts, apt, prefs),
        ]
        for check in checks:
            check()
            print(f"PASS {check.__name__ if hasattr(check, '__name__') else 'external_tool_check'}")
    print("All external astronomy tools regressions passed.")


if __name__ == "__main__":
    main()
