#!/usr/bin/env python3
"""Export a versioned inventory of the bundled command-line parsers."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

from check_distribution_snapshot import ROOT, ROOTS
from check_workflow_requirements import load_registry
from capability_io_contracts import IO_SCHEMA_VERSION, load_io_contracts, validate_parser_references


SCHEMA_VERSION = 1
FAMILY = ROOT / "skills"
MOTHER_SCRIPTS = FAMILY / "scientific-data-analysis/scripts"
VALUE_TYPES = {None: "string", str: "string", int: "integer", float: "number", Path: "path"}


class HelpRequested(BaseException):
    """Interrupt the normal help path before a workflow can start."""

    def __init__(self, parser: argparse.ArgumentParser):
        self.parser = parser


def capture_help(parser: argparse.ArgumentParser, file=None) -> None:
    raise HelpRequested(parser)


def describe_argument(action: argparse.Action) -> dict:
    argument = {
        "name": action.dest,
        "flags": action.option_strings,
        "required": action.required,
        "arity": 1 if action.nargs is None else action.nargs,
        "accumulates": isinstance(action, argparse._AppendAction),
        "value_type": "flag" if action.nargs == 0 else VALUE_TYPES[action.type],
    }
    if action.choices is not None:
        argument["choices"] = list(action.choices)
    if action.nargs == 0:
        argument["flag_value"] = action.const
    if action.default != argparse.SUPPRESS:
        default = action.default
        if isinstance(default, str) and Path(default).is_absolute():
            argument["default_relative_to_checkout"] = Path(default).relative_to(ROOT).as_posix()
        else:
            argument["default"] = default
    if action.help:
        argument["help"] = action.help
    return argument


def describe_parser(parser: argparse.ArgumentParser) -> dict:
    """Read the parser declarations reached by this command's own --help."""
    arguments = []
    subcommands = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subcommands = {
                "required": action.required,
                "parsers": {name: describe_parser(child) for name, child in action.choices.items()},
            }
        elif action.help != argparse.SUPPRESS and not isinstance(action, argparse._HelpAction):
            arguments.append(describe_argument(action))
    return {
        "option_abbreviations": parser.allow_abbrev,
        "arguments": arguments,
        "subcommands": subcommands,
        "mutually_exclusive": [
            {"required": group.required, "arguments": [action.dest for action in group._group_actions]}
            for group in parser._mutually_exclusive_groups
        ],
    }


def bundled_script(relative: str) -> Path:
    parts = Path(relative).parts
    if (len(parts) != 3 or parts[0] not in ROOTS or parts[1] != "scripts"
            or Path(relative).suffix != ".py"):
        raise ValueError(f"invalid CLI entrypoint {relative!r}")
    target = (FAMILY / relative).resolve(strict=True)
    if not target.is_file() or not target.is_relative_to(FAMILY / parts[0]):
        raise ValueError(f"CLI entrypoint is outside its owning skill: {relative}")
    return target


def inspect_parser(relative: str, tail: list[str], arguments: list[str] | None = None) -> dict:
    """Run in an isolated interpreter so imports cannot leak across skills."""
    script = bundled_script(relative)
    sys.argv[:] = [str(script), *tail, "--help"]
    sys.path.insert(0, str(script.parent))
    print_help = argparse.ArgumentParser.print_help
    argparse.ArgumentParser.print_help = capture_help
    try:
        runpy.run_path(str(script), run_name="__main__")
    except HelpRequested as capture:
        parser = capture.parser
    except SystemExit as error:
        raise ValueError(f"command exited during help before exposing a parser ({error.code})") from error
    else:
        raise ValueError("command returned without exposing a parser")
    finally:
        argparse.ArgumentParser.print_help = print_help
    if arguments is not None:
        if arguments[:len(tail)] != tail:
            raise ValueError("guided command is missing its registered subcommand")
        parser.parse_args(arguments[len(tail):])
    return describe_parser(parser)


def command_records(entries: list[dict]) -> list[dict]:
    sys.path.insert(0, str(MOTHER_SCRIPTS))
    try:
        from scientific_workflow_router import module_metadata_for
    finally:
        sys.path.pop(0)

    commands = []
    for entry in entries:
        capability = entry["id"]
        route = module_metadata_for(entry["label"], capability)
        owner = route.get("child_skill_path")
        if owner not in ROOTS:
            raise ValueError(f"{capability} has no verified router owner")
        name, _, subcommand = capability.partition(".")
        if Path(entry["script"]).stem != name:
            raise ValueError(f"{capability} differs from its registry script stem")
        relative = f"{owner}/{entry['script']}"
        bundled_script(relative)
        commands.append({
            "id": capability,
            "skill": owner,
            "argv": [f"skills/{relative}", *([subcommand] if subcommand else [])],
            "kind": entry["kind"],
            "platform": entry["platform"],
            "requires_datanalysis": entry["requires_datanalysis"],
            "preflight_mode": entry["preflight_mode"],
        })
    return commands


def load_command_schema(command: dict, scratch: Path, arguments: list[str] | None = None) -> dict:
    script, *tail = command["argv"]
    environment = {
        **os.environ,
        "DATAANALYSIS_PYTHON": sys.executable,
        "MPLCONFIGDIR": str(scratch / "matplotlib"),
    }
    operation = "--inspect-parser" if arguments is None else "--inspect-guided-parser"
    process = subprocess.run(
        [sys.executable, "-B", __file__, operation, script.removeprefix("skills/"), *tail],
        cwd=scratch, env=environment, capture_output=True, text=True, timeout=30,
        input=None if arguments is None else json.dumps(arguments),
    )
    if process.returncode:
        reason = process.stderr.strip().splitlines()
        raise ValueError(f"{command['id']}: {reason[-1] if reason else f'exit {process.returncode}'}")
    try:
        schema = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"{command['id']}: parser probe did not return JSON") from error
    return {**command, "parser": schema}


def load_guided_arguments(path: Path, commands: list[dict]) -> dict[str, list[str]]:
    owners = {command["id"]: command["skill"] for command in commands}
    arguments = {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("guided argument evidence must contain at least one invocation")
    for row in rows:
        capability = row["id"]
        argv = row["argv"]
        if capability in arguments or owners.get(capability) != row["skill"]:
            raise ValueError(f"{capability}: duplicate guided invocation or incorrect owning skill")
        if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
            raise ValueError(f"{capability}: guided arguments must be a list of strings")
        if "-h" in argv or "--help" in argv:
            raise ValueError(f"{capability}: guided arguments must describe a workflow invocation")
        arguments[capability] = argv
    return arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", action="append", help="Limit output to this registry ID. Repeatable.")
    parser.add_argument("--guided-arguments", type=Path, help="Check command arguments exported by Swift tests.")
    args = parser.parse_args(argv)
    try:
        commands = command_records(load_registry())
        contracts = load_io_contracts()
        registry_ids = {command["id"] for command in commands}
        unknown_contracts = set(contracts) - registry_ids
        if unknown_contracts:
            raise ValueError(f"I/O contracts reference unknown registry IDs: {sorted(unknown_contracts)}")
        if args.capability:
            unknown = set(args.capability) - registry_ids
            if unknown:
                parser.error(f"unknown registry IDs: {', '.join(sorted(unknown))}")
            commands = [command for command in commands if command["id"] in args.capability]
        arguments = load_guided_arguments(args.guided_arguments, commands) if args.guided_arguments else {}
        with tempfile.TemporaryDirectory(prefix="swb-cli-contracts-") as directory:
            scratch = Path(directory)
            with ThreadPoolExecutor(max_workers=4) as pool:
                schemas = list(pool.map(
                    lambda command: load_command_schema(command, scratch, arguments.get(command["id"])),
                    commands,
                ))
        for command in schemas:
            contract = contracts.get(command["id"])
            if contract is not None:
                validate_parser_references(command["id"], contract, command["parser"])
                command["io_contract"] = contract
        catalog = {
            "schema_version": SCHEMA_VERSION,
            "io_schema_version": IO_SCHEMA_VERSION,
            "commands": schemas,
        }
        if arguments:
            catalog["validated_guided_invocations"] = sorted(arguments)
        output = json.dumps(catalog, indent=2, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"CLI contract export failed: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--inspect-parser"]:
        print(json.dumps(inspect_parser(sys.argv[2], sys.argv[3:]), allow_nan=False))
    elif sys.argv[1:2] == ["--inspect-guided-parser"]:
        print(json.dumps(inspect_parser(sys.argv[2], sys.argv[3:], json.load(sys.stdin)), allow_nan=False))
    else:
        raise SystemExit(main())
