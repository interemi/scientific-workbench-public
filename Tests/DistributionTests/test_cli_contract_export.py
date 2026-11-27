import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXPORTER = ROOT / "script/render_cli_contracts.py"
sys.path.insert(0, str(ROOT / "script"))

from capability_io_contracts import validate_summary_contract


class CLIContractExportTests(unittest.TestCase):
    def test_photometry_parser_does_not_load_scientific_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c",
                 "import json, sys; "
                 "sys.path.insert(0, sys.argv[1]); "
                 "from render_cli_contracts import inspect_parser; "
                 "parser = inspect_parser('scientific-data-astro/scripts/photometric_solution.py', [], "
                 "{'fit': ['standard-stars.csv', '--residual-plot', 'residuals.png']}); "
                 "assert not {'numpy', 'pandas', 'matplotlib'}.intersection(sys.modules); "
                 "print(json.dumps(parser))",
                 str(EXPORTER.parent)],
                cwd=directory, capture_output=True, text=True, check=True, timeout=15,
            )
            self.assertIn("--residual-plot", process.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_exports_live_selected_parsers_and_owned_subcommands(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-B", str(EXPORTER),
                 "--capability", "photometry_noise_budget",
                 "--capability", "stilts_workbench",
                 "--capability", "catalog_workbench.crossmatch-sky",
                 "--capability", "legacy_external_reference_check",
                 "--capability", "companion_route_check"],
                cwd=directory, capture_output=True, text=True, check=True, timeout=45,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])

        export = json.loads(process.stdout)
        self.assertEqual(export["schema_version"], 1)
        self.assertEqual(export["io_schema_version"], 1)
        records = {row["id"]: row for row in export["commands"]}
        self.assertEqual(set(records), {
            "photometry_noise_budget", "stilts_workbench",
            "catalog_workbench.crossmatch-sky", "legacy_external_reference_check", "companion_route_check",
        })

        noise = records["photometry_noise_budget"]
        self.assertEqual(noise["skill"], "scientific-data-astro")
        noise_args = {arg["name"]: arg for arg in noise["parser"]["arguments"]}
        self.assertTrue(noise_args["source"]["required"])
        self.assertEqual(noise_args["source"]["value_type"], "number")
        self.assertEqual(noise_args["units"]["choices"], ["electrons", "adu"])
        self.assertEqual(noise_args["units"]["default"], "electrons")
        self.assertEqual(noise["io_contract"]["revision"], 1)
        self.assertEqual(noise["io_contract"]["summary"]["complete"]["snr"], "number_or_null")
        self.assertEqual(records["companion_route_check"]["io_contract"]["summary"]["complete"]["policy"], "object")

        crossmatch = records["catalog_workbench.crossmatch-sky"]
        self.assertEqual(crossmatch["argv"], [
            "skills/scientific-data-analysis/scripts/catalog_workbench.py", "crossmatch-sky",
        ])
        sky_args = {arg["name"]: arg for arg in crossmatch["parser"]["arguments"]}
        self.assertEqual(sky_args["left_ra_unit"]["choices"], ["deg", "rad", "hourangle"])
        self.assertEqual(sky_args["left_dec_unit"]["choices"], ["deg", "rad"])
        self.assertEqual(crossmatch["parser"]["subcommands"], {})

        stilts = records["stilts_workbench"]["parser"]["subcommands"]
        self.assertTrue(stilts["required"])
        self.assertIn("preflight", stilts["parsers"])
        self.assertIn("crossmatch-sky", stilts["parsers"])
        stilts_io = records["stilts_workbench"]["io_contract"]
        modes = stilts_io["subcommands"]
        self.assertEqual(set(modes), set(stilts["parsers"]))
        self.assertEqual(stilts_io["default_subcommand"], "preflight")
        self.assertEqual(stilts_io["inputs"], modes["preflight"]["inputs"])
        units = {item["argument"]: item.get("unit") for item in modes["crossmatch-sky"]["inputs"]}
        self.assertEqual(units["--left-ra"], "degrees")
        self.assertEqual(units["--radius-arcsec"], "arcseconds")

        reference = records["legacy_external_reference_check"]
        self.assertEqual(list(reference["parser"]["subcommands"]["parsers"]), ["check"])
        self.assertEqual(reference["io_contract"]["inputs"][0]["argument"], "--rv-summary")

        routing = records["companion_route_check"]["parser"]["arguments"]
        file_arg = next(arg for arg in routing if arg["flags"] == ["--file"])
        self.assertTrue(file_arg["accumulates"])
        self.assertEqual(file_arg["default"], [])

    def test_unknown_capability_is_reported_on_stderr(self):
        process = subprocess.run(
            [sys.executable, "-B", str(EXPORTER), "--capability", "unknown-capability"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("unknown registry IDs: unknown-capability", process.stderr)
        self.assertEqual(process.stdout, "")

    def test_checks_guided_arguments_without_running_the_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            evidence = root / "guided.json"
            invocation = {
                "id": "external_astro_tools_preflight",
                "skill": "scientific-data-astro",
                "argv": ["--summary-json", str(summary)],
            }
            command = [
                sys.executable, "-B", str(EXPORTER),
                "--capability", invocation["id"], "--guided-arguments", str(evidence),
                "--require-guided-coverage",
            ]
            variant = {**invocation, "variant": "with-probe", "argv": [*invocation["argv"], "--probe"]}
            evidence.write_text(json.dumps([invocation, variant]), encoding="utf-8")
            valid = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True, timeout=30)
            catalog = json.loads(valid.stdout)
            self.assertEqual(catalog["validated_guided_invocations"], [invocation["id"]])
            self.assertEqual(catalog["validated_guided_variants"][invocation["id"]], ["default", "with-probe"])
            self.assertFalse(summary.exists())

            variant["argv"].append("--removed-preflight-flag")
            evidence.write_text(json.dumps([invocation, variant]), encoding="utf-8")
            invalid = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=30)
            self.assertEqual(invalid.returncode, 1)
            self.assertIn("unrecognized arguments: --removed-preflight-flag", invalid.stderr)
            self.assertIn("[with-probe]", invalid.stderr)
            self.assertEqual(invalid.stdout, "")
            self.assertFalse(summary.exists())

            evidence.write_text(json.dumps([invocation]), encoding="utf-8")
            missing = subprocess.run(
                [*command, "--capability", "catalog_workbench.crossmatch-sky"],
                cwd=root, capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(missing.returncode, 1)
            self.assertIn("missing guided arguments for catalog_workbench.crossmatch-sky", missing.stderr)

    def test_retained_summary_rejects_a_missing_or_wrong_typed_result(self):
        summary = {
            "tool": "photometry_noise_budget",
            "contract_version": "1.8",
            "app_status": "WARNING",
            "results": {
                "variance_terms_e2": {},
                "total_noise_e": 0,
                "snr": None,
                "measurement_summary": {},
                "additional_evidence": "compatible",
            },
        }
        validate_summary_contract(summary)
        summary["results"]["snr"] = "unavailable"
        with self.assertRaisesRegex(ValueError, r"results\.snr must be number_or_null"):
            validate_summary_contract(summary)
        del summary["results"]["snr"]
        with self.assertRaisesRegex(ValueError, r"results\.snr must be number_or_null"):
            validate_summary_contract(summary)

    def test_subcommands_can_share_a_tool_name_and_require_the_correct_mode(self):
        summary = {
            "tool": "astrometry_net_workbench",
            "contract_version": "1.8",
            "app_status": "BLOCKED_CONTROLADO",
            "results": {"mode": "verify-existing-wcs", "blocked_reason": "No WCS", "measurement_summary": {}},
        }
        capability = "astrometry_net_workbench.verify-existing-wcs"
        validate_summary_contract(summary, capability=capability)
        summary["results"]["mode"] = "preflight"
        with self.assertRaisesRegex(ValueError, "summary mode differs"):
            validate_summary_contract(summary, capability=capability)

    def test_environment_status_retains_its_legacy_root_fields(self):
        summary = {
            "tool": "datanalysis_env.status",
            "contract_version": "1.8",
            "app_status": "BLOCKED_CONTROLADO",
            "found": False,
            "next_step": "Check the selected interpreter",
            "warnings": [],
        }
        validate_summary_contract(summary)
        summary["found"] = 0
        with self.assertRaisesRegex(ValueError, r"found must be boolean"):
            validate_summary_contract(summary)
