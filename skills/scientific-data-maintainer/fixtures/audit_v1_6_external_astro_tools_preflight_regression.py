#!/usr/bin/env python3
"""Narrow v1.6 regression checks for external_astro_tools_preflight.py."""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "external_astro_tools_preflight.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def make_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_preflight(args: list[str], summary: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    if summary is not None:
        command.extend(["--summary-json", str(summary)])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, env=env)


def assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="external-astro-preflight-v1-6-") as tmp_raw:
        tmp = Path(tmp_raw)
        tools = tmp / "tool dir with spaces"
        java = make_executable(tools / "fake java.py", "#!/usr/bin/env python3\nimport sys\nprint('fake java 17')\nsys.exit(0)\n")
        stilts = make_executable(tools / "fake STILTS.py", "#!/usr/bin/env python3\nimport sys\nprint('fake stilts')\nsys.exit(0)\n")
        apt = make_executable(tools / "fake APT.csh", "#!/usr/bin/env python3\nimport sys\nprint('fake APT help')\nsys.exit(0)\n")
        prefs = make_text(tools / "APT prefs.pref", "fake preferences\n")

        explicit_summary = tmp / "explicit spaces.json"
        explicit = run_preflight(
            [
                "--java-command",
                str(java),
                "--stilts-command",
                str(stilts),
                "--apt-command",
                str(apt),
                "--apt-preferences",
                str(prefs),
                "--probe",
            ],
            explicit_summary,
        )
        assert explicit.returncode == 0, explicit.stderr
        assert_no_traceback(explicit)
        payload = read_json(explicit_summary)
        assert payload["status"] == "ok", payload
        assert payload["results"]["capabilities"]["stilts_ready"], payload
        assert payload["results"]["capabilities"]["apt_batch_ready"], payload
        assert payload["results"]["probes"]["java"]["returncode"] == 0, payload

        env_summary = tmp / "env spaces.json"
        env = os.environ.copy()
        env.update(
            {
                "JAVA_COMMAND": shlex.quote(str(java)),
                "STILTS_COMMAND": shlex.quote(str(stilts)),
                "APT_COMMAND": shlex.quote(str(apt)),
                "APT_PREFERENCES": str(prefs),
            }
        )
        env_result = run_preflight(["--probe"], env_summary, env=env)
        assert env_result.returncode == 0, env_result.stderr
        assert_no_traceback(env_result)
        assert read_json(env_summary)["status"] == "ok"

        pref_dir = tmp / "APT.pref"
        pref_dir.mkdir()
        pref_dir_summary = tmp / "pref dir.json"
        pref_dir_result = run_preflight(
            [
                "--java-command",
                str(java),
                "--apt-command",
                str(apt),
                "--apt-preferences",
                str(pref_dir),
                "--require-apt",
            ],
            pref_dir_summary,
        )
        assert pref_dir_result.returncode == 2, pref_dir_result.stdout
        assert_no_traceback(pref_dir_result)
        pref_payload = read_json(pref_dir_summary)
        assert pref_payload["status"] == "blocked", pref_payload
        assert not pref_payload["results"]["apt_preferences"]["is_file"], pref_payload

        missing_summary = tmp / "missing stilts.json"
        missing = run_preflight(["--stilts-command", str(tmp / "missing stilts"), "--require-stilts", "--probe"], missing_summary)
        assert missing.returncode == 2, missing.stderr
        assert_no_traceback(missing)
        assert read_json(missing_summary)["status"] == "blocked"

        nonexec_java = make_text(tmp / "java not executable.sh", "#!/bin/sh\necho should-not-run\n")
        nonexec_summary = tmp / "nonexec java.json"
        nonexec = run_preflight(["--java-command", str(nonexec_java), "--stilts-command", str(stilts), "--probe"], nonexec_summary)
        assert nonexec.returncode == 2, nonexec.stderr
        assert_no_traceback(nonexec)
        nonexec_payload = read_json(nonexec_summary)
        assert nonexec_payload["status"] == "blocked", nonexec_payload
        assert not nonexec_payload["results"]["java"]["found"], nonexec_payload

        parent_file = tmp / "summary parent is file"
        parent_file.write_text("not a directory\n", encoding="utf-8")
        bad_summary = parent_file / "summary.json"
        bad_summary_result = run_preflight(["--summary-json", str(bad_summary)])
        assert bad_summary_result.returncode == 2, bad_summary_result.stderr
        assert_no_traceback(bad_summary_result)
        assert "Could not write summary JSON" in bad_summary_result.stderr
        assert not bad_summary.exists()

    print("external_astro_tools_preflight v1.6 regression: ok")


if __name__ == "__main__":
    main()
