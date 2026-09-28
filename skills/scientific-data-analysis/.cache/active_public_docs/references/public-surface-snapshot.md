# Public Surface Snapshot

This generated reference keeps the registry-derived public surface out of the always-loaded `SKILL.md` router. Do not edit the generated block by hand; update `public_surface_registry.yaml` and run `python scripts/sync_public_surface_docs.py`.

<!-- BEGIN GENERATED PUBLIC SURFACE SNAPSHOT -->
_This snapshot is generated from `public_surface_registry.yaml`._
_Compact v2.5 form: labels and routing metadata only; keep full descriptions in the registry._

### core / routing
- `datanalysis_env.py status` [golden_path, stable, smoke `none`]
- `datanalysis_healthcheck.py` [golden_path, stable, smoke `none`]
- `env_doctor.py` [golden_path, stable, smoke `core`]
- `companion_route_check.py` [supporting_tool, stable, smoke `none`]
- `external_astro_tools_preflight.py` [supporting_tool, optional, smoke `none`]

### astronomy observational
- `astrometry_net_workbench.py preflight` [golden_path, stable, smoke `full`]
- `echelle_multispec_inventory.py` [golden_path, narrow, smoke `core`]
- `inspect_fits.py` [golden_path, stable, smoke `core`]
- `legacy_spectroscopy_envcheck.py` [golden_path, narrow, smoke `none`]
- `photometric_solution.py` [golden_path, stable, smoke `core`]
- `photometry_noise_budget.py` [golden_path, stable, smoke `core`]
- `radial_velocity_workbench.py inspect` [golden_path, stable, smoke `core`]
- `teareduce_router.py` [golden_path, optional, smoke `none`]
- `apt_workbench.py` [supporting_tool, optional, smoke `none`]
- `astrometry_net_workbench.py verify-existing-wcs` [supporting_tool, stable, smoke `full`]
- `fits_rgb_batch.py` [supporting_tool, stable, smoke `none`]
- `fxcor_iraf_workbench.py prepare-session` [supporting_tool, narrow, smoke `none`]
- `fxcor_iraf_workbench.py run-auto` [supporting_tool, narrow, smoke `none`]
- `istarmod_workbench.py inspect-tree` [supporting_tool, narrow, smoke `none`]
- `istarmod_workbench.py prepare-copy` [supporting_tool, narrow, smoke `none`]
- `legacy_external_reference_check.py` [supporting_tool, narrow, smoke `none`]
- `legacy_rv_coursework_workbench.py analyze` [supporting_tool, narrow, smoke `none`]
- `legacy_spectroscopy_report_builder.py populate` [supporting_tool, narrow, smoke `none`]
- `legacy_spectroscopy_report_builder.py scaffold` [supporting_tool, narrow, smoke `none`]
- `li6708_equivalent_width_workbench.py measure` [supporting_tool, stable, smoke `core`]
- `radial_velocity_workbench.py validate-manifest` [supporting_tool, stable, smoke `none`]
- `rgb_visual_fits_export.py` [supporting_tool, stable, smoke `none`]
- `sb2_double_gaussian_workbench.py fit` [supporting_tool, narrow, smoke `none`]
- `stilts_workbench.py` [supporting_tool, optional, smoke `none`]

### documents + reporting
- `document_intake_workbench.py` [golden_path, stable, smoke `core`]
- `latex_workbench.py review` [golden_path, stable, smoke `full`]
- `latex_workbench.py scaffold` [golden_path, stable, smoke `full`]
- `scientific_writeup_review.py` [golden_path, stable, smoke `core`]
- `deliverable_factory.py scaffold` [supporting_tool, stable, smoke `core`]
- `iwork_workbench.py` [supporting_tool, optional, smoke `none`]
- `keynote_export.py` [supporting_tool, platform_bound, smoke `none`]
- `latex_workbench.py compile` [supporting_tool, stable, smoke `full`]
- `office_roundtrip.py docx-style-inventory` [supporting_tool, stable, smoke `none`]
- `office_roundtrip.py docx-styled-replace` [supporting_tool, stable, smoke `none`]
- `presentation_workbench.py existing-deck-style-audit` [supporting_tool, stable, smoke `full`]
- `presentation_workbench.py inspect` [supporting_tool, stable, smoke `full`]
- `quicklook_bridge.py` [supporting_tool, platform_bound, smoke `full`]
- `semantic_diff.py` [supporting_tool, stable, smoke `core`]

### notebooks + cross-domain
- `bootstrap_analysis_notebook.py` [golden_path, stable, smoke `core`]
- `cross_domain_data_workbench.py` [golden_path, stable, smoke `core`]
- `notebook_workbench.py execute-copy` [golden_path, stable, smoke `full`]
- `profile_table.py` [golden_path, stable, smoke `core`]
- `spectra_ascii_coursework_workbench.py` [golden_path, stable, smoke `full`]
- `timeseries_forecasting_workbench.py` [golden_path, stable, smoke `none`]
- `catalog_workbench.py crossmatch-sky` [supporting_tool, stable, smoke `core`]
- `coursework_notebook_fidelity_check.py` [supporting_tool, stable, smoke `none`]
- `duckdb_workbench.py` [supporting_tool, optional, smoke `none`]
- `inspect_data_container.py` [supporting_tool, stable, smoke `core`]
- `notebook_branch_compare.py` [supporting_tool, stable, smoke `none`]
- `physical_qa.py` [supporting_tool, stable, smoke `none`]
<!-- END GENERATED PUBLIC SURFACE SNAPSHOT -->
