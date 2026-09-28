# Real-World Measurement Patterns

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-notebooks/.cache/archived_references/references/real-world-measurement-patterns.md`.
> Original SHA-256: `713c4f27b51fb4596f0ff178a49e4a59b4f55a2dcf67695bb3cc5adc63e7b01c`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Use this reference when a non-astronomy task still has a scientific measurement shape: a sensor reading, a calibration table, a region of interest, a measurement series with uncertainties, or a table that may contain NaN/Inf and physically suspicious ranges.

This is a v1.7 transfer note. It does not turn astronomy tools into generic black boxes. It explains when the existing contracts are useful outside their original domain and when they should be left alone.

## Quick Route

| Need | Existing capability | Transferable pattern | Honest limit |
|---|---|---|---|
| ROI or sensor SNR | `scripts/photometry_noise_budget.py` | Add independent noise terms in quadrature for signal, background, leakage/dark, read noise, ROI size, and repeated frames. | Not a complete camera, lab instrument, microscopy, medical, or industrial sensor simulator. |
| First-order instrument calibration | `scripts/photometric_solution.py` | Fit a linear offset between raw and reference standards, with optional context/color term and residual QA. | Output terminology remains photometric/magnitude-oriented; use only when the offset model is valid. |
| Lab table sanity checks | `scripts/physical_qa.py` | Catch non-finite values, negative uncertainties, duplicate/nonmonotonic time, negative signal/counts, and missing units. | Conservative name-based QA; it does not know every domain's valid range. |
| Measurement series before manual fit | `scripts/radial_velocity_workbench.py inspect` | Inspect time/value/uncertainty rows, count malformed/nonfinite rows, and preserve provenance before a manual model or report. | The `.vels` and RV language remains; use as an intake pattern, not as a generic modeling tool. |

## Pattern 1: Sensor Or ROI Noise

Map terms explicitly:

- `--source`: signal above baseline inside the ROI per frame
- `--sky-per-pixel`: ambient background, clutter, or baseline per ROI pixel
- `--dark-per-pixel`: leakage, thermal contribution, or exposure-time background per ROI pixel
- `--read-noise`: per-pixel electronics/readout noise
- `--n-pixels`: effective ROI footprint
- `--sky-estimate-pixels`: baseline-estimation area

Example:

```bash
python3 scripts/photometry_noise_budget.py \
  --source 4200 \
  --sky-per-pixel 12 \
  --dark-per-pixel 0.3 \
  --read-noise 2.1 \
  --n-pixels 64 \
  --sky-estimate-pixels 800 \
  --n-frames 5 \
  --units electrons \
  --summary-json sensor_roi_noise_summary.json \
  --report-md sensor_roi_noise_report.md \
  --manifest-json sensor_roi_noise_manifest.json
```

Good use: deciding whether a repeated sensor ROI measurement is signal-shot, background, or read-noise limited.

Bad use: claiming this replaces a calibrated instrument-specific uncertainty budget.

## Pattern 2: First-Order Instrument Calibration

`photometric_solution.py` fits this form:

```text
standard - raw = intercept + slope_1 * context_1 (+ slope_2 * context_2)
```

For astronomy, the labels are instrumental magnitude, standard magnitude, airmass, and color. Outside astronomy, map them cautiously:

- `--inst-mag-col`: raw instrument reading
- `--std-mag-col`: reference or calibrated standard value
- `--airmass-col`: primary context/load/exposure term
- `--color-col`: optional secondary context term
- `--error-col`: uncertainty on the offset

Example:

```bash
python3 scripts/photometric_solution.py instrument_calibration_standards.csv \
  --inst-mag-col raw_reading \
  --std-mag-col reference_value \
  --airmass-col load_level \
  --color-col temperature_code \
  --include-color-term \
  --error-col cal_uncert \
  --summary-json calibration_summary.json \
  --coefficients-csv coefficients.csv \
  --residual-csv residuals.csv \
  --residual-plot residuals.png \
  --report-md calibration_report.md \
  --manifest-json calibration_manifest.json
```

Good use: a small calibration table where the expected relationship is a linear offset plus one or two context terms.

Bad use: nonlinear calibration, hysteresis, drift modeling, or regulated calibration certificates.

## Pattern 3: Light QA For Measurement Tables

`physical_qa.py` is useful before cleaning or modeling when a table has recognizable columns such as:

- `time`, `date`, `mjd`, `jd`
- `signal`, `flux`, `counts`, `intensity`
- `error`, `sigma`, `uncertainty`
- `wavelength` or similar ordered axes

It can flag:

- non-finite numeric values
- negative uncertainties
- negative signal/count values that need sign-convention review
- duplicate or nonmonotonic times
- duplicate or decreasing wavelength-like axes
- missing unit metadata in scientific table formats

Good use: fast first pass over a lab or sensor table before deeper domain review.

Bad use: final acceptance testing for a regulated device, because the valid ranges are domain-specific.

## Pattern 4: Measurement Series Intake

`radial_velocity_workbench.py inspect` expects Systemic-style `.vels` files:

```text
# value_units = micrometers
2450000.0000 10.0 0.30
2450000.2500 10.4 0.28
```

The transferable part is not radial velocity itself. The reusable pattern is:

- time-like coordinate
- measured value
- optional positive uncertainty
- explicit counts of malformed, nonfinite, missing-error, and nonpositive-error rows

Good use: a copied temporary measurement series that needs intake before manual fitting or handoff.

Bad use: presenting `.vels` as the native format for arbitrary business time series. For ordinary tabular time series, start with `profile_table.py`, `duckdb_workbench.py`, or `timeseries_forecasting_workbench.py` instead.

## v1.7 Gate

The maintained regression for this phase is:

```bash
python3 scripts/audit_v1_7_phase2_measurement_noise_qa_regression.py \
  --output-dir "${RUNS_DIR:?Set RUNS_DIR to a fresh output root}/v1_7_phase2_measurement_noise_qa"
```

It writes copied fixtures, command logs, JSON summaries, markdown report, manifests, and hash-preservation checks under the output directory.
