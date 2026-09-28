#!/usr/bin/env python3
"""v1.7 real-world non-astro regression for profile_table.py."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "profile_table.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_ops_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ["ticket_id", "opened_at", "closed_at", "channel", "team", "priority", "region", "first_response_min", "resolution_hours", "sla_breached", "customer_score", "revenue_impact_eur", "notes"],
        ["T-1001", "2026-04-01 08:15", "2026-04-01 13:20", "email", "support", "P2", "EU", "35", "5.08", "false", "4.7", "1200", "routine onboarding issue"],
        ["T-1002", "2026-04-02 10:05", "2026-04-04 09:13", "chat", "billing", "P1", "US", "240", "47.13", "true", "", "inf", "bad imported finance placeholder"],
        ["T-1003", "2026-04-03 11:00", "2026-04-03 16:45", "phone", "ops", "P3", "LATAM", "18", "5.75", "false", "4.2", "350", "normal operational record"],
        ["T-1004", "2026-04-04 12:20", "2026-04-05 09:50", "email", "support", "P2", "EU", "55", "21.5", "false", "3.9", "780", "handoff required"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def run_profile(input_csv: Path, summary: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            str(input_csv),
            "--head",
            "4",
            "--max-columns",
            "13",
            "--summary-json",
            str(summary),
            "--manifest-json",
            str(manifest),
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_v1_7_profile_real_world_") as tmp_name:
        tmp = Path(tmp_name)
        input_csv = tmp / "inputs" / "ops_support_anon.csv"
        summary = tmp / "outputs" / "profile_summary.json"
        manifest = tmp / "outputs" / "profile_manifest.json"
        write_ops_csv(input_csv)
        before_hash = sha256(input_csv)
        proc = run_profile(input_csv, summary, manifest)
        after_hash = sha256(input_csv)

        if proc.returncode != 0:
            fail(proc.stderr or proc.stdout)
        if "Traceback" in proc.stdout or "Traceback" in proc.stderr:
            fail("profile_table emitted traceback")
        if before_hash != after_hash:
            fail("profile_table modified the input CSV")
        if not summary.exists() or not manifest.exists():
            fail("summary and manifest should be written")

        payload = json.loads(summary.read_text(encoding="utf-8"))
        if payload.get("tool") != "profile_table":
            fail(f"unexpected tool id: {payload.get('tool')}")
        if payload.get("status") != "warning":
            fail(f"expected warning because one value is infinite, got {payload.get('status')}")
        results = payload.get("results", {})
        qa = payload.get("qa", {})
        if results.get("rows") != 4 or results.get("columns") != 13:
            fail(f"unexpected table shape: {results.get('rows')} x {results.get('columns')}")
        if qa.get("metrics", {}).get("infinite_value_count") != 1:
            fail(f"expected exactly one infinite value, got {qa.get('metrics')}")
        findings = " ".join(qa.get("findings", []))
        if "infinite numeric values" not in findings:
            fail(f"warning should name infinite numeric values: {findings}")

    print(
        json.dumps(
            {
                "status": "ok",
                "capability": "profile_table.py",
                "pattern": "real_world_tabular_intake",
                "rows": 4,
                "columns": 13,
                "infinite_value_count": 1,
                "input_hash_preserved": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
