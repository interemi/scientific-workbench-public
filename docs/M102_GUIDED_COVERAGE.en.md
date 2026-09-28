# M102: guided scientific coverage

English publication edition of the private record
`docs/M102_GUIDED_COVERAGE.md` at commit
`457ca65`. Original SHA-256:
`83cda8844dcda8a3643189ae5c15839aafb80182bbcafda35ac37d9306ed1eaa`.
The Spanish original is preserved privately. Translation does not constitute
new execution evidence.

M102 reduces handwritten CLI arguments without hiding scientific decisions.
The public registry is the source of truth: 61 capabilities, with 55 visible
to users and six reserved for maintenance.

## Recorded state

After review of the CLI contracts, all 55 visible capabilities have a guided
route in Scientific Workbench:

- 51 declare a guided requirement and build conservative arguments.
- `companion_route_check`, `photometry_noise_budget`,
  `catalog_workbench.crossmatch-sky`, and
  `legacy_spectroscopy_report_builder.populate` use dedicated forms.

`publicRegistryGuidedCoverageCoversEveryUserFacingCapability` checks this
coverage. Registry or classification changes that alter 55/55 fail the Swift
suite.

## Contracts covered by M102

| Capability | Reviewed guided default |
| --- | --- |
| `fits_rgb_batch` | Selected FITS root, derived products inside the run, cleanup limited to its own outputs |
| `duckdb_workbench` | Input preview with controlled aliases; no arbitrary SQL by default |
| `external_astro_tools_preflight` | Local detection without probes or requiring optional backends |
| `rgb_visual_fits_export` | One PNG into a new FITS inside the run; no forced overwrite |
| `astrometry_net_workbench.preflight` | Local FITS/image inspection and a report inside the run |
| `astrometry_net_workbench.verify-existing-wcs` | Existing-WCS QA and derived quicklooks inside the run |
| `radial_velocity_workbench.validate-manifest` | Existing-manifest validation without a new scientific fit |
| `iwork_workbench` | Inspection and derived previews; OCR off by default |
| `quicklook_bridge` | Separate PNG preview without modifying input |
| `teareduce_router` | Input-based recommendation; no TEAREDUCE execution or invented intent |
| `spectra_ascii_coursework_workbench` | Derived bundle; no notebook execution or LaTeX compilation by default |
| `legacy_rv_coursework_workbench.analyze` | Consolidation of attached results; optional calibration/FITS are not inferred |
| `sb2_double_gaussian_workbench.fit` | Fit attached CCFs; retain backend defaults for minimum separation and optional comparisons |
| `legacy_external_reference_check` | First RV summary required; optional checks are not inferred |
| `catalog_workbench.crossmatch-sky` | Two distinct tables, four explicit columns, confirmed decimal degrees, positive angular radius |
| `legacy_spectroscopy_report_builder.populate` | Scaffold copied into the run and each JSON explicitly assigned to a section; FXCOR/lithium accept multiple evidence items |

Optional and legacy workflows retain their explicit confirmations and
availability states. A guided constructor does not turn an absent backend into
a core dependency or automatically enable restricted planner steps.

## Specialized scientific forms

### `catalog_workbench.crossmatch-sky`

The form accepts two distinct text tables, inspects headers and bounded value
previews, shows numeric fractions and ranges, and requires selected RA/Dec
columns, confirmed decimal degrees, and a reviewed radius in arcseconds.
It blocks nonfinite values, repeated columns, and coordinates outside
RA `[0, 360)` or Dec `[-90, 90]`. The backend validates every row again.

Native inspection covers CSV, TSV, ECSV, and delimited text. Binary FITS tables,
Parquet, and spreadsheets remain available through the expert backend CLI.
Convert them to a reviewed text table before using the guided form. The UI
and architecture document this limitation.

### `legacy_spectroscopy_report_builder.populate`

The form separates the scaffold from JSON evidence, displays each envelope's
`tool` identifier and status, and requires manual assignment to envcheck,
inventory, FXCOR, RV, iSTARMOD, lithium, or external reference. It blocks
incompatible assignments and duplicates in single-item roles; FXCOR and lithium
accept multiple summaries.

The app copies the project into the run, rejects symlinks, and only then permits
the backend to update derived report sections.

## Completion evidence in the source record

`script/run_m102_guided_smoke.sh` executes both backends on synthetic fixtures,
validates envelopes, manifests, and outputs, and compares SHA-256 values before
and after. It is part of the quality gate. Swift tests cover valid selections,
unit confirmation, invalid ranges, nonnumeric values, incompatible roles, and
repeatable evidence.

The source record closes M102 with guided coverage of 55/55. Constructor
coverage and smoke tests do not replace methodological review of each
scientific result or extend the set of formats the UI can natively inspect.
