"""Reports must survive an external notebook kernel with no launcher TEAREDUCE."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
sys.path.insert(0, str(FIXTURES))

from teareduce_cookbook_cr2images_workflow import build_report as cr2images_report  # noqa: E402
from teareduce_cookbook_wavecal_workflow import build_report as wavecal_report  # noqa: E402
from teareduce_flat_workflow import build_report as flat_report  # noqa: E402
from teareduce_master_bias_workflow import build_report as bias_report  # noqa: E402


class ExternalTeareduceKernelReportTests(unittest.TestCase):
    def test_reports_do_not_require_teareduce_in_launcher_python(self) -> None:
        base = {
            "notebook": "reviewed.ipynb",
            "source_mode": "local",
            "teareduce": {"installed": False, "interpreter_scope": "launcher_python_only"},
            "teareduce_run": {"assessment": {"status": "pass"}, "duration_sec": 0},
        }
        reports = [
            bias_report({
                **base,
                "notebook_scan": {},
                "native_stack": {
                    "bias_frame_count": 0,
                    "master_bias_duration_sec": 0,
                    "science_subtraction_duration_sec": 0,
                    "native_science_products_written": 0,
                    "science_frame_count": 0,
                },
                "comparison": {
                    "teareduce_product_count": 0,
                    "teareduce_master_bias": "copy.fits",
                    "native_master_bias": "native.fits",
                },
            }),
            flat_report({**base, "notebook_scan": {}, "sidecars": [], "filters": {}}),
            cr2images_report({**base, "comparisons": {}}),
            wavecal_report({**base, "comparison": {}}),
        ]
        for report in reports:
            with self.subTest(report=report.splitlines()[0]):
                self.assertIn("TEAREDUCE in launcher Python: `not detected`", report)
                self.assertIn("selected notebook kernel version not verified", report)


if __name__ == "__main__":
    unittest.main()
