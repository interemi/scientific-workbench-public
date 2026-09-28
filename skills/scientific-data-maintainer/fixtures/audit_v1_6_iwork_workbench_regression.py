#!/usr/bin/env python3
"""Regression checks for iwork_workbench.py v1.6 hardening."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iwork_workbench.py"
TMP = Path("/tmp/scientific-data-analysis-v1-6-iwork-workbench-regression")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def assert_no_traceback(completed: subprocess.CompletedProcess[str]) -> None:
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert "Traceback (most recent call last)" not in combined, combined


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_preview(path: Path, label: str) -> None:
    image = Image.new("RGB", (420, 260), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 400, 240], outline=(31, 85, 130), width=5)
    draw.text((40, 120), label, fill=(20, 20, 20))
    image.save(path)


def make_iwork(path: Path, *, suffix_kind: str, preview: bool = True, image: bool = True) -> None:
    image_path = TMP / f"{path.stem}_preview.jpg"
    make_preview(image_path, suffix_kind)
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(
            "Metadata/Properties.plist",
            "<?xml version='1.0'?><plist version='1.0'><dict><key>fileFormatVersion</key><string>synthetic</string></dict></plist>",
        )
        bundle.writestr("Index/Document.iwa", b"Synthetic IWA hint: spectrum lightcurve flux table")
        if preview:
            bundle.write(image_path, "preview.jpg")
        if image:
            bundle.write(image_path, "Data/spectrum_asset.png")
        if suffix_kind == "numbers":
            bundle.writestr("Index/Tables/DataList.iwa", b"Sheet 1 Table 1 rows columns formulas")
    image_path.unlink(missing_ok=True)


def assert_payload(path: Path, *, status: str, qa_status: str) -> dict:
    payload = load_payload(path)
    assert payload["status"] == status, payload
    assert payload["qa"]["status"] == qa_status, payload
    return payload


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    happy = TMP / "happy.pages"
    incomplete = TMP / "incomplete.numbers"
    corrupt = TMP / "corrupt.pages"
    unsupported = TMP / "archive.zip"
    make_iwork(happy, suffix_kind="pages", preview=True, image=True)
    make_iwork(incomplete, suffix_kind="numbers", preview=False, image=False)
    corrupt.write_bytes(b"not an iWork zip\n")
    make_iwork(unsupported, suffix_kind="pages", preview=True, image=True)

    happy_summary = TMP / "happy_summary.json"
    happy_out = TMP / "happy_out"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(happy),
            "--output-dir",
            str(happy_out),
            "--output-json",
            str(happy_summary),
            "--html-report",
            str(TMP / "happy_report.html"),
            "--manifest-json",
            str(TMP / "happy_manifest.json"),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert_payload(happy_summary, status="ok", qa_status="ok")
    assert (happy_out / "report.md").exists()
    assert (happy_out / "member_manifest.csv").exists()

    incomplete_summary = TMP / "incomplete_summary.json"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(incomplete),
            "--output-dir",
            str(TMP / "incomplete_out"),
            "--output-json",
            str(incomplete_summary),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    payload = assert_payload(incomplete_summary, status="warning", qa_status="warning")
    assert payload["qa"]["metrics"]["preview_file_count"] == 0, payload

    conflict_parent = TMP / "preview_parent_is_file"
    conflict_parent.write_text("not a directory\n", encoding="utf-8")
    preview_summary = TMP / "preview_summary.json"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(happy),
            "--output-dir",
            str(TMP / "preview_out"),
            "--output-json",
            str(preview_summary),
            "--native-preview",
            str(conflict_parent / "preview.png"),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert_payload(preview_summary, status="warning", qa_status="warning")

    for input_path, label in [
        (corrupt, "corrupt"),
        (TMP / "missing.pages", "missing"),
        (unsupported, "unsupported"),
    ]:
        summary = TMP / f"{label}_summary.json"
        completed = run(
            [
                sys.executable,
                str(SCRIPT),
                str(input_path),
                "--output-dir",
                str(TMP / f"{label}_out"),
                "--output-json",
                str(summary),
            ]
        )
        assert completed.returncode == 2, completed.stdout + completed.stderr
        assert_no_traceback(completed)
        assert_payload(summary, status="blocked", qa_status="blocked")

    output_file = TMP / "output_dir_is_file"
    output_file.write_text("conflict\n", encoding="utf-8")
    output_target_summary = TMP / "output_target_summary.json"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(happy),
            "--output-dir",
            str(output_file),
            "--output-json",
            str(output_target_summary),
        ]
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert_payload(output_target_summary, status="blocked", qa_status="blocked")

    print("iwork_workbench regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
