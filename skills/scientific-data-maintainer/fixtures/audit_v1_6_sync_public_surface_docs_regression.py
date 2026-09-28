#!/usr/bin/env python3
"""Regression checks for sync_public_surface_docs.py v1.6 hardening."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_RELS = [
    "scripts/sync_public_surface_docs.py",
    "scripts/_internal/public_contract.py",
    "scripts/_internal/public_surface_registry.py",
    "scripts/_internal/provenance_utils.py",
]
SNAPSHOT_REL = Path("references/public-surface-snapshot.md")


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)


def combined_output(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + "\n" + (completed.stderr or "")


def assert_no_traceback(completed: subprocess.CompletedProcess, label: str) -> None:
    if "Traceback" in combined_output(completed):
        raise AssertionError(f"{label}: command emitted a traceback")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stdout_json(completed: subprocess.CompletedProcess) -> dict:
    return json.loads(completed.stdout)


def make_tree(base: Path, name: str, *, stale: bool = True, missing_marker: bool = False) -> Path:
    root = base / name
    for rel in SCRIPT_RELS:
        if rel == "scripts/sync_public_surface_docs.py":
            canonical = SKILL_ROOT.parent / "scientific-data-maintainer" / "fixtures" / "sync_public_surface_docs.py"
            source = canonical if canonical.exists() else SKILL_ROOT / rel
        else:
            source = SKILL_ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    registry = textwrap.dedent(
        """\
        entries:
          - id: alpha
            label: alpha.py
            script: scripts/alpha.py
            visible_block: core / routing
            kind: golden_path
            support_level: stable
            platform: portable
            requires_datanalysis: false
            preflight_mode: none
            smoke_tier: core
            short_description: Alpha capability.
          - id: beta
            label: beta.py
            script: scripts/beta.py
            visible_block: notebooks + cross-domain
            kind: supporting_tool
            support_level: stable
            platform: portable
            requires_datanalysis: false
            preflight_mode: none
            smoke_tier: none
            short_description: Beta capability.
        """
    )
    (root / "public_surface_registry.yaml").write_text(registry, encoding="utf-8")
    middle = "STALE CONTENT\n" if stale else ""
    (root / "SKILL.md").write_text("# Skill\ncompact router without generated registry snapshot\n", encoding="utf-8")
    snapshot = root / SNAPSHOT_REL
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if missing_marker:
        snapshot.write_text("# Public Surface\nno generated block\n", encoding="utf-8")
    else:
        snapshot.write_text(
            "# Public Surface\n"
            "<!-- BEGIN GENERATED PUBLIC SURFACE SNAPSHOT -->\n"
            f"{middle}"
            "<!-- END GENERATED PUBLIC SURFACE SNAPSHOT -->\n",
            encoding="utf-8",
        )
    for name in ("README.txt", "RELEASE-v1.txt"):
        (root / name).write_text(
            f"{name}\n"
            "BEGIN GENERATED PUBLIC SURFACE SNAPSHOT\n"
            f"{middle}"
            "END GENERATED PUBLIC SURFACE SNAPSHOT\n",
            encoding="utf-8",
        )
    return root


def command(root: Path, *args: str) -> list[str]:
    return [sys.executable, str(root / "scripts" / "sync_public_surface_docs.py"), *args]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_sync_public_surface_") as tmp_raw:
        tmp = Path(tmp_raw)

        root = make_tree(tmp, "write_updates")
        summary = tmp / "write_updates.json"
        completed = run(command(root, "--summary-json", str(summary)), cwd=root)
        assert completed.returncode == 0, combined_output(completed)
        assert_no_traceback(completed, "write_updates")
        payload = read_json(summary)
        assert payload["status"] == "ok"
        assert len(payload["results"]["touched_targets"]) == 3
        assert "STALE CONTENT" not in (root / SNAPSHOT_REL).read_text(encoding="utf-8")
        results.append({"case": "write_updates_stale_docs", "status": "PASS"})

        check_summary = tmp / "check_after_write.json"
        completed = run(command(root, "--check", "--summary-json", str(check_summary)), cwd=root)
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(check_summary)
        assert payload["results"]["drifted_targets"] == []
        assert payload["results"]["touched_targets"] == []
        results.append({"case": "check_after_write_clean", "status": "PASS"})

        write_again_summary = tmp / "write_again_clean.json"
        completed = run(command(root, "--summary-json", str(write_again_summary)), cwd=root)
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(write_again_summary)
        assert payload["results"]["drifted_targets"] == []
        assert payload["results"]["touched_targets"] == []
        results.append({"case": "write_clean_does_not_claim_touched", "status": "PASS"})

        drift_root = make_tree(tmp, "check_drift")
        drift_summary = tmp / "check_drift.json"
        completed = run(command(drift_root, "--check", "--summary-json", str(drift_summary)), cwd=drift_root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "check_drift")
        payload = read_json(drift_summary)
        assert payload["status"] == "fail"
        assert len(payload["results"]["drifted_targets"]) == 3
        assert "STALE CONTENT" in (drift_root / "README.txt").read_text(encoding="utf-8")
        assert "STALE CONTENT" in (drift_root / SNAPSHOT_REL).read_text(encoding="utf-8")
        results.append({"case": "check_drift_blocks_without_writing", "status": "PASS"})

        missing_marker_root = make_tree(tmp, "missing_marker", missing_marker=True)
        missing_summary = tmp / "missing_marker.json"
        completed = run(command(missing_marker_root, "--check", "--summary-json", str(missing_summary)), cwd=missing_marker_root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_marker")
        payload = read_json(missing_summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"] == "RuntimeError"
        results.append({"case": "missing_marker_clean_fail", "status": "PASS"})

        bad_registry_root = make_tree(tmp, "bad_registry")
        (bad_registry_root / "public_surface_registry.yaml").write_text("entries: [\n", encoding="utf-8")
        bad_registry_summary = tmp / "bad_registry.json"
        completed = run(
            command(bad_registry_root, "--check", "--summary-json", str(bad_registry_summary)),
            cwd=bad_registry_root,
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "bad_registry")
        payload = read_json(bad_registry_summary)
        assert payload["status"] == "fail"
        results.append({"case": "invalid_registry_clean_fail", "status": "PASS"})

        missing_yaml_root = make_tree(tmp, "missing_yaml")
        blocker = tmp / "import_blocker"
        blocker.mkdir()
        (blocker / "yaml.py").write_text("raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8")
        missing_yaml_summary = tmp / "missing_yaml.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(blocker)
        completed = run(
            command(missing_yaml_root, "--check", "--summary-json", str(missing_yaml_summary)),
            cwd=missing_yaml_root,
            env=env,
        )
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_yaml")
        payload = read_json(missing_yaml_summary)
        assert payload["status"] == "fail"
        assert payload["results"]["drifted_targets"]
        assert "ModuleNotFoundError" not in combined_output(completed)
        results.append({"case": "missing_yaml_fallback_blocks_drift_without_traceback", "status": "PASS"})

        summary_dir_root = make_tree(tmp, "summary_dir")
        summary_dir = tmp / "summary_dir_output"
        summary_dir.mkdir()
        completed = run(command(summary_dir_root, "--summary-json", str(summary_dir)), cwd=summary_dir_root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_directory")
        payload = stdout_json(completed)
        assert payload["status"] == "fail"
        assert "summary_json_error" in payload["results"]
        results.append({"case": "summary_json_directory_clean_fail", "status": "PASS"})

    report = {
        "tool": "audit_v1_6_sync_public_surface_docs_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
