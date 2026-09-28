#!/usr/bin/env python3
"""Focused v1.4 regression gate for companion-routing decisions."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str], cwd: Path = ROOT) -> dict:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def companions(payload: dict) -> set[str]:
    return {item["companion"] for item in payload["results"]["recommendations"]}


def excluded_ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["results"]["excluded_by_policy"]}


def run_route(tmp: Path, name: str, *args: str) -> dict:
    summary_json = tmp / f"{name}.json"
    result = run([sys.executable, str(SCRIPTS / "companion_route_check.py"), *args, "--summary-json", str(summary_json)])
    require(result["returncode"] == 0, f"companion_route_check failed for {name}: {result['stderr']}")
    payload = read_json(summary_json)
    require(payload["tool"] == "companion_route_check", "unexpected tool name")
    require("recommendations" in payload["results"], "missing recommendations list")
    return payload


def check_pdf_route(tmp: Path) -> None:
    payload = run_route(tmp, "pdf", "--task", "Revisar visualmente un PDF cientifico pagina a pagina", "--file", "report.pdf")
    require("pdf" in companions(payload), "PDF route should recommend pdf skill")


def check_notebook_plotly_route(tmp: Path) -> None:
    payload = run_route(
        tmp,
        "notebook",
        "--task",
        "Notebook con Plotly que aparece como cuadro blanco en HTML",
        "--file",
        "analysis.ipynb",
        "--file",
        "preview.html",
    )
    recs = companions(payload)
    require("jupyter-notebook" in recs, "Notebook route should recommend jupyter-notebook")
    require("Browser Use / playwright" in recs, "Plotly/HTML route should recommend browser visual QA")


def check_presentation_and_spreadsheet_routes(tmp: Path) -> None:
    deck = run_route(tmp, "deck", "--task", "Preparar slides editables", "--file", "presentation.pptx")
    require("Presentations" in companions(deck), "PPTX route should recommend Presentations")
    sheet = run_route(tmp, "sheet", "--task", "Revisar formulas y graficos de Excel", "--file", "measurements.xlsx")
    require("Spreadsheets" in companions(sheet), "XLSX route should recommend Spreadsheets")


def check_excluded_connectors(tmp: Path) -> None:
    payload = run_route(
        tmp,
        "excluded",
        "--task",
        "Buscar en Zotero, Google Drive y Gmail referencias para un informe",
    )
    rec_text = json.dumps(payload["results"]["recommendations"], ensure_ascii=True).lower()
    require("gmail" not in rec_text, "Gmail should not be recommended by v1.4 routing")
    require("google drive" not in rec_text, "Google Drive should not be recommended by v1.4 routing")
    require("zotero" not in rec_text, "Zotero should not be recommended by v1.4 routing")
    require({"gmail", "google_drive", "zotero"} <= excluded_ids(payload), "excluded connectors should be reported as policy exclusions")


def check_v1_4_docs(tmp: Path) -> None:
    expected = {
        "SKILL.md": ["companion-routing", "email, Google Drive, and Zotero remain outside"],
        "README.txt": ["companion_route_check.py", "does not route to email, Google Drive, or Zotero"],
        "RELEASE-v1.txt": ["v1.4 adds companion routing", "email, Google Drive, and Zotero outside"],
        "references/architecture.md": ["audit_v1_4_companion_routing_regression.py"],
        "references/companion-routing.md": ["Email, Google Drive, and Zotero are not part of v1.4 routing"],
    }
    for relative, terms in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        require(not missing, f"{relative} is missing v1.4 terms: {missing}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scientific-data-analysis-v1-4-") as tmp_raw:
        tmp = Path(tmp_raw)
        checks = [
            check_pdf_route,
            check_notebook_plotly_route,
            check_presentation_and_spreadsheet_routes,
            check_excluded_connectors,
            check_v1_4_docs,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All v1.4 companion-routing regressions passed.")


if __name__ == "__main__":
    main()
