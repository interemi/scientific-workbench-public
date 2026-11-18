import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXPORTER = ROOT / "script/render_cli_contracts.py"


class CLIContractExportTests(unittest.TestCase):
    def test_exports_live_selected_parsers_and_owned_subcommands(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-B", str(EXPORTER),
                 "--capability", "photometry_noise_budget",
                 "--capability", "stilts_workbench",
                 "--capability", "catalog_workbench.crossmatch-sky",
                 "--capability", "companion_route_check"],
                cwd=directory, capture_output=True, text=True, check=True, timeout=45,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])

        export = json.loads(process.stdout)
        self.assertEqual(export["schema_version"], 1)
        records = {row["id"]: row for row in export["commands"]}
        self.assertEqual(set(records), {
            "photometry_noise_budget", "stilts_workbench",
            "catalog_workbench.crossmatch-sky", "companion_route_check",
        })

        noise = records["photometry_noise_budget"]
        self.assertEqual(noise["skill"], "scientific-data-astro")
        noise_args = {arg["name"]: arg for arg in noise["parser"]["arguments"]}
        self.assertTrue(noise_args["source"]["required"])
        self.assertEqual(noise_args["source"]["value_type"], "number")
        self.assertEqual(noise_args["units"]["choices"], ["electrons", "adu"])
        self.assertEqual(noise_args["units"]["default"], "electrons")

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
