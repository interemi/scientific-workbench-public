#!/usr/bin/env python3
"""Narrow regression checks for fxcor_iraf_workbench.py run-auto."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fxcor_iraf_workbench.py"
SOURCE_FITS = ROOT / "examples" / "science" / "legacy_spectroscopy_mini" / "mini_multispec.fits"
REQUIRED_FITS = [
    "npwand_n3.fits",
    "nhd161096_n3.fits",
    "nhd166620_n2.fits",
    "nrej1101_foces02_n2.fits",
    "nhd100696_n3.fits",
    "nhd97004_n4.fits",
    "nhd92588_n2.fits",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_practice(root: Path) -> None:
    fits_dir = root / "fits_p1"
    fits_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FITS:
        shutil.copy2(SOURCE_FITS, fits_dir / name)
    login_dir = root / "CODEX" / "01_iraf_safe"
    login_dir.mkdir(parents=True, exist_ok=True)
    (login_dir / "login.cl").write_text("set home = .\n", encoding="utf-8")


def make_fake_cl(bin_dir: Path, *, mode: str = "ok") -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    iraf_root = bin_dir / "iraf"
    cl = iraf_root / "unix" / "hlib" / "cl"
    cl.parent.mkdir(parents=True, exist_ok=True)
    package_par = iraf_root / "noao" / "rv" / "fxcor.par"
    package_par.parent.mkdir(parents=True, exist_ok=True)
    package_par.write_text("# synthetic fxcor parameter file\n", encoding="utf-8")
    cl.write_text(
        f"""#!{sys.executable}
from pathlib import Path
import re, sys
text = sys.stdin.read()
match = re.search(r'output="([^"]+)"', text)
out_base = Path(match.group(1) if match else '../logs/fake_case')
if {mode!r} == 'no_txt':
    print('fake cl ran without txtonly')
    sys.exit(0)
out_base.parent.mkdir(parents=True, exist_ok=True)
if {mode!r} == 'empty_txt':
    out_base.with_suffix('.txt').write_text('# no usable fxcor rows\\n', encoding='utf-8')
    sys.exit(0)
out_base.with_suffix('.txt').write_text(\"\"\"# fake fxcor txtonly
#                   Image = 'template.fits' Vhelio = -12.5
Velocity Dispersion = 3.75
star image.fits A B 21 C -8.120 0.62 37.50 10.00 D -30.100 E 1.500
\"\"\", encoding='utf-8')
if {mode!r} == 'native_error':
    print('ERROR: segmentation violation')
sys.exit(1 if {mode!r} == 'warn_rc' else 0)
""",
        encoding="utf-8",
    )
    cl.chmod(cl.stat().st_mode | stat.S_IXUSR)
    (bin_dir / "cl").symlink_to(cl)


def prepare_workspace(practice: Path, workspace: Path, summary: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "prepare-session", str(practice), "--output-dir", str(workspace), "--summary-json", str(summary)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    require(result.returncode == 0, result.stderr or result.stdout)


def run_auto(workspace: Path, *, path: Path, summary: Path | None = None, manifest: Path | None = None, case_ids: list[str] | None = None) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [sys.executable, str(SCRIPT), "run-auto", str(workspace)]
    for case_id in case_ids or []:
        cmd.extend(["--case-id", case_id])
    if summary:
        cmd.extend(["--summary-json", str(summary)])
    if manifest:
        cmd.extend(["--manifest-json", str(manifest)])
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PATH"] = str(path)
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=30, env=env)
    payload_text = summary.read_text(encoding="utf-8") if summary and summary.exists() else result.stdout
    payload = json.loads(payload_text)
    return result, payload


def clear_case_artifacts(workspace: Path, case_id: str) -> None:
    for path in [
        workspace / "logs" / f"{case_id}.txt",
        workspace / "logs" / f"{case_id}.cl_stdout.log",
        workspace / "parsed" / f"{case_id}_auto.csv",
        workspace / "scripts" / f"{case_id}.cl",
    ]:
        path.unlink(missing_ok=True)


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="sda_fxcor_run_auto_regression_", dir="/tmp"))
    try:
        fake_ok = base / "fake_ok"
        fake_warn = base / "fake_warn"
        fake_no_txt = base / "fake_no_txt"
        fake_empty_txt = base / "fake_empty_txt"
        fake_native_error = base / "fake_native_error"
        fake_empty = base / "fake_empty"
        make_fake_cl(fake_ok)
        make_fake_cl(fake_warn, mode="warn_rc")
        make_fake_cl(fake_no_txt, mode="no_txt")
        make_fake_cl(fake_empty_txt, mode="empty_txt")
        make_fake_cl(fake_native_error, mode="native_error")
        fake_empty.mkdir()

        practice = base / "practice"
        workspace = base / "workspace"
        make_practice(practice)
        prepare_workspace(practice, workspace, base / "prepare.json")

        result, payload = run_auto(workspace, path=fake_ok, summary=base / "ok.json", manifest=base / "ok_manifest.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 0, result.stderr or result.stdout or repr(payload))
        require(payload["status"] == "ok", payload)
        require(len(payload["artifacts"]["parsed_csvs"]) == 1, payload["artifacts"])
        require((workspace / "parsed" / "pwand_vsini36_auto.csv").exists(), "parsed CSV missing")
        require((workspace / ".iraf" / "uparm" / "rvfxcor.par").exists(), "IRAF fxcor parameter seed missing")

        result, payload = run_auto(workspace, path=fake_warn, summary=base / "warn.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 0, result.stderr or result.stdout or repr(payload))
        require(payload["status"] == "warning", payload)
        require(payload["qa"]["metrics"]["warning_case_count"] == 1, payload["qa"])

        result, payload = run_auto(workspace, path=fake_empty, summary=base / "missing_cl.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require("Traceback" not in result.stderr, result.stderr)
        require(payload["qa"]["metrics"]["blocked_case_count"] == 1, payload["qa"])

        result, payload = run_auto(workspace, path=fake_ok, summary=base / "invalid_case.json", case_ids=["does_not_exist"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require("does_not_exist" in payload["notes"][0], payload["notes"])

        no_txt_workspace = base / "workspace_no_txt"
        shutil.copytree(workspace, no_txt_workspace)
        result, payload = run_auto(no_txt_workspace, path=fake_no_txt, summary=base / "no_txt.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require(any("txtonly" in item for item in payload["notes"]), payload["notes"])

        empty_txt_workspace = base / "workspace_empty_txt"
        shutil.copytree(workspace, empty_txt_workspace)
        result, payload = run_auto(empty_txt_workspace, path=fake_empty_txt, summary=base / "empty_txt.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require(payload["qa"]["metrics"]["parsed_csv_count"] == 0, payload["qa"])
        require(any("filas fxcor utilizables" in item for item in payload["notes"]), payload["notes"])

        native_error_workspace = base / "workspace_native_error"
        shutil.copytree(workspace, native_error_workspace)
        result, payload = run_auto(native_error_workspace, path=fake_native_error, summary=base / "native_error.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require(payload["qa"]["metrics"]["parsed_csv_count"] == 0, payload["qa"])
        require(any("error nativo" in item for item in payload["notes"]), payload["notes"])

        bad_parent = base / "summary_parent_is_file"
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        bad_summary_workspace = base / "workspace_bad_summary"
        shutil.copytree(workspace, bad_summary_workspace)
        clear_case_artifacts(bad_summary_workspace, "pwand_vsini36")
        result, payload = run_auto(bad_summary_workspace, path=fake_ok, summary=bad_parent / "summary.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require("Traceback" not in result.stderr, result.stderr)
        require(not (bad_summary_workspace / "logs" / "pwand_vsini36.txt").exists(), "invalid summary should block before run")

        corrupt_workspace = base / "workspace_corrupt"
        shutil.copytree(workspace, corrupt_workspace)
        (corrupt_workspace / "fxcor_cases.json").write_text("{ broken json", encoding="utf-8")
        result, payload = run_auto(corrupt_workspace, path=fake_ok, summary=base / "corrupt.json", case_ids=["pwand_vsini36"])
        require(result.returncode == 2, result.stderr)
        require(payload["status"] == "blocked", payload)
        require("Traceback" not in result.stderr, result.stderr)

        print("fxcor run-auto regression passed")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
