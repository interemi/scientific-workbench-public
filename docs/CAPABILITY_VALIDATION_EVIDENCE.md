# Capability validation evidence

This record distinguishes registry coverage, a narrow diagnostic probe, and full scientific or interface acceptance. It includes local runs through 28 September 2026. Checks on a later changed tree must be repeated before relying on them. The registry has 55 user-facing IDs; six maintainer gates are outside this table. [Setup requirements](CAPABILITY_SETUP_MATRIX.md) and [portable validation](PORTABLE_VALIDATION.md) explain how to run a selected route.

**Core tier:** clean-root public-source commit `b57c168` passed
[hosted macOS 15 Core CI](https://github.com/interemi/scientific-workbench-public/actions/runs/36435979426)
on arm64 (locked) and Intel (unlocked), with 23 synthetic workflows per job.
Its tier coverage report marks all 16 Core IDs below as covered. These dated
results validate only that SHA; check the exact commit's own workflow runs.

**Full tier:** on 28 September 2026, the clean-root local source candidate
passed 38/38 synthetic Full cases with the 1,926-entry backend snapshot intact
before and after and `original_modified=false`. The run used the maintainer's
existing Python 3.11.15 environment. It was **not** a fresh installation of
the current 200-package Full lock, and it did not exercise every optional
backend. The separate [manual hosted Full job](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
passed a fresh locked installation, 23 Core synthetic cases, and 39 document
tests on `b57c168`; it did **not** run the 38-case Full smoke.
See [portable validation](PORTABLE_VALIDATION.md) for the run scope.

**No smoke tier:** on 28 September 2026, the clean-root local source candidate
ran the 29 narrow probes below: 34 commands, 15 PASS, 11 WARNING, three
`BLOCKED_CONTROLADO`, zero FAIL or `NO_PROBE`, exit 0, and overall status
`warning`. The recorded results show no original modified in the 33 commands
that reported this field. This is not Core/Full smoke coverage or hosted CI
evidence, and the warnings and controlled blocks remain open limitations.

The table's **Evidence** names the actual smoke case or narrow probe. `PASS` for a probe means only that its stated synthetic operation or preflight completed. A warning or controlled block remains visible. None of these rows proves scientific correctness for real data, installation of every optional application, interactive use on another Mac, or readiness of a later checkout.

| Capability ID | Declared tier / observed result | Exact checked scope |
| --- | --- | --- |
| **Core and routing (5)** |  |  |
| `datanalysis_env.status` | No smoke; PASS | status probe; 1 command. |
| `datanalysis_healthcheck` | No smoke; PASS | dependency healthcheck without notebook execution; 1 command. |
| `env_doctor` | Core smoke covered (dated) | Synthetic `env_doctor` case; exit 0. |
| `companion_route_check` | No smoke; PASS | advisory routing probe; 1 command. |
| `external_astro_tools_preflight` | No smoke; WARNING | external optional backend preflight; 1 command. |
| **Observational astronomy (24)** |  |  |
| `inspect_fits` | Core smoke covered (dated) | Synthetic `inspect_fits` case; exit 0. |
| `fits_rgb_batch` | No smoke; PASS | synthetic RGB batch; 1 command. |
| `rgb_visual_fits_export` | No smoke; PASS | display-only RGB FITS export with comparison and manifest; 1 command. |
| `stilts_workbench` | No smoke; BLOCKED_CONTROLADO | STILTS optional backend preflight; 1 command. |
| `astrometry_net_workbench.preflight` | Full smoke covered (dated local) | Synthetic `astrometry_preflight` case; exit 0. |
| `astrometry_net_workbench.verify-existing-wcs` | Full smoke covered (dated local) | Synthetic `astrometry_verify_existing_wcs` case; exit 0. |
| `radial_velocity_workbench.inspect` | Core smoke covered (dated) | Synthetic `radial_velocity_workbench_inspect` case; exit 0. |
| `radial_velocity_workbench.validate-manifest` | No smoke; WARNING | synthetic RV session manifest; 2 commands. |
| `legacy_spectroscopy_envcheck` | No smoke; WARNING | synthetic legacy practice preflight; 1 command. |
| `echelle_multispec_inventory` | Core smoke covered (dated) | Synthetic `echelle_multispec_inventory` case; exit 0. |
| `fxcor_iraf_workbench.prepare-session` | No smoke; WARNING | synthetic fxcor workspace; 1 command. |
| `fxcor_iraf_workbench.run-auto` | No smoke; BLOCKED_CONTROLADO | fxcor auto run blocks cleanly when IRAF output is unavailable; 2 commands. |
| `legacy_rv_coursework_workbench.analyze` | No smoke; BLOCKED_CONTROLADO | input validation blocked case; 1 command. |
| `sb2_double_gaussian_workbench.fit` | No smoke; PASS | synthetic SB2 CCF; 1 command. |
| `li6708_equivalent_width_workbench.measure` | Core smoke covered (dated) | Synthetic `li6708_equivalent_width_workbench` case; exit 0. |
| `legacy_external_reference_check` | No smoke; WARNING | reference check with missing measurements; 1 command. |
| `istarmod_workbench.inspect-tree` | No smoke; WARNING | synthetic iSTARMOD tree; 1 command. |
| `istarmod_workbench.prepare-copy` | No smoke; WARNING | synthetic iSTARMOD copy; 1 command. |
| `legacy_spectroscopy_report_builder.scaffold` | No smoke; PASS | legacy report scaffold; 1 command. |
| `legacy_spectroscopy_report_builder.populate` | No smoke; PASS | populate a fresh synthetic legacy report scaffold without scientific input data; 2 commands. |
| `photometric_solution` | Core smoke covered (dated) | Synthetic `photometric_solution` case; exit 0. |
| `photometry_noise_budget` | Core smoke covered (dated) | Synthetic `photometry_noise_budget` case; exit 0. |
| `apt_workbench` | No smoke; WARNING | APT preflight plus source-list and .tbl parse probes; 3 commands. |
| `teareduce_router` | No smoke; WARNING | TEAREDUCE routing decision; 1 command. |
| **Documents and reporting (14)** |  |  |
| `document_intake_workbench` | Core smoke covered (dated) | Synthetic `document_intake_workbench` case; exit 0. |
| `presentation_workbench.inspect` | Full smoke covered (dated local) | Synthetic `presentation_workbench_inspect` case; exit 0. |
| `presentation_workbench.existing-deck-style-audit` | Full smoke covered (dated local) | Synthetic `presentation_workbench_style_audit` case; exit 0. |
| `iwork_workbench` | No smoke; PASS | synthetic iWork bundle inspection; 1 command. |
| `office_roundtrip.docx-style-inventory` | No smoke; PASS | styled DOCX inventory; 1 command. |
| `office_roundtrip.docx-styled-replace` | No smoke; PASS | styled DOCX replacement on copy; 1 command. |
| `quicklook_bridge` | Full smoke covered (dated local) | Synthetic `quicklook_bridge` case; exit 0. |
| `keynote_export` | No smoke; PASS | Keynote preflight only; 1 command. |
| `latex_workbench.scaffold` | Full smoke covered (dated local) | Synthetic `latex_scaffold` case; exit 0. |
| `latex_workbench.review` | Full smoke covered (dated local) | Synthetic `latex_review` case; exit 0. |
| `latex_workbench.compile` | Full smoke covered (dated local) | Synthetic `latex_compile` case; exit 0. |
| `scientific_writeup_review` | Core smoke covered (dated) | Synthetic `scientific_writeup_review_good` case; exit 0. |
| `deliverable_factory.scaffold` | Core smoke covered (dated) | Synthetic `deliverable_status_report` case; exit 0. |
| `semantic_diff` | Core smoke covered (dated) | Synthetic `semantic_diff` case; exit 0. |
| **Notebooks and cross-domain (12)** |  |  |
| `profile_table` | Core smoke covered (dated) | Synthetic `profile_table` case; exit 0. |
| `duckdb_workbench` | No smoke; PASS | synthetic DuckDB query; 1 command. |
| `cross_domain_data_workbench` | Core smoke covered (dated) | Synthetic `cross_domain_data_workbench` case; exit 0. |
| `bootstrap_analysis_notebook` | Core smoke covered (dated) | Synthetic `bootstrap_analysis_notebook` case; exit 0. |
| `notebook_workbench.execute-copy` | Full smoke covered (dated local) | Synthetic `notebook_workbench` case; exit 0. |
| `coursework_notebook_fidelity_check` | No smoke; WARNING | synthetic professor-notebook fidelity scan; 1 command. |
| `notebook_branch_compare` | No smoke; WARNING | synthetic branch/product inventory; 1 command. |
| `spectra_ascii_coursework_workbench` | Full smoke covered (dated local) | Synthetic `spectra_ascii_coursework` case; exit 0. |
| `timeseries_forecasting_workbench` | No smoke; PASS | forecasting notebook scaffold; 1 command. |
| `inspect_data_container` | Core smoke covered (dated) | Synthetic `inspect_data_container` case; exit 0. |
| `catalog_workbench.crossmatch-sky` | Core smoke covered (dated) | Synthetic `catalog_workbench_crossmatch` case; exit 0. |
| `physical_qa` | No smoke; PASS | synthetic table physical QA; 1 command. |

To repeat only the 29 narrow diagnostics after the Full installation in
[INSTALL.md](../INSTALL.md), run the maintainer harness on its included
synthetic fixtures. Use the Python path from your own installation if you
chose a different destination. It writes to a new results directory; inspect
each row and its `capability_probe_runs.json` before interpreting the overall
status:

```bash
SW_PY="$HOME/Library/Application Support/Scientific Workbench/environments/full/datanalysis/bin/python"
mkdir -p "$HOME/ScientificWorkbenchRuns"
SW_PROBE=$(mktemp -d "$HOME/ScientificWorkbenchRuns/capability-probes-XXXXXX")
"$SW_PY" skills/scientific-data-maintainer/scripts/capability_probe_matrix.py \
  --output-dir "$SW_PROBE" \
  --summary-json "$SW_PROBE/summary.json" > "$SW_PROBE/stdout.json"
```

The command above has not yet been verified in a fresh locked Full environment.
The 28 September local run used the maintainer's existing `datanalysis` Python
3.11.15 on Apple Silicon. Its raw summaries and diagnostic logs are retained
outside Git by the maintainer. The
repository's CI artifacts must be checked on the same commit being used and
downloaded before their retention period ends. A
registry row with `smoke_tier: none` has no Core/Full smoke contract, even if
the narrow probe above passed. Backend availability and scientific correctness
still require route-specific checks.
