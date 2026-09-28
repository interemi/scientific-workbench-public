#!/usr/bin/env python3
"""Regression checks for skill_surface_audit.py v1.6 hardening."""

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
    "scripts/skill_surface_audit.py",
    "scripts/skill_hygiene_check.py",
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


def registry_text(*, missing_script: bool = False, duplicate: bool = False) -> str:
    script = "scripts/missing.py" if missing_script else "scripts/alpha.py"
    extra = ""
    if duplicate:
        extra = textwrap.dedent(
            """\
              - id: alpha
                label: alpha_duplicate.py
                script: scripts/beta.py
                visible_block: core / routing
                kind: supporting_tool
                support_level: stable
                platform: portable
                requires_datanalysis: false
                preflight_mode: none
                smoke_tier: none
                short_description: Duplicate id.
            """
        )
    return textwrap.dedent(
        f"""\
        entries:
          - id: alpha
            label: alpha.py
            script: {script}
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
        {extra}"""
    )


def make_tree(
    base: Path,
    name: str,
    *,
    missing_marker: bool = False,
    missing_doc_ref: bool = False,
    missing_script: bool = False,
    duplicate: bool = False,
    clean_snapshot: bool = False,
) -> Path:
    root = base / name
    for rel in SCRIPT_RELS:
        source = SKILL_ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (root / "public_surface_registry.yaml").write_text(
        registry_text(missing_script=missing_script, duplicate=duplicate),
        encoding="utf-8",
    )
    (root / "scripts" / "alpha.py").write_text("# alpha\n", encoding="utf-8")
    (root / "scripts" / "beta.py").write_text("# beta\n", encoding="utf-8")
    if duplicate:
        (root / "scripts" / "beta.py").write_text("# beta duplicate fixture\n", encoding="utf-8")
    root.joinpath("references").mkdir(exist_ok=True)
    if missing_doc_ref:
        (root / "references" / "doc.md").write_text("See scripts/not_here.py for details.\n", encoding="utf-8")

    (root / "SKILL.md").write_text("# Skill\ncompact router without generated registry snapshot\n", encoding="utf-8")
    snapshot = root / SNAPSHOT_REL
    if missing_marker:
        snapshot.write_text("# Public Surface\nno generated marker here\n", encoding="utf-8")
    else:
        snapshot.write_text(
            "# Public Surface\n"
            "<!-- BEGIN GENERATED PUBLIC SURFACE SNAPSHOT -->\n"
            "STALE\n"
            "<!-- END GENERATED PUBLIC SURFACE SNAPSHOT -->\n",
            encoding="utf-8",
        )
    for file_name in ("README.txt", "RELEASE-v1.txt"):
        (root / file_name).write_text(
            f"{file_name}\n"
            "BEGIN GENERATED PUBLIC SURFACE SNAPSHOT\n"
            "STALE\n"
            "END GENERATED PUBLIC SURFACE SNAPSHOT\n",
            encoding="utf-8",
        )
    if clean_snapshot:
        completed = run(
            [sys.executable, str(root / "scripts" / "sync_public_surface_docs.py")],
            cwd=root,
        )
        if completed.returncode != 0:
            raise AssertionError(combined_output(completed))
    return root


def command(root: Path, *args: str) -> list[str]:
    return [sys.executable, str(root / "scripts" / "skill_surface_audit.py"), *args]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    args = parser.parse_args(argv)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sda_v16_skill_surface_audit_") as tmp_raw:
        tmp = Path(tmp_raw)

        root = make_tree(tmp, "clean", clean_snapshot=True)
        summary = tmp / "clean.json"
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root)
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(summary)
        assert payload["status"] == "ok"
        assert payload["qa"]["metrics"]["snapshot_drift_count"] == 0
        results.append({"case": "clean_tree_ok", "status": "PASS"})

        root = make_tree(tmp, "drift")
        summary = tmp / "drift.json"
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "drift")
        payload = read_json(summary)
        assert payload["qa"]["metrics"]["snapshot_drift_count"] == 3
        results.append({"case": "snapshot_drift_blocks", "status": "PASS"})

        root = make_tree(tmp, "missing_marker", missing_marker=True)
        summary = tmp / "missing_marker.json"
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_marker")
        payload = read_json(summary)
        reasons = {item["reason"] for item in payload["results"]["snapshot_drift"]}
        assert "missing_markers" in reasons
        results.append({"case": "missing_marker_blocks", "status": "PASS"})

        root = make_tree(tmp, "bad_registry", clean_snapshot=False)
        (root / "public_surface_registry.yaml").write_text("entries: [\n", encoding="utf-8")
        summary = tmp / "bad_registry.json"
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "bad_registry")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"]
        results.append({"case": "invalid_registry_clean_fail", "status": "PASS"})

        root = make_tree(tmp, "missing_script_and_doc", missing_script=True, missing_doc_ref=True, clean_snapshot=False)
        summary = tmp / "missing_script_and_doc.json"
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_script_and_doc")
        payload = read_json(summary)
        findings = payload["qa"]["findings"]
        assert any(item.get("title") == "Registry script is missing" for item in findings)
        assert any(item.get("title") == "Documentation references a missing script" for item in findings)
        results.append({"case": "missing_script_and_doc_blocks", "status": "PASS"})

        root = make_tree(tmp, "hygiene", clean_snapshot=True)
        (root / "scripts" / "__pycache__").mkdir()
        (root / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"cache")
        summary = tmp / "hygiene.json"
        completed = run(command(root, "--summary-json", str(summary)), cwd=root)
        assert completed.returncode == 0, combined_output(completed)
        payload = read_json(summary)
        assert payload["status"] == "warning"
        assert payload["qa"]["metrics"]["hygiene_candidate_count"] >= 1
        results.append({"case": "hygiene_warning_only", "status": "PASS"})

        root = make_tree(tmp, "invalid_root", clean_snapshot=True)
        summary = tmp / "invalid_root.json"
        completed = run(command(root, "--root", str(tmp / "not_a_skill"), "--summary-json", str(summary)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "invalid_root")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        results.append({"case": "invalid_root_clean_fail", "status": "PASS"})

        root = make_tree(tmp, "summary_dir", clean_snapshot=True)
        summary_dir = tmp / "summary_dir_output"
        summary_dir.mkdir()
        completed = run(command(root, "--summary-json", str(summary_dir)), cwd=root)
        assert completed.returncode != 0
        assert_no_traceback(completed, "summary_json_directory")
        payload = stdout_json(completed)
        assert payload["status"] == "fail"
        assert "summary_json_error" in payload["results"]
        results.append({"case": "summary_json_directory_clean_fail", "status": "PASS"})

        root = make_tree(tmp, "missing_yaml", clean_snapshot=False)
        blocker = tmp / "import_blocker"
        blocker.mkdir()
        (blocker / "yaml.py").write_text("raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8")
        summary = tmp / "missing_yaml.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(blocker)
        completed = run(command(root, "--skip-hygiene", "--summary-json", str(summary)), cwd=root, env=env)
        assert completed.returncode != 0
        assert_no_traceback(completed, "missing_yaml")
        payload = read_json(summary)
        assert payload["status"] == "fail"
        assert payload["results"]["error_type"] == "ModuleNotFoundError"
        results.append({"case": "missing_yaml_clean_fail", "status": "PASS"})

    report = {
        "tool": "audit_v1_6_skill_surface_audit_regression",
        "status": "PASS",
        "results": results,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
