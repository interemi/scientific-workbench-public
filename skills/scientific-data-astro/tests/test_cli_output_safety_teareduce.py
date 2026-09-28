"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from astro_cli_output_safety_support import *  # noqa: F403


class AstroCliOutputSafetyRegressionTest(AstroCliCollisionAssertions, unittest.TestCase):
    def test_teareduce_smoke_protects_implicit_home_search_roots(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / "home"
            documents = home / "Documents"
            documents.mkdir(parents=True)
            notebook = documents / "P2_03_correccion_bias.ipynb"
            notebook.write_text(
                json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}),
                encoding="utf-8",
            )
            before = tree_snapshot(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "teareduce_smoke_test.py"),
                    "--output-dir",
                    str(root / "output"),
                    "--summary-json",
                    str(notebook),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "HOME": str(home),
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(payload["artifacts"], {})
            self.assertEqual(tree_snapshot(root), before)

    def test_all_registered_astro_outputs_block_before_success_or_failure_emitters(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            outputs = root / "outputs"
            tree = inputs / "tree"
            practice = inputs / "practice"
            session = inputs / "session"
            project = inputs / "project"
            for directory in (inputs, outputs, tree, practice, session, project):
                directory.mkdir(parents=True, exist_ok=True)

            valid_fits = inputs / "valid.fits"
            valid_fits.write_bytes(b"SIMPLE  =                    T immutable\n")
            invalid_fits = inputs / "invalid.fits"
            invalid_fits.write_text("not a FITS file\n", encoding="utf-8")
            valid_csv = inputs / "valid.csv"
            valid_csv.write_text(
                "inst_mag,std_mag,airmass,x,y,id\n10,34.7,1.2,1,2,a\n",
                encoding="utf-8",
            )
            invalid_csv = inputs / "invalid.csv"
            invalid_csv.write_text("bad\nvalue\n", encoding="utf-8")
            preferences = inputs / "APT.pref"
            preferences.write_text("immutable preferences\n", encoding="utf-8")
            previous_png = inputs / "previous.png"
            previous_png.write_bytes(b"immutable png\n")
            tree_member = tree / "member.fits"
            tree_member.write_text("immutable tree member\n", encoding="utf-8")
            practice_member = practice / "raw.fits"
            practice_member.write_text("immutable practice member\n", encoding="utf-8")
            session_manifest = session / "session_manifest.json"
            session_manifest.write_text("{}\n", encoding="utf-8")
            project_env = inputs / "envcheck.json"
            project_env.write_text("{}\n", encoding="utf-8")
            source_list = inputs / "sources.txt"
            source_list.write_text("1 2 a\n", encoding="utf-8")
            peer_seed = inputs / "img_001.fits"
            peer_seed.write_text("immutable peer seed\n", encoding="utf-8")
            peer_other = inputs / "img_002.fits"
            peer_other.write_text("immutable peer\n", encoding="utf-8")
            inferred_practice = inputs / "legacy-practice"
            (inferred_practice / "fits_p1").mkdir(parents=True)
            inferred_calibration = inferred_practice / "FWHM_vsini_datafit.csv"
            inferred_calibration.write_text("FWHM,vsini\n1,2\n", encoding="utf-8")
            legacy_summary = inputs / "legacy-summary.json"
            legacy_summary.write_text(
                json.dumps({"practice_root": str(inferred_practice)}),
                encoding="utf-8",
            )
            referenced_log = inputs / "istarmod.log"
            referenced_log.write_text("immutable log\n", encoding="utf-8")
            istarmod_summary = inputs / "istarmod-summary.json"
            istarmod_summary.write_text(
                json.dumps({"artifacts": {"log_path": str(referenced_log)}}),
                encoding="utf-8",
            )
            duplicate_a = inputs / "duplicate-a"
            duplicate_b = inputs / "duplicate-b"
            duplicate_a.mkdir()
            duplicate_b.mkdir()
            duplicate_science_a = duplicate_a / "same.fits"
            duplicate_science_b = duplicate_b / "same.fits"
            duplicate_science_a.write_text("science a\n", encoding="utf-8")
            duplicate_science_b.write_text("science b\n", encoding="utf-8")

            preview_symlink = outputs / "preview.png"
            preview_symlink.symlink_to(valid_fits)
            output_json_symlink = outputs / "photometric.json"
            output_json_symlink.symlink_to(valid_csv)
            manifest_hardlink = outputs / "manifest.json"
            os.link(valid_fits, manifest_hardlink)
            coefficient_hardlink = outputs / "coefficients.csv"
            os.link(valid_csv, coefficient_hardlink)
            apt_hardlink = outputs / "apt-sources.txt"
            os.link(valid_csv, apt_hardlink)
            descendant_hardlink = outputs / "tree-member-summary.json"
            os.link(tree_member, descendant_hardlink)
            derived_ccd = outputs / "ccd-derived"
            derived_ccd.mkdir()
            derived_master = derived_ccd / "master_bias.fits"
            os.link(practice_member, derived_master)

            case_paths = dict(locals())
            case_paths["ROOT"] = ROOT
            cases = resolve_cli_collision_cases(load_cli_case_data()["collision_cases"], case_paths)

            self.assertGreaterEqual(len(cases), 90)
            for label, script, args in cases:
                with self.subTest(label=label, script=script):
                    self.assert_controlled_collision(root, script, args)


if __name__ == "__main__":
    unittest.main()
