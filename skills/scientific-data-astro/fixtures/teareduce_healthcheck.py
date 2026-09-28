#!/usr/bin/env python3
"""Check local TEAREDUCE availability and scan TEAREDUCE-style notebooks safely."""

import argparse
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path

from _internal.provenance_utils import environment_summary, public_path, sanitize_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import configure_runtime

TEAREDUCE_VERSION_PATTERN = re.compile(r"(?i)teareduce[^0-9]{0,24}([0-9]+\.[0-9]+\.[0-9]+)")
TEA_CALL_PATTERN = re.compile(r"\btea\.([A-Za-z_][A-Za-z0-9_]*)")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
HELPER_NOTEBOOK_PATTERN = re.compile(r"([0-9]{2}[a-z]?_[A-Za-z0-9_\-]+\.ipynb)")

NOTEBOOK_STAGE_MAP = {
    "00": {
        "label": "raw header fixes",
        "family": "raw-preparation",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "01": {
        "label": "master bias and bias application",
        "family": "calibration-frames",
        "route": "scripts/teareduce_master_bias_workflow.py",
    },
    "02": {
        "label": "master flat and flat application",
        "family": "calibration-frames",
        "route": "scripts/teareduce_flat_workflow.py",
    },
    "03": {
        "label": "wavelength calibration",
        "family": "spectroscopy-calibration",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "04": {
        "label": "sky subtraction and cosmic rays",
        "family": "spectroscopy-cleaning",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "05": {
        "label": "spectral extraction and storage",
        "family": "spectroscopy-extraction",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "06": {
        "label": "atmospheric extinction correction",
        "family": "flux-calibration",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "07": {
        "label": "geometric distortion",
        "family": "spectroscopy-geometry",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "08": {
        "label": "tres en uno imaging examples",
        "family": "imaging-visualization",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "09": {
        "label": "response curves",
        "family": "instrument-response",
        "route": "scripts/teareduce_notebook_runner.py",
    },
    "10": {
        "label": "astrometry.net assisted imaging",
        "family": "astrometry-manual",
        "route": "scripts/astrometry_net_workbench.py",
    },
    "11": {
        "label": "photometric calibration imaging",
        "family": "photometric-calibration",
        "route": "scripts/photometric_solution.py",
    },
    "12": {
        "label": "CK04 model reading",
        "family": "reference-models",
        "route": "scripts/notebook_workbench.py",
    },
}

KNOWN_SUPPORT_BASENAMES = {
    "tea_cafos_setup_2025.py": "external-python-sidecar",
    "pincushion_distortion_coef_G100.fits": "external-fits-sidecar",
    "NGC4490_SDSS_DR18.csv": "external-photometric-table",
}


def bootstrap_runtime_dirs():
    base = configure_runtime("teareduce_healthcheck")
    return {
        "runtime_root": str(base),
        "mplconfigdir": str(Path(base) / "mplconfig"),
        "xdg_cache_home": str(Path(base) / "xdgcache"),
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional TEAREDUCE notebooks or directories to scan for usage patterns.",
    )
    parser.add_argument("--summary-json", help="Optional JSON report path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    parser.add_argument("--max-notebooks", type=int, default=8, help="Maximum notebooks to inspect.")
    parser.add_argument("--concise", action="store_true", help="Print a short terminal-oriented summary instead of the full JSON payload.")
    return parser.parse_args()


def notebook_candidates(paths, max_notebooks):
    candidates = []
    seen = set()
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file() and (path.suffix.lower() == ".ipynb" or path.name.lower().endswith(".ipynb.txt")):
            resolved = str(path.resolve())
            if resolved not in seen:
                candidates.append(path)
                seen.add(resolved)
            continue
        if not path.is_dir():
            continue
        preferred = (
            list(path.rglob("00*.ipynb"))
            + list(path.rglob("01*.ipynb"))
            + list(path.rglob("02*.ipynb"))
            + list(path.rglob("03*.ipynb"))
            + list(path.rglob("04*.ipynb"))
            + list(path.rglob("05*.ipynb"))
            + list(path.rglob("06*.ipynb"))
            + list(path.rglob("07*.ipynb"))
            + list(path.rglob("08*.ipynb"))
            + list(path.rglob("09*.ipynb"))
            + list(path.rglob("10*.ipynb"))
            + list(path.rglob("11*.ipynb"))
            + list(path.rglob("12*.ipynb"))
            + list(path.rglob("P2_*.ipynb"))
            + list(path.rglob("P3_*.ipynb"))
            + list(path.rglob("00*.ipynb.txt"))
            + list(path.rglob("01*.ipynb.txt"))
            + list(path.rglob("02*.ipynb.txt"))
            + list(path.rglob("03*.ipynb.txt"))
            + list(path.rglob("04*.ipynb.txt"))
            + list(path.rglob("05*.ipynb.txt"))
            + list(path.rglob("06*.ipynb.txt"))
            + list(path.rglob("07*.ipynb.txt"))
            + list(path.rglob("08*.ipynb.txt"))
            + list(path.rglob("09*.ipynb.txt"))
            + list(path.rglob("10*.ipynb.txt"))
            + list(path.rglob("11*.ipynb.txt"))
            + list(path.rglob("12*.ipynb.txt"))
            + list(path.rglob("P2_*.ipynb.txt"))
            + list(path.rglob("P3_*.ipynb.txt"))
        )
        source = preferred or list(path.rglob("*.ipynb")) + list(path.rglob("*.ipynb.txt"))
        for notebook in sorted(source):
            if ".ipynb_checkpoints" in notebook.parts:
                continue
            resolved = str(notebook.resolve())
            if resolved in seen:
                continue
            candidates.append(notebook)
            seen.add(resolved)
            if len(candidates) >= max_notebooks:
                return candidates
    return candidates[:max_notebooks]


def cell_text(cell):
    parts = []
    source = cell.get("source", [])
    if isinstance(source, list):
        parts.append("".join(source))
    elif source:
        parts.append(str(source))
    for output in cell.get("outputs", []):
        text = output.get("text", "")
        if isinstance(text, list):
            parts.append("".join(text))
        elif text:
            parts.append(str(text))
        data = output.get("data", {})
        for key in ("text/plain", "text/markdown"):
            value = data.get(key)
            if isinstance(value, list):
                parts.append("".join(value))
            elif value:
                parts.append(str(value))
    return "\n".join(parts)


def scan_notebook(path):
    path = Path(path)
    extension_note = None
    raw_text = path.read_text(errors="replace")
    if path.name.lower().endswith(".ipynb.txt"):
        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict) or "cells" not in data:
                raise ValueError("Notebook-like JSON not found")
            notebook_format = "ipynb-json-with-txt-extension"
            extension_note = "Notebook JSON stored with a .ipynb.txt suffix; treat it as a misnamed notebook copy."
        except Exception:
            functions = TEA_CALL_PATTERN.findall(raw_text)
            observed_versions = TEAREDUCE_VERSION_PATTERN.findall(raw_text)
            counts = Counter(functions)
            return {
                "path": str(path.resolve()),
                "format": "ipynb-text-export",
                "extension_note": "The file has a .ipynb.txt suffix but does not parse as notebook JSON.",
                "cells": None,
                "title": None,
                "imports_teareduce": "import teareduce as tea" in raw_text,
                "top_functions": [{"name": name, "count": count} for name, count in counts.most_common(12)],
                "observed_versions": sorted(set(observed_versions)),
                "kernel": {"display_name": None, "language": None, "name": None},
                "course_pack_profile": build_course_pack_profile(path, None, raw_text),
            }
    else:
        data = json.loads(raw_text)
        notebook_format = "ipynb"
    functions = []
    observed_versions = []
    imports_teareduce = False
    for cell in data.get("cells", []):
        blob = cell_text(cell)
        imports_teareduce = imports_teareduce or ("import teareduce as tea" in blob)
        functions.extend(TEA_CALL_PATTERN.findall(blob))
        observed_versions.extend(TEAREDUCE_VERSION_PATTERN.findall(blob))
    counts = Counter(functions)
    kernelspec = data.get("metadata", {}).get("kernelspec", {})
    return {
        "path": str(path.resolve()),
        "format": notebook_format,
        "extension_note": extension_note,
        "cells": len(data.get("cells", [])),
        "title": extract_notebook_title(data),
        "imports_teareduce": imports_teareduce,
        "top_functions": [{"name": name, "count": count} for name, count in counts.most_common(10)],
        "observed_versions": sorted(set(observed_versions)),
        "kernel": {
            "display_name": kernelspec.get("display_name"),
            "language": kernelspec.get("language"),
            "name": kernelspec.get("name"),
        },
        "course_pack_profile": build_course_pack_profile(path, data, raw_text),
    }


def summarize_notebooks(paths, max_notebooks=8):
    notebooks = notebook_candidates(paths, max_notebooks=max_notebooks)
    scanned = [scan_notebook(path) for path in notebooks]
    aggregate = Counter()
    versions = set()
    stage_counts = Counter()
    role_counts = Counter()
    execution_profiles = Counter()
    helper_pairs = []
    for entry in scanned:
        for item in entry["top_functions"]:
            aggregate[item["name"]] += item["count"]
        versions.update(entry["observed_versions"])
        profile = entry.get("course_pack_profile") or {}
        if profile.get("stage_code"):
            stage_counts[f"{profile['stage_code']} {profile['stage_label']}"] += 1
        if profile.get("notebook_role"):
            role_counts[profile["notebook_role"]] += 1
        if profile.get("execution_profile"):
            execution_profiles[profile["execution_profile"]] += 1
        if profile.get("helper_notebooks"):
            helper_pairs.append(
                {
                    "notebook": Path(entry["path"]).name,
                    "helper_notebooks": profile["helper_notebooks"],
                }
            )
    return {
        "count": len(scanned),
        "notebooks": scanned,
        "top_functions": [{"name": name, "count": count} for name, count in aggregate.most_common(12)],
        "observed_versions": sorted(versions),
        "course_pack_summary": {
            "stages": dict(stage_counts),
            "roles": dict(role_counts),
            "execution_profiles": dict(execution_profiles),
            "helper_pairs": helper_pairs,
        },
    }


def extract_notebook_title(data):
    if not isinstance(data, dict):
        return None
    for cell in data.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source or "")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip() or None
    return None


def infer_stage(path: Path):
    stem = path.name
    if stem.lower().endswith(".ipynb.txt"):
        stem = stem[:-10]
    elif stem.lower().endswith(".ipynb"):
        stem = stem[:-6]
    code = stem[:2]
    stage = NOTEBOOK_STAGE_MAP.get(code)
    if not stage:
        return None
    return {"stage_code": code, **stage}


def extract_support_files(raw_text):
    support = []
    urls = sorted(set(URL_PATTERN.findall(raw_text)))
    seen = set()
    for url in urls:
        basename = Path(url.rstrip(").,;")).name
        if basename in KNOWN_SUPPORT_BASENAMES and basename not in seen:
            seen.add(basename)
            support.append(
                {
                    "name": basename,
                    "kind": KNOWN_SUPPORT_BASENAMES[basename],
                    "source_hint": url.rstrip(").,;"),
                }
            )
    return support


def extract_manual_steps(raw_text):
    lower = raw_text.lower()
    steps = []
    if "astrometry.net" in lower or "new-image.fits" in lower:
        steps.append("Manual astrometry.net/browser step is documented inside the notebook.")
    if "skyserver" in lower or "pinchando con el ratón" in lower:
        steps.append("Manual web-based star or catalog inspection step is documented inside the notebook.")
    return steps


def build_course_pack_profile(path, data, raw_text):
    stage = infer_stage(path)
    lower_name = path.name.lower()
    helper_notebooks = []
    available_in_directory = {child.name for child in path.parent.glob("*.ipynb")}
    available_in_directory.update({child.name for child in path.parent.glob("*.ipynb.txt")})
    for helper in sorted(set(HELPER_NOTEBOOK_PATTERN.findall(raw_text))):
        if available_in_directory and helper not in available_in_directory:
            continue
        helper_notebooks.append(helper)
    support_files = extract_support_files(raw_text)
    manual_steps = extract_manual_steps(raw_text)
    undefined_parameter = "Undefined parameter:" in raw_text
    auxiliary_template = "_exec_" in lower_name or "cuaderno auxiliar" in raw_text.lower()
    requires_absolute_path_root = '/Volumes/' in raw_text or 'Path("/' in raw_text or "Path('/" in raw_text
    notebook_role = "standalone"
    if auxiliary_template:
        notebook_role = "auxiliary-template"
    elif helper_notebooks:
        notebook_role = "driver-with-helper"
    elif manual_steps:
        notebook_role = "manual-assisted"
    execution_profile = "copy_execution_candidate"
    if auxiliary_template or undefined_parameter:
        execution_profile = "parameterized_template"
    elif manual_steps:
        execution_profile = "manual_or_web_assisted"
    elif support_files:
        execution_profile = "copy_execution_with_support_files"
    profile = {
        "stage_code": stage["stage_code"] if stage else None,
        "stage_label": stage["label"] if stage else None,
        "workflow_family": stage["family"] if stage else None,
        "notebook_role": notebook_role,
        "helper_notebooks": helper_notebooks,
        "requires_absolute_path_root": requires_absolute_path_root,
        "support_files": support_files,
        "manual_steps": manual_steps,
        "parameterized_template_signals": ["Undefined parameter placeholders"] if undefined_parameter else [],
        "execution_profile": execution_profile,
        "recommended_skill_route": stage["route"] if stage else "scripts/teareduce_notebook_runner.py",
        "route_note": build_route_note(stage, execution_profile, support_files, manual_steps),
    }
    return profile


def build_route_note(stage, execution_profile, support_files, manual_steps):
    if not stage:
        return "Treat this as a generic TEAREDUCE notebook and inspect it with teareduce_healthcheck.py before running a copied execution."
    if stage["stage_code"] == "01":
        return "Bias notebooks integrate best through the canonical master-bias workflow when you want a validated route, or through teareduce_notebook_runner.py when you specifically want the raw notebook copy."
    if stage["stage_code"] == "02":
        return "Flat notebooks integrate best through the canonical flat workflow when the official sidecars are staged; keep notebook copies for teaching fidelity."
    if stage["stage_code"] in {"03", "04", "05", "06", "07", "08", "09"}:
        return "Treat this as a TEAREDUCE course recipe: inspect with teareduce_healthcheck.py first, then use teareduce_notebook_runner.py on a copied workspace with the required sidecars or processed tree."
    if stage["stage_code"] == "10":
        return "This notebook includes manual astrometry.net steps; use astrometry_net_workbench.py for the web solve itself and keep the notebook as the guided classroom recipe."
    if stage["stage_code"] == "11":
        return "This notebook pairs naturally with photometric_solution.py for the final fit/report, while the notebook itself remains the course-faithful worked example."
    if stage["stage_code"] == "12":
        return "Treat this as a reference or model-reading notebook; inspect and copy it non-destructively rather than forcing a full automation path."
    if manual_steps:
        return "This notebook contains manual or browser-assisted steps and should be treated as a guided recipe."
    if support_files:
        return "Stage the required support files before executing a copied notebook workspace."
    if execution_profile == "parameterized_template":
        return "This notebook is better treated as a parameterized template than as a turnkey run."
    return "Copied execution is the preferred integration path."


def inspect_teareduce_environment():
    try:
        distribution = metadata.distribution("teareduce")
        spec = importlib.util.find_spec("teareduce")
    except (metadata.PackageNotFoundError, ImportError, ValueError) as exc:
        return {
            "installed": False,
            "error": f"{exc.__class__.__name__}: {exc}",
            "python_executable": public_path(sys.executable),
            "interpreter_scope": "launcher_python_only",
            "import_verified": False,
        }
    if spec is None:
        return {
            "installed": False,
            "error": "Package metadata exists, but the teareduce module was not found.",
            "python_executable": public_path(sys.executable),
            "interpreter_scope": "launcher_python_only",
            "import_verified": False,
        }
    env_bin = Path(sys.executable).resolve().parent
    script_name = "tea-cleanest.exe" if sys.platform.startswith("win") else "tea-cleanest"
    tea_cleanest_path = env_bin / script_name
    console_scripts = [ep.name for ep in metadata.entry_points(group="console_scripts") if ep.name == "tea-cleanest"]
    pycosmic_spec = importlib.util.find_spec("pycosmic") or importlib.util.find_spec("PyCosmic")
    return {
        "installed": True,
        "version": distribution.version,
        "module_path": public_path(Path(spec.origin).resolve()) if spec.origin else None,
        "python_executable": public_path(sys.executable),
        "interpreter_scope": "launcher_python_only",
        "import_verified": False,
        "inspection_scope": "Installed metadata and module discovery only; TEAREDUCE code was not imported or executed.",
        "extras": {
            "tea_cleanest_path": str(tea_cleanest_path) if tea_cleanest_path.exists() else shutil.which("tea-cleanest"),
            "tea_cleanest_console_script": bool(console_scripts),
            "cleanest_module": None,
            "pycosmic": bool(pycosmic_spec),
            "pycosmic_module": None if pycosmic_spec is None else pycosmic_spec.name,
        },
    }


def build_notes(environment_payload, notebook_payload):
    notes = [
        "TEAREDUCE is an externally installed optional astronomy backend, not part of the core profile."
    ]
    if not environment_payload.get("installed"):
        notes.append("TEAREDUCE was not detected in the current Python environment.")
        return notes
    notes.append("Package discovery did not import or run TEAREDUCE; API compatibility and notebook execution remain unverified.")
    extras = environment_payload.get("extras", {})
    if not extras.get("tea_cleanest_path"):
        notes.append("tea-cleanest is not available as an executable in the current environment.")
    if not extras.get("pycosmic"):
        notes.append("PyCosmic is not installed, so PyCosmic-dependent cleanest workflows may be unavailable.")
    elif extras.get("pycosmic_module"):
        notes.append(f"PyCosmic is available through module name {extras['pycosmic_module']}.")
    observed_versions = notebook_payload.get("observed_versions", [])
    installed_version = environment_payload.get("version")
    if observed_versions and installed_version and installed_version not in observed_versions:
        notes.append(
            "Notebook version skew detected: installed TEAREDUCE version "
            f"{installed_version} differs from notebook-observed versions {', '.join(observed_versions)}."
        )
    if notebook_payload.get("top_functions"):
        top = ", ".join(item["name"] for item in notebook_payload["top_functions"][:6])
        notes.append(f"Notebook usage concentrates on: {top}.")
    course_pack_summary = notebook_payload.get("course_pack_summary") or {}
    if course_pack_summary.get("stages"):
        stage_blob = ", ".join(course_pack_summary["stages"].keys())
        notes.append(
            "The scanned TEAREDUCE notebooks behave like a staged course pack rather than a single turnkey notebook set: "
            f"{stage_blob}."
        )
    if course_pack_summary.get("execution_profiles"):
        if course_pack_summary["execution_profiles"].get("parameterized_template"):
            notes.append("Some scanned notebooks are parameterized templates or auxiliary exec notebooks and should be treated as recipes, not turnkey runs.")
        if course_pack_summary["execution_profiles"].get("manual_or_web_assisted"):
            notes.append("Some scanned notebooks document browser-assisted or manual steps; keep those as guided recipes instead of forcing a full automation path.")
    return notes


def render_concise(payload: dict) -> str:
    teareduce = payload.get("teareduce") or {}
    notebooks = payload.get("notebooks") or {}
    course_pack = notebooks.get("course_pack_summary") or {}
    lines = [
        "TEAREDUCE healthcheck",
        f"- installed: {'yes' if teareduce.get('installed') else 'no'}",
    ]
    if teareduce.get("version"):
        lines.append(f"- version: {teareduce['version']}")
    lines.append(f"- notebooks inspected: {notebooks.get('count', 0)}")
    if course_pack.get("stages"):
        lines.append("- stages: " + ", ".join(f"{stage} ({count})" for stage, count in course_pack["stages"].items()))
    if course_pack.get("roles"):
        lines.append("- roles: " + ", ".join(f"{role}={count}" for role, count in course_pack["roles"].items()))
    if course_pack.get("execution_profiles"):
        lines.append(
            "- execution profiles: "
            + ", ".join(f"{name}={count}" for name, count in course_pack["execution_profiles"].items())
        )
    notes = payload.get("notes") or []
    if notes:
        lines.append("- notes:")
        lines.extend(f"  - {note}" for note in notes[:6])
    return "\n".join(lines)


def main():
    bootstrap = bootstrap_runtime_dirs()
    args = parse_args()
    environment_payload = inspect_teareduce_environment()
    notebook_payload = summarize_notebooks(args.paths, max_notebooks=args.max_notebooks)
    base_payload = {
        "tool": "teareduce_healthcheck",
        "environment": environment_summary(extra={"runtime_overrides": bootstrap}),
        "teareduce": environment_payload,
        "notebooks": notebook_payload,
        "notes": build_notes(environment_payload, notebook_payload),
    }
    status = "warning" if environment_payload.get("installed") else "blocked"
    payload = standard_tool_payload(
        "teareduce_healthcheck",
        status=status,
        notes=base_payload["notes"],
        artifacts={"summary_json": args.summary_json, "manifest_json": args.manifest_json},
        results={
            "environment": base_payload["environment"],
            "teareduce": environment_payload,
            "notebooks": notebook_payload,
        },
        qa={
            "status": status,
            "findings": ["teareduce_api_not_verified"] if environment_payload.get("installed") else ["teareduce_not_detected"],
            "metrics": {
                "notebook_count": notebook_payload.get("notebook_count", 0),
                "teareduce_installed": bool(environment_payload.get("installed")),
            },
        },
        legacy=base_payload,
    )
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n")
    if args.manifest_json:
        outputs = [args.summary_json] if args.summary_json else []
        write_manifest(
            args.manifest_json,
            inputs=[Path(item) for item in args.paths if Path(item).exists()],
            outputs=[Path(item) for item in outputs if Path(item).exists()],
            parameters={"max_notebooks": args.max_notebooks},
            command="teareduce_healthcheck.py",
            notes=payload["notes"],
            extra={"teareduce": environment_payload},
        )
    rendered_payload = sanitize_payload(payload)
    if args.concise:
        print(render_concise(rendered_payload))
    else:
        print(json.dumps(rendered_payload, indent=2, ensure_ascii=True))
    raise SystemExit(0 if environment_payload.get("installed") else 1)


if __name__ == "__main__":
    main()
