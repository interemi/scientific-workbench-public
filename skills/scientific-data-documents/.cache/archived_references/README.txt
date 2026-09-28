SCIENTIFIC-DATA-ANALYSIS SKILL
v2.2 evaluation-hardening over v2.1 compact-router, v2.0 integrated skill + ScientificWorkbench, v1.9 contract-freeze, v1.8 app-ready backend, v1.7 real-world, and v1.6 stable

Compatibility anchors for historical gates: v1.7 stable over v1.6 stable; v1.6 remains the installed stable baseline.

Purpose
- Codex skill for scientific data analysis, with a strong astronomy, notebooks, FITS, reporting, and document-handoff bias.
- Use it to inspect inputs, choose the right route, run safe local tools, build reproducible outputs, and explain results clearly in Spanish or English.
- It is practical rather than magical: preserve originals, work on copies when editing, record provenance, and keep conclusions tied to evidence.
- v2.2 is the evaluation-hardening release: the installed bundle stays compact for plugin-eval, temporary outputs and caches stay outside the active skill surface, historical routing is stubbed rather than eagerly loaded, and the guide advances to v2.2 without changing scientific contracts.
- v2.1 is the compact-router release: SKILL.md stays as a focused router while generated public-surface details and long routing notes live in references.
- v2.0 is the integrated skill + ScientificWorkbench release: the skill remains the deterministic local execution engine, while the macOS app consumes the installed registry, envelopes, run bundles, typed artifacts, previews, job states, and controlled failures through tested app-side workflows.
- v1.9 is the contract-freeze and app-facing hardening release: artifact type names are frozen, app-facing errors are cleaner, app hints and next actions are richer, exposure modes are locked, v2.0 deferrals are protected, and app-like regression coverage is broader.
- v1.8 is the app-ready backend release: JSON envelopes, run-bundle contract, app-readiness matrix, dry-run router, app-like regressions, and a clear boundary that ScientificWorkbench sync remains future work.
- v1.7 is the installed real-world applicability update: the 59 public capabilities now have a classification matrix, general/non-astro routes, transferable-pattern docs, professional/personal package examples, and explicit not-applicable criteria.
- v1.6 remains the installed stable baseline and completed 59-capability audit-and-hardening release: every public registry entry has been tested through happy, realistic, edge, and broken cases where applicable; accepted P0/P1/P2 fixes were retested before phase sync.
- v1.5 stable was the capability-coverage release: the public surface kept the same product architecture, while capabilities without direct smoke coverage gained a maintainer probe matrix and a release gate that rejects real failures or unprobed stable entries.
- v1.4 added companion routing: the skill can recommend local installed companion skills/plugins for narrow handoff steps without invoking connectors or changing the scientific owner of the task.
- Optional STILTS/TOPCAT and APT routes are available for astronomy catalog and aperture-photometry workflows, but Java/STILTS/APT are not core dependencies.
- v1.3 remains the capability-audit hardening base: DuckDB reserved-alias safety, public SB2 `fit` alias, legacy RV blocked JSON for incomplete inputs, reduced ASCII spectra coursework full-smoke repair, and a focused v1.3 regression gate.

Four visible blocks
- core / routing
  Environment choice, install checks, datanalysis wrapper, healthchecks, and route selection.
- astronomy observational
  FITS, astrometry, photometry, spectra, radial velocity, legacy coursework, and optional TEAREDUCE routes.
- documents + reporting
  PDF/Office/iWork intake, LaTeX, scientific writing, presentation handoff, and deliverable QA.
- notebooks + cross-domain
  Jupyter notebooks, tables, forecasting, DuckDB-style exploration, and non-astro applied analysis.

Normal entry
1. If the machine or Python environment is unclear, start with:
   python scripts/datanalysis_env.py status
   python scripts/env_doctor.py --summary-json env_doctor.json

   If the task may need a local companion skill/plugin for a narrow step, use:
   references/companion-routing.md
   python scripts/companion_route_check.py --task "..." --file path-or-name

2. If the work is observational astronomy, start with:
   references/astronomy-fits.md
   scripts/inspect_fits.py
   Then route only as needed to astrometry, FITS RGB batch products, photometry, spectra, RV, legacy spectroscopy, or TEAREDUCE.
   For derived RGB or pseudo-RGB products from FITS trees, use:
   references/fits-rgb-workflow.md
   scripts/fits_rgb_batch.py
   scripts/rgb_visual_fits_export.py when a repaired visual RGB needs a display-only FITS export or before/after comparison.
   For optional STILTS/TOPCAT catalog operations or APT batch output, use:
   references/external-astronomy-tools.md
   scripts/external_astro_tools_preflight.py
   scripts/stilts_workbench.py
   scripts/apt_workbench.py

3. If the work starts from a professor notebook or a group practical, start with:
   references/coursework-notebook-fidelity.md
   references/coursework-notebook-comparison.md
   references/coursework-figure-equivalents.md
   scripts/coursework_notebook_fidelity_check.py
   scripts/notebook_branch_compare.py
   scripts/notebook_workbench.py

4. If the work is reporting, LaTeX, PDF, Pages/Office, poster, or presentation handoff, start with:
   references/formats-and-handoffs.md
   references/scientific-presentation-handoff.md
   references/academic-reporting.md
   scripts/document_intake_workbench.py
   scripts/latex_workbench.py
   scripts/scientific_writeup_review.py
   scripts/presentation_workbench.py

5. If the work is table-first or outside astronomy, start with:
   references/v1-7-real-world-guide.md
   references/non-astro-start-here.md
   references/cross-domain-workflows.md
   references/general-timeseries.md
   scripts/profile_table.py
   scripts/cross_domain_data_workbench.py

Public surface snapshot
The block below is generated from public_surface_registry.yaml. Do not edit it by hand; update the registry and run scripts/sync_public_surface_docs.py when the public surface really changes. The Markdown copy for maintainers lives in references/public-surface-snapshot.md so SKILL.md can stay compact.

BEGIN GENERATED PUBLIC SURFACE SNAPSHOT
This snapshot is generated from public_surface_registry.yaml.
Compact text form: see references/public-surface-snapshot.md for descriptions.

core / routing:
- datanalysis_env.py status [golden_path, stable, smoke none]
- datanalysis_healthcheck.py [golden_path, stable, smoke none]
- env_doctor.py [golden_path, stable, smoke core]
- companion_route_check.py [supporting_tool, stable, smoke none]
- external_astro_tools_preflight.py [supporting_tool, optional, smoke none]

astronomy observational:
- astrometry_net_workbench.py preflight [golden_path, stable, smoke full]
- echelle_multispec_inventory.py [golden_path, narrow, smoke core]
- inspect_fits.py [golden_path, stable, smoke core]
- legacy_spectroscopy_envcheck.py [golden_path, narrow, smoke none]
- photometric_solution.py [golden_path, stable, smoke core]
- photometry_noise_budget.py [golden_path, stable, smoke core]
- radial_velocity_workbench.py inspect [golden_path, stable, smoke core]
- teareduce_router.py [golden_path, optional, smoke none]
- apt_workbench.py [supporting_tool, optional, smoke none]
- astrometry_net_workbench.py verify-existing-wcs [supporting_tool, stable, smoke full]
- fits_rgb_batch.py [supporting_tool, stable, smoke none]
- fxcor_iraf_workbench.py prepare-session [supporting_tool, narrow, smoke none]
- fxcor_iraf_workbench.py run-auto [supporting_tool, narrow, smoke none]
- istarmod_workbench.py inspect-tree [supporting_tool, narrow, smoke none]
- istarmod_workbench.py prepare-copy [supporting_tool, narrow, smoke none]
- legacy_external_reference_check.py [supporting_tool, narrow, smoke none]
- legacy_rv_coursework_workbench.py analyze [supporting_tool, narrow, smoke none]
- legacy_spectroscopy_report_builder.py populate [supporting_tool, narrow, smoke none]
- legacy_spectroscopy_report_builder.py scaffold [supporting_tool, narrow, smoke none]
- li6708_equivalent_width_workbench.py measure [supporting_tool, stable, smoke core]
- radial_velocity_workbench.py validate-manifest [supporting_tool, stable, smoke none]
- rgb_visual_fits_export.py [supporting_tool, stable, smoke none]
- sb2_double_gaussian_workbench.py fit [supporting_tool, narrow, smoke none]
- stilts_workbench.py [supporting_tool, optional, smoke none]

documents + reporting:
- document_intake_workbench.py [golden_path, stable, smoke core]
- latex_workbench.py review [golden_path, stable, smoke full]
- latex_workbench.py scaffold [golden_path, stable, smoke full]
- scientific_writeup_review.py [golden_path, stable, smoke core]
- deliverable_factory.py scaffold [supporting_tool, stable, smoke core]
- iwork_workbench.py [supporting_tool, optional, smoke none]
- keynote_export.py [supporting_tool, platform_bound, smoke none]
- latex_workbench.py compile [supporting_tool, stable, smoke full]
- office_roundtrip.py docx-style-inventory [supporting_tool, stable, smoke none]
- office_roundtrip.py docx-styled-replace [supporting_tool, stable, smoke none]
- presentation_workbench.py existing-deck-style-audit [supporting_tool, stable, smoke full]
- presentation_workbench.py inspect [supporting_tool, stable, smoke full]
- quicklook_bridge.py [supporting_tool, platform_bound, smoke full]
- semantic_diff.py [supporting_tool, stable, smoke core]

notebooks + cross-domain:
- bootstrap_analysis_notebook.py [golden_path, stable, smoke core]
- cross_domain_data_workbench.py [golden_path, stable, smoke core]
- notebook_workbench.py execute-copy [golden_path, stable, smoke full]
- profile_table.py [golden_path, stable, smoke core]
- spectra_ascii_coursework_workbench.py [golden_path, stable, smoke full]
- timeseries_forecasting_workbench.py [golden_path, stable, smoke none]
- catalog_workbench.py crossmatch-sky [supporting_tool, stable, smoke core]
- coursework_notebook_fidelity_check.py [supporting_tool, stable, smoke none]
- duckdb_workbench.py [supporting_tool, optional, smoke none]
- inspect_data_container.py [supporting_tool, stable, smoke core]
- notebook_branch_compare.py [supporting_tool, stable, smoke none]
- physical_qa.py [supporting_tool, stable, smoke none]
END GENERATED PUBLIC SURFACE SNAPSHOT

Install and runtime
- Installed skill path:
  ~/.codex/skills/scientific-data-analysis
- Preferred full environment for maintenance, notebooks, astronomy-heavy work, and optional backends:
  conda env create -f environment.yml
  conda activate datanalysis
  python scripts/datanalysis_env.py status
- Lightweight route for core functionality:
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -r requirements-core.txt
- If base Python lacks optional packages, use the datanalysis wrapper instead of forcing the shell interpreter:
  python scripts/datanalysis_env.py run-tool TOOL_NAME ...

Validation
- Normal install check:
  python scripts/env_doctor.py --summary-json env_doctor.json --manifest-json env_doctor_manifest.json
  python scripts/portable_smoke_test.py --profile core --output-dir smoke-out --examples-dir examples --summary-json smoke-out/summary.json
- Maintainer check after editing public docs, registry, or scripts:
  python scripts/sync_public_surface_docs.py --check
  python scripts/skill_surface_audit.py
  python scripts/audit_v1_2_release_regression.py
  python scripts/audit_v1_3_release_regression.py
  python scripts/audit_v1_4_companion_routing_regression.py
  python scripts/audit_v1_5_release_regression.py
  python scripts/audit_v1_6_release_regression.py
  python scripts/capability_probe_matrix.py --output-dir capability-probe --summary-json capability-probe/summary.json
  python scripts/audit_fits_rgb_batch_regression.py
  python scripts/audit_external_astro_tools_regression.py
  python scripts/validate_skill_samples.py . --output-dir skill-smoke --max-per-ext 0 --validation-profile quick
- Deeper checks are for broad releases or optional-backend work, not for every small README or reference edit.

Boundaries
- Do not overwrite original notebooks, data, decks, PDFs, or iWork files. Work on copies when editing or executing.
- TEAREDUCE, IRAF/fxcor, Keynote GUI export, Quick Look rendering, OCR, DuckDB, and deep iWork roundtrips are optional or platform-bound routes.
- STILTS/TOPCAT and APT are optional external astronomy routes. Prefer STILTS over TOPCAT GUI for reproducible catalog work, and use APT batch mode only with a saved `APT.pref` recorded in provenance.
- If a machine intentionally installs STILTS/APT, validate that local setup with `scripts/external_astro_tools_local_validation.py`; absence remains a controlled optional-backend result, not a failed skill install.
- Notebook execution success is not the same as visual-portability success; check rendered outputs when figures matter.
- Companion routing is advisory. It can recommend local helpers such as pdf, Documents, Presentations, Spreadsheets, jupyter-notebook, Browser Use/playwright, screenshot, transcribe/speech, imagegen, or frontend tools for narrow steps, but this skill's routing layer does not route to email, Google Drive, or Zotero.
- FITS RGB batch products are visual derived products. They preserve source FITS files and record WCS/phase alignment choices, but they are not a substitute for full CCD calibration QA.
- FITS RGB visual exports use normalized display intensities. They are valid handoff/inspection containers, not calibrated flux products.
- Generated public-surface snapshots belong to public_surface_registry.yaml, not to manual editing.
- Detailed cookbook behavior belongs in references/, not in this README.

More detail
- references/v1-7-real-world-guide.md
- references/real-world-capability-classification-v1-7.md
- references/real-world-use-cases.md
- references/real-world-measurement-patterns.md
- references/astro-transferable-patterns.md
- references/real-world-package-playbooks.md
- references/portable-install.md
- references/deployment-quickstart.md
- references/core-and-optional.md
- references/architecture.md
- references/external-astronomy-tools.md
- references/output-and-colab-policy.md
