"""Stdlib-visible wrappers around representative audit_* regressions.

The main skill regression suite lives in executable scripts under ``scripts/``.
These wrappers make that convention visible to generic Python evaluators without
duplicating the release gates, requiring pytest, without optional backends
into the fast path.
"""

from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MAINTAINER_CHILD = ROOT.parent / "scientific-data-maintainer"

REPRESENTATIVE_REGRESSIONS = [
    "audit_v1_8_app_ready_contract_regression.py",
    "audit_v1_9_artifact_types_regression.py",
    "audit_v1_9_error_contract_regression.py",
    "audit_v2_0_skill_app_contract_regression.py",
]


def maintainer_targets() -> list[Path]:
    matrix_path = ROOT.parent / "scientific-data-maintainer" / "references" / "v2-3-module-ownership-matrix.json"
    if not matrix_path.exists():
        matrix_path = ROOT / "references" / "v2-3-module-ownership-matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    fixture_rel = matrix.get("canonical_fixture")
    if matrix.get("archived") and fixture_rel:
        fixture_path = ROOT.parent / "scientific-data-maintainer" / fixture_rel
        if not fixture_path.exists():
            fixture_path = ROOT / fixture_rel
        matrix = json.loads(fixture_path.read_text(encoding="utf-8"))
    targets = []
    for row in matrix.get("rows", []):
        if row.get("owner_module") != "maintainer":
            continue
        path = row.get("path", "")
        if not path.startswith("scripts/"):
            continue
        script = ROOT / path
        if script.exists() and "archived_regression_runner" in script.read_text(encoding="utf-8"):
            targets.append(script)
    return sorted(targets)


def python_executable() -> str:
    datanalysis = Path(os.environ.get("DATAANALYSIS_PYTHON") or sys.executable)
    return str(datanalysis) if datanalysis.exists() else sys.executable


def write_minimal_fits(path: Path) -> None:
    cards = [
        "SIMPLE  =                    T",
        "BITPIX  =                  -32",
        "NAXIS   =                    2",
        "NAXIS1  =                    4",
        "NAXIS2  =                    3",
        "OBJECT  = 'v2.2 synthetic'",
        "END",
    ]
    header = "".join(map(lambda card: card.ljust(80), cards)).encode("ascii")
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    data = b"".join(map(lambda i: struct.pack(">f", float(i)), range(12)))
    data += b"\0" * ((2880 - len(data) % 2880) % 2880)
    path.write_bytes(header + data)


class AuditRegressionWrappersTest(unittest.TestCase):
    def run_command(self, command: list[str], tmp: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=120,
        )

    def test_representative_audit_regressions_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_audit_wrappers_") as tmp_raw:
            tmp = Path(tmp_raw)
            results = []
            for script_name in REPRESENTATIVE_REGRESSIONS:
                script = SCRIPTS / script_name
                self.assertTrue(script.exists(), f"missing representative regression: {script_name}")
                completed = self.run_command([python_executable(), str(script)], tmp)
                results.append(
                    {
                        "script": script_name,
                        "returncode": completed.returncode,
                        "stdout_tail": completed.stdout[-1200:],
                        "stderr_tail": completed.stderr[-1200:],
                    }
                )
            self.assertEqual(completed.returncode, 0, json.dumps(results[-1], indent=2, ensure_ascii=True))

    def test_v2_3_maintainer_child_has_full_bodies_and_mother_keeps_wrappers(self) -> None:
        self.assertTrue(MAINTAINER_CHILD.exists(), f"missing child skill: {MAINTAINER_CHILD}")
        self.assertTrue((MAINTAINER_CHILD / "SKILL.md").exists(), "child skill is missing SKILL.md")
        targets = maintainer_targets()
        self.assertGreaterEqual(len(targets), 120)
        for wrapper in targets:
            wrapper_text = wrapper.read_text(encoding="utf-8")
            self.assertIn("archived_regression_runner", wrapper_text, f"mother route is not a wrapper: {wrapper.name}")
            child_script = MAINTAINER_CHILD / "scripts" / wrapper.name
            self.assertTrue(child_script.exists(), f"missing child body: {wrapper.name}")
            child_text = child_script.read_text(encoding="utf-8")
            self.assertNotIn("archived_regression_runner", child_text, f"child body is still a wrapper: {wrapper.name}")
        self.assertTrue((MAINTAINER_CHILD / "scripts" / "_internal" / "public_contract.py").exists())

    def test_public_surface_sync_and_audit_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_public_surface_wrappers_") as tmp_raw:
            tmp = Path(tmp_raw)
            commands = [
                [python_executable(), str(SCRIPTS / "sync_public_surface_docs.py"), "--check"],
                [python_executable(), str(SCRIPTS / "skill_surface_audit.py"), "--skip-hygiene"],
            ]
            for command in commands:
                completed = self.run_command(command, tmp)
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"command failed: {' '.join(command)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
                )

    def test_app_ready_run_bundles_for_general_routes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_app_ready_general_") as tmp_raw:
            tmp = Path(tmp_raw)
            csv_path = tmp / "operations_table.csv"
            docs_dir = tmp / "documents"
            docs_dir.mkdir()
            csv_path.write_text("id,value,group\nA,1.5,x\nB,2.0,y\nC,,x\n", encoding="utf-8")
            (docs_dir / "handoff.txt").write_text(
                "Anonymous administrative handoff\nAmount: 1200\nDate: 2026-01-02\n",
                encoding="utf-8",
            )
            original_csv = csv_path.read_bytes()
            commands = [
                [
                    python_executable(),
                    str(SCRIPTS / "profile_table.py"),
                    str(csv_path),
                    "--run-dir",
                    str(tmp / "run_table"),
                ],
                [
                    python_executable(),
                    str(SCRIPTS / "document_intake_workbench.py"),
                    str(docs_dir),
                    "--run-dir",
                    str(tmp / "run_docs"),
                    "--max-files",
                    "5",
                ],
            ]
            for command in commands:
                completed = self.run_command(command, tmp)
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"command failed: {' '.join(command)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
                )
            for run_dir in [tmp / "run_table", tmp / "run_docs"]:
                summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                self.assertIn(summary.get("app_status"), {"PASS", "WARNING", "ok", "warning"})
                self.assertTrue((run_dir / "manifest.json").exists())
                self.assertTrue((run_dir / "next_steps.md").exists())
                self.assertTrue((run_dir / "command.txt").exists())
            self.assertEqual(csv_path.read_bytes(), original_csv)

    def test_fits_inspection_emits_summary_manifest_and_preview(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_fits_wrapper_") as tmp_raw:
            tmp = Path(tmp_raw)
            fits_path = tmp / "simple.fits"
            write_minimal_fits(fits_path)
            original_bytes = fits_path.read_bytes()
            completed = self.run_command(
                [
                    python_executable(),
                    str(SCRIPTS / "inspect_fits.py"),
                    str(fits_path),
                    "--force-simple-fallback",
                    "--summary-json",
                    str(tmp / "summary.json"),
                    "--manifest-json",
                    str(tmp / "manifest.json"),
                    "--preview",
                    str(tmp / "preview.png"),
                ],
                tmp,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"inspect_fits failed\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
            summary = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
            self.assertIn(summary.get("status"), {"ok", "PASS"})
            self.assertTrue((tmp / "manifest.json").exists())
            self.assertTrue((tmp / "preview.png").exists())
            self.assertEqual(fits_path.read_bytes(), original_bytes)

    def test_missing_table_fails_with_parseable_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sda_broken_wrapper_") as tmp_raw:
            tmp = Path(tmp_raw)
            summary_path = tmp / "missing_summary.json"
            completed = self.run_command(
                [
                    python_executable(),
                    str(SCRIPTS / "profile_table.py"),
                    str(tmp / "missing.csv"),
                    "--summary-json",
                    str(summary_path),
                ],
                tmp,
            )
            combined_output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("Traceback", combined_output)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary.get("app_status"), "FAIL")
            self.assertFalse(summary.get("original_modified"))
            self.assertTrue(summary.get("errors"))
            self.assertEqual(summary["errors"][0].get("kind"), "missing_input")


if __name__ == "__main__":
    unittest.main()
