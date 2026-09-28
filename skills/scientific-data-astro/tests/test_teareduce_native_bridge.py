"""Verify the legacy-named bridge performs native work without TEAREDUCE."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from astropy.io import fits


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
sys.path.insert(0, str(FIXTURES))
from teareduce_bridge import native_summary  # noqa: E402


class NativeTeareduceBridgeTests(unittest.TestCase):
    def test_native_summary_handles_nonfinite_values_explicitly(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
        with self.assertRaisesRegex(ValueError, "--rm-nan"):
            native_summary(values)
        result = native_summary(values, rm_nan=True)
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["median"], 2.5)
        self.assertAlmostEqual(result["mean"], 2.5)
        self.assertAlmostEqual(result["std"], np.sqrt(1.25))
        self.assertAlmostEqual(result["robust_std"], 1.4826)
        with self.assertRaisesRegex(ValueError, "no finite"):
            native_summary(np.array([np.nan]), rm_nan=True)

    def test_constant_fits_quicklook_preserves_input_and_labels_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix="native-fits-quicklook-") as temporary:
            root = Path(temporary)
            source = root / "input.fits"
            output = root / "quicklook.png"
            summary = root / "summary.json"
            fits.PrimaryHDU(np.ones((4, 4), dtype=float)).writeto(source)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            result = subprocess.run(
                [sys.executable, str(FIXTURES / "teareduce_bridge.py"), "imshow-fits",
                 str(source), "--output", str(output), "--summary-json", str(summary)],
                cwd=root,
                env={**os.environ, "MPLBACKEND": "Agg",
                     "MPLCONFIGDIR": str(root / "matplotlib"),
                     "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["backend"], "native_matplotlib")
            self.assertIs(payload["teareduce_executed"], False)
            self.assertLess(payload["display_limits"]["vmin"], payload["display_limits"]["vmax"])
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)


if __name__ == "__main__":
    unittest.main()
