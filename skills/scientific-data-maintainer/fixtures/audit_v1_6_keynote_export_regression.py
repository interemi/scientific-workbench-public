#!/usr/bin/env python3
"""Narrow v1.6 regression checks for keynote_export.py."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "keynote_export.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_blocked_payload(path: Path, expected_fragment: str) -> None:
    payload = read_json(path)
    assert payload["tool"] == "keynote_export", payload
    assert payload["status"] == "blocked", payload
    assert payload["qa"]["status"] == "blocked", payload
    native_error = payload["results"].get("native_error") or ""
    assert expected_fragment in native_error, native_error


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_clean_blocked_cli(completed: subprocess.CompletedProcess[str], summary: Path, expected_fragment: str) -> None:
    assert completed.returncode == 2, completed
    assert "Traceback" not in completed.stderr, completed.stderr
    assert summary.exists(), completed
    assert_blocked_payload(summary, expected_fragment)


def run_main_with_fakes(tmp: Path, *, returncode: int, write_pdf: bool) -> tuple[int, Path, Path, str, str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import keynote_export  # noqa: PLC0415

    deck = tmp / "fake_deck.pptx"
    pdf = tmp / f"fake_{returncode}_{int(write_pdf)}.pdf"
    summary = tmp / f"fake_{returncode}_{int(write_pdf)}.json"
    deck.write_text("not a real pptx; export is monkeypatched", encoding="utf-8")

    def fake_report():
        return {
            "status": "ok",
            "blocking_findings": [],
            "warning_findings": [],
            "recommendation": "fake Keynote is ready",
            "capabilities": {"platform": "darwin", "osascript": True, "keynote_app": True},
        }

    def fake_export(_presentation_path: Path, target_pdf: Path):
        if write_pdf:
            target_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return subprocess.CompletedProcess(["osascript"], returncode, stdout="", stderr="synthetic native failure")

    old_argv = sys.argv[:]
    old_report = keynote_export.build_capability_report
    old_export = keynote_export.export_with_keynote
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0
    try:
        keynote_export.build_capability_report = fake_report
        keynote_export.export_with_keynote = fake_export
        sys.argv = [
            str(SCRIPT),
            str(deck),
            str(pdf),
            "--summary-json",
            str(summary),
        ]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                keynote_export.main()
            except SystemExit as exc:
                exit_code = int(exc.code or 0)
    finally:
        keynote_export.build_capability_report = old_report
        keynote_export.export_with_keynote = old_export
        sys.argv = old_argv
    return exit_code, summary, pdf, stdout.getvalue(), stderr.getvalue()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="keynote-export-regression-") as tmp_raw:
        tmp = Path(tmp_raw)
        deck = tmp / "valid_name.pptx"
        deck.write_text("placeholder deck", encoding="utf-8")
        text_input = tmp / "not_a_deck.txt"
        text_input.write_text("not a deck", encoding="utf-8")

        unsupported_summary = tmp / "unsupported.json"
        unsupported = run_cli([str(text_input), str(tmp / "unsupported.pdf"), "--summary-json", str(unsupported_summary)])
        assert_clean_blocked_cli(unsupported, unsupported_summary, "Unsupported presentation suffix")

        missing_summary = tmp / "missing.json"
        missing = run_cli([str(tmp / "missing.pptx"), str(tmp / "missing.pdf"), "--summary-json", str(missing_summary)])
        assert_clean_blocked_cli(missing, missing_summary, "does not exist")

        parent_file = tmp / "pdf_parent_is_file"
        parent_file.write_text("not a directory", encoding="utf-8")
        parent_summary = tmp / "parent.json"
        parent_conflict = run_cli([str(deck), str(parent_file / "export.pdf"), "--summary-json", str(parent_summary)])
        assert_clean_blocked_cli(parent_conflict, parent_summary, "Output parent exists")

        success_code, success_summary, success_pdf, success_stdout, success_stderr = run_main_with_fakes(
            tmp,
            returncode=0,
            write_pdf=True,
        )
        assert success_code == 0, (success_code, success_stdout, success_stderr)
        success_payload = read_json(success_summary)
        assert success_payload["status"] == "ok", success_payload
        assert success_payload["qa"]["status"] == "ok", success_payload
        assert success_pdf.exists() and success_pdf.stat().st_size > 0

        failure_code, failure_summary, failure_pdf, failure_stdout, failure_stderr = run_main_with_fakes(
            tmp,
            returncode=1,
            write_pdf=False,
        )
        assert failure_code == 2, (failure_code, failure_stdout, failure_stderr)
        assert_blocked_payload(failure_summary, "synthetic native failure")
        assert not failure_pdf.exists()

        missing_artifact_code, missing_artifact_summary, missing_artifact_pdf, missing_artifact_stdout, missing_artifact_stderr = (
            run_main_with_fakes(tmp, returncode=0, write_pdf=False)
        )
        assert missing_artifact_code == 2, (missing_artifact_code, missing_artifact_stdout, missing_artifact_stderr)
        assert_blocked_payload(missing_artifact_summary, "target PDF was not created")
        assert not missing_artifact_pdf.exists()

        sys.path.insert(0, str(ROOT / "scripts"))
        import keynote_export  # noqa: PLC0415

        apostrophe_deck = tmp / "reviewer's deck.pptx"
        apostrophe_pdf = tmp / "reviewer's export.pdf"
        captured_command = None

        def fake_run(command, **_kwargs):
            nonlocal captured_command
            captured_command = command
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        old_run = keynote_export.subprocess.run
        try:
            keynote_export.subprocess.run = fake_run
            keynote_export.export_with_keynote(apostrophe_deck, apostrophe_pdf)
        finally:
            keynote_export.subprocess.run = old_run
        assert captured_command is not None
        assert "on run argv" in captured_command[2], captured_command
        assert str(apostrophe_deck.resolve()) == captured_command[-2], captured_command
        assert str(apostrophe_pdf.resolve()) == captured_command[-1], captured_command
        assert str(apostrophe_deck.resolve()) not in captured_command[2], captured_command

    print("keynote_export v1.6 regression: ok")


if __name__ == "__main__":
    main()
