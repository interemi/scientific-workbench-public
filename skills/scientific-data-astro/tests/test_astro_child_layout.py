"""v2.3 astro child layout checks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASTRO_SCRIPTS = [
    "external_astro_tools_preflight.py",
    "inspect_fits.py",
    "fits_rgb_batch.py",
    "rgb_visual_fits_export.py",
    "stilts_workbench.py",
    "astrometry_net_workbench.py",
    "radial_velocity_workbench.py",
    "legacy_spectroscopy_envcheck.py",
    "echelle_multispec_inventory.py",
    "fxcor_iraf_workbench.py",
    "legacy_rv_coursework_workbench.py",
    "sb2_double_gaussian_workbench.py",
    "li6708_equivalent_width_workbench.py",
    "legacy_external_reference_check.py",
    "istarmod_workbench.py",
    "legacy_spectroscopy_report_builder.py",
    "photometric_solution.py",
    "photometry_noise_budget.py",
    "apt_workbench.py",
    "teareduce_router.py",
    "spectra_ascii_coursework_workbench.py",
    "aperture_photometry.py",
    "ascii_spectrum_workbench.py",
    "astrometry_index_healthcheck.py",
    "astrometry_local_smoke_test.py",
    "exoplanet_timeseries_workbench.py",
    "fits_quicklook.py",
    "reduce_ccd_batch.py",
    "spectral_workbench.py",
    "spectroscopy_pipeline_workbench.py",
    "teareduce_bridge.py",
    "teareduce_cookbook_cr2images_workflow.py",
    "teareduce_cookbook_wavecal_workflow.py",
    "teareduce_flat_workflow.py",
    "teareduce_healthcheck.py",
    "teareduce_master_bias_workflow.py",
    "teareduce_notebook_runner.py",
    "teareduce_smoke_test.py",
]


class AstroChildLayoutTest(unittest.TestCase):
    def test_child_has_full_script_bodies(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").exists())
        self.assertTrue((ROOT / "scripts" / "_internal" / "public_contract.py").exists())
        self.assertTrue((ROOT / "scripts" / "datanalysis_env.py").exists())
        for name in ASTRO_SCRIPTS:
            path = ROOT / "scripts" / name
            self.assertTrue(path.exists(), name)
            self.assertNotIn("child_skill_dispatch", path.read_text(encoding="utf-8"), name)

    def test_references_are_present(self) -> None:
        for name in [
            "astronomy-fits.md",
            "photometry-detectors.md",
            "spectra-and-pipelines.md",
            "external-astronomy-tools.md",
        ]:
            self.assertTrue((ROOT / "references" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
