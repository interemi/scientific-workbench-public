#!/usr/bin/env python3
"""Check cross-platform readiness for the scientific-data-analysis skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path

from _internal.provenance_utils import (
    environment_summary,
    public_path,
    sanitize_payload,
    standard_tool_payload,
    write_manifest,
)
from _internal.runtime_common import configure_runtime, detect_presentation_export_backends, find_executable
from external_astro_tools_preflight import (
    command_display,
    resolve_apt_command,
    resolve_apt_preferences,
    resolve_java_command,
    resolve_stilts_command,
    resolve_topcat_command,
)


MODULE_PACKAGE_MAP = {
    "docx": "python-docx",
    "pptx": "python-pptx",
    "yaml": "PyYAML",
    "pypdfium2": "pypdfium2",
    "sklearn": "scikit-learn",
    "python_calamine": "python-calamine",
    "numbers_parser": "numbers-parser",
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
}

CORE_MODULES = {
    "numpy": "General arrays and numerics",
    "scipy": "Fitting, optimization, and signal processing",
    "pandas": "General tabular data",
    "matplotlib": "Static plots and figure export",
    "astropy": "FITS, tables, coordinates, and astronomy support",
    "pypdf": "Basic PDF inspection and text extraction",
    "docx": "DOCX editing and text extraction",
    "pptx": "PPTX inspection and editing",
    "openpyxl": "XLSX editing",
    "yaml": "YAML config support",
    "xarray": "Scientific labeled arrays and NetCDF-like workflows",
    "h5py": "HDF5 support",
}

OPTIONAL_GROUPS = {
    "general_data_sql": {
        "label": "General data and SQL extras",
        "modules": {
            "duckdb": "SQL over mixed tabular files",
            "pyarrow": "Arrow, IPC, and some parquet or feather workflows",
            "fastparquet": "Alternative parquet backend",
        },
    },
    "general_timeseries": {
        "label": "General time-series and econometrics extras",
        "modules": {
            "statsmodels": "ARIMA, diagnostics, and econometric time-series models",
            "sklearn": "Forecast metrics and general modeling helpers",
        },
    },
    "astronomy_extras": {
        "label": "Astronomy and reduction extras",
        "modules": {
            "photutils": "Aperture photometry and source tools",
            "ccdproc": "CCD reduction helpers",
            "specutils": "Spectral analysis support",
            "astroquery": "Remote astronomy archives and catalog queries",
            "reproject": "WCS reprojection",
            "regions": "Astronomy region handling",
        },
    },
    "notebook_runtime": {
        "label": "Notebook execution extras",
        "modules": {
            "plotly": "Interactive plotting often used in coursework notebooks",
            "nbclient": "Notebook execution engine",
            "nbformat": "Notebook format support",
            "nbconvert": "Notebook export and preprocessors",
            "jupyter_client": "Kernel communication",
            "ipykernel": "Python kernel support",
            "notebook": "Notebook server package",
        },
    },
    "documents_ocr": {
        "label": "Document and OCR extras",
        "modules": {
            "pypdfium2": "PDF recovery and OCR preparation",
            "rapidocr_onnxruntime": "OCR backend",
            "python_calamine": "Robust XLSB and spreadsheet reads",
            "pyxlsb": "Alternative XLSB reader",
            "pyxlsbwriter": "XLSB writing support",
            "numbers_parser": "Numbers and iWork parsing",
            "olefile": "Legacy Office stream and metadata inspection (not VBA detection)",
        },
    },
    "containers_imaging": {
        "label": "Container and imaging extras",
        "modules": {
            "tifffile": "TIFF scientific containers",
            "zarr": "Chunked scientific array containers",
        },
    },
}


def candidate_conda_roots() -> list[Path]:
    conda_prefix = os.environ.get("CONDA_PREFIX")
    conda_exe = os.environ.get("CONDA_EXE")
    conda_bin = find_executable(["conda"])
    roots = []
    if conda_prefix:
        prefix_path = Path(conda_prefix).resolve()
        if prefix_path.name == "datanalysis" and prefix_path.parent.name == "envs":
            roots.append(prefix_path.parent.parent)
        else:
            roots.append(prefix_path)
    if conda_exe:
        roots.append(Path(conda_exe).resolve().parent.parent)
    if conda_bin:
        roots.append(Path(conda_bin).resolve().parent.parent)
    roots.extend(
        [
            Path.home() / "anaconda3",
            Path.home() / "opt" / "anaconda3",
            Path("/opt/anaconda3"),
            Path.home() / "miniconda3",
            Path.home() / "mambaforge",
        ]
    )
    environments_txt = Path.home() / ".conda" / "environments.txt"
    if environments_txt.exists():
        try:
            for raw_line in environments_txt.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                env_path = Path(line).expanduser()
                if env_path.name == "datanalysis":
                    roots.append(env_path.parent.parent if env_path.parent.name == "envs" else env_path.parent)
                elif env_path.name == "envs":
                    roots.append(env_path.parent)
                elif env_path.is_dir():
                    roots.append(env_path)
        except OSError:
            pass
    deduped = []
    seen = set()
    for root in roots:
        resolved = str(root)
        if resolved not in seen:
            deduped.append(root)
            seen.add(resolved)
    return deduped


def locate_named_conda_env(env_name: str) -> dict:
    candidates = []
    for root in candidate_conda_roots():
        env_root = root / "envs" / env_name
        for python_name in ("bin/python", "python.exe"):
            python_bin = env_root / python_name
            if python_bin.exists():
                candidates.append(
                    {
                        "root": public_path(root),
                        "env_root": public_path(env_root),
                        "python": public_path(python_bin),
                    }
                )
                break
    selected = candidates[0] if candidates else None
    return {"found": selected is not None, "selected": selected, "candidates": candidates}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json", help="Optional JSON output path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    parser.add_argument("--strict-core", action="store_true", help="Exit non-zero if any core dependency is missing.")
    return parser.parse_args()


def output_target_error(path: str | Path | None, *, label: str) -> str | None:
    if not path:
        return None
    target = Path(path)
    if target.exists() and target.is_dir():
        return f"{label} must point to a file, not a directory: {public_path(target)}"
    parent = target.parent
    if parent.exists() and not parent.is_dir():
        return f"{label} parent is not a directory: {public_path(parent)}"
    return None


def emit_blocked(args, message: str, *, error_type: str = "OutputConflict") -> int:
    artifacts = {
        "summary_json": public_path(args.summary_json) if args.summary_json else None,
        "manifest_json": public_path(args.manifest_json) if args.manifest_json else None,
    }
    payload = standard_tool_payload(
        "env_doctor",
        status="blocked",
        notes=[
            "env_doctor did not complete because an app-facing precondition failed.",
            "No input files or original project assets were modified.",
        ],
        artifacts=artifacts,
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "requested_outputs": artifacts,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": 1},
        },
        legacy={"blocked_reason": message, "error_type": error_type},
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    print(rendered, end="")
    if args.summary_json and output_target_error(args.summary_json, label="--summary-json") is None:
        try:
            Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.summary_json).write_text(rendered, encoding="utf-8")
        except OSError:
            pass
    return 2


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


def module_report(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    installed = spec is not None
    package_name = MODULE_PACKAGE_MAP.get(name, name)
    version = None
    if installed:
        for candidate in (package_name, name):
            try:
                version = metadata.version(candidate)
                break
            except metadata.PackageNotFoundError:
                continue
    return {"installed": installed, "version": version}


def build_group_report(modules: dict[str, str]) -> dict:
    return {name: {"purpose": purpose, **module_report(name)} for name, purpose in modules.items()}


def missing_from_report(report: dict[str, dict]) -> list[str]:
    return [name for name, entry in report.items() if not entry["installed"]]


def build_payload() -> dict:
    configure_runtime("env_doctor")
    root_dir = Path(__file__).resolve().parent.parent
    datanalysis_env = locate_named_conda_env("datanalysis")
    active_python = Path(sys.executable).resolve()
    active_matches_named_env = "/envs/datanalysis/" in str(active_python).replace("\\", "/") or any(
        candidate.get("python") == public_path(active_python) for candidate in datanalysis_env["candidates"]
    )
    core_report = build_group_report(CORE_MODULES)
    core_missing = missing_from_report(core_report)

    optional_reports = {}
    optional_missing = {}
    for group_name, group in OPTIONAL_GROUPS.items():
        modules = build_group_report(group["modules"])
        missing = missing_from_report(modules)
        optional_reports[group_name] = {
            "label": group["label"],
            "ready": not missing,
            "missing": missing,
            "modules": modules,
        }
        optional_missing[group_name] = missing

    executables = {
        "python": sys.executable,
        "jupyter": find_executable(["jupyter"]),
        "latexmk": find_executable(["latexmk"]),
        "pdflatex": find_executable(["pdflatex"]),
        "soffice": find_executable(["soffice", "libreoffice"]),
        "qlmanage": find_executable(["qlmanage"]),
        "osascript": find_executable(["osascript"]),
        "java": find_executable(["java"]),
        "stilts": find_executable(["stilts"]),
        "topcat": find_executable(["topcat"]),
        "apt_csh": find_executable(["APT.csh", "APT.bat", "AperturePhotometryTool"]),
    }
    external_java = resolve_java_command()
    external_topcat = resolve_topcat_command()
    external_stilts = resolve_stilts_command()
    external_apt = resolve_apt_command()
    external_apt_pref = resolve_apt_preferences()
    presentation = detect_presentation_export_backends()
    system = platform.system()

    capabilities = {
        "core_ready": not core_missing,
        "general_data_sql_ready": optional_reports["general_data_sql"]["ready"],
        "general_timeseries_ready": optional_reports["general_timeseries"]["ready"],
        "astronomy_extras_ready": optional_reports["astronomy_extras"]["ready"],
        "notebook_runtime_ready": optional_reports["notebook_runtime"]["ready"],
        "documents_ocr_ready": optional_reports["documents_ocr"]["ready"],
        "containers_imaging_ready": optional_reports["containers_imaging"]["ready"],
        "full_ready": not core_missing and all(group["ready"] for group in optional_reports.values()),
        "latex_ready": bool(executables["pdflatex"] or executables["latexmk"]),
        "presentation_pdf_ready": bool(presentation["soffice"] or presentation["keynote_available"]),
        "quicklook_native_ready": bool(system == "Darwin" and executables["qlmanage"]),
        "teareduce_ready": importlib.util.find_spec("teareduce") is not None,
        "datanalysis_env_found": datanalysis_env["found"] or active_matches_named_env,
        "external_astro_java_ready": bool(external_java["found"]),
        "external_astro_stilts_ready": bool(external_stilts["found"] and external_java["found"]),
        "external_astro_topcat_ready": bool(external_topcat["found"] and external_java["found"]),
        "external_astro_apt_command_ready": bool(external_apt["found"] and external_java["found"]),
        "external_astro_apt_batch_ready": bool(external_apt["found"] and external_java["found"] and external_apt_pref["found"]),
    }

    recommendations = []
    if core_missing:
        recommendations.append(
            "Missing core modules: "
            + ", ".join(core_missing)
            + ". Install the stable base with requirements-core.txt or environment.yml."
        )
    for group_name, group in optional_reports.items():
        if group["missing"]:
            recommendations.append(
                f"Optional group '{group['label']}' is incomplete: "
                + ", ".join(group["missing"])
                + ". Install requirements-full.txt or the subset you need."
            )
    if not capabilities["latex_ready"]:
        recommendations.append("Install a LaTeX distribution if you want local PDF builds from LaTeX.")
    if active_matches_named_env:
        recommendations.append("The active interpreter already matches the dedicated 'datanalysis' environment.")
    elif not datanalysis_env["found"]:
        recommendations.append(
            "Create the dedicated 'datanalysis' environment if you want the heaviest astronomy and notebook workflows to run in a stable isolated stack."
        )
    if system == "Darwin":
        if not capabilities["presentation_pdf_ready"]:
            recommendations.append("Install Keynote or LibreOffice if you want copied-deck PDF export on macOS.")
    else:
        if not presentation["soffice"]:
            recommendations.append("Install LibreOffice if you want local PPTX to PDF export on this platform.")

    platform_notes = [
        "Keynote and Quick Look fallbacks are macOS-only.",
        "LibreOffice is the cross-platform presentation PDF path.",
        "Deep iWork behavior is strongest on macOS.",
        "TEAREDUCE remains optional and is only needed on astronomy-focused machines that use it.",
        "STILTS/TOPCAT and APT are optional Java-backed astronomy tools; absence is not a core install failure.",
    ]

    legacy_payload = {
        "environment": environment_summary(),
        "platform": {
            "system": system,
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "scope": {
            "stable_release": "v1",
            "primary_domain": "science-first, especially astronomy and technical analysis",
            "core_note": "The core stack should remain usable even when optional extras are absent.",
        },
        "core_modules": {
            "ready": not core_missing,
            "missing": core_missing,
            "modules": core_report,
        },
        "optional_groups": optional_reports,
        "executables": executables,
        "dedicated_environment": {
            "name": "datanalysis",
            "found": datanalysis_env["found"] or active_matches_named_env,
            "active": active_matches_named_env,
            "active_python": public_path(active_python),
            "python": None if not datanalysis_env["selected"] else datanalysis_env["selected"]["python"],
            "env_root": None if not datanalysis_env["selected"] else datanalysis_env["selected"]["env_root"],
            "checked_candidates": datanalysis_env["candidates"],
            "note": (
                "The active interpreter already matches the named datanalysis environment."
                if active_matches_named_env
                else "Prefer scripts/datanalysis_env.py for heavy astronomy, reduction, or notebook runs."
            ),
        },
        "presentation_backends": presentation,
        "external_astronomy_tools": {
            "java": {**external_java, "command": command_display(external_java["command"])},
            "topcat": {**external_topcat, "command": command_display(external_topcat["command"])},
            "stilts": {**external_stilts, "command": command_display(external_stilts["command"])},
            "apt": {**external_apt, "command": command_display(external_apt["command"])},
            "apt_preferences": {
                "found": external_apt_pref["found"],
                "source": external_apt_pref["source"],
                "path": public_path(external_apt_pref["path"]),
            },
            "note": "Run scripts/external_astro_tools_preflight.py for the detailed STILTS/TOPCAT/APT readiness contract.",
        },
        "capabilities": capabilities,
        "recommendations": recommendations,
        "platform_notes": platform_notes,
        "install_profiles": {
            "core_pip": "python -m pip install -r requirements-core.txt",
            "full_pip": "python -m pip install -r requirements-full.txt",
            "conda": "conda env create -f environment.yml",
            "datanalysis": "conda create -n datanalysis python=3.11 pip",
            "posix_core_wrapper": "deploy/install-core.sh",
            "posix_full_wrapper": "deploy/install-full.sh",
            "windows_core_wrapper": "deploy/install-core.ps1",
            "windows_full_wrapper": "deploy/install-full.ps1",
            "portable_smoke_test": "python scripts/portable_smoke_test.py --output-dir smoke-out",
        },
        "artifact_paths": {
            "readme": public_path(root_dir / "README.txt"),
            "requirements_core": public_path(root_dir / "requirements-core.txt"),
            "requirements_full": public_path(root_dir / "requirements-full.txt"),
            "environment_yml": public_path(root_dir / "environment.yml"),
            "portable_install_guide": public_path(root_dir / "references" / "portable-install.md"),
            "deployment_quickstart": public_path(root_dir / "references" / "deployment-quickstart.md"),
            "core_optional_scope": public_path(root_dir / "references" / "core-and-optional.md"),
            "datanalysis_wrapper": public_path(root_dir / "scripts" / "datanalysis_env.py"),
            "datanalysis_healthcheck": public_path(root_dir / "scripts" / "datanalysis_healthcheck.py"),
            "portable_smoke_test": public_path(root_dir / "scripts" / "portable_smoke_test.py"),
            "external_astro_tools_preflight": public_path(root_dir / "scripts" / "external_astro_tools_preflight.py"),
            "stilts_workbench": public_path(root_dir / "scripts" / "stilts_workbench.py"),
            "apt_workbench": public_path(root_dir / "scripts" / "apt_workbench.py"),
            "deploy_dir": public_path(root_dir / "deploy"),
            "examples_dir": public_path(root_dir / "examples"),
        },
    }
    notes = [
        "env_doctor distinguishes the active interpreter from merely discovering a named environment on disk.",
        "Use scripts/datanalysis_env.py when you want the skill to relaunch itself inside the dedicated environment automatically.",
    ]
    if active_matches_named_env:
        notes.append("The current Python already belongs to the named datanalysis environment.")
    elif datanalysis_env["found"]:
        notes.append("A named datanalysis environment exists on disk, but the current interpreter does not point to it.")
    if core_missing:
        status = "blocked"
    elif not capabilities["full_ready"]:
        status = "warning"
    else:
        status = "ok"
    payload = standard_tool_payload(
        "env_doctor",
        status=status,
        notes=notes,
        artifacts=legacy_payload["artifact_paths"],
        results=legacy_payload,
        legacy=legacy_payload,
    )
    return sanitize_payload(payload)


def main():
    args = parse_args()
    for raw_path, label in ((args.summary_json, "--summary-json"), (args.manifest_json, "--manifest-json")):
        error = output_target_error(raw_path, label=label)
        if error:
            raise SystemExit(emit_blocked(args, error))
    payload = build_payload()
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.summary_json:
        try:
            write_text_or_die(args.summary_json, rendered, label="JSON summary")
        except SystemExit as exc:
            raise SystemExit(emit_blocked(args, str(exc), error_type="WriteError")) from None
    if args.manifest_json:
        outputs = [Path(args.summary_json)] if args.summary_json and Path(args.summary_json).exists() else []
        try:
            write_manifest_or_die(
                args.manifest_json,
                outputs=outputs,
                command="env_doctor.py",
                notes=["This report checks whether the current machine is ready to run the scientific-data-analysis skill."],
                extra={
                    "capabilities": payload["capabilities"],
                    "core_missing": payload["core_modules"]["missing"],
                    "optional_missing": {name: group["missing"] for name, group in payload["optional_groups"].items()},
                    "recommendations": payload["recommendations"],
                },
            )
        except SystemExit as exc:
            raise SystemExit(emit_blocked(args, str(exc), error_type="WriteError")) from None
    print(rendered, end="")
    if args.strict_core and not payload["capabilities"]["core_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
