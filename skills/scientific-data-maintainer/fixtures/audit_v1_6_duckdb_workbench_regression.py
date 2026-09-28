#!/usr/bin/env python3
"""v1.6 regression checks for duckdb_workbench.py edge behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TOOL = SCRIPT_DIR / "duckdb_workbench.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def run_tool(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def read_json_strict(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(
        text,
        parse_constant=lambda token: fail(f"non-strict JSON constant emitted: {token}"),
    )


def require_envelope(path: Path, status: str) -> dict:
    payload = read_json_strict(path)
    if payload.get("tool") != "duckdb_workbench":
        fail(f"unexpected tool id: {payload.get('tool')}")
    if payload.get("status") != status:
        fail(f"expected status {status}, got {payload.get('status')}")
    qa = payload.get("qa")
    allowed_qa_statuses = {status}
    if status == "ok":
        allowed_qa_statuses.add("not_applicable")
    if not isinstance(qa, dict) or qa.get("status") not in allowed_qa_statuses:
        fail(f"expected qa.status {status}, got {qa}")
    return payload


def write_fixtures(tmp: Path) -> dict[str, Path]:
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - environment diagnostic
        raise AssertionError(f"pandas unavailable for duckdb regression fixture: {exc}") from exc

    tmp.mkdir(parents=True, exist_ok=True)
    basic = tmp / "basic.csv"
    basic.write_text("id,category,value\n1,A,10.5\n2,A,11.0\n3,B,20.25\n", encoding="utf-8")
    obs = tmp / "observations.csv"
    obs.write_text(
        "id,object,flux,date\n"
        "1,alpha,100.5,2026-01-01\n"
        "2,beta,,2026-01-02\n"
        "3,gamma,inf,2026-01-03\n"
        "4,delta,-5,2026-01-04\n",
        encoding="utf-8",
    )
    labels = tmp / "labels.jsonl"
    labels.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"id": 1, "quality": "good"},
                {"id": 2, "quality": "missing_flux"},
                {"id": 3, "quality": "bad_inf"},
                {"id": 4, "quality": "negative"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    parquet = tmp / "calibration.parquet"
    pd.DataFrame({"id": [1, 2, 3, 4], "gain": [1.2, 1.2, 1.3, 1.4]}).to_parquet(parquet, index=False)
    reserved = tmp / "table.csv"
    reserved.write_text("id,group,value\n1,x,1\n2,x,2\n", encoding="utf-8")
    return {"basic": basic, "obs": obs, "labels": labels, "parquet": parquet, "reserved": reserved}


def check_happy_csv(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "happy" / "summary.json"
    output = tmp / "happy" / "result.csv"
    manifest = tmp / "happy" / "manifest.json"
    proc = run_tool(
        [
            str(fixtures["basic"]),
            "--sql",
            "SELECT category, count(*) AS n, avg(value) AS avg_value FROM source0 GROUP BY category ORDER BY category",
            "--output",
            str(output),
            "--summary-json",
            str(summary),
            "--manifest-json",
            str(manifest),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["result_rows"] != 2:
        fail("expected grouped CSV query to produce two rows")
    if "source0" not in payload["results"]["aliases"]:
        fail("source0 alias missing")
    if not output.exists() or not manifest.exists():
        fail("query output and manifest should be written")


def check_mixed_sources_and_json_safety(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "mixed" / "summary.json"
    output = tmp / "mixed" / "joined.json"
    proc = run_tool(
        [
            str(fixtures["obs"]),
            str(fixtures["labels"]),
            str(fixtures["parquet"]),
            "--sql",
            "SELECT source0.id, object, flux, quality, gain FROM source0 JOIN source1 USING(id) JOIN source2 USING(id) ORDER BY source0.id;",
            "--output",
            str(output),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode != 0:
        fail(proc.stderr or proc.stdout)
    payload = require_envelope(summary, "ok")
    if payload["results"]["result_rows"] != 4:
        fail("expected four joined rows")
    read_json_strict(output)


def check_reserved_alias_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "reserved" / "summary.json"
    proc = run_tool([str(fixtures["reserved"]), "--sql", "SELECT * FROM table LIMIT 1", "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("reserved alias query should return non-zero")
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        fail("reserved alias query emitted traceback")
    payload = require_envelope(summary, "blocked")
    if "source0" not in payload["results"]["aliases"]:
        fail("blocked payload should preserve source aliases")
    if "source0" not in payload["results"]["blocked_reason"]:
        fail("blocked reason should remind user to use source0")


def check_missing_file_blocked(tmp: Path) -> None:
    summary = tmp / "missing" / "summary.json"
    proc = run_tool([str(tmp / "missing.csv"), "--sql", "SELECT count(*) AS n FROM source0", "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("missing file should return non-zero")
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        fail("missing file emitted traceback")
    payload = require_envelope(summary, "blocked")
    if "File not found" not in payload["results"]["blocked_reason"]:
        fail("missing file reason should be explicit")


def check_invalid_output_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "bad_output" / "summary.json"
    bad_output = tmp / "bad_output" / "result.unsupported"
    proc = run_tool(
        [
            str(fixtures["basic"]),
            "--sql",
            "SELECT * FROM source0",
            "--output",
            str(bad_output),
            "--summary-json",
            str(summary),
        ]
    )
    if proc.returncode == 0:
        fail("unsupported output extension should return non-zero")
    if "Traceback" in proc.stderr or "Traceback" in proc.stdout:
        fail("unsupported output emitted traceback")
    require_envelope(summary, "blocked")


def check_invalid_preview_rows_blocked(tmp: Path, fixtures: dict[str, Path]) -> None:
    summary = tmp / "preview_rows" / "summary.json"
    proc = run_tool([str(fixtures["basic"]), "--preview-rows", "0", "--summary-json", str(summary)])
    if proc.returncode == 0:
        fail("zero preview rows should return non-zero")
    payload = require_envelope(summary, "blocked")
    if "--preview-rows must be positive" not in payload["results"]["blocked_reason"]:
        fail("preview-rows blocked reason should be explicit")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sda_duckdb_regression_") as tmp_name:
        tmp = Path(tmp_name)
        fixtures = write_fixtures(tmp / "fixtures")
        check_happy_csv(tmp, fixtures)
        print("PASS check_happy_csv")
        check_mixed_sources_and_json_safety(tmp, fixtures)
        print("PASS check_mixed_sources_and_json_safety")
        check_reserved_alias_blocked(tmp, fixtures)
        print("PASS check_reserved_alias_blocked")
        check_missing_file_blocked(tmp)
        print("PASS check_missing_file_blocked")
        check_invalid_output_blocked(tmp, fixtures)
        print("PASS check_invalid_output_blocked")
        check_invalid_preview_rows_blocked(tmp, fixtures)
        print("PASS check_invalid_preview_rows_blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
