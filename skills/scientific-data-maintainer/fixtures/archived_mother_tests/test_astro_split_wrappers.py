"""v2.3 astro child split checks for mother wrappers."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ASTRO_CHILD = ROOT.parent / "scientific-data-astro"
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


class AstroSplitWrappersTest(unittest.TestCase):
    def test_child_exists_and_mother_uses_wrappers(self) -> None:
        self.assertTrue((ASTRO_CHILD / "SKILL.md").exists())
        self.assertTrue((ASTRO_CHILD / "scripts" / "_internal" / "public_contract.py").exists())
        for name in ASTRO_SCRIPTS:
            mother = SCRIPTS / name
            child = ASTRO_CHILD / "scripts" / name
            self.assertTrue(mother.exists(), name)
            self.assertIn("child_skill_dispatch", mother.read_text(encoding="utf-8"), name)
            self.assertTrue(child.exists(), name)
            self.assertNotIn("child_skill_dispatch", child.read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
