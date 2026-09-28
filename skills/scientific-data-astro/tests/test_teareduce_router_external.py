"""Routing to an external backend must not imply that it has run or is ready."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from teareduce_router import classify  # noqa: E402


class ExternalTeareduceRouterTests(unittest.TestCase):
    def test_specific_request_warns_and_points_to_copy_runner(self) -> None:
        route = classify("Use TEAREDUCE for wavelength calibration", [])
        self.assertEqual(route["recommended_backend"], "teareduce")
        self.assertEqual(route["route_status"], "warning")
        self.assertEqual(route["suggested_entrypoint"], "scripts/teareduce_healthcheck.py")
        self.assertIn("scripts/teareduce_notebook_runner.py", route["supporting_scripts"])
        self.assertNotIn("scripts/teareduce_bridge.py", route["supporting_scripts"])
        self.assertTrue(any("does not verify" in finding for finding in route["warning_findings"]))

    def test_default_native_route_does_not_claim_optional_backend_is_ready(self) -> None:
        route = classify("Create a report from a catalog", [])
        self.assertEqual(route["recommended_backend"], "native")
        self.assertTrue(any("does not verify" in note for note in route["notes"]))


if __name__ == "__main__":
    unittest.main()
