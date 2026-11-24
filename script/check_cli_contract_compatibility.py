#!/usr/bin/env python3
"""Compare existing CLI invocations and results across two contract exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from capability_io_contracts import IO_SCHEMA_VERSION
from render_cli_contracts import SCHEMA_VERSION


ARGUMENT_FIELDS = ("arity", "value_type", "accumulates", "flag_value", "default", "default_relative_to_checkout")
ABSENT = object()


def command_index(export: dict) -> dict[str, dict]:
    version = export["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"unsupported CLI export schema {version!r}")
    io_version = export.get("io_schema_version")
    if io_version is not None and (type(io_version) is not int or io_version != IO_SCHEMA_VERSION):
        raise ValueError(f"unsupported I/O contract schema {io_version!r}")
    commands = export["commands"]
    indexed = {command["id"]: command for command in commands}
    if not indexed or len(indexed) != len(commands):
        raise ValueError("an export needs a nonempty command list with unique IDs")
    return indexed


def argument_changes(before: dict, after: dict) -> list[str]:
    changes = []
    for field in ARGUMENT_FIELDS:
        old, new = before.get(field, ABSENT), after.get(field, ABSENT)
        if type(old) is not type(new) or old != new:
            changes.append(f"{field} changed")
    if after["required"] and not before["required"]:
        changes.append("became required")
    old_choices, new_choices = before.get("choices"), after.get("choices")
    if new_choices is not None and (old_choices is None or any(choice not in new_choices for choice in old_choices)):
        changes.append("accepted choices narrowed")
    return changes


def exclusive_groups(parser: dict) -> set[tuple[bool, frozenset[str]]]:
    return {(group["required"], frozenset(group["arguments"])) for group in parser["mutually_exclusive"]}


def parser_changes(before: dict, after: dict, route: str) -> list[str]:
    changes = []
    left = [argument for argument in before["arguments"] if not argument["flags"]]
    right = [argument for argument in after["arguments"] if not argument["flags"]]
    if [argument["name"] for argument in left] != [argument["name"] for argument in right]:
        changes.append(f"{route}: positional argument layout changed")
    else:
        for old, new in zip(left, right):
            name = old["name"]
            changes.extend(f"{route} {name}: {change}" for change in argument_changes(old, new))

    old_flags = {flag: argument for argument in before["arguments"] for flag in argument["flags"]}
    new_flags = {flag: argument for argument in after["arguments"] for flag in argument["flags"]}
    for flag, old in sorted(old_flags.items()):
        if flag not in new_flags:
            changes.append(f"{route} {flag}: flag removed")
        else:
            changes.extend(f"{route} {flag}: {change}" for change in argument_changes(old, new_flags[flag]))
    for argument in after["arguments"]:
        flags = argument["flags"]
        if flags and argument["required"] and old_flags.keys().isdisjoint(flags):
            changes.append(f"{route} {flags[0]}: new required flag")
    if before["option_abbreviations"] and not after["option_abbreviations"]:
        changes.append(f"{route}: option abbreviations disabled")
    if exclusive_groups(before) != exclusive_groups(after):
        changes.append(f"{route}: mutually exclusive groups changed")

    old_commands, new_commands = before["subcommands"], after["subcommands"]
    if new_commands.get("required", False) and not old_commands.get("required", False):
        changes.append(f"{route}: subcommand became required")
    new_parsers = new_commands.get("parsers", {})
    for name, old_parser in sorted(old_commands.get("parsers", {}).items()):
        child = f"{route} {name}"
        if name not in new_parsers:
            changes.append(f"{child}: subcommand removed")
        else:
            changes.extend(parser_changes(old_parser, new_parsers[name], child))
    return changes


def io_changes(before: dict, after: dict, capability: str) -> list[str]:
    old_contract = before.get("io_contract")
    if old_contract is None:
        return []
    new_contract = after.get("io_contract")
    if new_contract is None:
        return [f"{capability}: I/O contract removed"]

    return contract_changes(old_contract, new_contract, capability)


def contract_changes(old_contract: dict, new_contract: dict, capability: str) -> list[str]:
    changes = []
    if new_contract["revision"] < old_contract["revision"]:
        changes.append(f"{capability}: I/O revision decreased")
    if ("subcommands" in old_contract) != ("subcommands" in new_contract):
        return [*changes, f"{capability}: I/O subcommand layout changed"]
    if "subcommands" in old_contract:
        updated = new_contract["subcommands"]
        for mode, old in old_contract["subcommands"].items():
            if mode not in updated:
                changes.append(f"{capability}.{mode}: I/O subcommand removed")
            else:
                changes.extend(contract_changes(old, updated[mode], f"{capability}.{mode}"))
        return changes

    for role in ("inputs", "outputs"):
        new_fields = {field["argument"]: field for field in new_contract[role]}
        for field in old_contract[role]:
            argument = field["argument"]
            new = new_fields.get(argument)
            if new is None:
                changes.append(f"{capability} {argument}: declared {role} entry removed")
            else:
                for key in ("unit", "format"):
                    if field.get(key) != new.get(key):
                        changes.append(f"{capability} {argument}: {role} {key} changed")

    old_summary, new_summary = old_contract["summary"], new_contract["summary"]
    for key, default in (("tool", capability), ("container", "results"), ("mode", None), ("version", None)):
        if old_summary.get(key, default) != new_summary.get(key, default):
            changes.append(f"{capability}: summary {key} changed")
    if "rejected_container" in old_summary or "rejected_container" in new_summary:
        old_rejected = old_summary.get("rejected_container", old_summary.get("container", "results"))
        new_rejected = new_summary.get("rejected_container", new_summary.get("container", "results"))
        if old_rejected != new_rejected:
            changes.append(f"{capability}: rejected summary container changed")
    for outcome in ("complete", "rejected"):
        for field, kind in sorted(old_summary[outcome].items()):
            actual = new_summary[outcome].get(field)
            if actual != kind:
                detail = "removed" if actual is None else f"type changed from {kind} to {actual}"
                changes.append(f"{capability}: {outcome} summary field {field} {detail}")
    return changes


def compare_exports(baseline: dict, candidate: dict) -> list[str]:
    before, after = command_index(baseline), command_index(candidate)
    changes = []
    for capability, old in sorted(before.items()):
        new = after.get(capability)
        if new is None:
            changes.append(f"{capability}: command removed")
            continue
        if old["argv"] != new["argv"]:
            changes.append(f"{capability}: invocation route changed")
        if old["platform"] != new["platform"]:
            changes.append(f"{capability}: declared platform changed")
        if old["preflight_mode"] != new["preflight_mode"]:
            changes.append(f"{capability}: declared preflight mode changed")
        if old["kind"] != "maintainer_only" and new["kind"] == "maintainer_only":
            changes.append(f"{capability}: moved to maintainer-only")
        if new["requires_datanalysis"] and not old["requires_datanalysis"]:
            changes.append(f"{capability}: dedicated datanalysis became required")
        changes.extend(parser_changes(old["parser"], new["parser"], capability))
        changes.extend(io_changes(old, new, capability))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="Export from before the change.")
    parser.add_argument("candidate", type=Path, help="Export from the proposed revision.")
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        changes = compare_exports(baseline, candidate)
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        print(f"Could not compare contract exports: {error}", file=sys.stderr)
        return 2
    if changes:
        print("Compatibility review required:", file=sys.stderr)
        for change in changes:
            print(f"- {change}", file=sys.stderr)
        return 1
    print(f"Compatible declarations for {len(baseline['commands'])} baseline commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
