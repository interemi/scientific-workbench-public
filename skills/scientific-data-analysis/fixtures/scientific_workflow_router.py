#!/usr/bin/env python3
"""Dry-run workflow router for scientific-data-analysis v1.8.

The router is advisory only: it inventories an input path, recommends safe
capability routes, and emits an app-ready JSON envelope. It never executes the
recommended capabilities and never mutates input files.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import zipfile
from pathlib import Path
from typing import Any

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import describe_path, public_path, sanitize_payload, write_manifest
from _internal.public_contract import build_tool_payload
from _internal.public_surface_registry import load_public_surface_registry


TOOL = "scientific_workflow_router"
CONTRACT_VERSION = "1.8"
MAX_DIRECTORY_ITEMS = 250
MODULE_MAP_PATH = Path(__file__).resolve().parents[1] / "references" / "v2-3-mother-router-module-map.json"

TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".dat"}
NOTEBOOK_SUFFIXES = {".ipynb"}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"}
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".key", ".pages", ".md", ".rtf", ".tex"}
FITS_SUFFIXES = {".fits", ".fit", ".fts"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}

EXPOSURE_LIMITS = {
    "external_astro_tools_preflight.py": {
        "capability_id": "external_astro_tools_preflight",
        "exposure_mode": "optional",
        "v1_9_decision": "v1_9",
        "normal_user_action": False,
        "router_decision": "relegated_optional",
        "allowed_context": "Backend-readiness panel or explicit astronomy request for STILTS/TOPCAT/APT.",
        "reason": "Optional Java astronomy backends are not core analysis actions.",
        "safer_next": "Use native routes first; open optional backend preflight only when STILTS/TOPCAT/APT is explicitly needed.",
    },
    "external_astro_tools_local_validation.py": {
        "capability_id": "external_astro_tools_local_validation",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Maintainer validation on a machine intentionally configured with real optional astronomy backends.",
        "reason": "This validates local backend installations and is not a user analysis route.",
        "safer_next": "Use external_astro_tools_preflight.py for user-facing optional-backend readiness.",
    },
    "stilts_workbench.py": {
        "capability_id": "stilts_workbench",
        "exposure_mode": "optional",
        "v1_9_decision": "v2_0",
        "normal_user_action": False,
        "router_decision": "relegated_optional",
        "allowed_context": "Explicit STILTS/TOPCAT conversion, filtering, VOTable validation, or sky crossmatch.",
        "reason": "STILTS/TOPCAT is an optional Java astronomy backend and must not appear as a normal table action.",
        "safer_next": "Use catalog_workbench.py or profile_table.py unless the user explicitly needs STILTS/TOPCAT.",
    },
    "legacy_spectroscopy_envcheck.py": {
        "capability_id": "legacy_spectroscopy_envcheck",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit IRAF/iSTARMOD coursework or legacy spectroscopy environment check.",
        "reason": "macOS IRAF/iSTARMOD readiness is a narrow legacy route.",
        "safer_next": "Use inspect_fits.py or document_intake_workbench.py unless the task explicitly names the legacy stack.",
    },
    "fxcor_iraf_workbench.py prepare-session": {
        "capability_id": "fxcor_iraf_workbench.prepare-session",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit IRAF fxcor coursework workspace preparation.",
        "reason": "Preparing an IRAF fxcor workspace requires legacy coursework structure and expert confirmation.",
        "safer_next": "Use notebook/document/table routes for general work; use this only after legacy envcheck.",
    },
    "fxcor_iraf_workbench.py run-auto": {
        "capability_id": "fxcor_iraf_workbench.run-auto",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit automatic IRAF fxcor batch on a prepared copied workspace.",
        "reason": "Automatic fxcor batches depend on IRAF, prepared copies, and spectroscopy-specific judgement.",
        "safer_next": "Run only from a prepared legacy workspace; never expose as a normal action.",
    },
    "legacy_rv_coursework_workbench.py analyze": {
        "capability_id": "legacy_rv_coursework_workbench.analyze",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit legacy RV/vsini coursework result consolidation.",
        "reason": "The route assumes narrow coursework outputs and should not become a general table analysis action.",
        "safer_next": "Use profile_table.py or cross_domain_data_workbench.py for ordinary tables.",
    },
    "sb2_double_gaussian_workbench.py fit": {
        "capability_id": "sb2_double_gaussian_workbench.fit",
        "exposure_mode": "expert",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "expert_only",
        "allowed_context": "Explicit SB2 cross-correlation peak fitting with copied CCF data.",
        "reason": "Double-Gaussian SB2 fitting is domain-specific and parameter-sensitive.",
        "safer_next": "Use only in expert spectroscopy mode after confirming the data are CCF peaks.",
    },
    "li6708_equivalent_width_workbench.py measure": {
        "capability_id": "li6708_equivalent_width_workbench.measure",
        "exposure_mode": "expert",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "expert_only",
        "allowed_context": "Explicit Li I 6707.8 or nearby narrow spectral-line equivalent-width measurement.",
        "reason": "This is a narrow spectral-line tool and has no honest general-world analogue.",
        "safer_next": "Use profile_table.py, physical_qa.py, or a spectrum-specific expert route only when the line is real.",
    },
    "legacy_external_reference_check.py": {
        "capability_id": "legacy_external_reference_check",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit PW And / GZ Leo coursework reference check.",
        "reason": "The references are fixed to a narrow practice and are not a general literature checker.",
        "safer_next": "Use scientific_writeup_review.py for general report critique.",
    },
    "istarmod_workbench.py inspect-tree": {
        "capability_id": "istarmod_workbench.inspect-tree",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit iSTARMOD tree inspection.",
        "reason": "iSTARMOD tree structure is legacy spectroscopy state, not a normal file intake.",
        "safer_next": "Use inspect_data_container.py or document_intake_workbench.py for general folders.",
    },
    "istarmod_workbench.py prepare-copy": {
        "capability_id": "istarmod_workbench.prepare-copy",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit iSTARMOD copy preparation.",
        "reason": "Preparing a clean iSTARMOD copy is legacy workflow management, not general cleanup.",
        "safer_next": "Use generic container/document/notebook routes unless the source is a confirmed iSTARMOD tree.",
    },
    "legacy_spectroscopy_report_builder.py scaffold": {
        "capability_id": "legacy_spectroscopy_report_builder.scaffold",
        "exposure_mode": "legacy",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "legacy_expert_only",
        "allowed_context": "Explicit Spanish legacy spectroscopy coursework report scaffold.",
        "reason": "The scaffold is tailored to one legacy spectroscopy route.",
        "safer_next": "Use deliverable_factory.py scaffold or scientific_writeup_review.py for general reporting.",
    },
    "apt_workbench.py": {
        "capability_id": "apt_workbench",
        "exposure_mode": "optional",
        "v1_9_decision": "v2_0",
        "normal_user_action": False,
        "router_decision": "relegated_optional",
        "allowed_context": "Explicit APT batch route with saved APT preferences and copied source lists.",
        "reason": "APT batch mode depends on an optional GUI-configured backend and saved preferences provenance.",
        "safer_next": "Use native photometry routes unless APT compatibility is explicitly required.",
    },
    "teareduce_router.py": {
        "capability_id": "teareduce_router",
        "exposure_mode": "optional",
        "v1_9_decision": "v1_9",
        "normal_user_action": False,
        "router_decision": "relegated_optional",
        "allowed_context": "Explicit TEAREDUCE routing decision for astronomy reduction workflows.",
        "reason": "TEAREDUCE is an optional legacy/science backend choice, not a general package or table route.",
        "safer_next": "Use the native stack unless the task explicitly justifies TEAREDUCE.",
    },
    "spectra_ascii_coursework_workbench.py": {
        "capability_id": "spectra_ascii_coursework_workbench",
        "exposure_mode": "expert",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "expert_only",
        "allowed_context": "Explicit reduced ASCII spectra coursework bundle.",
        "reason": "This is a coursework/spectroscopy bundle route, not a general notebook or table workbench.",
        "safer_next": "Use notebook_workbench.py, profile_table.py, or cross_domain_data_workbench.py for general inputs.",
    },
    "keynote_export.py": {
        "capability_id": "keynote_export",
        "exposure_mode": "optional",
        "v1_9_decision": "v2_0",
        "normal_user_action": False,
        "router_decision": "relegated_optional",
        "allowed_context": "Explicit copied Keynote deck export when the GUI path is the only faithful option.",
        "reason": "Keynote export is macOS/GUI-bound and should not run as a silent normal document action.",
        "safer_next": "Use document_intake_workbench.py or quicklook_bridge.py unless faithful Keynote export is explicitly needed.",
    },
    "capability_probe_matrix.py": {
        "capability_id": "capability_probe_matrix",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Release probe matrix for public capabilities with no direct smoke tier.",
        "reason": "This is internal release validation, not user analysis.",
        "safer_next": "Use env_doctor.py or datanalysis_healthcheck.py for user-facing diagnostics.",
    },
    "portable_smoke_test.py": {
        "capability_id": "portable_smoke_test",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Release or install validation by a maintainer.",
        "reason": "Portable smoke tests validate the skill distribution, not a user dataset.",
        "safer_next": "Use env_doctor.py for normal machine readiness.",
    },
    "validate_skill_samples.py": {
        "capability_id": "validate_skill_samples",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Internal validation of packaged skill samples.",
        "reason": "Sample validation is a maintainer gate.",
        "safer_next": "Use a normal capability against copied user inputs.",
    },
    "sync_public_surface_docs.py": {
        "capability_id": "sync_public_surface_docs",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Release/doc synchronization check for generated public surface docs.",
        "reason": "This mutates or checks documentation snapshots and is not a user workflow.",
        "safer_next": "Use only as a release gate; do not expose in normal app actions.",
    },
    "skill_surface_audit.py": {
        "capability_id": "skill_surface_audit",
        "exposure_mode": "maintainer",
        "v1_9_decision": "no_procede",
        "normal_user_action": False,
        "router_decision": "maintainer_only",
        "allowed_context": "Internal public-surface audit for maintainers.",
        "reason": "This audits the skill itself, not user data.",
        "safer_next": "Use normal routes for user inputs; reserve this for release checks.",
    },
}

GENERAL_INPUT_KINDS = {
    "table_csv",
    "table_like",
    "table_folder",
    "mixed_folder",
    "notebook_ipynb",
    "notebook_folder",
    "archive_container",
    "archive_folder",
    "archive_like_unverified",
    "document_file",
    "document_folder",
    "image_file",
    "unknown_file",
    "generic_directory",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode in ("inspect", "plan", "explain"):
        subparser = subparsers.add_parser(mode, help=f"{mode} without executing downstream tools.")
        subparser.add_argument("path", help="Input file or directory to inspect for routing.")
        subparser.add_argument("--task", default="", help="Optional human task description to tune recommendations.")
        subparser.add_argument(
            "--capability",
            help="Capability label/id to explain. Especially useful with the 'explain' mode.",
        )
        subparser.add_argument("--summary-json", help="Optional app-ready summary JSON output path.")
        subparser.add_argument("--manifest-json", help="Optional provenance manifest output path.")
    return parser.parse_args()


def shell_join(argv: list[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in argv)


def command_payload(argv: list[str]) -> dict[str, Any]:
    return {
        "argv": argv,
        "cwd": public_path(Path.cwd()),
        "rendered": shell_join(argv),
        "redacted": True,
        "dry_run_only": True,
    }


def _safe_read_prefix(path: Path, size: int = 2880) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


def _is_probably_fits(path: Path) -> bool:
    prefix = _safe_read_prefix(path, 80)
    return prefix.startswith(b"SIMPLE  =") or prefix.startswith(b"XTENSION=")


def _is_probably_notebook(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("nbformat") is not None and isinstance(payload.get("cells"), list)


def _is_probably_zip(path: Path) -> bool:
    try:
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def _suffix(path: Path) -> str:
    return path.suffix.lower()


def _classify_file(path: Path) -> tuple[str, list[str], dict[str, Any]]:
    suffix = _suffix(path)
    warnings: list[str] = []
    facts: dict[str, Any] = {"suffix": suffix, "is_file": True}

    if suffix in FITS_SUFFIXES:
        facts["fits_header_detected"] = _is_probably_fits(path)
        if facts["fits_header_detected"]:
            return "fits_file", warnings, facts
        warnings.append("La extension sugiere FITS, pero la cabecera no parece FITS valida.")
        return "fits_like_unverified", warnings, facts

    if suffix in NOTEBOOK_SUFFIXES:
        facts["notebook_json_detected"] = _is_probably_notebook(path)
        if facts["notebook_json_detected"]:
            return "notebook_ipynb", warnings, facts
        warnings.append("La extension sugiere notebook, pero el JSON no parece un .ipynb valido.")
        return "notebook_like_unverified", warnings, facts

    if suffix in ARCHIVE_SUFFIXES:
        facts["zip_detected"] = _is_probably_zip(path) if suffix == ".zip" else None
        if suffix == ".zip" and not facts["zip_detected"]:
            warnings.append("La extension sugiere ZIP, pero la firma no valida como ZIP.")
            return "archive_like_unverified", warnings, facts
        return "archive_container", warnings, facts

    if suffix in TABLE_SUFFIXES:
        return "table_csv" if suffix == ".csv" else "table_like", warnings, facts
    if suffix in DOCUMENT_SUFFIXES:
        return "document_file", warnings, facts
    if suffix in IMAGE_SUFFIXES:
        return "image_file", warnings, facts
    return "unknown_file", ["No se reconocio una ruta principal segura para este formato."], facts


def _scan_directory(path: Path) -> tuple[list[Path], bool]:
    items: list[Path] = []
    truncated = False
    try:
        for item in path.rglob("*"):
            if item.is_file():
                items.append(item)
                if len(items) >= MAX_DIRECTORY_ITEMS:
                    truncated = True
                    break
    except OSError:
        truncated = True
    return items, truncated


def _classify_directory(path: Path) -> tuple[str, list[str], dict[str, Any]]:
    files, truncated = _scan_directory(path)
    suffix_counts: dict[str, int] = {}
    for item in files:
        suffix_counts[_suffix(item)] = suffix_counts.get(_suffix(item), 0) + 1

    facts: dict[str, Any] = {
        "is_directory": True,
        "file_count_scanned": len(files),
        "scan_truncated": truncated,
        "suffix_counts": dict(sorted(suffix_counts.items())),
    }
    warnings: list[str] = []
    if truncated:
        warnings.append(f"El inventario se limito a {MAX_DIRECTORY_ITEMS} archivos para mantener el dry-run ligero.")
    if not files:
        return "empty_directory", warnings, facts

    suffixes = set(suffix_counts)
    has_tables = bool(suffixes & TABLE_SUFFIXES)
    has_docs = bool(suffixes & DOCUMENT_SUFFIXES)
    has_notebooks = bool(suffixes & NOTEBOOK_SUFFIXES)
    has_archives = bool(suffixes & ARCHIVE_SUFFIXES)
    has_fits = bool(suffixes & FITS_SUFFIXES)
    has_images = bool(suffixes & IMAGE_SUFFIXES)
    facts.update(
        {
            "has_tables": has_tables,
            "has_documents": has_docs,
            "has_notebooks": has_notebooks,
            "has_archives": has_archives,
            "has_fits": has_fits,
            "has_images": has_images,
        }
    )

    feature_count = sum([has_tables, has_docs, has_notebooks, has_archives, has_fits, has_images])
    if feature_count >= 2:
        return "mixed_folder", warnings, facts
    if has_tables:
        return "table_folder", warnings, facts
    if has_docs:
        return "document_folder", warnings, facts
    if has_notebooks:
        return "notebook_folder", warnings, facts
    if has_archives:
        return "archive_folder", warnings, facts
    if has_fits:
        return "fits_folder", warnings, facts
    if has_images:
        return "image_folder", warnings, facts
    return "generic_directory", warnings + ["La carpeta no contiene formatos reconocidos por el router."], facts


def inspect_input(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    descriptor = describe_path(path)
    if not path.exists():
        return {
            "path": path,
            "input_kind": "missing_path",
            "warnings": [],
            "facts": {"exists": False},
            "inputs": [{"path": public_path(path), "role": "primary_input", "kind": "missing_path", "exists": False}],
            "descriptor": descriptor,
        }
    if path.is_dir():
        kind, warnings, facts = _classify_directory(path)
    elif path.is_file():
        kind, warnings, facts = _classify_file(path)
    else:
        kind, warnings, facts = "unsupported_path", ["La ruta existe pero no es archivo ni carpeta ordinaria."], {}
    return {
        "path": path,
        "input_kind": kind,
        "warnings": warnings,
        "facts": facts,
        "inputs": [
            {
                "path": public_path(path),
                "role": "primary_input",
                "kind": kind,
                "exists": True,
                "is_directory": path.is_dir(),
                "is_file": path.is_file(),
            }
        ],
        "descriptor": descriptor,
    }


def run_placeholder() -> str:
    return "<run>"


_MODULE_MAP_CACHE: dict[str, Any] | None = None
_KNOWN_CAPABILITY_ALIASES_CACHE: set[str] | None = None
MODULE_MAP_MAX_DEPTH = 8

_FALLBACK_MODULE_RULES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("smoke", "sync_public_surface", "validate_skill", "skill_surface", "capability_probe", "local_validation"), "maintainer", "scientific-data-maintainer", "maintainer_only"),
    (("stilts", "topcat", "apt_workbench", "teareduce"), "astro", "scientific-data-astro", "blocked_optional"),
    (("fits", "astrometry", "photometry", "radial_velocity", "spectr", "catalog", "physical_qa"), "astro", "scientific-data-astro", "delegated"),
    (("document", "office", "presentation", "latex", "semantic_diff", "quicklook", "keynote", "iwork"), "documents", "scientific-data-documents", "delegated"),
    (("notebook", "table", "timeseries", "duckdb", "profile_table", "cross_domain", "bootstrap"), "notebooks", "scientific-data-notebooks", "delegated"),
)


class ModuleMapIntegrityError(RuntimeError):
    """Raised when canonical routing metadata cannot be trusted."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _known_capability_aliases() -> set[str]:
    global _KNOWN_CAPABILITY_ALIASES_CACHE
    if _KNOWN_CAPABILITY_ALIASES_CACHE is not None:
        return _KNOWN_CAPABILITY_ALIASES_CACHE
    aliases: set[str] = set()
    for item in load_public_surface_registry():
        for value in (item.get("id"), item.get("label"), item.get("script")):
            if value:
                aliases.add(str(value).lower())
        label = str(item.get("label", ""))
        if ".py " in label:
            aliases.add(label.replace(".py ", ".").lower())
    _KNOWN_CAPABILITY_ALIASES_CACHE = aliases
    return aliases


def _load_module_map(path: Path, *, max_depth: int = MODULE_MAP_MAX_DEPTH) -> dict[str, Any]:
    family_root = MODULE_MAP_PATH.parents[2].resolve()
    current = path.expanduser().absolute()
    visited: list[Path] = []
    for depth in range(max_depth + 1):
        resolved = current.resolve()
        if not _is_within(resolved, family_root):
            raise ModuleMapIntegrityError(f"module map escapes skill family: {resolved}")
        if resolved in visited:
            chain = " -> ".join(str(item) for item in [*visited, resolved])
            raise ModuleMapIntegrityError(f"module map cycle detected: {chain}")
        if not resolved.is_file():
            raise ModuleMapIntegrityError(f"module map target is missing: {resolved}")
        visited.append(resolved)
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModuleMapIntegrityError(f"invalid module map {resolved}: {type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ModuleMapIntegrityError(f"module map must be a JSON object: {resolved}")
        capabilities = payload.get("capabilities")
        if isinstance(capabilities, list):
            break
        target = payload.get("canonical_fixture")
        if not target:
            raise ModuleMapIntegrityError(f"module map has neither capabilities nor canonical_fixture: {resolved}")
        # Resolve relative pointers from the public stub location, not from a
        # symlink's physical target under .cache.
        current = current.parent / str(target)
    else:
        raise ModuleMapIntegrityError(f"module map chain exceeds max depth {max_depth}: {path}")

    required = {"capability_id", "owner_module", "child_skill_path", "delegation_mode", "wrapper_status"}
    if len(capabilities) != 61:
        raise ModuleMapIntegrityError(f"module map must contain exactly 61 capabilities, found {len(capabilities)}")
    identifiers: list[str] = []
    for index, item in enumerate(capabilities):
        if not isinstance(item, dict):
            raise ModuleMapIntegrityError(f"module map capability {index} is not an object")
        missing = sorted(required - set(item))
        if missing:
            raise ModuleMapIntegrityError(f"module map capability {index} misses fields: {', '.join(missing)}")
        identifiers.append(str(item["capability_id"]))
    if len(set(identifiers)) != 61:
        raise ModuleMapIntegrityError("module map capability_id values must be unique")
    canonical_registry_ids = {str(item["id"]).lower() for item in load_public_surface_registry()}
    if {item.lower() for item in identifiers} != canonical_registry_ids:
        missing = sorted(canonical_registry_ids - {item.lower() for item in identifiers})
        extra = sorted({item.lower() for item in identifiers} - canonical_registry_ids)
        raise ModuleMapIntegrityError(f"module map IDs differ from registry; missing={missing}, extra={extra}")
    payload["_resolved_path"] = str(resolved)
    return payload


def _module_map() -> dict[str, Any]:
    global _MODULE_MAP_CACHE
    if _MODULE_MAP_CACHE is not None:
        return _MODULE_MAP_CACHE
    payload = _load_module_map(MODULE_MAP_PATH)
    by_key: dict[str, dict[str, Any]] = {}
    for item in payload.get("capabilities", []):
        keys = {
            str(item.get("capability_id", "")).lower(),
            str(item.get("label", "")).lower(),
        }
        label = str(item.get("label", ""))
        if ".py " in label:
            keys.add(label.replace(".py ", ".").lower())
        for key in {key for key in keys if key}:
            if key in by_key and by_key[key] is not item:
                raise ModuleMapIntegrityError(f"duplicate module map alias: {key}")
            by_key[key] = item
    payload["_by_key"] = by_key
    _MODULE_MAP_CACHE = payload
    return payload


def module_metadata_for(label: str, capability_id: str | None = None) -> dict[str, Any]:
    aliases = {label.lower()}
    if capability_id:
        aliases.add(capability_id.lower())
    if ".py " in label:
        aliases.add(label.replace(".py ", ".").lower())
    try:
        index = _module_map().get("_by_key", {})
    except (ModuleMapIntegrityError, OSError, ValueError) as exc:
        return {
            "owner_module": "unknown",
            "child_skill_path": None,
            "delegation_mode": "blocked_contract_error",
            "wrapper_status": "module_map_error",
            "module_map_error": str(exc),
        }
    record = next((index[alias] for alias in aliases if alias in index), None)
    if not record:
        if aliases & _known_capability_aliases():
            return {
                "owner_module": "unknown",
                "child_skill_path": None,
                "delegation_mode": "blocked_contract_error",
                "wrapper_status": "module_map_missing_known_capability",
            }
        key = " ".join(sorted(aliases))
        for needles, owner, child, mode in _FALLBACK_MODULE_RULES:
            if any(needle in key for needle in needles):
                return {
                    "owner_module": owner,
                    "child_skill_path": child,
                    "delegation_mode": mode,
                    "wrapper_status": "compact_stub_fallback",
                }
        return {
            "owner_module": "mother",
            "child_skill_path": "scientific-data-analysis",
            "delegation_mode": "direct",
            "wrapper_status": "module_map_missing",
        }
    return {
        "owner_module": record["owner_module"],
        "child_skill_path": record["child_skill_path"],
        "delegation_mode": record["delegation_mode"],
        "wrapper_status": record["wrapper_status"],
    }


def route(
    label: str,
    capability_id: str,
    reason: str,
    confidence: str,
    command: str,
    *,
    app_readiness: str = "app_ready",
    artifact_types: list[str] | None = None,
    required_backends: list[str] | None = None,
    side_effect_policy: str = "read_only_input_new_outputs",
    workflow_mode: str = "normal",
    requires_confirmation: bool | None = None,
    uses_inputs: bool = True,
    uses_previous_output: bool = False,
    app_raw_arguments: str = "",
) -> dict[str, Any]:
    if requires_confirmation is None:
        requires_confirmation = workflow_mode != "normal" or app_readiness != "app_ready"
    record = {
        "label": label,
        "capability_id": capability_id,
        "app_readiness": app_readiness,
        "confidence": confidence,
        "reason": reason,
        "dry_run_command": command,
        "artifact_types": artifact_types or ["summary_json"],
        "required_backends": required_backends or ["python-stdlib"],
        "side_effect_policy": side_effect_policy,
        "workflow_mode": workflow_mode,
        "requires_confirmation": requires_confirmation,
        "uses_inputs": uses_inputs,
        "uses_previous_output": uses_previous_output,
        "app_raw_arguments": app_raw_arguments,
    }
    record.update(module_metadata_for(label, capability_id))
    return record


def reject(label: str, reason: str, *, safer_next: str | None = None, **extra: Any) -> dict[str, Any]:
    record = {"label": label, "reason": reason}
    if safer_next:
        record["safer_next"] = safer_next
    record.update(extra)
    return record


def exposure_record(label: str, info: dict[str, Any]) -> dict[str, Any]:
    record = {
        "label": label,
        "capability_id": info["capability_id"],
        "exposure_mode": info["exposure_mode"],
        "v1_9_decision": info["v1_9_decision"],
        "normal_user_action": info["normal_user_action"],
        "router_decision": info["router_decision"],
        "allowed_context": info["allowed_context"],
        "reason": info["reason"],
        "safer_next": info["safer_next"],
    }
    record.update(module_metadata_for(label, info["capability_id"]))
    return record


def exposure_rejection(label: str, info: dict[str, Any]) -> dict[str, Any]:
    record = reject(
        label,
        info["reason"],
        safer_next=info["safer_next"],
        capability_id=info["capability_id"],
        exposure_mode=info["exposure_mode"],
        v1_9_decision=info["v1_9_decision"],
        normal_user_action=info["normal_user_action"],
        router_decision=info["router_decision"],
        allowed_context=info["allowed_context"],
    )
    record.update(module_metadata_for(label, info["capability_id"]))
    return record


def append_exposure_rejections(
    profile: dict[str, Any],
    recommendations: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> None:
    if profile["input_kind"] not in GENERAL_INPUT_KINDS:
        return
    existing_labels = {item.get("label") for item in rejected}
    existing_ids = {item.get("capability_id") for item in rejected}
    recommended_ids = {item.get("capability_id") for item in recommendations}
    for label, info in EXPOSURE_LIMITS.items():
        if (
            label not in existing_labels
            and info["capability_id"] not in existing_ids
            and info["capability_id"] not in recommended_ids
        ):
            rejected.append(exposure_rejection(label, info))


def recommended_for(profile: dict[str, Any], task: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kind = profile["input_kind"]
    path = public_path(profile["path"])
    run = run_placeholder()
    task_l = task.lower()
    wants_timeseries = any(
        word in task_l
        for word in (
            "time series",
            "timeseries",
            "serie temporal",
            "series temporales",
            "forecast",
            "forecasting",
            "prediccion",
            "prevision",
            "tendencia temporal",
        )
    )
    wants_sensor_qa = any(
        word in task_l
        for word in (
            "sensor",
            "medicion",
            "medición",
            "qa",
            "quality",
            "calidad",
            "nan",
            "inf",
            "rango",
            "outlier",
            "incertidumbre",
        )
    )
    wants_document_intake = any(
        word in task_l
        for word in (
            "document",
            "documento",
            "documentos",
            "administrativo",
            "administrativa",
            "admin",
            "intake",
            "handoff",
            "informe",
            "pdf",
            "docx",
        )
    )
    negates_stilts = any(phrase in task_l for phrase in ("no stilts", "sin stilts", "not stilts", "no topcat", "sin topcat"))
    wants_stilts = any(word in task_l for word in ("stilts", "topcat", "votable")) and not negates_stilts
    negates_apt = any(phrase in task_l for phrase in ("no apt", "sin apt", "not apt"))
    wants_apt = any(
        word in task_l.split()
        for word in ("apt", "aperture-photometry-tool", "aperture_photometry_tool")
    ) and not negates_apt
    recommendations: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    if kind in {"table_csv", "table_like", "table_folder"}:
        if wants_timeseries:
            recommendations.append(
                route(
                    "timeseries_forecasting_workbench.py",
                    "timeseries_forecasting_workbench",
                    "La tarea declara serie temporal/forecasting; usar la ruta dedicada si hay columnas fecha/valor claras.",
                    "high",
                    f"python scripts/timeseries_forecasting_workbench.py --output-dir {run}/forecast --data-path {shlex.quote(path)} --date-column <date_column> --value-column <value_column> --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    artifact_types=["summary_json", "manifest_json", "notebook_ipynb", "report_md", "handoff_bundle"],
                    required_backends=["datanalysis"],
                )
            )
        if wants_sensor_qa:
            recommendations.append(
                route(
                    "physical_qa.py",
                    "physical_qa",
                    "La tarea pide QA de medicion/sensor; esta ruta detecta NaN/Inf, rangos sospechosos y riesgos ligeros.",
                    "high",
                    f"python scripts/physical_qa.py {shlex.quote(path)} --summary-json {run}/summary.json",
                    artifact_types=["summary_json", "qa_report"],
                    side_effect_policy="read_only",
                )
            )
        recommendations.extend(
            [
                route(
                    "profile_table.py",
                    "profile_table",
                    "Entrada tabular: perfila columnas, tipos, nulos y riesgos sin modificar el original.",
                    "high",
                    f"python scripts/profile_table.py {shlex.quote(path)} --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    artifact_types=["summary_json", "manifest_json", "qa_report"],
                ),
                route(
                    "cross_domain_data_workbench.py",
                    "cross_domain_data_workbench",
                    "Buen segundo paso si la tabla pertenece a un paquete o necesita informe de handoff.",
                    "medium",
                    f"python scripts/cross_domain_data_workbench.py {shlex.quote(path)} --output-dir {run}/cross_domain --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    artifact_types=["summary_json", "manifest_json", "report_md", "table_csv", "handoff_bundle"],
                ),
            ]
        )
        if any(word in task_l for word in ("sql", "query", "join", "duckdb", "consulta")):
            recommendations.append(
                route(
                    "duckdb_workbench.py",
                    "duckdb_workbench",
                    "La tarea menciona consulta/join/SQL; DuckDB puede ser util si el backend opcional existe.",
                    "medium",
                    f"python scripts/duckdb_workbench.py {shlex.quote(path)} --sql <query.sql> --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    app_readiness="blocked_optional",
                    artifact_types=["summary_json", "manifest_json", "table_csv", "log_txt"],
                    required_backends=["datanalysis", "duckdb-optional"],
                    workflow_mode="optional",
                )
            )
        rejected.extend(
            [
                reject("inspect_fits.py", "La entrada no parece FITS; usar una ruta FITS aqui seria un falso positivo."),
                reject("notebook_workbench.py execute-copy", "No es un notebook; no hay celdas que ejecutar."),
                reject("legacy/astro narrow routes", "No hay senales de flujo legacy o astro que justifiquen rutas expertas."),
            ]
        )
        if not wants_timeseries:
            rejected.append(
                reject(
                    "timeseries_forecasting_workbench.py",
                    "No se menciono una necesidad temporal/forecasting; perfilar la tabla primero es mas seguro.",
                )
            )
        if not wants_sensor_qa:
            rejected.append(
                reject("physical_qa.py", "No se pidio QA fisica/de sensor; perfilar columnas primero evita sobrediagnosticar.")
            )

    elif kind == "mixed_folder":
        cross_domain_route = route(
            "cross_domain_data_workbench.py",
            "cross_domain_data_workbench",
            "Carpeta mixta: inventaria tablas y crea un informe de paquete sin ejecutar logica pesada.",
            "high",
            f"python scripts/cross_domain_data_workbench.py {shlex.quote(path)} --output-dir {run}/cross_domain --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
            artifact_types=["summary_json", "manifest_json", "report_md", "table_csv", "handoff_bundle"],
        )
        document_route = route(
            "document_intake_workbench.py",
            "document_intake_workbench",
            "Hay documentos o material mixto; esta ruta resume riesgos de intake y handoff.",
            "high",
            f"python scripts/document_intake_workbench.py {shlex.quote(path)} --output-dir {run}/intake --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
            artifact_types=["summary_json", "manifest_json", "report_md", "table_csv", "handoff_bundle"],
        )
        recommendations.extend(
            [document_route, cross_domain_route] if wants_document_intake else [cross_domain_route, document_route]
        )
        if profile["facts"].get("has_archives"):
            recommendations.append(
                route(
                    "inspect_data_container.py",
                    "inspect_data_container",
                    "La carpeta contiene contenedores/archives; inspeccionarlos primero evita descomprimir a ciegas.",
                    "medium",
                    f"python scripts/inspect_data_container.py {shlex.quote(path)} --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    artifact_types=["summary_json", "manifest_json", "qa_report"],
                )
            )
        rejected.extend(
            [
                reject("profile_table.py", "Demasiado estrecho como primera ruta para una carpeta mixta.", safer_next="cross_domain_data_workbench.py"),
                reject("fits_rgb_batch.py", "Solo procede si la carpeta es un grupo FITS/RGB claro; aqui hay mezcla de formatos."),
                reject("maintainer_only gates", "No son acciones de usuario normal ni diagnostico de paquete."),
            ]
        )

    elif kind in {"notebook_ipynb", "notebook_folder"}:
        recommendations.extend(
            [
                route(
                    "coursework_notebook_fidelity_check.py",
                    "coursework_notebook_fidelity_check",
                    "Primero inspecciona el notebook heredado sin ejecutarlo ni modificarlo.",
                    "high",
                    f"python scripts/coursework_notebook_fidelity_check.py {shlex.quote(path)} --report-md {run}/fidelity.md --summary-json {run}/summary.json",
                    app_readiness="app_ready_partial",
                    artifact_types=["summary_json", "report_md", "qa_report"],
                    side_effect_policy="read_only",
                ),
                route(
                    "notebook_workbench.py execute-copy",
                    "notebook_workbench.execute-copy",
                    "Si el inspect pasa, ejecuta una copia controlada y conserva el original intacto.",
                    "medium",
                    f"python scripts/notebook_workbench.py execute-copy {shlex.quote(path)} --output-dir {run}/notebook --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                    artifact_types=["summary_json", "manifest_json", "notebook_ipynb", "log_txt"],
                    required_backends=["datanalysis", "jupyter"],
                    side_effect_policy="copies_only_no_original_mutation",
                    requires_confirmation=True,
                ),
            ]
        )
        rejected.extend(
            [
                reject("profile_table.py", "Un notebook no es una tabla plana; extraer tablas seria una decision posterior."),
                reject("timeseries_forecasting_workbench.py", "No asumir forecasting solo porque haya un notebook."),
                reject("raw notebook execution", "Ejecutar el original directamente romperia la politica de copias."),
            ]
        )

    elif kind in {"fits_file", "fits_folder"}:
        recommendations.extend(
            [
                route(
                    "inspect_fits.py",
                    "inspect_fits",
                    "La entrada parece FITS valida; empezar por inspeccion y preview es la ruta segura.",
                    "high",
                    f"python scripts/inspect_fits.py {shlex.quote(path)} --summary-json {run}/summary.json --manifest-json {run}/manifest.json --preview {run}/preview.png",
                    artifact_types=["summary_json", "manifest_json", "preview_png", "qa_report"],
                    workflow_mode="expert",
                ),
                route(
                    "physical_qa.py",
                    "physical_qa",
                    "Puede detectar NaN/Inf/rangos sospechosos antes de derivar productos.",
                    "medium",
                    f"python scripts/physical_qa.py {shlex.quote(path)} --summary-json {run}/summary.json",
                    artifact_types=["summary_json", "qa_report"],
                ),
            ]
        )
        if kind == "fits_folder":
            recommendations.append(
                route(
                    "fits_rgb_batch.py",
                    "fits_rgb_batch",
                    "Solo si el objetivo real es construir RGB/pseudo-RGB desde un grupo FITS copiado.",
                    "low",
                    f"python scripts/fits_rgb_batch.py --input-root {shlex.quote(path)} --output-dir {run}/rgb --summary-json {run}/summary.json",
                    app_readiness="app_ready_partial",
                    artifact_types=["summary_json", "manifest_json", "preview_png", "report_md", "handoff_bundle"],
                    required_backends=["datanalysis"],
                    workflow_mode="expert",
                )
            )
        rejected.extend(
            [
                reject("document_intake_workbench.py", "No es un paquete documental; FITS requiere ruta cientifica."),
                reject("photometric_solution.py", "No hay tabla de estandares fotometricos ni contrato de calibracion."),
            ]
        )

    elif kind == "fits_like_unverified":
        recommendations.append(
            route(
                "inspect_fits.py",
                "inspect_fits",
                "La extension pide verificacion FITS, pero debe esperarse WARNING/BLOCKED si Astropy no puede abrirlo.",
                "low",
                f"python scripts/inspect_fits.py {shlex.quote(path)} --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                artifact_types=["summary_json", "manifest_json", "qa_report"],
                workflow_mode="expert",
            )
        )
        rejected.extend(
            [
                reject("fits_rgb_batch.py", "No derivar RGB desde un archivo que no verifica como FITS."),
                reject("astrometry_net_workbench.py", "No intentar resolver astrometria hasta confirmar que el archivo es imagen valida."),
                reject("photometric_solution.py", "La entrada no es una tabla de calibracion."),
            ]
        )

    elif kind in {"archive_container", "archive_folder", "archive_like_unverified"}:
        recommendations.append(
            route(
                "inspect_data_container.py",
                "inspect_data_container",
                "Primero inspecciona el contenedor en seco para evitar extraccion o ejecucion accidental.",
                "high" if kind != "archive_like_unverified" else "low",
                f"python scripts/inspect_data_container.py {shlex.quote(path)} --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                artifact_types=["summary_json", "manifest_json", "qa_report"],
            )
        )
        rejected.extend(
            [
                reject("cross_domain_data_workbench.py", "Primero hay que saber que contiene el archivo comprimido."),
                reject("notebook_workbench.py execute-copy", "No ejecutar notebooks dentro de un contenedor sin inspeccion previa."),
            ]
        )

    elif kind in {"document_file", "document_folder"}:
        recommendations.append(
            route(
                "document_intake_workbench.py",
                "document_intake_workbench",
                "Entrada documental: inspecciona handoff, riesgos y estructura sin editar originales.",
                "high",
                f"python scripts/document_intake_workbench.py {shlex.quote(path)} --output-dir {run}/intake --summary-json {run}/summary.json --manifest-json {run}/manifest.json",
                artifact_types=["summary_json", "manifest_json", "report_md", "table_csv", "handoff_bundle"],
            )
        )
        rejected.extend(
            [
                reject("profile_table.py", "No es una tabla plana."),
                reject("notebook_workbench.py", "No es un notebook."),
            ]
        )

    elif kind in {"missing_path", "empty_directory"}:
        rejected.extend(
            [
                reject("all analysis capabilities", "No hay input legible que analizar."),
                reject("destructive repair", "El router no crea, borra ni repara rutas de entrada."),
            ]
        )

    else:
        rejected.extend(
            [
                reject("normal app routes", "El formato no fue reconocido con suficiente confianza."),
                reject("domain-specific routes", "No hay senales de dominio suficientes para recomendar una ruta experta."),
            ]
        )

    if wants_stilts:
        recommendations.insert(
            0,
            route(
                "stilts_workbench.py",
                "stilts_workbench",
                "La tarea pide STILTS/TOPCAT/VOTable de forma explicita; ejecutar primero el preflight opcional.",
                "high",
                f"python scripts/stilts_workbench.py preflight --summary-json {run}/summary.json",
                app_readiness="blocked_optional",
                artifact_types=["summary_json", "log_txt"],
                required_backends=["java-optional", "stilts-optional"],
                workflow_mode="optional",
                uses_inputs=False,
            ),
        )
    if wants_apt:
        recommendations.insert(
            0,
            route(
                "apt_workbench.py",
                "apt_workbench",
                "La tarea pide APT de forma explicita; ejecutar primero el preflight opcional y revisar preferencias.",
                "high",
                f"python scripts/apt_workbench.py preflight --summary-json {run}/summary.json",
                app_readiness="blocked_optional",
                artifact_types=["summary_json", "log_txt"],
                required_backends=["java-optional", "apt-optional"],
                workflow_mode="optional",
                uses_inputs=False,
            ),
        )

    append_exposure_rejections(profile, recommendations, rejected)
    return recommendations, rejected


def status_for(profile: dict[str, Any], recommendations: list[dict[str, Any]]) -> str:
    kind = profile["input_kind"]
    if kind in {"missing_path", "empty_directory"}:
        return "blocked"
    if kind.endswith("_unverified") or kind in {"unknown_file", "generic_directory", "unsupported_path"}:
        return "warning"
    if not recommendations:
        return "warning"
    if profile.get("warnings"):
        return "warning"
    return "ok"


def safety_notes_for(profile: dict[str, Any]) -> list[str]:
    notes = [
        "Dry-run solamente: no se ejecutaron capabilities recomendadas.",
        "El router no modifica originales ni crea outputs derivados salvo summary/manifest solicitados.",
        "Usar copias temporales para ejecutar cualquier capability posterior.",
    ]
    if profile["input_kind"] in {"fits_like_unverified", "notebook_like_unverified", "archive_like_unverified"}:
        notes.append("La extension no basta para confiar en el formato; validar antes de derivar productos.")
    if profile["input_kind"] == "mixed_folder":
        notes.append("La carpeta mixta debe tratarse como paquete: inventario primero, ejecucion despues.")
    if profile["input_kind"] == "notebook_ipynb":
        notes.append("No ejecutar el notebook original; usar execute-copy si se decide correrlo.")
    return notes


def required_backends_for(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {
        "python-stdlib": {
            "backend": "python-stdlib",
            "required_for": ["scientific_workflow_router"],
            "availability": "assumed",
        }
    }
    for item in recommendations:
        for backend in item.get("required_backends", []):
            record = seen.setdefault(
                backend,
                {
                    "backend": backend,
                    "required_for": [],
                    "availability": "unknown" if backend != "python-stdlib" else "assumed",
                },
            )
            record["required_for"].append(item["label"])
    return list(seen.values())


def plan_steps_for(mode: str, profile: dict[str, Any], recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kind = profile["input_kind"]
    if kind == "missing_path":
        return [
            {
                "step": 1,
                "action": "provide_existing_path",
                "description": "Elegir una ruta existente o copiar el input real a una carpeta temporal.",
                "dry_run": True,
            }
        ]
    if kind == "empty_directory":
        return [
            {
                "step": 1,
                "action": "add_inputs",
                "description": "La carpeta esta vacia; anadir/copiar archivos antes de seleccionar capability.",
                "dry_run": True,
            }
        ]

    steps = [
        {
            "step": 1,
            "action": "review_router_summary",
            "description": "Confirmar tipo de input, warnings y politica de seguridad.",
            "dry_run": True,
        }
    ]
    for index, item in enumerate(recommendations[:4], start=2):
        steps.append(
            {
                "step": index,
                "action": "candidate_capability",
                "capability": item["label"],
                "description": item["reason"],
                "command": item["dry_run_command"],
                "workflow_mode": item["workflow_mode"],
                "requires_confirmation": item["requires_confirmation"],
                "owner_module": item.get("owner_module"),
                "child_skill_path": item.get("child_skill_path"),
                "delegation_mode": item.get("delegation_mode"),
                "wrapper_status": item.get("wrapper_status"),
                "dry_run": True,
            }
        )
    if mode == "plan":
        steps.append(
            {
                "step": len(steps) + 1,
                "action": "execute_only_after_copy",
                "description": "Ejecutar la capability elegida solo sobre copia temporal o ruta de trabajo controlada.",
                "dry_run": True,
            }
        )
    return steps


def next_actions_for(profile: dict[str, Any], recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    kind = profile["input_kind"]
    if kind == "missing_path":
        return [
            {
                "label": "Seleccionar una ruta existente o copiar el input a temporal.",
                "kind": "user_input",
                "priority": "high",
            }
        ]
    if kind == "empty_directory":
        return [
            {
                "label": "Anadir archivos a la carpeta temporal antes de planificar.",
                "kind": "user_input",
                "priority": "high",
            }
        ]
    if recommendations:
        return [
            {
                "label": f"Revisar y, si procede, ejecutar en copia: {recommendations[0]['label']}",
                "kind": "route_decision",
                "priority": "normal",
            }
        ]
    return [
        {
            "label": "Pedir una decision humana: el router no reconoce una ruta segura.",
            "kind": "human_review",
            "priority": "high",
        }
    ]


def explain_capability(
    requested: str | None,
    recommendations: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not requested:
        return None
    target = requested.strip().lower()
    for item in recommendations:
        aliases = {item["label"].lower(), item["capability_id"].lower()}
        if target in aliases or target.replace(".py", "") in aliases:
            return {
                "capability": requested,
                "decision": "applies",
                "reason": item["reason"],
                "confidence": item["confidence"],
                "recommended_command": item["dry_run_command"],
                "owner_module": item.get("owner_module"),
                "child_skill_path": item.get("child_skill_path"),
                "delegation_mode": item.get("delegation_mode"),
                "wrapper_status": item.get("wrapper_status"),
            }
    for item in rejected:
        if target in item["label"].lower():
            module_metadata = module_metadata_for(item["label"], item.get("capability_id"))
            for key in ("owner_module", "child_skill_path", "delegation_mode", "wrapper_status"):
                if item.get(key) is not None:
                    module_metadata[key] = item[key]
            return {
                "capability": requested,
                "decision": item.get("router_decision", "not_applicable"),
                "reason": item["reason"],
                "confidence": "high",
                "exposure_mode": item.get("exposure_mode"),
                "normal_user_action": item.get("normal_user_action"),
                "allowed_context": item.get("allowed_context"),
                **module_metadata,
            }
    for label, info in EXPOSURE_LIMITS.items():
        aliases = {label.lower(), info["capability_id"].lower()}
        if target in aliases or target.replace(".py", "") in aliases:
            return {
                "capability": requested,
                "decision": info["router_decision"],
                "reason": info["reason"],
                "confidence": "high",
                "exposure_mode": info["exposure_mode"],
                "normal_user_action": info["normal_user_action"],
                "allowed_context": info["allowed_context"],
                **module_metadata_for(label, info["capability_id"]),
            }
    return {
        "capability": requested,
        "decision": "unknown",
        "reason": "El router no tiene evidencia suficiente para recomendar o rechazar esa capability para este input.",
        "confidence": "low",
        **module_metadata_for(requested),
    }


def build_router_payload(args: argparse.Namespace) -> dict[str, Any]:
    profile = inspect_input(args.path)
    recommendations, rejected = recommended_for(profile, args.task)
    status = status_for(profile, recommendations)
    safety_notes = safety_notes_for(profile)
    plan_steps = plan_steps_for(args.mode, profile, recommendations)
    required_backends = required_backends_for(recommendations)
    explanation = explain_capability(args.capability, recommendations, rejected)
    warnings = list(profile.get("warnings") or [])
    if explanation and explanation["decision"] == "unknown":
        warnings.append(explanation["reason"])
    if status == "blocked":
        findings = [f"No hay input ejecutable para `{profile['input_kind']}`."]
    else:
        findings = warnings

    artifacts = {"summary_json": args.summary_json, "manifest_json": args.manifest_json}
    results = {
        "mode": args.mode,
        "task": args.task,
        "input_kind": profile["input_kind"],
        "input_profile": sanitize_payload(
            {
                "descriptor": profile["descriptor"],
                "facts": profile["facts"],
                "warnings": warnings,
            }
        ),
        "recommended_capabilities": recommendations,
        "rejected_capabilities": rejected,
        "exposure_modes": [exposure_record(label, info) for label, info in EXPOSURE_LIMITS.items()],
        "plan_steps": plan_steps,
        "required_backends": required_backends,
        "safety_notes": safety_notes,
        "module_map": {
            "contract_reference": "references/v2-3-mother-router-contract.md",
            "map_reference": "references/v2-3-mother-router-module-map.json",
            "public_capability_count": _module_map().get("public_capability_count"),
            "routing_states": list((_module_map().get("routing_states") or {}).keys()),
        },
    }
    if explanation:
        results["capability_explanation"] = explanation

    payload = build_tool_payload(
        TOOL,
        status=status,
        notes=safety_notes + warnings,
        artifacts=artifacts,
        results=results,
        qa={
            "status": status,
            "findings": findings,
            "metrics": {
                "recommendation_count": len(recommendations),
                "rejected_count": len(rejected),
                "plan_step_count": len(plan_steps),
            },
        },
        include_environment=True,
    )

    payload.update(
        sanitize_payload(
            {
                "capability_id": TOOL,
                "capability_label": "scientific_workflow_router.py",
                "command": command_payload(list(sys.argv)),
                "inputs": profile["inputs"],
                "input_kind": profile["input_kind"],
                "recommended_capabilities": recommendations,
                "rejected_capabilities": rejected,
                "exposure_modes": [exposure_record(label, info) for label, info in EXPOSURE_LIMITS.items()],
                "plan_steps": plan_steps,
                "required_backends": required_backends,
                "safety_notes": safety_notes,
                "next_actions": next_actions_for(profile, recommendations),
                "original_modified": False,
            }
        )
    )
    payload["app_hints"] = sanitize_payload(
        {
            "short_summary": f"Router dry-run: {profile['input_kind']} -> {len(recommendations)} rutas candidatas.",
            "severity": {
                "ok": "ok",
                "warning": "warning",
                "blocked": "blocked",
                "fail": "error",
            }.get(status, "warning"),
            "preview_artifact_types": ["summary_json"] if args.summary_json else [],
            "tags": ["router", "dry_run", profile["input_kind"]],
        }
    )
    return payload


def failure_payload(args: argparse.Namespace, message: str) -> dict[str, Any]:
    payload = build_tool_payload(
        TOOL,
        status="fail",
        notes=["El router fallo antes de completar el dry-run."],
        artifacts={"summary_json": getattr(args, "summary_json", None), "manifest_json": getattr(args, "manifest_json", None)},
        results={
            "mode": getattr(args, "mode", None),
            "input_kind": "unknown",
            "recommended_capabilities": [],
            "rejected_capabilities": [],
            "plan_steps": [],
            "required_backends": [{"backend": "python-stdlib", "required_for": [TOOL], "availability": "assumed"}],
            "safety_notes": ["No se ejecutaron capabilities recomendadas."],
        },
        qa={"status": "fail", "findings": [message], "metrics": {}},
    )
    payload.update(
        {
            "capability_id": TOOL,
            "capability_label": "scientific_workflow_router.py",
            "command": command_payload(sys.argv),
            "inputs": [],
            "input_kind": "unknown",
            "recommended_capabilities": [],
            "rejected_capabilities": [],
            "plan_steps": [],
            "required_backends": [{"backend": "python-stdlib", "required_for": [TOOL], "availability": "assumed"}],
            "safety_notes": ["No se ejecutaron capabilities recomendadas."],
            "next_actions": [{"label": "Corregir el comando o ruta de salida del router.", "kind": "user_input", "priority": "high"}],
            "original_modified": False,
        }
    )
    return sanitize_payload(payload)


def emit_payload_safely(payload: dict[str, Any], args: argparse.Namespace) -> int:
    rendered = json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n"
    if getattr(args, "manifest_json", None):
        try:
            manifest_outputs = [args.summary_json] if args.summary_json else []
            write_manifest(
                args.manifest_json,
                inputs=[args.path],
                outputs=manifest_outputs,
                parameters={"mode": args.mode, "task": args.task, "capability": args.capability},
                command=shell_join(sys.argv),
                notes=payload.get("notes", []),
                extra={"router_summary_status": payload.get("status"), "input_kind": payload.get("input_kind")},
            )
        except OSError as exc:
            failure = failure_payload(args, f"No se pudo escribir --manifest-json: {exc}")
            print(json.dumps(failure, indent=2, ensure_ascii=True) + "\n", end="")
            return 2

    if getattr(args, "summary_json", None):
        try:
            summary = Path(args.summary_json)
            if summary.exists() and summary.is_dir():
                raise IsADirectoryError(f"--summary-json apunta a una carpeta: {summary}")
            summary.parent.mkdir(parents=True, exist_ok=True)
            summary.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            failure = failure_payload(args, f"No se pudo escribir --summary-json: {exc}")
            print(json.dumps(failure, indent=2, ensure_ascii=True) + "\n", end="")
            return 2

    print(rendered, end="")
    return 0


def emit_collision_only(args: argparse.Namespace, collisions: list[dict[str, str]]) -> int:
    message = "El router rechaza outputs que solapan el input inspeccionado."
    payload = build_tool_payload(
        TOOL,
        status="blocked",
        notes=[message, "No se escribio summary ni manifest y no se modifico el input."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "mode": args.mode,
            "collisions": collisions,
        },
        qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": len(collisions)}},
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True) + "\n", end="")
    return 2


def main() -> int:
    args = parse_args()
    collisions = find_output_input_collisions(
        [("path", args.path)],
        [("--summary-json", args.summary_json), ("--manifest-json", args.manifest_json)],
    )
    if collisions:
        return emit_collision_only(args, collisions)
    try:
        payload = build_router_payload(args)
        return emit_payload_safely(payload, args)
    except Exception as exc:  # defensive: public CLI must fail cleanly
        failure = failure_payload(args, f"Fallo controlado del router: {exc}")
        print(json.dumps(failure, indent=2, ensure_ascii=True) + "\n", end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
