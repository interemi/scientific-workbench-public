#!/usr/bin/env python3
"""Healthcheck for the dedicated datanalysis environment, including notebook execution."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime, suppress_fd_output


STACK_MODULES = {
    "numpy": "Numerics",
    "scipy": "Scientific methods",
    "pandas": "Tabular data",
    "matplotlib": "Plotting",
    "plotly": "Interactive plotting for notebooks",
    "astropy": "Astronomy core",
    "photutils": "Photometry",
    "ccdproc": "CCD reduction",
    "specutils": "Spectroscopy",
    "astroquery": "Archive queries",
    "reproject": "WCS reprojection",
    "regions": "Region handling",
    "duckdb": "SQL over mixed tables",
    "statsmodels": "Time-series and econometric models",
    "sklearn": "General modeling metrics and utilities",
    "pypdfium2": "PDF recovery and rendering",
    "pdfplumber": "PDF text extraction",
    "rapidocr_onnxruntime": "OCR",
    "python_calamine": "XLSB and spreadsheet reads",
    "numbers_parser": "iWork parsing",
    "pyarrow": "Arrow/parquet",
    "tifffile": "TIFF support",
    "zarr": "Chunked arrays",
    "notebook": "Notebook server",
    "ipykernel": "Jupyter kernel",
    "nbclient": "Notebook execution",
    "nbformat": "Notebook format",
    "nbconvert": "Notebook conversion",
    "jupyter_client": "Jupyter client",
}

PACKAGE_NAME_MAP = {
    "pypdfium2": "pypdfium2",
    "pdfplumber": "pdfplumber",
    "python_calamine": "python-calamine",
    "numbers_parser": "numbers-parser",
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
}

NOISY_IMPORTS = {
    "matplotlib",
    "pyarrow",
    "rapidocr_onnxruntime",
}


def import_module_quietly(name: str) -> tuple[bool, str | None]:
    command = [sys.executable, "-c", f"import {name}"]
    env = dict(os.environ)
    env.setdefault("ORT_LOGGING_LEVEL", "4")
    env.setdefault("GLOG_minloglevel", "3")
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode == 0:
        return True, None
    details = clean_known_stderr((result.stderr or "").strip() or (result.stdout or "").strip())
    if not details:
        details = f"Subprocess import failed with exit code {result.returncode}"
    return False, details


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json")
    parser.add_argument("--manifest-json")
    parser.add_argument("--kernel-name", default="python3")
    parser.add_argument("--skip-notebook-exec", action="store_true")
    return parser.parse_args()


def write_text_or_die(path: str | Path, text: str, *, label: str) -> None:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"Could not write {label} to {public_path(target)}: {exc.__class__.__name__}: {exc}"
        ) from None


def write_manifest_or_die(path: str | Path, **kwargs) -> None:
    try:
        write_manifest(path, **kwargs)
    except OSError as exc:
        raise SystemExit(
            f"Could not write manifest to {public_path(path)}: {exc.__class__.__name__}: {exc}"
        ) from None


def module_status(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    installed = spec is not None
    version = None
    import_ok = False
    import_error = None
    if installed:
        for candidate in (PACKAGE_NAME_MAP.get(name, name), name):
            try:
                version = metadata.version(candidate)
                break
            except metadata.PackageNotFoundError:
                continue
        try:
            if name in NOISY_IMPORTS:
                import_ok, import_error = import_module_quietly(name)
            else:
                with suppress_fd_output(False):
                    importlib.import_module(name)
                import_ok = True
        except Exception as exc:
            import_ok = False
            import_error = f"{exc.__class__.__name__}: {exc}"
    return {"installed": installed, "version": version, "import_ok": import_ok, "import_error": import_error}


def execute_smoke_notebook(kernel_name: str) -> dict:
    try:
        import nbformat
        from nbclient import NotebookClient
    except Exception as exc:
        return {"attempted": False, "success": False, "error": f"{exc.__class__.__name__}: {exc}"}

    workdir = Path(tempfile.mkdtemp(prefix="datanalysis-nbcheck-"))
    try:
        notebook_path = workdir / "healthcheck.ipynb"
        nb = nbformat.v4.new_notebook(
            cells=[
                nbformat.v4.new_code_cell(
                    "import json, sys\n"
                    "import numpy as np\n"
                    "payload = {'python_executable': sys.executable, 'numpy_ok': bool(np.arange(3).sum() == 3)}\n"
                    "try:\n"
                    "    import plotly.graph_objects as go\n"
                    "    payload['plotly_ok'] = bool(go.Figure().to_dict() is not None)\n"
                    "except Exception as exc:\n"
                    "    payload['plotly_ok'] = False\n"
                    "    payload['plotly_error'] = f'{exc.__class__.__name__}: {exc}'\n"
                    "print(json.dumps(payload))\n"
                )
            ]
        )
        nbformat.write(nb, notebook_path)
        try:
            client = NotebookClient(nb, kernel_name=kernel_name, timeout=180, resources={"metadata": {"path": str(workdir)}})
            client.execute()
            outputs = nb.cells[0].get("outputs", [])
            text_output = ""
            for output in outputs:
                if output.get("output_type") == "stream":
                    text_output += output.get("text", "")
            parsed = None
            for line in text_output.splitlines():
                candidate = line.strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    parsed = json.loads(candidate)
                    break
            return {
                "attempted": True,
                "success": True,
                "status": "ready",
                "kernel_name": kernel_name,
                "workdir": public_path(workdir),
                "notebook_path": public_path(notebook_path),
                "workdir_retained": False,
                "kernel_payload": parsed,
            }
        except Exception as exc:
            message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}")
            status = "failed"
            if "permissionerror" in message.lower() or "operation not permitted" in message.lower():
                status = "sandbox_blocked"
            return {
                "attempted": True,
                "success": False,
                "status": status,
                "kernel_name": kernel_name,
                "workdir": public_path(workdir),
                "notebook_path": public_path(notebook_path),
                "workdir_retained": False,
                "error": message,
            }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    args = parse_args()
    ensure_datanalysis_runtime("datanalysis_healthcheck", strict=False)
    configure_runtime("datanalysis_healthcheck")
    modules = {name: {"purpose": purpose, **module_status(name)} for name, purpose in STACK_MODULES.items()}
    missing = [name for name, entry in modules.items() if not entry["installed"]]
    import_failures = [name for name, entry in modules.items() if entry["installed"] and not entry["import_ok"]]
    notebook_execution = {"attempted": False, "success": None, "reason": "Skipped by request."}
    if not args.skip_notebook_exec and not any(name in missing or name in import_failures for name in ("nbclient", "nbformat", "ipykernel")):
        notebook_execution = execute_smoke_notebook(args.kernel_name)
    notebook_blocked = notebook_execution.get("status") == "sandbox_blocked"
    notebook_skipped = not notebook_execution.get("attempted") and notebook_execution.get("success") is None
    notebook_ready = notebook_skipped or bool(notebook_execution.get("success")) or notebook_blocked
    ready = not missing and not import_failures and notebook_ready
    recommendations = []
    if "plotly" in missing:
        recommendations.append("Install plotly in the datanalysis environment if notebooks or figures depend on it.")
    if "statsmodels" in missing or "sklearn" in missing:
        recommendations.append("Install statsmodels and scikit-learn in the datanalysis environment if you want the general forecasting and econometrics notebook routes to work cleanly.")
    if notebook_blocked:
        recommendations.append("Notebook execution appears blocked by the current sandbox; test again in a less restricted desktop context if you need live execution.")
    elif notebook_execution.get("attempted") and not notebook_execution.get("success"):
        recommendations.append("Register or repair the Jupyter kernel for datanalysis; notebook execution is not currently reliable.")
    legacy_payload = {
        "environment_name": "datanalysis",
        "python_executable": public_path(sys.executable),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "ready": ready,
        "missing": missing,
        "import_failures": import_failures,
        "modules": modules,
        "notebook_execution": notebook_execution,
        "recommendations": recommendations,
    }
    notes = [
        "This healthcheck is the strongest quick read on whether datanalysis is ready for the heaviest astronomy and notebook routes.",
    ]
    if notebook_blocked:
        status = "warning"
        notes.append("Notebook execution looks blocked by the current sandbox, even though imports and modules are otherwise healthy.")
    elif ready:
        status = "ok"
    else:
        status = "blocked"
    payload = standard_tool_payload(
        "datanalysis_healthcheck",
        status=status,
        notes=notes,
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results=legacy_payload,
        legacy=legacy_payload,
    )
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    if args.summary_json:
        write_text_or_die(args.summary_json, rendered, label="JSON summary")
    if args.manifest_json:
        outputs = [Path(args.summary_json)] if args.summary_json and Path(args.summary_json).exists() else []
        write_manifest_or_die(
            args.manifest_json,
            outputs=outputs,
            command="datanalysis_healthcheck.py",
            notes=["This report checks whether the dedicated datanalysis environment is ready for heavy astronomy and notebook workflows."],
            extra={
                "ready": legacy_payload["ready"],
                "missing": legacy_payload["missing"],
                "import_failures": legacy_payload["import_failures"],
                "notebook_execution": legacy_payload["notebook_execution"],
            },
        )
    print(rendered, end="")
    raise SystemExit(0 if legacy_payload["ready"] else 1)


if __name__ == "__main__":
    main()
