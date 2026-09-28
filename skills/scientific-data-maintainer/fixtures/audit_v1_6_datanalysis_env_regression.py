#!/usr/bin/env python3
"""Regression checks for datanalysis_env.py status hardening."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "datanalysis_env.py"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=SKILL_ROOT, env=env, text=True, capture_output=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_traceback(completed: subprocess.CompletedProcess, label: str) -> None:
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if "Traceback" in combined:
        raise AssertionError(f"{label}: command emitted a traceback")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_datanalysis_env_") as tmp_raw:
        tmp = Path(tmp_raw)

        valid_root = Path.home() / "anaconda3" / "envs" / "datanalysis"
        valid_summary = tmp / "valid" / "status.json"
        env = os.environ.copy()
        if valid_root.exists():
            env["DATAANALYSIS_ENV_ROOT"] = str(valid_root)
        completed = run([sys.executable, str(SCRIPT), "status", "--summary-json", str(valid_summary)], env=env)
        assert completed.returncode == 0, completed.stderr or completed.stdout
        payload = read_json(valid_summary)
        assert payload["found"] is True
        assert "python" in payload["selected_python"].lower()
        results.append({"case": "valid_status", "status": "PASS"})

        invalid_override_summary = tmp / "invalid_override.json"
        env = os.environ.copy()
        env["DATAANALYSIS_PYTHON"] = "/bin/ls"
        completed = run(
            [sys.executable, str(SCRIPT), "status", "--summary-json", str(invalid_override_summary)],
            env=env,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
        payload = read_json(invalid_override_summary)
        assert payload["selected_python"] != "/bin/ls"
        assert payload.get("warnings"), "invalid override should be reported as a warning"
        results.append({"case": "invalid_override_ignored_with_warning", "status": "PASS"})

        summary_dir = tmp / "summary_dir"
        summary_dir.mkdir()
        completed = run([sys.executable, str(SCRIPT), "status", "--summary-json", str(summary_dir)])
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_directory")
        assert "Could not write JSON summary" in ((completed.stdout or "") + (completed.stderr or ""))
        results.append({"case": "summary_json_directory_clean_error", "status": "PASS"})

        parent_file = tmp / "not_a_dir_parent"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        completed = run([sys.executable, str(SCRIPT), "status", "--summary-json", str(parent_file / "out.json")])
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_parent_file")
        assert "Could not write JSON summary" in ((completed.stdout or "") + (completed.stderr or ""))
        results.append({"case": "summary_json_parent_file_clean_error", "status": "PASS"})

        system_python = Path("/usr/bin/python3")
        if system_python.exists():
            fake_home = tmp / "fake_home"
            fake_home.mkdir()
            missing_summary = tmp / "missing_env.json"
            env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}
            completed = run(
                [str(system_python), str(SCRIPT), "status", "--summary-json", str(missing_summary)],
                env=env,
            )
            assert completed.returncode != 0
            assert_no_traceback(completed, "missing_environment")
            payload = read_json(missing_summary)
            assert payload["found"] is False
            assert payload["recovery_hint"]
            results.append({"case": "missing_environment_clean_block", "status": "PASS"})
        else:
            results.append({"case": "missing_environment_clean_block", "status": "NO_APLICA"})

    report = {
        "tool": "audit_v1_6_datanalysis_env_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
