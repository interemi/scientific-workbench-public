#!/usr/bin/env python3
"""Regression checks for quicklook_bridge.py v1.6 hardening."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quicklook_bridge.py"
TMP = Path("/tmp/scientific-data-analysis-v1-6-quicklook-bridge-regression")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def assert_no_traceback(completed: subprocess.CompletedProcess[str]) -> None:
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert "Traceback (most recent call last)" not in combined, combined


def payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_payload(path: Path, *, status: str, qa_status: str) -> dict:
    data = payload(path)
    assert data["status"] == status, data
    assert data["qa"]["status"] == qa_status, data
    return data


def make_image(path: Path, label: str) -> None:
    image = Image.new("RGB", (640, 360), (245, 248, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle([28, 28, 612, 332], outline=(35, 88, 145), width=5)
    draw.line([70, 280, 570, 95], fill=(225, 170, 62), width=7)
    draw.text((50, 52), label, fill=(20, 20, 20))
    image.save(path)


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    image_path = TMP / "input.png"
    preview_asset = TMP / "preview-web.jpg"
    iwork_path = TMP / "preview_asset.key"
    corrupt_image = TMP / "corrupt.png"
    truncated_pptx = TMP / "truncated.pptx"
    make_image(image_path, "quicklook regression")
    make_image(preview_asset, "embedded preview")
    with zipfile.ZipFile(iwork_path, "w") as archive:
        archive.write(preview_asset, "QuickLook/preview-web.jpg")
    corrupt_image.write_bytes(b"not an image\n")
    truncated_pptx.write_bytes(b"PK\x03\x04truncated deck\n")

    happy_summary = TMP / "happy_summary.json"
    happy_output = TMP / "happy.png"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(image_path),
            "--output",
            str(happy_output),
            "--summary-json",
            str(happy_summary),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert happy_output.exists()
    assert_payload(happy_summary, status="ok", qa_status="ok")

    iwork_summary = TMP / "iwork_summary.json"
    iwork_output = TMP / "iwork.png"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(iwork_path),
            "--output",
            str(iwork_output),
            "--timeout-sec",
            "0.0001",
            "--summary-json",
            str(iwork_summary),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert iwork_output.exists()
    assert_payload(iwork_summary, status="warning", qa_status="warning")

    missing_summary = TMP / "missing_summary.json"
    missing_output = TMP / "missing.png"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(TMP / "missing.pdf"),
            "--output",
            str(missing_output),
            "--summary-json",
            str(missing_summary),
        ]
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert not missing_output.exists()
    assert_payload(missing_summary, status="blocked", qa_status="blocked")

    parent_file = TMP / "not_a_directory"
    parent_file.write_text("conflict\n", encoding="utf-8")
    output_conflict_summary = TMP / "output_conflict_summary.json"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(image_path),
            "--output",
            str(parent_file / "preview.png"),
            "--summary-json",
            str(output_conflict_summary),
        ]
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert_payload(output_conflict_summary, status="blocked", qa_status="blocked")

    corrupt_summary = TMP / "corrupt_summary.json"
    corrupt_output = TMP / "corrupt_preview.png"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(corrupt_image),
            "--output",
            str(corrupt_output),
            "--timeout-sec",
            "0.0001",
            "--summary-json",
            str(corrupt_summary),
        ]
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert not corrupt_output.exists()
    assert_payload(corrupt_summary, status="blocked", qa_status="blocked")

    truncated_summary = TMP / "truncated_summary.json"
    truncated_output = TMP / "truncated_preview.png"
    completed = run(
        [
            sys.executable,
            str(SCRIPT),
            str(truncated_pptx),
            "--output",
            str(truncated_output),
            "--timeout-sec",
            "0.0001",
            "--summary-json",
            str(truncated_summary),
        ]
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert_no_traceback(completed)
    assert not truncated_output.exists()
    assert_payload(truncated_summary, status="blocked", qa_status="blocked")

    print("quicklook_bridge regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
