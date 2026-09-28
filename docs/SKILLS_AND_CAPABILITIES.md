# What the Scientific Workbench skills and capabilities do

Scientific Workbench bundles **five local skills**. A skill is a group of
related instructions, Python commands, examples, and checks. A **capability**
is a specific action exposed by that family, such as inspecting a FITS file or
profiling a table. The app can guide some actions; expert and legacy actions
may require the command line. The five skills do not mean that every external
program or scientific workflow works on every Mac.

This page answers **what each action is for**. For its actual entrypoint,
Python profile, optional programs, safe first input, expected output, and
known limitations, use the [55-capability setup matrix](CAPABILITY_SETUP_MATRIX.md).
The [validation evidence](CAPABILITY_VALIDATION_EVIDENCE.md) distinguishes
tested synthetic workflows from narrower diagnostics and controlled blocks.
For the installation sequence, start with [INSTALL.md](../INSTALL.md).

## The five skills

| Skill | Role | Typical use |
| --- | --- | --- |
| [`scientific-data-analysis`](../skills/scientific-data-analysis/SKILL.md) | Main entrypoint and router for the family; owns environment checks and some shared actions. | Start with a broad science task, identify the right tool, and check the selected Python environment. |
| [`scientific-data-astro`](../skills/scientific-data-astro/SKILL.md) | Observational astronomy tools. | Inspect FITS/WCS, photometry, spectra, radial velocities, and explicitly selected external or legacy backends. |
| [`scientific-data-documents`](../skills/scientific-data-documents/SKILL.md) | Scientific documents and reports. | Inspect or derive PDF, Office, iWork, presentation, LaTeX, writing-review, and handoff outputs from copies. |
| [`scientific-data-notebooks`](../skills/scientific-data-notebooks/SKILL.md) | Tables, notebooks, containers, and cross-domain analysis. | Profile data, inspect or execute a copied notebook, compare branches, forecast time series, and check physical plausibility. |
| [`scientific-data-maintainer`](../skills/scientific-data-maintainer/SKILL.md) | Maintainer-only validation and release controls. | Audit the registry, run regressions and synthetic smokes, and check family integrity; its six gates are not ordinary user actions. |

The names above are internal skill identifiers. They are bundled inside this
repository: using the app does not require installing Codex or copying these
skills into `~/.codex/skills`. Core and Full refer to selectable **Python
dependency profiles**, not additional skills. Full includes Core. Ollama is
for local chat/planning; an individual capability command does not need an
Ollama model merely to run. See [optional backends](OPTIONAL_BACKENDS.md) for
tools that must be installed separately.

## Core and routing: 5 capabilities

| Capability | What it is for |
| --- | --- |
| `datanalysis_env.status` | Report which dedicated Python environment is selected and whether it can be discovered. |
| `datanalysis_healthcheck` | Summarize the available Python science stack and identify missing components. |
| `env_doctor` | Diagnose machine, interpreter, and optional-backend readiness before a run. |
| `companion_route_check` | Suggest which part of the skill family fits a task description; it does not perform the task. |
| `external_astro_tools_preflight` | Check whether named astronomy programs such as Java/STILTS, TOPCAT, or APT can be used. |

## Observational astronomy: 24 capabilities

| Capability | What it is for |
| --- | --- |
| `inspect_fits` | Inspect FITS extensions, headers, and available image or WCS metadata without changing the file. |
| `fits_rgb_batch` | Derive an RGB visualization from aligned filter images and record its inputs and quality checks. |
| `rgb_visual_fits_export` | Put an RGB visualization into a display-oriented FITS product; it is not a calibrated science image. |
| `stilts_workbench` | Prepare or run supported STILTS table operations after checking the external Java backend. |
| `astrometry_net_workbench.preflight` | Check whether an image and the chosen local or web Astrometry.net route are ready for solving. |
| `astrometry_net_workbench.verify-existing-wcs` | Assess an existing celestial WCS without requesting a new astrometric solution. |
| `radial_velocity_workbench.inspect` | Inspect a radial-velocity table, its time/velocity/uncertainty columns, and basic plausibility. |
| `radial_velocity_workbench.validate-manifest` | Validate the structure of a prepared radial-velocity session manifest. |
| `legacy_spectroscopy_envcheck` | Check the environment and copied practice tree needed by legacy spectroscopy routes. |
| `echelle_multispec_inventory` | Inventory orders and dispersion information in a copied MULTISPEC spectrum. |
| `fxcor_iraf_workbench.prepare-session` | Create a safe working copy and manifest for a legacy IRAF FXCOR session. |
| `fxcor_iraf_workbench.run-auto` | Execute a prepared FXCOR session when IRAF is available; retain its actual logs and measurements. |
| `legacy_rv_coursework_workbench.analyze` | Consolidate supplied FXCOR or radial-velocity coursework tables using explicit mappings. |
| `sb2_double_gaussian_workbench.fit` | Fit two peaks in a cross-correlation function as a starting point for SB2 review. |
| `li6708_equivalent_width_workbench.measure` | Estimate Li 6708 equivalent width from a reviewed spectrum and continuum choice. |
| `legacy_external_reference_check` | Compare a supplied radial-velocity summary with a supported fixed reference for plausibility. |
| `istarmod_workbench.inspect-tree` | Inspect whether a user-provided legacy iSTARMOD-like tree has the expected layout. |
| `istarmod_workbench.prepare-copy` | Create a derived working copy of that tree without modifying the source. |
| `legacy_spectroscopy_report_builder.scaffold` | Create a new LaTeX coursework-report scaffold. |
| `legacy_spectroscopy_report_builder.populate` | Populate a fresh scaffold from explicitly selected derived JSON summaries. |
| `photometric_solution` | Fit photometric calibration coefficients from standard-star measurements. |
| `photometry_noise_budget` | Estimate detector/aperture signal-to-noise contributions from supplied values and assumptions. |
| `apt_workbench` | Preflight and, when configured, use the external Aperture Photometry Tool on reviewed copies. |
| `teareduce_router` | Recommend and preflight a CCD-reduction route; it does not itself execute TEAREDUCE. |

## Documents and reporting: 14 capabilities

| Capability | What it is for |
| --- | --- |
| `document_intake_workbench` | Inventory a copied folder of documents and report readability or format concerns. |
| `presentation_workbench.inspect` | Inspect slide content, structure, and editability in a copied presentation. |
| `presentation_workbench.existing-deck-style-audit` | Review layout and style consistency and trace figure sources in an existing deck. |
| `iwork_workbench` | Inspect or preview supported Pages and Keynote bundles, with optional macOS export routes. |
| `office_roundtrip.docx-style-inventory` | List Word paragraph/run styles before a controlled edit. |
| `office_roundtrip.docx-styled-replace` | Replace explicitly selected styled text in a new DOCX output and read it back. |
| `quicklook_bridge` | Produce a preview of a supported copied document using Quick Look or an available fallback. |
| `keynote_export` | Export a copy of a Keynote presentation to PDF through macOS automation. |
| `latex_workbench.scaffold` | Create source files for a new LaTeX report project. |
| `latex_workbench.review` | Inspect a LaTeX tree for structure and portability issues without claiming it compiles. |
| `latex_workbench.compile` | Compile a copied or new LaTeX tree with a supported TeX engine and retain the build log. |
| `scientific_writeup_review` | Review scientific prose for unclear methods, unsupported claims, and reporting gaps. |
| `deliverable_factory.scaffold` | Create a new organized handoff or status-report directory. |
| `semantic_diff` | Compare two supplied versions and report meaningful changes for human review. |

## Notebooks and cross-domain data: 12 capabilities

| Capability | What it is for |
| --- | --- |
| `profile_table` | Report a table's shape, columns, types, and missingness before analysis. |
| `duckdb_workbench` | Explore selected tables with bounded SQL when the optional DuckDB backend is present. |
| `cross_domain_data_workbench` | Inventory a mixed tabular data package and prepare a first-pass cross-domain view. |
| `bootstrap_analysis_notebook` | Create a starter notebook for a chosen domain without pretending it has been run. |
| `notebook_workbench.execute-copy` | Execute a staged copy of a notebook and preserve cell errors, logs, and outputs. |
| `coursework_notebook_fidelity_check` | Check whether a received notebook and declared sidecars can be reproduced structurally. |
| `notebook_branch_compare` | Compare notebook or result branches for missing and duplicate outputs. |
| `spectra_ascii_coursework_workbench` | Build a derived coursework bundle from a reduced ASCII spectrum and reviewed choices. |
| `timeseries_forecasting_workbench` | Prepare a time-series forecast notebook and report with a held-out horizon. |
| `inspect_data_container` | Inspect the structure of a supported HDF5, NetCDF, Zarr, or archive container before extraction. |
| `catalog_workbench.crossmatch-sky` | Match two sky catalogs from explicit coordinates and a chosen angular radius. |
| `physical_qa` | Run bounded physical sanity checks on FITS, spectrum, or table inputs; warnings require scientific judgment. |

These are descriptions of intended actions, **not guarantees of scientific
validity or universal availability**. Use copied or synthetic inputs and a new
results directory. Review units, calibration, uncertainty, assumptions,
warnings, and generated artifacts before using any result in research.
