"""Focused scientific regression tests split by domain."""

from __future__ import annotations

from scientific_regression_support import *  # noqa: F403


class MultispecRegressionTest(unittest.TestCase):
    def test_linear_and_log_linear_axes_follow_iraf_specwcs(self) -> None:
        linear = LEGACY.parse_multispec_entries({"WAT2_001": 'spec1 = "1 1 0 5000 2 3 0 0 0"'})[0]
        self.assertEqual(LEGACY.multispec_wavelength_axis(linear), [5000.0, 5002.0, 5004.0])

        log_linear = LEGACY.parse_multispec_entries({"WAT2_001": 'spec1 = "1 1 1 3.8 0.0001 3 0 0 0"'})[0]
        axis = LEGACY.multispec_wavelength_axis(log_linear)
        self.assertAlmostEqual(axis[0], 10**3.8, places=9)
        self.assertAlmostEqual(axis[2], 10**3.8002, places=9)

    def test_nonlinear_multispec_is_blocked(self) -> None:
        with self.assertRaises(LEGACY.UnsupportedMultispecDispersion):
            LEGACY.parse_multispec_entries({"WAT2_001": 'spec1 = "1 1 2 5000 2 3 0 0 0 1 2 3"'})

    def test_li_windows_are_disjoint_and_recover_known_equivalent_width(self) -> None:
        LI.validate_measurement_windows(LI.DEFAULT_CONTINUUM_WINDOWS, LI.DEFAULT_INTEGRATION_WINDOW)
        with self.assertRaises(ValueError):
            LI.validate_measurement_windows([(6707.80, 6708.60)], LI.DEFAULT_INTEGRATION_WINDOW)

        wavelength = np.linspace(6705.0, 6709.0, 4001)
        depth = 0.10
        sigma = 0.05
        flux = 1.0 - depth * np.exp(-0.5 * ((wavelength - 6707.5) / sigma) ** 2)
        measured = LI.measure_ew(
            wavelength,
            flux,
            LI.DEFAULT_CONTINUUM_WINDOWS,
            LI.DEFAULT_INTEGRATION_WINDOW,
            degree=1,
        )
        expected = depth * sigma * math.sqrt(2.0 * math.pi)
        self.assertAlmostEqual(measured["ew_angstrom"], expected, delta=expected * 0.01)

    def test_li_summary_csv_and_markdown_have_correct_artifact_types(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spectrum = root / "li.dat"
            output = root / "out"
            summary = root / "summary.json"
            wavelength = np.linspace(6705.0, 6709.0, 2001)
            flux = 1.0 - 0.10 * np.exp(-0.5 * ((wavelength - 6707.5) / 0.05) ** 2)
            np.savetxt(spectrum, np.column_stack([wavelength, flux]))
            result = run_script(
                "scripts/li6708_equivalent_width_workbench.py",
                "measure",
                str(spectrum),
                "--output-dir",
                str(output),
                "--skip-systematic-grid",
                "--summary-json",
                str(summary),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            artifacts = {item["label"]: item["artifact_type"] for item in payload["typed_artifacts"]}
            self.assertEqual(artifacts["summary csv"], "table_csv")
            self.assertEqual(artifacts["summary md"], "report_md")


class AstrometryRegressionTest(unittest.TestCase):
    @staticmethod
    def _write_peer(path: Path, object_name: str, image: np.ndarray) -> None:
        header = fits.Header()
        header["OBJECT"] = object_name
        header["FILTER"] = "R"
        header["EXPTIME"] = 30.0
        fits.PrimaryHDU(image.astype(np.float32), header=header).writeto(path)

    def test_peer_defaults_are_safe_and_mixed_objects_do_not_stack(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            [
                "astrometry_net_workbench.py",
                "stack-peers",
                "IMG_002.fits",
                "--output-path",
                "stack.fits",
            ],
        ):
            args = ASTROMETRY.parse_args()
        self.assertTrue(args.same_object)
        self.assertTrue(args.same_exptime)
        self.assertFalse(args.allow_unregistered_stack)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = np.zeros((32, 32), dtype=float)
            image[16, 16] = 1000.0
            for index, object_name in enumerate(("FIELD_A", "FIELD_B", "FIELD_C"), start=1):
                self._write_peer(root / f"IMG_{index:03d}.fits", object_name, image)
            seed = root / "IMG_002.fits"
            _index, header, shape = ASTROMETRY._first_image_hdu(seed)
            peers = ASTROMETRY.select_peer_frames_with_strategy(
                seed,
                header,
                shape,
                peer_count=3,
                same_object=True,
                same_exptime=True,
                max_separation_index=5,
            )
            self.assertEqual(peers, [seed])
            with self.assertRaises(SystemExit):
                ASTROMETRY.build_peer_stack(peers, root / "unsafe.fits")

    def test_compatible_peers_are_phase_registered_before_stacking(self) -> None:
        from scipy.ndimage import shift

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            yy, xx = np.indices((48, 48))
            base = (
                1000 * np.exp(-((xx - 14) ** 2 + (yy - 16) ** 2) / 5)
                + 700 * np.exp(-((xx - 33) ** 2 + (yy - 29) ** 2) / 8)
                + 400 * np.exp(-((xx - 25) ** 2 + (yy - 9) ** 2) / 3)
            )
            images = [base, shift(base, (1.2, -1.7), order=1), shift(base, (-0.8, 1.1), order=1)]
            paths = []
            for index, image in enumerate(images, start=1):
                path = root / f"IMG_{index:03d}.fits"
                self._write_peer(path, "SAFE_FIELD", image)
                paths.append(path)
            info = ASTROMETRY.build_peer_stack(paths, root / "registered.fits")
            self.assertEqual(info["registration_status"], "registered")
            self.assertEqual(len(info["registration"]), 3)
            self.assertTrue((root / "registered.fits").is_file())

    def test_app_status_never_overrides_warning_qa(self) -> None:
        skipped = {"mode": "solve-web-best-effort", "result_status": "skipped_unsuitable_input"}
        self.assertEqual(ASTROMETRY.build_astrometry_qa(skipped)["status"], "warning")
        self.assertEqual(ASTROMETRY.astrometry_status(skipped), "warning")

    def test_mixed_object_cli_is_controlled_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            peers = root / "peers"
            peers.mkdir()
            image = np.zeros((32, 32), dtype=float)
            image[16, 16] = 1000.0
            for index, object_name in enumerate(("FIELD_A", "FIELD_B", "FIELD_C"), start=1):
                self._write_peer(peers / f"IMG_{index:03d}.fits", object_name, image)
            summary = root / "summary.json"
            output = root / "stack.fits"
            result = run_script(
                "scripts/astrometry_net_workbench.py",
                "stack-peers",
                str(peers / "IMG_002.fits"),
                "--output-path",
                str(output),
                "--peer-count",
                "3",
                "--summary-json",
                str(summary),
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["qa"]["status"], "blocked")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
