#!/usr/bin/env python3
"""Narrow v1.6 regression checks for external_astro_tools_local_validation.py."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "external_astro_tools_local_validation.py"


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


def fake_java(path: Path) -> Path:
    return make_executable(path, "#!/usr/bin/env python3\nimport sys\nprint('fake java 17')\nsys.exit(0)\n")


def fake_stilts(path: Path, *, write_output: bool = True) -> Path:
    if write_output:
        body = """#!/usr/bin/env python3
import pathlib
import sys

out = None
for arg in sys.argv[1:]:
    if arg.startswith("out="):
        out = arg.split("=", 1)[1]
if out:
    pathlib.Path(out).write_text("id,ra,dec\\nA,10.0,20.0\\n", encoding="utf-8")
print("fake stilts ok")
sys.exit(0)
"""
    else:
        body = """#!/usr/bin/env python3
import sys

print("fake stilts claimed success without output")
sys.exit(0)
"""
    return make_executable(path, body)


def fake_apt(path: Path) -> Path:
    body = """#!/usr/bin/env python3
import pathlib
import sys

if "-h" in sys.argv:
    print("fake APT help")
    sys.exit(0)
out = None
for index, arg in enumerate(sys.argv[1:], start=1):
    if arg == "-o" and index + 1 < len(sys.argv):
        out = sys.argv[index + 1]
if out:
    pathlib.Path(out).write_text(
        "Number Image X Y SourceIntensity\\n1 image.fits 10 20 123.4\\n",
        encoding="utf-8",
    )
print("fake APT batch ok")
sys.exit(0)
"""
    return make_executable(path, body)


def run_local_validation(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True, check=False)


def assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="external-astro-local-validation-v1-6-") as tmp_raw:
        tmp = Path(tmp_raw)
        tools = tmp / "tool dir with spaces"
        java = fake_java(tools / "fake java.py")
        stilts = fake_stilts(tools / "fake STILTS.py")
        apt = fake_apt(tools / "fake APT.csh")
        prefs = make_text(tools / "APT prefs.pref", "fake preferences\n")

        happy_dir = tmp / "happy out"
        happy_summary = tmp / "happy summary.json"
        happy = run_local_validation(
            [
                "--output-dir",
                str(happy_dir),
                "--summary-json",
                str(happy_summary),
                "--java-command",
                str(java),
                "--stilts-command",
                str(stilts),
                "--apt-command",
                str(apt),
                "--apt-preferences",
                str(prefs),
            ]
        )
        assert happy.returncode == 0, {
            "stdout": happy.stdout,
            "stderr": happy.stderr,
            "summary": read_json(happy_summary) if happy_summary.exists() else None,
        }
        assert_no_traceback(happy)
        happy_payload = read_json(happy_summary)
        assert happy_payload["status"] == "ok", happy_payload
        validations = {item["id"]: item for item in happy_payload["results"]["validations"]}
        assert validations["stilts_real_crossmatch"]["status"] == "PASS", validations
        assert validations["apt_batch_validation"]["status"] == "PASS", validations

        real_batch_dir = tmp / "real batch out"
        real_batch_summary = tmp / "real batch summary.json"
        real_batch = run_local_validation(
            [
                "--output-dir",
                str(real_batch_dir),
                "--summary-json",
                str(real_batch_summary),
                "--java-command",
                str(java),
                "--stilts-command",
                str(stilts),
                "--apt-command",
                str(apt),
                "--apt-preferences",
                str(prefs),
                "--tool",
                "apt",
                "--include-apt-batch",
            ]
        )
        assert real_batch.returncode == 0, real_batch.stderr
        assert_no_traceback(real_batch)
        real_batch_payload = read_json(real_batch_summary)
        batch_validation = real_batch_payload["results"]["validations"][-1]
        assert real_batch_payload["status"] == "ok", real_batch_payload
        assert batch_validation["mode"] == "real_batch", batch_validation
        assert Path(batch_validation["output_table"]).exists(), batch_validation

        stale_dir = tmp / "stale out"
        stale_dir.mkdir()
        (stale_dir / "stilts_matched.csv").write_text("stale\n", encoding="utf-8")
        (stale_dir / "stilts_crossmatch_manifest.json").write_text('{"stale": true}\n', encoding="utf-8")
        bad_stilts = fake_stilts(tools / "fake STILTS no output.py", write_output=False)
        stale_summary = tmp / "stale summary.json"
        stale = run_local_validation(
            [
                "--output-dir",
                str(stale_dir),
                "--summary-json",
                str(stale_summary),
                "--java-command",
                str(java),
                "--stilts-command",
                str(bad_stilts),
                "--tool",
                "stilts",
                "--require-stilts",
            ]
        )
        assert stale.returncode == 1, stale.stderr
        assert_no_traceback(stale)
        stale_payload = read_json(stale_summary)
        stale_validation = stale_payload["results"]["validations"][-1]
        assert stale_payload["status"] == "fail", stale_payload
        assert stale_validation["status"] == "FAIL", stale_validation
        assert stale_validation["output_table"] is None, stale_validation

        output_file = tmp / "output-dir-is-file"
        output_file.write_text("not a directory\n", encoding="utf-8")
        blocked_summary = tmp / "blocked summary.json"
        blocked = run_local_validation(["--output-dir", str(output_file), "--summary-json", str(blocked_summary)])
        assert blocked.returncode == 2, blocked.stderr
        assert_no_traceback(blocked)
        assert read_json(blocked_summary)["status"] == "blocked"

        bad_parent = tmp / "summary-parent-file"
        bad_parent.write_text("not a directory\n", encoding="utf-8")
        bad_summary = bad_parent / "summary.json"
        bad_summary_result = run_local_validation(["--summary-json", str(bad_summary)])
        assert bad_summary_result.returncode == 2, bad_summary_result.stderr
        assert_no_traceback(bad_summary_result)
        assert "Could not write summary JSON" in bad_summary_result.stderr

        bad_timeout_summary = tmp / "bad timeout.json"
        bad_timeout = run_local_validation(["--timeout-sec", "0", "--summary-json", str(bad_timeout_summary)])
        assert bad_timeout.returncode == 2, bad_timeout.stderr
        assert_no_traceback(bad_timeout)
        assert read_json(bad_timeout_summary)["status"] == "blocked"

    print("external_astro_tools_local_validation v1.6 regression: ok")


if __name__ == "__main__":
    main()
