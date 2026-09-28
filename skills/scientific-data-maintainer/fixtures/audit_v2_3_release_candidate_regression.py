#!/usr/bin/env python3
"""Run the narrow v2.3 modular release-candidate regression set."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ["scripts/audit_v2_3_docs_regression.py"],
    ["scripts/audit_v2_3_module_ownership_regression.py"],
    ["scripts/audit_v2_3_mother_router_contract_regression.py"],
    ["scripts/audit_v2_3_shared_helpers_regression.py"],
    ["scripts/audit_v2_3_scientificworkbench_compat_regression.py"],
    ["scripts/sync_public_surface_docs.py", "--check"],
    ["scripts/skill_surface_audit.py", "--skip-hygiene"],
]


def _run(argv: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, *argv],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": " ".join(argv),
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
    }


def main() -> int:
    results = [_run(argv) for argv in COMMANDS]
    failures = [result for result in results if result["returncode"] != 0]
    status = "PASS" if not failures else "FAIL"
    payload = {
        "tool": "audit_v2_3_release_candidate_regression",
        "status": status,
        "command_count": len(COMMANDS),
        "results": results,
        "errors": [
            {"kind": "gate_failed", "message": result["command"]}
            for result in failures
        ],
        "warnings": [],
        "original_modified": False,
        "next_actions": []
        if status == "PASS"
        else [{"label": "Inspect failing v2.3 release-candidate gate", "priority": "high"}],
    }
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
