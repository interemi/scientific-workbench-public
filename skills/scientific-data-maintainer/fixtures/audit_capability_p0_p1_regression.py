#!/usr/bin/env python3
"""Regression gate for P0/P1 capability-audit hardening."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_apt_unidentified_tbl_blocks_cleanly(tmp: Path) -> None:
    bad_tbl = tmp / "bad_apt.tbl"
    bad_tbl.write_text("", encoding="utf-8")
    out_csv = tmp / "bad_apt.csv"
    summary = tmp / "bad_apt_summary.json"
    result = run(
        [
            sys.executable,
            str(SCRIPTS / "apt_workbench.py"),
            "parse-results",
            str(bad_tbl),
            str(out_csv),
            "--summary-json",
            str(summary),
        ]
    )
    require(result.returncode == 2, f"bad APT table should block, got {result.returncode}\n{result.stdout}\n{result.stderr}")
    require("Traceback" not in result.stderr, "APT parse must not leak raw traceback on known format errors")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    require(payload["status"] == "blocked", "APT parse should emit blocked JSON")
    suggestions = payload["results"].get("suggestions") or []
    require(any("--input-format" in item for item in suggestions), "APT parse should suggest --input-format")
    require(not out_csv.exists(), "blocked APT parse should not create output CSV")


def check_validate_samples_no_external_numbers_by_default(tmp: Path) -> None:
    import importlib.util

    module_path = SCRIPTS / "validate_skill_samples.py"
    spec = importlib.util.spec_from_file_location("validate_skill_samples_probe", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    root = tmp / "sample_root"
    root.mkdir()
    (root / "sample.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    samples = module.select_samples([str(root)], max_per_ext=1)
    require(".numbers" not in samples or not samples[".numbers"], "explicit roots contain no .numbers sample")

    # The default main path must not call supplement_numbers_samples. The opt-in
    # behavior is intentionally left available for release machines that want it.
    source = module_path.read_text(encoding="utf-8")
    require("--include-system-iwork-samples" in source, "opt-in flag should be visible")
    require("if args.include_system_iwork_samples:" in source, "system .numbers sampling should be gated by opt-in flag")


def check_presentation_findings_are_compacted() -> None:
    import importlib.util

    module_path = SCRIPTS / "presentation_workbench.py"
    spec = importlib.util.spec_from_file_location("presentation_workbench_probe", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    visual_audit = {
        "deck_findings": [{"severity": "medium", "title": "Deck issue", "detail": "Deck-level issue."}],
        "slide_qa": [
            {
                "index": index,
                "title": f"Slide {index}",
                "status": "warning",
                "findings": [{"severity": "high" if index % 2 else "low", "title": "Repeated issue", "detail": "Synthetic issue."}],
            }
            for index in range(1, 30)
        ],
    }
    summary = module._summarize_visual_findings(visual_audit, limit=5)
    require(summary["finding_count"] == 30, "summary should count all findings")
    require(summary["truncated"] is True, "summary should declare truncation")
    require(len(summary["top_findings"]) == 5, "top_findings should be compacted to limit")
    require(summary["severity_counts"]["high"] > 0, "severity counts should include high findings")

    qa = module.build_presentation_qa({"exists": True, "inspection": {}, "visual_audit": visual_audit})
    require(qa["metrics"]["finding_count"] == 30, "QA metrics should count all findings")
    require(qa["metrics"]["findings_truncated"] is True, "QA should expose truncation")
    require(len(qa["findings"]) == module.MAX_QA_FINDINGS, "QA findings should be capped")
    require(qa["finding_summary"]["finding_count"] == 30, "QA should carry full finding summary")


def main() -> None:
    ensure_datanalysis_runtime("audit_capability_p0_p1_regression", strict=False)
    with tempfile.TemporaryDirectory(prefix="sda_capability_p0_p1_") as tmp_raw:
        tmp = Path(tmp_raw)
        check_apt_unidentified_tbl_blocks_cleanly(tmp)
        print("PASS check_apt_unidentified_tbl_blocks_cleanly")
        check_validate_samples_no_external_numbers_by_default(tmp)
        print("PASS check_validate_samples_no_external_numbers_by_default")
        check_presentation_findings_are_compacted()
        print("PASS check_presentation_findings_are_compacted")
    print("All P0/P1 capability hardening regressions passed.")


if __name__ == "__main__":
    main()
