"""Focused scientific regression tests split by domain."""

from __future__ import annotations

from scientific_regression_support import *  # noqa: F403


class RgbSafetyRegressionTest(unittest.TestCase):
    def test_aligned_header_preserves_channel_metadata(self) -> None:
        runtime = RGB.import_runtime()
        stack_header = fits.Header({"FILTER": "G", "EXPTIME": 40.0})
        reference_header = fits.Header({"FILTER": "R", "EXPTIME": 30.0})
        stack = RGB.FilterStack("G", np.zeros((4, 4)), stack_header, [])
        reference = RGB.FilterStack("R", np.zeros((4, 4)), reference_header, [])
        output = RGB.aligned_output_header(
            stack,
            reference,
            {"method": "none", "shift_yx": [0.0, 0.0]},
            runtime,
        )
        self.assertEqual(output["FILTER"], "G")
        self.assertEqual(output["EXPTIME"], 40.0)

    def test_clean_quarantines_only_manifest_owned_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "out"
            owned = output / "reports" / "owned.json"
            foreign = output / "reports" / "user_notes.txt"
            owned.parent.mkdir(parents=True)
            owned.write_text("owned", encoding="utf-8")
            foreign.write_text("preserve", encoding="utf-8")
            manifest = output / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "extra": {
                            "owner": "fits_rgb_batch",
                            "owned_outputs": ["reports/owned.json", "manifest.json"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            quarantine = RGB.quarantine_manifest_owned_outputs(output)
            self.assertFalse(owned.exists())
            self.assertFalse(manifest.exists())
            self.assertTrue(foreign.is_file())
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve")
            self.assertTrue((quarantine / "reports" / "owned.json").is_file())
            self.assertTrue((quarantine / "manifest.json").is_file())

    def test_full_rgb_run_preserves_headers_and_safe_clean_preserves_foreign_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            output = root / "output"
            inputs.mkdir()
            yy, xx = np.indices((24, 24))
            image = 100.0 + 1000.0 * np.exp(-((xx - 12) ** 2 + (yy - 12) ** 2) / 4.0)
            for filter_name, exptime in (("R", 30.0), ("G", 40.0), ("B", 50.0)):
                header = fits.Header({"OBJECT": "AUDITSTAR", "FILTER": filter_name, "EXPTIME": exptime})
                fits.PrimaryHDU(image.astype(np.float32), header=header).writeto(inputs / f"audit_{filter_name}.fits")
            summary = root / "summary.json"
            command = [
                "scripts/fits_rgb_batch.py",
                "--input-root",
                str(inputs),
                "--output-dir",
                str(output),
                "--alignment-mode",
                "none",
                "--summary-json",
                str(summary),
            ]
            result = run_script(*command)
            self.assertEqual(result.returncode, 0, result.stderr)
            headers = [fits.getheader(path) for path in sorted((output / "aligned_stacked_fits").glob("*.fits"))]
            self.assertEqual({header["FILTER"] for header in headers}, {"R", "G", "B"})
            self.assertEqual({float(header["EXPTIME"]) for header in headers}, {30.0, 40.0, 50.0})

            foreign = output / "reports" / "user_notes.txt"
            foreign.write_text("preserve", encoding="utf-8")
            rerun = run_script(*command, "--clean-derived")
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve")
            self.assertTrue(any((output / ".trash").glob("fits_rgb_batch_*")))


class StatisticalValidationRegressionTest(unittest.TestCase):
    def test_supplied_photometric_sigmas_are_absolute(self) -> None:
        x = np.array([1.0, 1.2, 1.4, 1.6])
        design = np.column_stack([np.ones_like(x), x])
        values = 0.46 + 0.10 * x
        sigma = np.full_like(x, 0.01)
        _beta, covariance, _weights, _residuals = PHOTOMETRIC.weighted_lstsq(design, values, sigma)
        expected = np.linalg.inv((design / sigma[:, None]).T @ (design / sigma[:, None]))
        np.testing.assert_allclose(covariance, expected, rtol=1e-12, atol=1e-15)
        self.assertGreater(float(np.sqrt(covariance[0, 0])), 1.0e-4)

    def test_photometric_solution_materializes_both_requested_json_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            table = root / "standards.csv"
            summary = root / "summary.json"
            output = root / "output.json"
            table.write_text(
                "inst_mag,std_mag,airmass\n"
                "10.0,34.80,1.0\n"
                "10.1,34.86,1.2\n"
                "10.2,34.92,1.4\n"
                "10.3,34.98,1.6\n"
                "10.4,35.04,1.8\n",
                encoding="utf-8",
            )
            result = run_script(
                "scripts/photometric_solution.py",
                str(table),
                "--summary-json",
                str(summary),
                "--output-json",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(summary.is_file())
            self.assertTrue(output.is_file())
            self.assertEqual(
                json.loads(summary.read_text(encoding="utf-8")),
                json.loads(output.read_text(encoding="utf-8")),
            )

    def test_impossible_rv_manifest_fails_domain_validation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = {
                "system_name": "AUDIT",
                "objective": "audit",
                "rv_datasets": [{"source": "missing.vels", "value_units": "m/s", "sample_count": 10}],
                "conclusions": "done",
                "initial_search": {"dominant_periods_days": [-5.0], "false_alarm_probabilities": [2.0]},
                "fitted_model": {
                    "planet_count": 1,
                    "chi2_before": -1.0,
                    "chi2_after": -2.0,
                    "rms_before": -3.0,
                    "rms_after": -4.0,
                },
                "planets": [{"period_days": -10.0}],
            }
            validation = RV._validate_manifest_payload(manifest, Path(raw), "en")
            self.assertEqual(validation["status"], "fail")
            self.assertIn("initial_search.false_alarm_probabilities[0].outside_0_1", validation["domain_errors"])
            self.assertIn("planets[0].period_days.not_positive_finite", validation["domain_errors"])
            self.assertIn("rv_datasets[0].source.not_existing_file", validation["domain_errors"])

            manifest_path = Path(raw) / "session_manifest.json"
            summary_path = Path(raw) / "validation.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = run_script(
                "scripts/radial_velocity_workbench.py",
                "validate-manifest",
                str(manifest_path),
                "--summary-json",
                str(summary_path),
                "--language",
                "en",
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["app_status"], "FAIL")
            self.assertEqual(payload["qa"]["status"], "fail")

    def test_degenerate_sb2_covariance_is_rejected(self) -> None:
        x = np.linspace(-100.0, 100.0, 7)
        y = 0.1 + np.exp(-0.5 * ((x + 45) / 10) ** 2) + 0.8 * np.exp(-0.5 * ((x - 45) / 10) ** 2)
        with self.assertRaises(ValueError):
            SB2.fit_trace(x, y, 20.0)
        rows = [
            {
                "status": "accepted",
                "left": {"center_kms": -20.0, "center_err_kms": float("inf"), "sigma_kms": 10.0},
            }
        ]
        self.assertIsNone(SB2.weighted_component_mean(rows, "left"))


class ControlledInputFailureRegressionTest(unittest.TestCase):
    def test_invalid_aperture_annulus_is_controlled_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "image.fits"
            summary = root / "summary.json"
            fits.PrimaryHDU(np.ones((32, 32), dtype=np.float32)).writeto(image)
            result = run_script(
                "scripts/aperture_photometry.py",
                str(image),
                "--center",
                "16",
                "16",
                "--radius",
                "3",
                "--annulus-inner",
                "10",
                "--annulus-outer",
                "5",
                "--summary-json",
                str(summary),
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["qa"]["status"], "blocked")

    def test_ascii_nan_is_controlled_block_with_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spectrum = root / "spectrum.txt"
            output = root / "out"
            summary = output / "summary.json"
            spectrum.write_text(
                "\n".join(f"{6500 + index} {'nan' if index == 5 else 1.0}" for index in range(20)) + "\n",
                encoding="utf-8",
            )
            result = run_script(
                "scripts/ascii_spectrum_workbench.py",
                str(spectrum),
                "--output-dir",
                str(output),
                "--summary-json",
                str(summary),
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            rendered = summary.read_text(encoding="utf-8")
            self.assertNotIn(": NaN", rendered)
            self.assertNotIn(": Infinity", rendered)
            payload = json.loads(rendered)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["qa"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
