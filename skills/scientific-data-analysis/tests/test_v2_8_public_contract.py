import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "fixtures" / "_internal" / "provenance_utils.py"
SPEC = importlib.util.spec_from_file_location("v2_8_provenance_utils", MODULE_PATH)
PROVENANCE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(PROVENANCE)


class PublicContractHardeningTests(unittest.TestCase):
    def test_qa_failure_cannot_be_app_pass(self):
        payload = PROVENANCE.standard_tool_payload(
            "synthetic",
            status="ok",
            qa={"status": "fail", "findings": ["scientific invariant failed"]},
        )
        self.assertEqual(payload["app_status"], "FAIL")
        self.assertTrue(payload["errors"])

    def test_canonical_app_status_aliases(self):
        blocked = PROVENANCE.standard_tool_payload("synthetic", status="BLOCKED_CONTROLADO")
        broken = PROVENANCE.standard_tool_payload("synthetic", status="ROTO")
        self.assertEqual(blocked["app_status"], "BLOCKED_CONTROLADO")
        self.assertEqual(broken["app_status"], "ROTO")

    def test_sensitive_argv_values_are_redacted(self):
        secret = "SENTINEL_DO_NOT_LEAK"
        command = PROVENANCE.command_payload(
            [
                "tool",
                "--token",
                secret,
                f"--api-key={secret}",
                "--input_value",
                secret,
                f"OPENAI_API_KEY={secret}",
                f"https://example.invalid/run?token={secret}&mode=test",
                f"Authorization: Bearer {secret}",
                f"Authorization=Bearer {secret}",
            ]
        )
        rendered = json.dumps(command, allow_nan=False)
        self.assertNotIn(secret, rendered)
        self.assertGreaterEqual(rendered.count("[REDACTED]"), 3)

    def test_nonfinite_values_are_json_safe_and_declared(self):
        payload = PROVENANCE.standard_tool_payload(
            "synthetic",
            status="ok",
            results={"nan": math.nan, "positive": math.inf, "negative": -math.inf},
            qa={"status": "ok", "findings": []},
        )
        rendered = json.dumps(payload, allow_nan=False)
        self.assertEqual(payload["app_status"], "WARNING")
        self.assertIn('"NaN"', rendered)
        self.assertIn('"Infinity"', rendered)
        self.assertIn('"-Infinity"', rendered)
        self.assertTrue(any("Non-finite" in item for item in payload["qa"]["findings"]))


if __name__ == "__main__":
    unittest.main()
