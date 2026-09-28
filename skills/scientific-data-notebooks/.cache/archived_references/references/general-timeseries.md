# General Time-Series Forecasting

This belongs to the `notebooks + cross-domain` block.

Use this reference when the task is mainly about a regular tabular time series rather than astronomy: economics coursework, inflation or sales forecasting, applied ARIMA exercises, or notebook-first forecasting deliverables.

## Start Here

- If the user needs a fresh forecasting notebook, start with:
  - `python3 scripts/timeseries_forecasting_workbench.py --output-dir out`
- If the user already has a notebook and wants to preserve the original:
  - use `scripts/notebook_workbench.py`
- If the user first needs to inspect a CSV, TSV, or spreadsheet before modeling:
  - use `scripts/profile_table.py`
- If the work is notebook-heavy or depends on the full modeling stack:
  - prefer `scripts/datanalysis_env.py run-tool ...`

## What This Route Is Good At

- one main series plus a notebook as the main deliverable
- train/test splits with the last observations held out
- ARIMA-style model selection with benchmark comparisons
- notebook outputs plus exported PNG figures and one combined PDF
- local execution and Colab-style execution with fewer hard-coded path assumptions

## Recommended Operational Path

1. Profile the source table if the columns are still unclear.
2. Scaffold a forecasting notebook with `timeseries_forecasting_workbench.py`.
3. Execute or refine the notebook in copy with `notebook_workbench.py` if needed.
4. Keep exports under one output directory:
   - notebook
   - metric tables
   - forecast tables
   - PNG figures
   - one PDF figure bundle

## Runtime Rule

- For heavier model-fitting or notebook execution, prefer `datanalysis`.
- The dedicated environment should include `statsmodels` and `scikit-learn` for this route.
- Treat the forecasting notebook as a reproducible scaffold, not as an auto-pilot model selector.

## What Not To Oversell

- This is not a full econometrics platform.
- It helps with the notebook structure, evaluation path, exports, and reproducibility.
- It does not replace human judgement about transformations, identification, structural breaks, or economic interpretation.
