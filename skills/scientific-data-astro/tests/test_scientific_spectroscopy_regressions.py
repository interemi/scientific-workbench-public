"""Focused scientific regression tests split by domain."""

from __future__ import annotations

from scientific_regression_support import *  # noqa: F403


class SpectrumRegressionTest(unittest.TestCase):
    def test_fits_binary_table_is_read_before_image_branches(self) -> None:
        from scipy.signal import find_peaks

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "table.fits"
            columns = [
                fits.Column(name="junk", format="D", unit="s", array=np.arange(20.0)),
                fits.Column(name="flux", format="D", unit="electron/s", array=np.linspace(1.0, 2.0, 20)),
                fits.Column(name="wavelength", format="D", unit="Angstrom", array=np.linspace(6500.0, 6510.0, 20)),
                fits.Column(name="error", format="D", unit="electron/s", array=np.full(20, 0.1)),
            ]
            fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(path)
            wavelength, flux, error, meta, diagnostic = SPECTRAL.read_fits_spectrum(
                np, fits, find_peaks, path, error_col="error"
            )
            self.assertEqual(len(wavelength), 20)
            self.assertEqual(len(flux), 20)
            self.assertEqual(len(error), 20)
            self.assertEqual(meta["source"], "fits_table_hdu")
            self.assertEqual(meta["axis_unit"], "Angstrom")
            self.assertEqual(meta["flux_unit"], "electron/s")
            self.assertIsNone(diagnostic)

            summary = Path(raw) / "summary.json"
            result = run_script("scripts/spectral_workbench.py", str(path), "--summary-json", str(summary))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["app_status"], "PASS")

    def test_experimental_profile_weighting_conserves_simple_flux(self) -> None:
        oriented = np.array([[1.0], [2.0], [3.0]])
        flux, error, _background = SPECTRAL.extract_order_flux(
            np,
            oriented,
            np.array([1.0]),
            spatial_half_width=1,
            bg_inner=2,
            bg_outer=3,
            optimal=True,
        )
        self.assertAlmostEqual(float(flux[0]), 6.0, places=10)
        self.assertTrue(np.isfinite(error[0]))

    def test_known_gaussian_equivalent_width_uses_fit_and_flags_integral_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spectrum = root / "halpha.txt"
            summary = root / "summary.json"
            center = 6565.42693733276
            sigma = 0.42
            depth = 0.35
            wavelength = np.linspace(6545.0, 6585.0, 2401)
            continuum = 1.0 + 2.0e-4 * (wavelength - center)
            flux = continuum * (1.0 - depth * np.exp(-0.5 * ((wavelength - center) / sigma) ** 2))
            np.savetxt(
                spectrum,
                np.column_stack([wavelength, flux, np.full_like(wavelength, 0.005)]),
                header="wavelength flux error",
                comments="",
            )
            result = run_script(
                "scripts/spectral_workbench.py",
                str(spectrum),
                "--wavelength-col",
                "wavelength",
                "--flux-col",
                "flux",
                "--error-col",
                "error",
                "--line-window",
                str(center),
                "8",
                "--normalize",
                "--summary-json",
                str(summary),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            line_fit = payload["results"]["line_fit"]
            expected_ew = depth * sigma * math.sqrt(2.0 * math.pi)
            self.assertAlmostEqual(line_fit["center"], center, delta=0.001)
            self.assertAlmostEqual(line_fit["equivalent_width"], expected_ew, delta=expected_ew * 0.01)
            self.assertEqual(line_fit["equivalent_width"], line_fit["equivalent_width_fit"])
            self.assertFalse(line_fit["equivalent_width_consistent"])
            self.assertGreater(line_fit["equivalent_width_relative_difference"], 0.25)
            self.assertEqual(payload["app_status"], "WARNING")
            self.assertTrue(
                any("line_equivalent_width_fit_integral_inconsistent" in item for item in payload["qa"]["findings"])
            )


class CalibrationAndReductionRegressionTest(unittest.TestCase):
    def test_common_imagetyp_aliases_are_canonical(self) -> None:
        expected = {
            "BIAS": "bias",
            "Bias Frame": "bias",
            "DARK FRAME": "dark",
            "FLAT FIELD": "flat",
            "LIGHT FRAME": "science",
        }
        self.assertEqual({key: EXOPLANET.canonical_frame_type(key) for key in expected}, expected)
        row = EXOPLANET.classify_frame(
            Path("bias.fits"),
            {"IMAGETYP": "Bias Frame", "FILTER": "R", "EXPTIME": 0},
            np.zeros((4, 4)),
            object,
        )
        self.assertEqual(row["imagetyp"], "bias")
        self.assertEqual(row["filter_id"], "R")

    def test_dark_rate_is_scaled_by_each_exposure(self) -> None:
        bias = np.full((3, 3), 100.0)
        dark_rows = [
            {"name": "d10.fits", "raw": bias + 2.0 * 10.0, "exptime": 10.0},
            {"name": "d30.fits", "raw": bias + 2.0 * 30.0, "exptime": 30.0},
        ]
        dark_rate = EXOPLANET.build_master_dark_rate(np, dark_rows, bias)
        np.testing.assert_allclose(dark_rate, 2.0)
        science = {"name": "s20.fits", "raw": bias + 2.0 * 20.0 + 500.0, "exptime": 20.0}
        reduced, history = EXOPLANET.reduce_frame(np, science, bias, dark_rate, None)
        np.testing.assert_allclose(reduced, 500.0)
        self.assertIn("dark_rate_scaled_by_exptime", history)
        with self.assertRaises(SystemExit):
            EXOPLANET.build_master_dark_rate(np, dark_rows, None)

    def test_implicit_ccd_crop_is_blocked(self) -> None:
        with self.assertRaises(SystemExit):
            CCD.align_pair(np, np.zeros((10, 10)), np.zeros((8, 8)))
        science = np.zeros((8, 8))
        calibration = np.ones((8, 8))
        science_out, calibration_out, note = CCD.align_pair(np, science, calibration)
        self.assertIs(science_out, science)
        self.assertIs(calibration_out, calibration)
        self.assertIsNone(note)


if __name__ == "__main__":
    unittest.main()
