from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "script"))

from check_cli_contract_compatibility import compare_exports


def argument(name, *flags, **overrides):
    return {
        "name": name, "flags": list(flags), "required": not flags,
        "arity": 1, "value_type": "string", "accumulates": False, "default": None,
        **overrides,
    }


def parser(*arguments, **overrides):
    return {"arguments": list(arguments), "option_abbreviations": False,
            "mutually_exclusive": [], "subcommands": {}, **overrides}


class CLIContractCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "schema_version": 1,
            "io_schema_version": 1,
            "commands": [{
                "id": "sample.inspect", "argv": ["skills/sample/scripts/sample.py", "inspect"],
                "platform": "portable", "kind": "supporting_tool", "preflight_mode": "none",
                "requires_datanalysis": False,
                "parser": parser(argument("input"), argument("mode", "--mode", choices=["quick"])),
                "io_contract": {
                    "revision": 1, "inputs": [{"argument": "input", "format": "Table"}], "outputs": [],
                    "summary": {
                        "version": "1.8", "complete": {"rows": "integer"}, "rejected": {"error": "string"},
                    },
                },
            }],
        }
        self.candidate = deepcopy(self.baseline)
        self.updated = self.candidate["commands"][0]

    def compare(self):
        return compare_exports(self.baseline, self.candidate)

    def test_expanded_alias_choices_optional_flags_and_result_fields_are_compatible(self):
        mode = self.updated["parser"]["arguments"][1]
        mode["flags"].append("--strategy")
        mode["choices"].append("detailed")
        mode["help"] = "Select the analysis mode."
        self.updated["parser"]["arguments"].append(argument("preview", "--preview"))
        self.updated["io_contract"]["summary"]["complete"]["coverage"] = "number"
        self.assertEqual(self.compare(), [])

    def test_removed_flag_and_required_replacement_are_reported(self):
        self.updated["parser"]["arguments"][1] = argument("strategy", "--strategy", required=True)
        self.assertEqual(self.compare(), [
            "sample.inspect --mode: flag removed",
            "sample.inspect --strategy: new required flag",
        ])

    def test_narrowed_choices_and_suppressed_default_are_reported(self):
        mode = self.updated["parser"]["arguments"][1]
        mode["choices"] = ["details"]
        del mode["default"]
        self.assertEqual(self.compare(), [
            "sample.inspect --mode: default changed",
            "sample.inspect --mode: accepted choices narrowed",
        ])

    def test_positional_reorder_and_removed_subcommand_are_reported(self):
        baseline_parser = self.baseline["commands"][0]["parser"]
        baseline_parser["arguments"].append(argument("target"))
        self.updated["parser"]["arguments"] = [
            argument("target"), argument("input"), argument("mode", "--mode", choices=["quick"]),
        ]
        baseline_parser["subcommands"] = {"required": False, "parsers": {"diagnose": parser()}}
        self.assertEqual(self.compare(), [
            "sample.inspect: positional argument layout changed",
            "sample.inspect diagnose: subcommand removed",
        ])

    def test_result_type_container_and_unit_changes_are_reported(self):
        contract = self.updated["io_contract"]
        contract["summary"]["container"] = "root"
        contract["summary"]["complete"]["rows"] = "number"
        contract["summary"]["rejected"].clear()
        contract["inputs"][0]["unit"] = "degrees"
        self.assertEqual(self.compare(), [
            "sample.inspect input: inputs unit changed",
            "sample.inspect: summary container changed",
            "sample.inspect: complete summary field rows type changed from integer to number",
            "sample.inspect: rejected summary field error removed",
        ])

    def test_legacy_baseline_accepts_documenting_a_preexisting_io_contract(self):
        del self.baseline["io_schema_version"]
        del self.baseline["commands"][0]["io_contract"]
        self.assertEqual(self.compare(), [])

    def test_relocating_rejected_summary_fields_requires_review(self):
        self.updated["io_contract"]["summary"]["rejected_container"] = "root"
        self.assertEqual(self.compare(), ["sample.inspect: rejected summary container changed"])

    def test_explicit_inherited_rejected_container_is_compatible(self):
        self.updated["io_contract"]["summary"]["rejected_container"] = "results"
        self.assertEqual(self.compare(), [])

    def test_subcommand_contract_changes_are_reported(self):
        baseline = self.baseline["commands"][0]
        old = baseline["io_contract"]
        baseline["io_contract"] = {"revision": 1, "subcommands": {"check": old, "run": deepcopy(old)}}
        self.updated["io_contract"] = deepcopy(baseline["io_contract"])
        modes = self.updated["io_contract"]["subcommands"]
        modes["check"]["inputs"][0]["unit"] = "degrees"
        del modes["run"]
        self.assertEqual(self.compare(), [
            "sample.inspect.check input: inputs unit changed",
            "sample.inspect.run: I/O subcommand removed",
        ])

    def test_duplicate_ids_are_rejected(self):
        self.candidate["commands"].append(self.updated)
        with self.assertRaisesRegex(ValueError, "unique IDs"):
            self.compare()
