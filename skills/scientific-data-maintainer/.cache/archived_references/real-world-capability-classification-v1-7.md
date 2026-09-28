# Real-World Capability Classification v1.7

> English publication edition of the preserved private record at `766ba84`.
> Source: `skills/scientific-data-maintainer/.cache/archived_references/real-world-capability-classification-v1-7.md`.
> Original SHA-256: `91c03af11b72da582912ea68c7e443ecd68dcb45db62f1c2de0815f306865431`.
> Original states, row numbers, and classifications are historical evidence.
> This translation does not rerun the audit. The original remains unchanged privately.

Date: 2026-05-20

Editable skill: `$PRIVATE_WORKSPACE/skill_work/scientific-data-analysis`.
`$PRIVATE_WORKSPACE` denotes the original editable workspace, not the public checkout.

Audited baseline: v1.6 stable `public_surface_registry.yaml`.

This matrix is the Phase 0 contract for v1.7. It identifies which capabilities
already support general real-world work, which can transfer a pattern, and
which must retain a domain-specific or legacy scope.

## Criteria

- `general`: useful beyond astrophysics without a substantial conceptual change.
- `cross_domain_adaptable`: originated in science, astronomy, or coursework; its pattern can transfer with focused documentation/tests.
- `domain_specific`: useful, but dependent on its original scientific/astronomy domain.
- `legacy_specific`: tied to specific backends, practices, or inherited routes; must block cleanly without promising general use.
- `maintainer_only`: release, registry, smoke, probes, or internal validation work.

Do not generalize through weak analogy. Keep narrow capabilities narrow and document their limits.

## Numerical summary

| Classification | Total | Interpretation |
| --- | ---: | --- |
| `general` | 25 | Surface already suitable for academic, professional, and personal use. |
| `cross_domain_adaptable` | 9 | Candidates for focused real-world documentation/tests preserving the original domain. |
| `domain_specific` | 7 | Must retain scientific/astronomical precision. |
| `legacy_specific` | 12 | Useful routes tied to specific tools, practices, or backends. |
| `maintainer_only` | 6 | Outside normal end-user work. |
| **Total** | **59** | Matches the v1.6 registry. |

## Complete matrix

| N | Capability | Classification | Real-world rationale | Academic / professional / personal examples | Focused v1.7 action |
| ---: | --- | --- | --- | --- | --- |
| 1 | `datanalysis_env.py status` | `general` | Selecting the correct interpreter and wrapper is essential to reproducible analysis. | Academic: a dependency-heavy notebook. Professional: a local pipeline. Personal: exported data in an isolated environment. | Document general environment preflight, beyond astronomy. |
| 2 | `datanalysis_healthcheck.py` | `general` | Checks whether the environment supports notebooks, images, and technical dependencies. | Academic: SciPy/Astropy coursework. Professional: local analytics. Personal: a forecasting project. | Describe it as a substantial scientific/technical data environment. |
| 3 | `env_doctor.py` | `general` | Machine, interpreter, and optional-backend diagnosis applies across workflows. | Academic: setup before submission. Professional: environment support. Personal: understanding a script failure. | Use as the first v1.7 support route. |
| 4 | `companion_route_check.py` | `general` | Recommends companion skills/plugins without invoking them for mixed tasks. | Academic: selecting LaTeX/PDF support. Professional: documents plus data. Personal: PDFs, spreadsheets, and photos. | Document as a local handoff router. |
| 5 | `external_astro_tools_preflight.py` | `legacy_specific` | STILTS/TOPCAT/APT are specific astronomy backends; only the preflight pattern is general. | Academic: VOTable catalogs. Professional: astronomy only. Personal: usually not applicable. | Keep the scope narrow; document the optional external-backend pattern. |
| 6 | `external_astro_tools_local_validation.py` | `maintainer_only` | Validates optional local backends; not an ordinary end-user tool. | Academic: maintainer validates a local laboratory setup. Professional/personal: not applicable. | Keep outside normal routes. |
| 7 | `inspect_fits.py` | `domain_specific` | FITS is a scientific format; non-astronomy use requires actual FITS inputs. | Academic: FITS imaging. Professional: a laboratory or scientific FITS camera. Personal: astrophotography. | Keep the domain; direct general container work to `inspect_data_container.py`. |
| 8 | `fits_rgb_batch.py` | `cross_domain_adaptable` | Channel mapping, alignment, RGB, manifests, and visual QA transfer to multichannel sensors. | Academic: FITS RGB. Professional: industrial multichannel inspection. Personal: technical image composites. | Document the multichannel pattern; test non-FITS fixtures only if a capability/wrapper is created. |
| 9 | `rgb_visual_fits_export.py` | `cross_domain_adaptable` | Rendering with a manifest and before/after comparison supports reproducible visual handoff. | Academic: astronomy PNG to visual FITS. Professional: an audited preview. Personal: a traceable visual archive. | Retain FITS; document display-only semantics and limits. |
| 10 | `stilts_workbench.py` | `legacy_specific` | STILTS/TOPCAT is an external astronomy backend and must remain optional. | Academic: catalogs. Professional: astronomy teams. Personal: rarely applicable. | Retain controlled blocking; do not present it as a general SQL engine. |
| 11 | `astrometry_net_workbench.py preflight` | `domain_specific` | Astrometric hints are celestial; the preflight pattern transfers, but the capability does not. | Academic: plate solving. Professional: observatory work. Personal: astrophotography. | Use as an example of preflight for expensive or fragile backends. |
| 12 | `astrometry_net_workbench.py verify-existing-wcs` | `domain_specific` | Celestial WCS is astronomy-specific. | Academic: WCS header verification. Professional: observational QA. Personal: coordinate-bearing FITS. | Keep the domain and report limitations when no 2D plane exists. |
| 13 | `radial_velocity_workbench.py inspect` | `cross_domain_adaptable` | Time-tagged measurements, uncertainties, outliers, and manual-session inspection can transfer beyond RV. | Academic: radial velocities. Professional: batches of laboratory measurements. Personal: a measurement series with errors. | Document inspection of uncertain measurements before modeling. |
| 14 | `radial_velocity_workbench.py validate-manifest` | `cross_domain_adaptable` | Manifest validation before reporting can support manually produced results. | Academic: a Systemic session. Professional: analysis handoff. Personal: a reviewable results package. | Add a general manifest example in documentation without changing the RV contract. |
| 15 | `legacy_spectroscopy_envcheck.py` | `legacy_specific` | IRAF/iSTARMOD on macOS is a legacy route. | Academic: legacy coursework. Professional: old spectroscopy archives. Personal: legacy cases only. | Retain the macOS/legacy boundary and clear blocking. |
| 16 | `echelle_multispec_inventory.py` | `domain_specific` | MULTISPE/echelle inventory has a specific spectroscopy contract. | Academic: echelle data. Professional: spectroscopy. Personal: echelle data only. | Keep the domain; mention order-by-order inventory only where useful. |
| 17 | `fxcor_iraf_workbench.py prepare-session` | `legacy_specific` | Prepares a safe workspace before IRAF fxcor; the pattern transfers, the tool does not. | Academic: fxcor coursework preparation. Professional: historical analysis reproduction. Personal: normally not applicable. | Retain the tool; document preservation of originals as a pattern. |
| 18 | `fxcor_iraf_workbench.py run-auto` | `legacy_specific` | fxcor automation depends on IRAF and the RV context. | Academic: legacy RV/SB2/vsini. Professional: legacy spectroscopy archives. Personal: not applicable. | Retain preflight and clean errors. |
| 19 | `legacy_rv_coursework_workbench.py analyze` | `legacy_specific` | Consolidates legacy coursework RV/vsini results. | Academic: per-order results. Professional: historical reanalysis. Personal: not applicable. | Keep the scope; do not advertise universal consolidation. |
| 20 | `sb2_double_gaussian_workbench.py fit` | `domain_specific` | SB2/double-Gaussian fitting has analogies, but its contract is astrophysical. | Academic: per-order SB2. Professional: binary-star spectroscopy. Personal: normally not applicable. | Retain specialized fitting rather than generic fitting. |
| 21 | `li6708_equivalent_width_workbench.py measure` | `domain_specific` | Li I 6707.8 is a specific line; broad analogies would be misleading. | Academic: lithium equivalent width. Professional: stellar spectroscopy. Personal: not applicable. | Document the narrow scope clearly. |
| 22 | `legacy_external_reference_check.py` | `legacy_specific` | Fixed PW And/GZ Leo references belong to legacy coursework. | Academic: comparing specific results. Professional/personal: only those cases. | Keep the scope; extract only the canonical-reference comparison pattern. |
| 23 | `istarmod_workbench.py inspect-tree` | `legacy_specific` | Inspects a specific legacy iSTARMOD tree. | Academic: inspection before copying. Professional: inherited projects. Personal: normally not applicable. | Retain the tool; general inspection is covered by `inspect_data_container.py`/intake. |
| 24 | `istarmod_workbench.py prepare-copy` | `legacy_specific` | Creates an iSTARMOD copy excluding virtual environments and broken outputs. | Academic: preparing a submission. Professional: cleaning an inherited project. Personal: normally not applicable. | Preserve non-destructive behavior. |
| 25 | `legacy_spectroscopy_report_builder.py scaffold` | `legacy_specific` | Creates a Spanish report tailored to the legacy route. | Academic: coursework reporting. Professional: legacy documentation only. Personal: not applicable. | Keep specialized reporting; use `deliverable_factory.py`/LaTeX for general reports. |
| 26 | `photometric_solution.py` | `cross_domain_adaptable` | Linear calibration with standards, residuals, and provenance is transferable. | Academic: photometric calibration. Professional: sensor/instrument calibration. Personal: a home measurement scale. | Document first-order calibration with a non-astronomy example. |
| 27 | `photometry_noise_budget.py` | `cross_domain_adaptable` | Noise/SNR budgets apply to sensors, imaging, laboratories, and detectability decisions. | Academic: photometry. Professional: camera/sensor QA. Personal: noisy measurements. | Maintain non-astronomy SNR/simple-sensor documentation and tests. |
| 28 | `apt_workbench.py` | `legacy_specific` | APT batch is a specific external photometry backend. | Academic: APT photometry. Professional: an APT astronomy pipeline. Personal: advanced astrophotography. | Keep optional; block cleanly when APT/preferences are absent. |
| 29 | `teareduce_router.py` | `legacy_specific` | Routes between TEAREDUCE and the native stack for specific educational/astronomy work. | Academic: TEAREDUCE coursework. Professional/personal: normally not applicable. | Keep the router narrow and accurately described. |
| 30 | `document_intake_workbench.py` | `general` | Inspects document bundles while preserving originals. | Academic: assignment briefs and PDFs. Professional: project packages. Personal: administrative documents. | Promote as the main entrypoint for real document packages. |
| 31 | `presentation_workbench.py inspect` | `general` | Deck QA, text/images, style, and editability apply across contexts. | Academic: coursework presentations. Professional: client decks. Personal: talks/projects. | Add non-academic examples. |
| 32 | `presentation_workbench.py existing-deck-style-audit` | `general` | Retaining figure geometry, style, and provenance supports real handoffs. | Academic: posters. Professional: corporate decks. Personal: family/project presentations. | Document general style auditing and handoff. |
| 33 | `iwork_workbench.py` | `general` | iWork appears in professional and personal macOS workflows; safe inspection is general. | Academic: course Keynote/Pages. Professional: Apple documents. Personal: Pages/Numbers. | Retain optional macOS requirements and improve real-document examples. |
| 34 | `office_roundtrip.py docx-style-inventory` | `general` | DOCX style inventory supports precise editing beyond science. | Academic: DOCX reports. Professional: contracts/memos. Personal: CVs/formal documents. | Document with styled replacement as a safe Word/Pages workflow. |
| 35 | `office_roundtrip.py docx-styled-replace` | `general` | Style-targeted replacement in copies preserves unrelated text. | Academic: template corrections. Professional: controlled documents. Personal: CV/letter updates. | Keep regression checks that originals remain untouched. |
| 36 | `quicklook_bridge.py` | `general` | Native macOS previews are useful across domains. | Academic: PDF/deck review. Professional: deliverable QA. Personal: previewing without a large app. | Document fallback when Quick Look cannot render. |
| 37 | `keynote_export.py` | `general` | Faithful Keynote export is useful beyond scientific decks. | Academic: presentation conversion. Professional: Keynote PDFs. Personal: sharing decks. | Retain macOS/`platform_bound` scope and clear preflight. |
| 38 | `latex_workbench.py scaffold` | `general` | LaTeX supports reproducible academic, technical, and personal reports. | Academic: reports. Professional: technical notes. Personal: project documentation. | Broaden templates and descriptions to non-academic technical reports. |
| 39 | `latex_workbench.py review` | `general` | Structure, build, and portability checks apply to any LaTeX project. | Academic: papers/coursework. Professional: technical reports. Personal: books/notes. | Retain path and build checks. |
| 40 | `scientific_writeup_review.py` | `general` | Methodology, limitations, and tone review applies to technical and analytical writing. | Academic: scientific reports. Professional: technical memos. Personal: analysis explanations. | Describe scientific/technical writing while preserving rigor. |
| 41 | `deliverable_factory.py scaffold` | `general` | Non-destructive handoff/status/report scaffolding applies broadly. | Academic: coursework submissions. Professional: status packages. Personal: project summaries. | Promote as a standard output for real-world routes. |
| 42 | `semantic_diff.py` | `general` | Semantic table/document comparison supports many review tasks. | Academic: report versions. Professional: contracts/reports. Personal: two data exports. | Add personal/professional CSV examples. |
| 43 | `profile_table.py` | `general` | Table profiling is a standard first step before cleaning/modeling. | Academic: course datasets. Professional: business CSVs. Personal: expenses/habits. | Retain as the first table route. |
| 44 | `duckdb_workbench.py` | `general` | Local SQL over mixed tables supports real-world analysis. | Academic: multiple CSVs. Professional: Parquet/CSV/SQLite. Personal: historical exports. | Document missing-DuckDB blocking and explicit names. |
| 45 | `cross_domain_data_workbench.py` | `general` | Already targets non-astronomy data and report bundles. | Academic: laboratory data. Professional: analytics folders. Personal: mixed projects. | Promote as the main entrypoint for real data folders. |
| 46 | `bootstrap_analysis_notebook.py` | `general` | Reproducible notebooks support serious exploratory analysis across domains. | Academic: coursework. Professional: EDA. Personal: metric tracking. | Add personal/professional/academic domain profiles. |
| 47 | `notebook_workbench.py execute-copy` | `general` | Executing a copy of a received notebook preserves the original in every context. | Academic: instructor notebooks. Professional: inherited notebooks. Personal: downloaded notebooks. | Keep the non-destructive contract central. |
| 48 | `coursework_notebook_fidelity_check.py` | `cross_domain_adaptable` | Fidelity to a received notebook is general; its name/documentation is coursework-specific. | Academic: preserving assignment structure. Professional: team/client notebooks. Personal: tutorial notebooks. | Describe received-notebook fidelity; consider a future alias without breaking the current name. |
| 49 | `notebook_branch_compare.py` | `general` | Branch/output comparison applies beyond group coursework. | Academic: coursework groups. Professional: analysis variants. Personal: notebook versions. | Document as a project branch comparator. |
| 50 | `spectra_ascii_coursework_workbench.py` | `domain_specific` | ASCII spectra and scientific coursework define the domain; the bundle pattern transfers, the capability does not. | Academic: reduced spectra. Professional: spectroscopy. Personal: the user's spectral data. | Retain the domain rather than turning it into a general bundle tool. |
| 51 | `timeseries_forecasting_workbench.py` | `general` | Regular time-series forecasting spans multiple domains. | Academic: course series. Professional: sales/operations. Personal: consumption/expenses/habits. | Add non-astronomy examples and regular-frequency criteria. |
| 52 | `inspect_data_container.py` | `general` | Inspecting NPZ/HDF5/MAT/SQLite/ZIP and other containers before extraction is general. | Academic: laboratory data. Professional: technical archives. Personal: compressed exports. | Promote as an entrypoint for real containers. |
| 53 | `catalog_workbench.py crossmatch-sky` | `cross_domain_adaptable` | Sky crossmatching is astronomical; coordinate/tolerance matching is transferable. | Academic: sky catalogs. Professional: geodata/location inventories. Personal: places/GPS exports. | Document sky-coordinate limits; assess a future general record-linkage capability. |
| 54 | `physical_qa.py` | `cross_domain_adaptable` | NaN/Inf, ranges, units, and suspicious-data checks can generalize with explicit parameters. | Academic: FITS/spectra/tables. Professional: sensor QA. Personal: impossible-value detection. | Expand non-astronomy table tests/documentation with units and ranges. |
| 55 | `capability_probe_matrix.py` | `maintainer_only` | Release probe matrix, not an ordinary user tool. | Academic/professional/personal: not directly applicable. | Extend it to verify the v1.7 classification. |
| 56 | `portable_smoke_test.py` | `maintainer_only` | Distribution and fresh-machine smoke checks. | Academic: maintainer validates releases. Professional: maintainer validates installation. Personal: not directly applicable. | Retain as a baseline release gate; use `datanalysis` for official closure. |
| 57 | `validate_skill_samples.py` | `maintainer_only` | Sample/regression validation. | Academic/professional/personal: indirect use. | Add minimal real-world samples. |
| 58 | `sync_public_surface_docs.py` | `maintainer_only` | Regenerates or checks registry-derived documentation. | Academic/professional/personal: not applicable. | Update snapshots through this route when adding v1.7 registry fields. |
| 59 | `skill_surface_audit.py` | `maintainer_only` | Audits registry, documents, scripts, and hygiene. | Academic/professional/personal: indirect use. | Add real-world applicability matrix checks. |

## Key decisions

1. Do not artificially generalize `li6708_equivalent_width_workbench.py measure`, `echelle_multispec_inventory.py`, `astrometry_net_workbench.py verify-existing-wcs`, or IRAF/iSTARMOD routes.
2. The strongest real-world extensions concern tables, documents, notebooks, containers, time series, QA, noise/SNR, calibration, and manifest/handoff workflows.
3. Document useful astronomy-derived patterns while preserving original contracts.
4. Create a capability only when an actual case is not adequately covered by existing tools.

## Priorities for focused v1.7 work

| Priority | Capability | Work |
| ---: | --- | --- |
| 1 | `profile_table.py`, `cross_domain_data_workbench.py`, `inspect_data_container.py` | Documentation/examples as real-world entrypoints. |
| 2 | `timeseries_forecasting_workbench.py` | Professional/personal regular-series cases. |
| 3 | `photometry_noise_budget.py`, `photometric_solution.py`, `physical_qa.py` | Extend to sensors, measurement, laboratories, and data QA. |
| 4 | `coursework_notebook_fidelity_check.py`, `notebook_branch_compare.py`, `notebook_workbench.py execute-copy` | Describe received/inherited notebooks, beyond coursework. |
| 5 | `presentation_workbench.py`, `document_intake_workbench.py`, `semantic_diff.py`, `deliverable_factory.py` | Consolidate professional/personal document and deliverable use. |
| 6 | `fits_rgb_batch.py`, `catalog_workbench.py crossmatch-sky` | Document transferable patterns; decide later whether general wrappers are needed. |

## Recorded Phase 0 state

Classification completed: yes.

Skill files edited in that phase: this document and its validation regression.

Installed skill synchronized: no.

Recommended next phase at that time: Phase 1, starting with `general` intake
and data capabilities.
