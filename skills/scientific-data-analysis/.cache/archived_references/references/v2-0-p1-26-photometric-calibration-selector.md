# v2.0 P1-26: Photometric Calibration Column And Range Review

This closes the deferred app-side selector for `photometric_solution.py`.
The capability remains an expert astronomy route for first-order photometric
calibration from standard-star measurements.

## Boundary

- ScientificWorkbench owns interactive column selection, table preview,
  passband selection, and prefit range review.
- `photometric_solution.py` keeps its existing scientific fit and CLI contract.
- The app never edits the selected source table.
- The app stages a canonical CSV and a column-mapping JSON inside the run
  directory, then invokes the existing backend through `datanalysis_env.py
  run-tool`.
- A single fit uses one passband. Multiband input must be filtered explicitly.

The unchanged scientific model is:

`catalog_mag - instrumental_mag = zero_point + extinction * airmass`

An optional linear color term is included only when the user selects a color
column and enables it.

## Review Fields

| Role | Typical names | Required |
|---|---|---|
| Instrumental magnitude | `inst_mag`, `instrumental_mag`, `m_inst` | yes |
| Catalog magnitude | `std_mag`, `standard_mag`, `catalog_mag` | yes |
| Airmass | `airmass`, `air_mass`, `secz` | yes |
| Filter/passband | `filter`, `band`, `passband` | no, but required to separate multiband input |
| Offset uncertainty | `offset_err`, `mag_error`, `sigma`, `uncertainty` | no |
| Color index | `color`, `b_minus_v`, `b_v`, `g_r`, `bp_rp` | only for a color term |

The staged table uses stable backend names:

`inst_mag`, `std_mag`, `airmass`, optional `filter`, optional `color_index`,
and optional `offset_err`.

## Prefit Validation

| Condition | App state | Behavior |
|---|---|---|
| Unique required columns, one passband, finite rows, useful ranges | `PASS` | The fit can run after review. |
| Ambiguous names | `WARNING` | The user must confirm the intended columns. |
| NaN, Inf, or non-numeric values in selected roles | `WARNING` when at least three rows remain | Bad rows are excluded from the staged copy and counted. |
| More than one filter value | `BLOCKED_CONTROLADO` until one is selected | A mixed-passband fit is not attempted. |
| Fewer than three finite selected rows | `BLOCKED_CONTROLADO` | No backend command is run. |
| Missing required columns or repeated role selection | `BLOCKED_CONTROLADO` | The app explains which mapping must be corrected. |
| Nonpositive selected uncertainty | `BLOCKED_CONTROLADO` | Weighted fitting is withheld until errors are valid. |
| Airmass outside approximately 1 to 5, span below 0.25, broad magnitude anomaly, or narrow color coverage | `WARNING` | The fit remains available when mathematically valid, with the risk visible. |

These checks are preflight guidance, not a replacement for scientific
judgement or the backend quality flags.

## Artifacts And Fit Summary

The guided run requests:

- `summary.json`: app-facing fit summary and quality state;
- `manifest.json`: provenance;
- `artifacts/coefficients.csv`: fitted coefficients and uncertainties;
- `tables/residuals.csv`: per-standard residual diagnostics;
- `previews/residuals.png`: visual residual QA;
- `reports/photometric_solution.md`: readable fit report;
- `inputs/selected_photometric_standards.csv`: canonical copied input;
- `inputs/photometric_column_mapping.json`: selected source columns, filter,
  excluded-row count, next actions, and `original_modified=false`.

## Safety And Exposure

- Exposure: `expert_science`.
- Original files are read-only.
- The selector supports delimited text input for interactive review; the
  backend retains its wider table-format support.
- The app does not reinterpret fitted coefficients.
- Calibration validity, atmospheric stability, transformation-system
  compatibility, and standard-star suitability remain scientific decisions.
- No claim of general-purpose regression or non-astronomy calibration is made.
