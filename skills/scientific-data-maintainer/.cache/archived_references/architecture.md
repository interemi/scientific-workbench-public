# Skill Architecture

Use this note when you are maintaining the skill rather than just using it.

## Visible Entry Blocks

The user-facing entrance should now read as four visible blocks:

- `core / routing`
  - environment, install, portability, `datanalysis_env.py`, healthchecks, and route choice
- `astronomy observational`
  - astrometry, radial velocity, photometry, spectroscopy, TEAREDUCE, and related astronomy workbenches
- `documents + reporting`
  - document intake, PDF/Office/iWork handling, LaTeX, reporting, and handoff creation
- `notebooks + cross-domain`
  - notebooks, tables, forecasting, DuckDB, and non-astro applied analysis

These blocks are a routing layer for humans. They do not require the scripts or folders to move physically.

## Activable Domain Modes

The skill should remain generalist at the core. Domain-specific behavior is activated by the task, not baked into every answer.

- `scientific / astrophysics mode`
  - activate for observational astronomy, scientific coursework, FITS/spectra/photometry/astrometry outputs, notebooks that interpret physical results, and master-level reports
  - enforce explicit separation of procedure, physical interpretation, limitations, and uncertainty
  - prefer reproducible code, cautious claims, units, and literature comparisons when the assignment calls for them
- `documents + reporting mode`
  - activate when the main risk is source structure, LaTeX, citations, layout, handoff, or final deliverable quality
  - pair with scientific mode when the document is an astrophysics report

This avoids the main architecture mistake: turning the whole skill into "astro-only" even when the task is non-astro tabular work, business-style analysis, or document intake.

## Public Entry Layer

These are the normal entrypoints that user-facing routing should prefer:

- `core / routing`
  - `portable-install.md`
  - `datanalysis_env.py`
  - `datanalysis_healthcheck.py`
  - `env_doctor.py`
  - `external_astro_tools_preflight.py` when optional Java/STILTS/APT readiness matters
  - `external_astro_tools_local_validation.py` only for maintainer validation on machines that intentionally install STILTS/APT
- `astronomy observational`
  - `inspect_fits.py`
  - `fits_rgb_batch.py`
  - `rgb_visual_fits_export.py` for display-only RGB FITS exports and before/after comparison artifacts after a repaired visual RGB product
  - `stilts_workbench.py` for optional STILTS-backed catalog conversion, filtering, crossmatch, and VOTable validation
  - `apt_workbench.py` for optional APT batch runs when saved GUI preferences are part of the provenance
  - `astrometry_net_workbench.py`
  - `radial_velocity_workbench.py`
  - `exoplanet_timeseries_workbench.py`
  - `spectroscopy_pipeline_workbench.py`
  - TEAREDUCE runners and `teareduce_router.py`
  - short operational references such as `fits-rgb-workflow.md`, `astrometry-net.md`, `radial-velocity-systemic.md`, `teareduce-practical-guide.md`, `teareduce.md`, and `coursework-spectra.md`
- `documents + reporting`
  - `document_semantics.py`
  - `document_intake_workbench.py`
  - `latex_workbench.py`
  - `scientific_writeup_review.py`
  - `deliverable_factory.py`
  - `formats-and-handoffs.md`
  - `latex-overleaf.md`
  - `academic-reporting.md`
  - `astrophysics-academic-writing.md` when the report interprets physical science results
- `notebooks + cross-domain`
  - `bootstrap_analysis_notebook.py`
  - `notebook_workbench.py`
  - `cross_domain_data_workbench.py`
  - `timeseries_forecasting_workbench.py`
  - `profile_table.py`
  - `duckdb_workbench.py`
  - `non-astro-start-here.md`
  - `cross-domain-workflows.md`
  - `general-timeseries.md`

## Deep Reference Layer

These references are useful, but they are not the default first stop:

- `canonical-astronomy-workflows.md`
- `spectra-and-pipelines.md`
- `workflows.md`
- `astrophysics-academic-writing.md` when not already selected by a report-like task
- `teareduce-canonical-workflows.md`
- `deployment-quickstart.md`
- `core-and-optional.md`

Use them when the route is already known and you need detail, scope, or interpretation. In particular, `canonical-astronomy-workflows.md` should stay a deeper astronomy note rather than the first page a new user sees.

## Internal Helper Layer

The internal helper modules now live under `scripts/_internal/`.

They support the public scripts but should not normally be routed to directly:

- `runtime_common.py`
- `datanalysis_bootstrap.py`
- `provenance_utils.py`
- `tabular_io.py`
- `ocr_utils.py`
- `iwork_iwa.py`
- helper assets such as `apple_vision_ocr.swift` and `apple_vision_ocr_bin`
- `datanalysis_bootstrap.py` is intentionally internal: user-facing routing should still point people to `datanalysis_env.py`, not to the bootstrap helper itself.

## Practical Rule

- If the task is about using the skill, stay on the public entry layer.
- If the task is about debugging, porting, validating, or refactoring the skill, move into the deep references and internal helpers only as needed.
- The goal is to keep the user-facing surface small while preserving the internal building blocks that keep the workbenches consistent.

## Product Hygiene Gates

Keep the maintenance path small and boring:

- `scripts/skill_hygiene_check.py --clean` removes generated local residue only.
- `scripts/sync_public_surface_docs.py --check` verifies that the generated public-surface snapshots in `references/public-surface-snapshot.md`, `README.txt`, and `RELEASE-v1.txt` still match `public_surface_registry.yaml`. `SKILL.md` is intentionally a compact router and no longer carries the generated snapshot.
- `scripts/skill_surface_audit.py` checks the broader product contract: registry schema, duplicate public ids, missing public scripts, broken documented `scripts/*.py` references, generated snapshot drift, and optional hygiene residue.
- `scripts/audit_v1_2_release_regression.py` is the narrow v1.2 gate for the matured coursework/document handoff routes: professor-notebook fidelity, DOCX marked-fragment edits, PDF fallback guidance, and exact visual-equivalent handoff.
- `scripts/audit_v1_3_release_regression.py` is the narrow v1.3 gate for the full-capability audit follow-up: DuckDB reserved-alias safety, SB2 public `fit`, legacy RV blocked JSON, and the reduced ASCII spectra coursework full-smoke path.
- `scripts/audit_v1_4_companion_routing_regression.py` is the narrow v1.4 gate for advisory companion routing: local handoffs are recommended for justified PDF, document, presentation, spreadsheet, notebook, browser, screenshot, audio, image, and frontend cases while email, Google Drive, and Zotero remain excluded from this release's routing policy.
- `scripts/audit_fits_rgb_batch_regression.py` is the narrow astronomy visual-products gate for FITS RGB batch work and repaired RGB handoff: synthetic WCS-shifted channels must reproject into a clean RGB product with manifest and alignment QA, and rendered RGB PNGs must export to display-only FITS with `RGB_CUBE`, `RED`, `GREEN`, `BLUE`, manifest, and before/after comparison.
- `scripts/audit_external_astro_tools_regression.py` is the narrow external astronomy backend gate: fake STILTS/APT commands prove preflight, blocked states, command logging, manifests, source-list preparation, and APT table parsing without requiring those applications to be installed.
- `scripts/capability_probe_matrix.py` is the maintainer matrix for public entries that intentionally have `smoke_tier=none`; it exercises safe synthetic/preflight probes and classifies `PASS`, `WARNING`, `BLOCKED_CONTROLADO`, `FAIL`, or `NO_PROBE`.
- `scripts/audit_v1_5_release_regression.py` is the v1.5 capability-coverage gate: it runs the surface/snapshot checks, v1.4 companion routing, external astronomy wrapper checks, FITS RGB regressions, and capability probe matrix, then fails if any real `FAIL` or unprobed public entry remains.
- `scripts/audit_v1_6_release_regression.py` is the v1.6 release gate: it verifies the current release docs, public-surface sync, capability probe matrix, focused v1.6 regression inventory, FITS RGB batch regression, and a core portable smoke run.
- `scripts/external_astro_tools_local_validation.py` is the optional real-backend maintainer check: it uses tiny synthetic fixtures and only expects `ok` when the local machine deliberately exposes STILTS/APT commands and, for APT, a saved preferences file.
- `scripts/portable_smoke_test.py --profile core` remains the main lightweight gate after ordinary changes; `--profile full` is the release-style gate when broader workflows or optional backends are affected.

Do not register every helper just because it exists. Deep, legacy, optional, and regression-only scripts can stay documented as second-line tools when that keeps the first-line surface smaller and clearer.

## When Not To Automate

- Do not create a full automatic scientific poster generator; keep poster/presentation work as copy-safe inspection, asset selection, and handoff guidance.
- Do not turn Keynote or PowerPoint support into a complex layout engine. Preserve editability and use previews for visual acceptance.
- Do not hardcode specific coursework folder names, cohorts, institutions, or user paths. Convert observed folder names into general branch/product patterns.
- Do not execute every notebook when the task is only to compare branches and decide which products are coherent.
- Do not mix unrelated science domains into a route just because they appeared in the same group project. For example, do not add BPT/SFR/metallicity logic to a photometric-reduction audit unless that is the explicit scope.
- Do not automate TOPCAT or APT GUI sessions. TOPCAT/STILTS and APT support should stay as optional command/preflight wrappers with logs, manifests, and clear blocked states when Java, STILTS, APT, or `APT.pref` is unavailable.
