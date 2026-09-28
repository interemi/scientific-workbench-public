import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from run_portable_core import main, validate_summary
from setup_environment import validate_profile_readiness


class ProfileReadinessTests(unittest.TestCase):
    def test_core_readiness_does_not_claim_full_readiness(self):
        payload = {"capabilities": {"core_ready": True, "full_ready": False}}
        validate_profile_readiness(payload, "core")
        with self.assertRaisesRegex(ValueError, "full_ready"):
            validate_profile_readiness(payload, "full")

    def test_full_requires_explicit_boolean_success_but_not_teareduce(self):
        capabilities = {"core_ready": True, "full_ready": True, "teareduce_ready": False}
        validate_profile_readiness({"capabilities": capabilities}, "full")
        validate_profile_readiness({"capabilities": {"core_ready": True, "full_ready": True}}, "full")
        for key in ("core_ready", "full_ready"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_profile_readiness({"capabilities": {**capabilities, key: "true"}}, "full")
        with self.assertRaises(ValueError):
            validate_profile_readiness({}, "core")

    def test_core_summary_cannot_satisfy_full_validation(self):
        core = {"profile": "core", "overall_status": "PASS", "feature_runs": {"fits": {"returncode": 0}},
                "public_surface_coverage": {"tiers_enforced": ["core"], "missing_coverage": []}}
        self.assertEqual(validate_summary(core), 1)
        with self.assertRaises(ValueError):
            validate_summary(core, "full")
        with self.assertRaises(ValueError):
            validate_summary({**core, "profile": "full"}, "full")
        full = {**core, "profile": "full", "public_surface_coverage": {
            "tiers_enforced": ["core", "full"], "missing_coverage": []}}
        self.assertEqual(validate_summary(full, "full"), 1)

    def test_partial_environment_stops_before_running_full_smoke(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-run"
            calls = []

            def doctor(command, **kwargs):
                calls.append(command)
                target = Path(command[command.index("--summary-json") + 1])
                target.write_text(json.dumps({"capabilities": {"core_ready": True, "full_ready": False}}))
                return subprocess.CompletedProcess(command, 0)

            with patch("run_portable_core.sys.version_info", (3, 11)), \
                 patch("run_portable_core.verify", return_value=1919), \
                 patch("run_portable_core.subprocess.run", side_effect=doctor):
                with self.assertRaisesRegex(ValueError, "full_ready"):
                    main(["--profile", "full", "--output-dir", str(output)])
            self.assertEqual(len(calls), 1)
            evidence = json.loads((output / "verification.json").read_text())
            self.assertEqual(evidence["status"], "FAIL")
            self.assertEqual(evidence["profile"], "full")
            self.assertTrue((output / "step-1.log").exists())
            self.assertFalse((output / "step-2.log").exists())


if __name__ == "__main__":
    unittest.main()
