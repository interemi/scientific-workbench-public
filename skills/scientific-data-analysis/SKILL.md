---
name: "scientific-data-analysis"
description: "Use when the user needs reproducible scientific data analysis, astronomy/FITS, tables, notebooks, spectra, time series, documents, LaTeX, reporting, safe copies, JSON envelopes, run bundles, plots, QA, or bilingual English/Spanish scientific work."
---

# Scientific Data Analysis

Use this skill when the task needs reproducible scientific or technical work over data, notebooks, FITS files, spectra, tables, documents, LaTeX projects, reports, or ScientificWorkbench-compatible backend outputs.

Keep this file as the compact router. Load only the reference that matches the task. Historical routing detail is summarized in `references/v2-1-expanded-skill-routing.md`; the generated registry snapshot lives in `references/public-surface-snapshot.md`.

## Current Product Version

`v2.8 family integrity hardening` makes current-contract validation explicit. The mother resolves its canonical 61-capability map through maintainer, fails closed without valid routing metadata, and uses `audit_v2_8_family_integrity_regression.py` as the structural release gate. Historical snapshot regressions remain available but are not current blockers.

Compatibility anchors remain valid:

- `v2.7`: senior integration review and ScientificWorkbench sync plan.
- `v2.6`: measured usage, benchmark matrix, local proxy harness.
- `v2.5/v2.4/v2.3`: budget deferral and mother + child modular architecture.
- `v2.0/v1.9/v1.8`: app-ready envelopes, run bundles, artifact/error/exposure contracts.
- `v1.7/v1.6`: real-world applicability and completed 59-capability hardening baseline.

Optional STILTS/TOPCAT/APT, iWork, Keynote, TEAREDUCE, IRAF, iSTARMOD, and GUI routes stay optional, expert, legacy, platform-bound, or maintainer-scoped. Missing optional backends must block cleanly.

## Non-Destructive Rules

- Never overwrite raw data, original notebooks, original documents, original decks, or source FITS files.
- Work on copies or derived output directories unless the user explicitly asks otherwise and the tool supports it safely.
- For documents, iWork, Keynote, notebooks, and GUI-adjacent work, prefer copied workspaces and explicit manifests.
- Treat `PASS`, `WARNING`, `BLOCKED_CONTROLADO`, and `FAIL` honestly. Do not hide tracebacks, false success, NaN/Inf surprises, misleading products, or original mutation.
- Keep provenance visible: command, inputs, outputs, assumptions, parameters, warnings, errors, artifacts, and next actions.
- Match the user's language by default; support Spanish and English directly.

## Four Visible Blocks

1. `core / routing`: environment, install, healthchecks, registry, routers, and maintenance gates.
2. `astronomy observational`: FITS, astrometry, photometry, spectroscopy, radial velocity, TEAREDUCE, optional astronomy backends, and legacy coursework routes.
3. `documents + reporting`: document intake, PDF/Office/iWork, presentations, LaTeX, semantic diffs, handoff packages, and scientific writing review.
4. `notebooks + cross-domain`: notebooks, mixed tables, containers, forecasting, DuckDB, catalogs, packages, and non-astro applied analysis.

The authoritative public surface is `public_surface_registry.yaml`; the rendered snapshot is `references/public-surface-snapshot.md`. v1.6/v1.7 audited a 59-capability baseline, and v2.0/v2.1 expose 61 registry labels after the integrated-release additions.

## Start Here

### If The Task Is Broad Or Ambiguous

Use the shortest applicable front door:

- non-astro or real-world intake: `references/non-astro-start-here.md`
- mixed data/document package: `references/cross-domain-workflows.md`
- file formats and handoffs: `references/formats-and-handoffs.md`
- astronomy-like files or FITS: `references/astronomy-fits.md`
- full public surface lookup: `references/public-surface-snapshot.md`
- current family integrity gate and historical/current boundary: `references/v2-8-family-integrity-hardening.md`
- current release guide: `references/guia_scientific_data_analysis_v2_8.tex`, `references/guia_scientific_data_analysis_v2_8.pdf`
- senior integration hardening and app-sync prep: `references/v2-7-senior-integration-hardening.md`, `references/v2-7-scientificworkbench-sync-plan.md`
- measured usage notes: `references/v2-6-measured-usage-charter.md`, `references/v2-6-observed-usage-contract.md`, `references/v2-6-routing-cost-findings.md`
- deep budget-deferral hardening notes: `references/v2-5-budget-deferral-hardening.md`
- budget architecture hardening notes: `references/v2-4-budget-architecture-hardening.md`
- compact evaluation-hardening notes: `references/v2-2-evaluation-hardening.md`
- historical legacy routing summary: `references/v2-1-expanded-skill-routing.md`

### Core / Routing

- Environment or interpreter choice: `scripts/datanalysis_env.py status`
- Heavy environment readiness: `scripts/datanalysis_healthcheck.py`
- Machine readiness and optional backends: `scripts/env_doctor.py`
- Companion skill/plugin advice: `references/companion-routing.md` and `scripts/companion_route_check.py`
- App-ready dry-run planning: `scripts/scientific_workflow_router.py`
- Install and portability: `references/portable-install.md`, `references/deployment-quickstart.md`, `references/core-and-optional.md`

### Astronomy Observational

- FITS inspection: `references/astronomy-fits.md` and `scripts/inspect_fits.py`
- FITS RGB/pseudo-RGB: `references/fits-rgb-workflow.md`, `scripts/fits_rgb_batch.py`, `scripts/rgb_visual_fits_export.py`
- Astrometry: `references/astrometry-net.md`, `scripts/astrometry_net_workbench.py`
- Photometry and detector planning: `references/photometry-detectors.md`, `scripts/photometric_solution.py`, `scripts/photometry_noise_budget.py`
- Catalog/crossmatch work: `scripts/catalog_workbench.py`; optional STILTS via `references/external-astronomy-tools.md` and `scripts/stilts_workbench.py`
- Radial velocity/Systemic: `references/radial-velocity-systemic.md`, `scripts/radial_velocity_workbench.py`
- Spectra and spectroscopy: `references/spectra-and-pipelines.md`, `scripts/spectral_workbench.py`, `scripts/spectroscopy_pipeline_workbench.py`
- Legacy IRAF/fxcor/iSTARMOD coursework: `references/legacy-spectroscopy-coursework-macos.md` and the legacy workbench scripts
- TEAREDUCE only when explicitly requested or classroom-faithful: `references/teareduce-practical-guide.md`, `references/teareduce.md`, `scripts/teareduce_router.py`

### Documents + Reporting

- Mixed document intake: `references/formats-and-handoffs.md`, `scripts/document_intake_workbench.py`, `scripts/document_semantics.py`
- PDF recovery or weak scans: `scripts/pdf_recover_extract.py`; use the PDF skill or rendered previews when visual layout matters
- Office/iWork copied round trips: `scripts/office_roundtrip.py`, `scripts/iwork_workbench.py`, `scripts/iwork_roundtrip.py`
- Presentations and Keynote: `references/scientific-presentation-handoff.md`, `scripts/presentation_workbench.py`, `scripts/keynote_export.py`, `scripts/quicklook_bridge.py`
- LaTeX/Overleaf: `references/latex-overleaf.md`, `scripts/latex_workbench.py`
- Scientific writing review: `references/academic-reporting.md`, `references/astrophysics-academic-writing.md`, `scripts/scientific_writeup_review.py`
- Handoffs and semantic comparison: `scripts/deliverable_factory.py`, `scripts/semantic_diff.py`

### Notebooks + Cross-Domain

- Tabular profiling: `scripts/profile_table.py`
- Mixed data workbench: `references/cross-domain-workflows.md`, `scripts/cross_domain_data_workbench.py`
- Containers and archives: `scripts/inspect_data_container.py`
- Notebook inspection/execution copy: `scripts/notebook_workbench.py`
- Professor/coursework notebook fidelity: `references/coursework-notebook-fidelity.md`, `scripts/coursework_notebook_fidelity_check.py`
- Branch/product comparison: `references/coursework-notebook-comparison.md`, `scripts/notebook_branch_compare.py`
- Forecasting: `references/general-timeseries.md`, `scripts/timeseries_forecasting_workbench.py`
- Optional DuckDB queries: `scripts/duckdb_workbench.py`
- General scientific sanity checks: `scripts/physical_qa.py`

## Scientific Workflow

1. Lock the scientific or practical goal.
2. Preserve raw inputs and work on derived outputs.
3. Inventory formats, metadata, units, time systems, coordinate frames, nulls, ranges, and uncertainties.
4. Build a thin reproducible script, notebook, or run bundle.
5. Inspect before transforming.
6. Validate assumptions, units, shapes, WCS/time metadata, and dropped rows/pixels.
7. Deliver artifacts plus a short interpretation, caveats, and next actions.

## App-Ready Contract

For ScientificWorkbench-facing work, prefer JSON envelopes and run bundles documented in:

- `references/v1-8-app-ready-contract.md`
- `references/v1-8-run-bundle-contract.md`
- `references/v1-9-artifact-types-freeze.md`
- `references/v1-9-error-contract.md`
- `references/v2-0-skill-app-contract.md`

Minimum app-facing fields: `contract_version`, `tool`, `status`, `command`, `inputs`, `outputs`, `typed_artifacts`, `warnings`, `errors`, `qa`, `provenance`, `next_actions`, `original_modified`, and `app_hints`.

## Maintenance

For skill maintenance, validation, release checks, or plugin-eval work, use:

- `references/architecture.md`
- `references/v2-6-measured-usage-charter.md`
- `references/v2-6-routing-cost-findings.md`
- `references/v2-6-cost-optimization-log.md`
- `references/v2-5-budget-deferral-hardening.md`
- `references/v2-4-budget-architecture-hardening.md`
- `references/v2-3-modular-architecture-charter.md`
- `references/v2-2-evaluation-hardening.md`
- `references/v2-1-skill-compaction.md`
- `scripts/sync_public_surface_docs.py --check`
- `scripts/skill_surface_audit.py`
- `scripts/portable_smoke_test.py --profile core`
- `scripts/audit_*.py` and maintainer-only release tools are stable wrappers; full historical bodies live canonically in the sibling `scientific-data-maintainer` skill, with mother stubs or wrappers kept for compatibility
- `scripts/audit_v2_6_*` for measured-usage benchmark matrix, observed-usage harness, and app-ready cost sanity checks
- `scripts/audit_v2_8_family_integrity_regression.py` for the current 61-capability registry/module-map, ownership, router, policy, symlink, portability, and helper invariants
- `scripts/audit_v2_7_senior_integration_regression.py` as the preserved v2.7 snapshot gate; do not use it alone to declare a current release closed

Coverage summaries and plugin-eval ratings are scoped evidence, not exhaustive proof or release authority. Use the v2.8 gate plus the relevant portable smoke and app tests for the current change.

Do not load maintenance-heavy references during normal analysis unless the user is modifying, auditing, installing, validating, or releasing the skill.

## Example Requests

- "Analyze these FITS images, check the headers, and tell me if the WCS looks sane."
- "Haz una fotometria de apertura sobre esta imagen y dame el codigo y la interpretacion."
- "Fit a standard-star photometric solution and report zero point, extinction, residuals, and caveats."
- "Convierte este analisis en un notebook reproducible en espanol."
- "Inspecciona esta carpeta con PDFs, DOCX, CSV y notebooks sin tocar originales."
- "Create a LaTeX report that I can upload to Overleaf with bibliography, figures, and appendix material."
- "Profile this professional table, detect risks, and produce app-ready artifacts."
- "Evaluate the skill with plugin-eval and reduce the loaded routing surface without changing capabilities."
