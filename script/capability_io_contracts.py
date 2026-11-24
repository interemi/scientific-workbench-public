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
    "boolean": lambda value: isinstance(value, bool),
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
    arguments = parser["arguments"]
    subcommands = parser["subcommands"]
    if "subcommands" in contract:
        parsers = subcommands.get("parsers", {})
        modes = contract["subcommands"]
        if arguments or not subcommands.get("required") or set(parsers) != set(modes):
            raise ValueError(f"{capability}: I/O subcommands differ from the required CLI subcommands")
        default = modes.get(contract.get("default_subcommand"))
        matched_fields = ("backend", "inputs", "outputs", "warnings", "failure", "summary")
        if default is None or any(contract.get(field) != default[field] for field in matched_fields):
            raise ValueError(f"{capability}: top-level I/O contract must match its default subcommand")
        for name, mode in modes.items():
            validate_parser_references(f"{capability}.{name}", mode, parsers[name])
        return
    if not arguments and subcommands.get("required") and len(subcommands["parsers"]) == 1:
        only_subcommand, = subcommands["parsers"].values()
        arguments = only_subcommand["arguments"]
    provided = {name for arg in arguments for name in (arg["flags"] or [arg["name"]])}
    referenced = [field["argument"] for role in ("inputs", "outputs") for field in contract[role]]
    if len(referenced) != len(set(referenced)):
        raise ValueError(f"{capability}: repeated argument in the I/O contract")
    missing = provided - set(referenced)
    unknown = set(referenced) - provided
    if unknown or missing:
        raise ValueError(f"{capability}: I/O arguments differ from parser: missing={sorted(missing)}, unknown={sorted(unknown)}")
    summary = contract["summary"]
    for key in ("container", "rejected_container"):
        if key in summary and summary[key] not in {"root", "results"}:
            raise ValueError(f"{capability}: unsupported summary field container")
    for outcome in ("complete", "rejected"):
        if not summary[outcome] or set(summary[outcome].values()) - JSON_TYPES.keys():
            raise ValueError(f"{capability}: invalid JSON field types for {outcome}")


def validate_summary_contract(payload: dict, *, capability: str | None = None) -> None:
    """Check declared fields of a retained summary while allowing additional evidence."""
    tool = payload.get("tool")
    identifier = capability or tool
    if not isinstance(identifier, str):
        return
    declared = load_io_contracts()
    contract = declared.get(identifier)
    if contract is None:
        root, _, mode = identifier.partition(".")
        contract = declared.get(root, {}).get("subcommands", {}).get(mode)
    elif "subcommands" in contract:
        tool_root, _, mode = tool.partition(".") if isinstance(tool, str) else ("", "", "")
        modes = contract["subcommands"]
        if tool_root != identifier or mode not in modes:
            raise ValueError(f"{identifier}: summary requires a known subcommand")
        contract = modes[mode]
        identifier = tool
    if contract is None:
        if capability is not None:
            raise ValueError(f"{capability}: missing I/O contract")
        return
    summary = contract["summary"]
    capability = identifier
    status = payload.get("app_status")
    expected_tool = summary.get("tool", capability)
    if tool != expected_tool:
        # The CLI path guard runs before the subcommand body and reports the executable stem.
        error = payload.get("error")
        if not (status == "BLOCKED_CONTROLADO" and tool == expected_tool.partition(".")[0]
                and isinstance(error, dict) and error.get("code") == "unsafe_output_input_collision"):
            raise ValueError(f"{capability}: summary tool differs from I/O contract")
    if payload.get("contract_version") != summary["version"]:
        raise ValueError(f"{capability}: summary version differs from I/O contract")
    if status in {"PASS", "WARNING"}:
        outcome = "complete"
    elif status in {"BLOCKED_CONTROLADO", "FAIL", "ROTO"}:
        outcome = "rejected"
    else:
        raise ValueError(f"{capability}: unrecognized summary status {status!r}")
    container = summary.get("container", "results")
    if outcome == "rejected":
        container = summary.get("rejected_container", container)
    nested_results = payload.get("results")
    results = payload if container == "root" else nested_results
    if not isinstance(results, dict):
        raise ValueError(f"{capability}: missing summary results")
    if "mode" in summary and (not isinstance(nested_results, dict) or nested_results.get("mode") != summary["mode"]):
        raise ValueError(f"{capability}: summary mode differs from I/O contract")
    for field, kind in summary[outcome].items():
        if field not in results or not JSON_TYPES[kind](results[field]):
            prefix = "results." if container == "results" else ""
            raise ValueError(f"{capability}: {prefix}{field} must be {kind} for {status}")
