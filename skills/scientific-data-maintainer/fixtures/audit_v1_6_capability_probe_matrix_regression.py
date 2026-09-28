#!/usr/bin/env python3
"""Regression checks for capability_probe_matrix.py v1.6 hardening."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "capability_probe_matrix.py"
DATANALYSIS_PYTHON = Path.home() / "anaconda3" / "envs" / "datanalysis" / "bin" / "python"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=SKILL_ROOT, env=env, text=True, capture_output=True)


def combined_output(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + "\n" + (completed.stderr or "")


def assert_no_traceback(completed: subprocess.CompletedProcess, label: str) -> None:
    if "Traceback" in combined_output(completed):
        raise AssertionError(f"{label}: command emitted a traceback")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stdout_json(completed: subprocess.CompletedProcess) -> dict:
    return json.loads(completed.stdout)


def write_registry(path: Path, *, entry_id: str = "capability_probe_matrix", maintainer: bool = True) -> None:
    kind = "maintainer_only" if maintainer else "supporting_tool"
    path.write_text(
        "\n".join(
            [
                "entries:",
                f"  - id: {entry_id}",
                "    label: capability_probe_matrix.py",
                "    script: scripts/capability_probe_matrix.py",
                "    visible_block: core / routing",
                f"    kind: {kind}",
                "    support_level: stable",
                "    platform: portable",
                "    requires_datanalysis: true",
                "    preflight_mode: none",
                "    smoke_tier: none",
                "    short_description: Probe matrix fixture.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def matrix_cmd(python: Path | str, output_dir: Path, registry: Path, summary: Path, *extra: str) -> list[str]:
    return [
        str(python),
        str(SCRIPT),
        "--output-dir",
        str(output_dir),
        "--registry",
        str(registry),
        "--summary-json",
        str(summary),
        *extra,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_capability_probe_matrix_") as tmp_raw:
        tmp = Path(tmp_raw)

        registry = tmp / "maintainer_registry.yaml"
        write_registry(registry)
        summary = tmp / "maintainer_help.json"
        completed = run(
            matrix_cmd(
                DATANALYSIS_PYTHON,
                tmp / "maintainer_help_out",
                registry,
                summary,
                "--include-maintainer-help",
            )
        )
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(summary)
        assert payload["status"] == "ok"
        assert payload["results"]["counts_by_probe_status"].get("PASS") == 1
        results.append({"case": "maintainer_help_registry_ok", "status": "PASS"})

        system_python = Path("/usr/bin/python3")
        if system_python.exists():
            summary = tmp / "base_python_rerun.json"
            completed = run(
                matrix_cmd(
                    system_python,
                    tmp / "base_python_rerun_out",
                    registry,
                    summary,
                    "--include-maintainer-help",
                )
            )
            assert completed.returncode == 0, combined_output(completed)
            assert "Re-running capability_probe_matrix inside datanalysis" in (completed.stderr or "")
            payload = read_json(summary)
            assert payload["status"] == "ok"
            results.append({"case": "base_python_reruns_to_datanalysis", "status": "PASS"})
        else:
            results.append({"case": "base_python_reruns_to_datanalysis", "status": "NO_APLICA"})

        no_probe_registry = tmp / "no_probe_registry.yaml"
        write_registry(no_probe_registry, entry_id="unmapped_probe_fixture", maintainer=False)
        summary = tmp / "no_probe.json"
        completed = run(matrix_cmd(DATANALYSIS_PYTHON, tmp / "no_probe_out", no_probe_registry, summary))
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(summary)
        assert payload["status"] == "warning"
        assert payload["results"]["counts_by_probe_status"].get("NO_PROBE") == 1
        results.append({"case": "unmapped_smoke_none_warns_no_probe", "status": "PASS"})

        bad_registry = tmp / "bad_registry.yaml"
        bad_registry.write_text("entries: [\n", encoding="utf-8")
        summary = tmp / "bad_registry.json"
        completed = run(matrix_cmd(DATANALYSIS_PYTHON, tmp / "bad_registry_out", bad_registry, summary))
        assert completed.returncode != 0
        assert_no_traceback(completed, "bad_registry")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"]
        results.append({"case": "invalid_registry_clean_fail", "status": "PASS"})

        output_file = tmp / "output_is_file"
        output_file.write_text("not a directory\n", encoding="utf-8")
        summary = tmp / "output_file.json"
        completed = run(matrix_cmd(DATANALYSIS_PYTHON, output_file, registry, summary, "--include-maintainer-help"))
        assert completed.returncode != 0
        assert_no_traceback(completed, "output_file")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"] == "FileExistsError"
        results.append({"case": "output_dir_file_clean_fail", "status": "PASS"})

        summary_dir = tmp / "summary_dir"
        summary_dir.mkdir()
        completed = run(
            matrix_cmd(DATANALYSIS_PYTHON, tmp / "summary_dir_out", registry, summary_dir, "--include-maintainer-help")
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_dir")
        payload = stdout_json(completed)
        assert payload["status"] == "fail"
        assert "summary_json_error" in payload["results"]
        results.append({"case": "summary_json_directory_clean_fail", "status": "PASS"})

        blocker = tmp / "import_blocker"
        blocker.mkdir()
        (blocker / "yaml.py").write_text("raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8")
        summary = tmp / "missing_yaml.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(blocker)
        completed = run(
            matrix_cmd(DATANALYSIS_PYTHON, tmp / "missing_yaml_out", registry, summary, "--include-maintainer-help"),
            env=env,
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_yaml")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"] == "ModuleNotFoundError"
        results.append({"case": "missing_yaml_clean_fail", "status": "PASS"})

    report = {
        "tool": "audit_v1_6_capability_probe_matrix_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
