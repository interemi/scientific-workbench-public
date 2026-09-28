# v2.0 P1-8 FITS RGB Batch Integration

`fits_rgb_batch.py` is exposed to ScientificWorkbench as an expert science
workflow, not as a normal general-purpose route. It builds derived visual RGB or
pseudo-RGB products from copied FITS folders and keeps source FITS files
read-only.

## Closed Scope

- App command building uses `--input-root`, `--output-dir`, `--clean-derived`,
  and `--summary-json`.
- The output folder remains the run bundle's `artifacts/` directory.
- The backend emits individual RGB PNG products as `preview_png`, the manifest
  as `manifest_json`, alignment QA sidecars as `metadata_json`, CSV inventories
  as `table_csv`, and derived folders as `handoff_bundle`.
- ScientificWorkbench Results shows typed artifact labels and previews PNG
  artifacts through the existing image preview surface.
- ScientificWorkbench job history, running state, and cancellation use the
  existing job runner and persisted job history paths; no special FITS-only job
  history store is introduced.

## Safety Rules

- Source FITS are never modified.
- Outputs must be outside `--input-root`.
- WCS problems are warnings or controlled blocks, not silent success.
- Products remain visual products unless upstream reduction/calibration is
  documented elsewhere.

## App Exposure

| Target | Exposure | Rationale |
|---|---|---|
| `fits_rgb_batch.py` | `expert_science` | It is useful from the app for astronomy/FITS projects but remains domain-specific and can produce visual-only products. |

## Regression

`scripts/audit_v2_0_p1_8_fits_rgb_batch_regression.py` validates:

- a synthetic RGB PASS/WARNING-compatible run creates at least one `preview_png`;
- the manifest is typed as `manifest_json`;
- WCS-ambiguous inputs produce useful warnings;
- `original_modified` remains `false`;
- input FITS hashes are unchanged.
