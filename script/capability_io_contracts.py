"""Read and validate the semantic I/O contracts beside the bundled registry."""

from __future__ import annotations

from functools import lru_cache
import json

from check_workflow_requirements import MOTHER_REGISTRY, ROOT
from resolve_skill_registry_evidence import resolve_registry_evidence


IO_SCHEMA_VERSION = 1
SCHEMA_NAME = "capability_io_contracts.json"
JSON_TYPES = {
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: type(value) is int,
    "number": lambda value: type(value) in (int, float),
    "number_or_null": lambda value: value is None or type(value) in (int, float),
}


@lru_cache(maxsize=1)
def load_io_contracts() -> dict:
    family = ROOT / "skills"
    evidence = resolve_registry_evidence(family, MOTHER_REGISTRY)
    source = (family / evidence["skill_registry_relative_path"]).with_name(SCHEMA_NAME)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Missing local I/O contracts beside the canonical registry: {source.name}")
    document = json.loads(source.read_text(encoding="utf-8"))
    if type(document.get("schema_version")) is not int or document["schema_version"] != IO_SCHEMA_VERSION:
        raise ValueError("Unsupported capability I/O contract schema")
    return document["capabilities"]


def validate_parser_references(capability: str, contract: dict, parser: dict) -> None:
    if type(contract["revision"]) is not int or contract["revision"] < 1:
        raise ValueError(f"{capability}: I/O contract revision must be a positive integer")
    provided = {name for arg in parser["arguments"] for name in (arg["flags"] or [arg["name"]])}
    referenced = [field["argument"] for role in ("inputs", "outputs") for field in contract[role]]
    if len(referenced) != len(set(referenced)):
        raise ValueError(f"{capability}: repeated argument in the I/O contract")
    missing = provided - set(referenced)
    unknown = set(referenced) - provided
    if unknown or missing:
        raise ValueError(f"{capability}: I/O arguments differ from parser: missing={sorted(missing)}, unknown={sorted(unknown)}")
    summary = contract["summary"]
    for outcome in ("complete", "rejected"):
        if not summary[outcome] or set(summary[outcome].values()) - JSON_TYPES.keys():
            raise ValueError(f"{capability}: invalid JSON field types for {outcome}")


def validate_summary_contract(payload: dict, *, capability: str | None = None) -> None:
    """Check declared fields of a retained summary while allowing additional evidence."""
    tool = payload.get("tool")
    identifier = capability or tool
    if not isinstance(identifier, str):
        return
    contract = load_io_contracts().get(identifier)
    if contract is None:
        if capability is not None:
            raise ValueError(f"{capability}: missing I/O contract")
        return
    summary = contract["summary"]
    capability = identifier
    if tool != summary.get("tool", capability):
        raise ValueError(f"{capability}: summary tool differs from I/O contract")
    if payload.get("contract_version") != summary["version"]:
        raise ValueError(f"{capability}: summary version differs from I/O contract")
    status = payload.get("app_status")
    if status in {"PASS", "WARNING"}:
        outcome = "complete"
    elif status in {"BLOCKED_CONTROLADO", "FAIL", "ROTO"}:
        outcome = "rejected"
    else:
        raise ValueError(f"{capability}: unrecognized summary status {status!r}")
    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError(f"{capability}: missing summary results")
    if "mode" in summary and results.get("mode") != summary["mode"]:
        raise ValueError(f"{capability}: summary mode differs from I/O contract")
    for field, kind in summary[outcome].items():
        if field not in results or not JSON_TYPES[kind](results[field]):
            raise ValueError(f"{capability}: results.{field} must be {kind} for {status}")
