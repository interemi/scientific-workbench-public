#!/usr/bin/env python3
"""Validate v2.0 Phase 7 job history, previews, recovery, and support."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = Path(__file__).resolve().parents[3]
TMP = ROOT / "tmp" / "v2_0_phase7_jobs_previews"
SUMMARY = TMP / "phase7_jobs_previews_summary.json"
REFERENCE = ROOT / "references" / "v2-0-jobs-previews-recovery.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_terms(path: Path, terms: list[str]) -> None:
    require(path.exists(), f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    for term in terms:
        require(term in text, f"{path.name} missing required term: {term}")


def run(command: list[str], cwd: Path, timeout: int = 240) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    require(
        completed.returncode == 0,
        f"command failed ({completed.returncode}): {' '.join(command)}\n"
        f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}",
    )
    require("Traceback" not in completed.stdout + completed.stderr, "command emitted traceback")
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
    }


def validate_sources() -> None:
    require_terms(
        APP / "Sources/ScientificWorkbench/Models/RunModels.swift",
        [
            "struct JobStructuredError",
            "struct JobNextAction",
            "contractVersion",
            "originalModified",
            "previewArtifactTypes",
            "let failureStatuses: Set<String>",
            '"ROTO"',
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Services/JobRunBundleService.swift",
        [
            "summary.json",
            "manifest.json",
            "stdout.txt",
            "stderr.txt",
            "command.txt",
            "next_steps.md",
            "func hydrate",
            "parseNextActions",
            "maximumSidecarBytes",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Services/ArtifactPreviewService.swift",
        [
            "case pdf",
            "case table",
            "case markdown",
            "case notebook",
            "case log",
            "maximumBytes",
            "maximumLines",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Views/JobsView.swift",
        [
            "Retry Job",
            "Run Remaining",
            "Refresh Bundle",
            "Support Bundle",
            "Reveal Run Folder",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Views/ResultsView.swift",
        [
            "selectPreferredArtifact",
            "ArtifactPreviewService",
            "Reveal",
            "Support Bundle",
            "JobFindingsView",
        ],
    )
    require_terms(
        APP / "Sources/ScientificWorkbench/Services/SupportBundleService.swift",
        [
            "func exportJob",
            "job_state.json",
            "copySafeRunSidecars",
            "Heavy or personal artifacts remain",
        ],
    )
    require_terms(
        APP / "Tests/ScientificWorkbenchTests/JobRunBundleAndPreviewTests.swift",
        [
            "structuredFailStatusWinsOverZeroExitCode",
            "runBundleHydratesJobMetadataAndCanonicalArtifacts",
            "runBundleRestoresRedactedSidecarsAndNextStepsAfterReload",
            "persistedInterruptedJobRecoversRunBundleArtifacts",
            "artifactPreviewCoversImagePDFTableMarkdownNotebookAndLogs",
            "jobSupportBundleCopiesOnlyRedactedSafeSidecars",
        ],
    )


def write_fixture_matrix() -> Path:
    fixtures = TMP / "fixture_bundle"
    for directory in ["artifacts", "previews", "reports", "tables", "logs"]:
        (fixtures / directory).mkdir(parents=True, exist_ok=True)
    (fixtures / "summary.json").write_text(
        json.dumps(
            {
                "contract_version": "2.0",
                "tool": "phase7_fixture",
                "status": "WARNING",
                "app_status": "WARNING",
                "warnings": ["Synthetic warning for preview evidence."],
                "errors": [],
                "next_actions": [{"label": "Inspect previews.", "kind": "inspect_artifact"}],
                "original_modified": False,
                "app_hints": {
                    "short_summary": "Synthetic Phase 7 run bundle.",
                    "severity": "warning",
                    "preview_artifact_types": [
                        "preview_png",
                        "preview_pdf",
                        "table_csv",
                        "report_md",
                        "notebook_ipynb",
                        "log_txt",
                    ],
                    "tags": ["phase7", "preview"],
                },
                "typed_artifacts": [
                    {"path": "tables/sample.csv", "artifact_type": "table_csv"},
                    {"path": "reports/report.md", "artifact_type": "report_md"},
                    {"path": "artifacts/notebook.ipynb", "artifact_type": "notebook_ipynb"},
                    {"path": "logs/stdout.log", "artifact_type": "log_txt"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (fixtures / "manifest.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "stdout.txt").write_text("synthetic stdout\n", encoding="utf-8")
    (fixtures / "stderr.txt").write_text("", encoding="utf-8")
    (fixtures / "command.txt").write_text("python synthetic.py\n", encoding="utf-8")
    (fixtures / "next_steps.md").write_text("# Next steps\n\n- Inspect previews.\n", encoding="utf-8")
    (fixtures / "tables/sample.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (fixtures / "reports/report.md").write_text("# Report\n\nSynthetic preview evidence.\n", encoding="utf-8")
    (fixtures / "artifacts/notebook.ipynb").write_text(
        '{"cells":[{"cell_type":"markdown","source":["# Notebook\\n"]}],"metadata":{},"nbformat":4,"nbformat_minor":5}\n',
        encoding="utf-8",
    )
    (fixtures / "logs/stdout.log").write_text("bounded log preview\n", encoding="utf-8")
    return fixtures


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    validate_sources()
    require_terms(
        REFERENCE,
        [
            "FAIL / ROTO, including exit 0",
            "Persisted jobs store",
            "PDF",
            "Notebook",
            "Run Remaining",
            "Support Bundle",
            "Original inputs remain read-only",
        ],
    )
    fixture_bundle = write_fixture_matrix()
    build = run(["swift", "build"], cwd=APP)
    focused_tests = run(
        [
            str(APP / "script" / "run_swift_tests.sh"),
            "--filter",
            "runBundle|artifactPreview|persistedInterruptedJob|jobSupportBundle|structuredFailStatus",
        ],
        cwd=APP,
        timeout=360,
    )
    payload = {
        "tool": "audit_v2_0_phase7_jobs_previews_regression",
        "status": "PASS",
        "app_root": str(APP),
        "fixture_bundle": str(fixture_bundle),
        "preview_types": ["PNG", "PDF", "CSV/TSV", "Markdown", "notebook", "JSON", "logs"],
        "states": ["queued", "running", "succeeded", "blocked", "failed", "cancelled", "timeout"],
        "original_modified": False,
        "sidecar_rehydration": "redacted",
        "next_steps_fallback": True,
        "checks": [build, focused_tests],
        "warnings": [],
    }
    SUMMARY.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
