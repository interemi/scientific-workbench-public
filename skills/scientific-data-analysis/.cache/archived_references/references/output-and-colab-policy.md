# Output And Colab Policy

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-analysis/.cache/archived_references/references/output-and-colab-policy.md`.
> Original SHA-256: `bcfe6ad49960b0f50ebbba4a06b428e8814d41abe9e7d6e1daf8b40f5918bd83`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Use this note when the deliverable is a notebook, figure set, or handoff that should remain portable across local execution and Colab-style environments.

## Output Policy

- Keep raw inputs untouched.
- Save derived files under one explicit output directory.
- Name exported artifacts predictably:
  - `metrics_summary.csv`
  - `forecast_table.csv`
  - `01_full_series.png`
  - `all_figures.pdf`
- Keep one light JSON summary when the workflow becomes more than trivial.

## Path Policy

- Prefer project-local paths over user-specific home paths.
- Avoid embedding absolute home-directory paths inside notebooks that may be shared.
- For Colab-friendly notebooks, make `DATA_PATH` and `OUTPUT_DIR` explicit configuration variables near the top.

## Notebook Policy

- Use markdown cells for:
  - objective
  - data description
  - methodology
  - results
  - interpretation
  - conclusion
- Keep helper cells small and preferably collapsible.
- Export figures from code instead of assuming the notebook view is the deliverable.
- For professor-provided coursework notebooks, treat the original notebook as canonical: run and fill a copy before adding new automation.
- If `input()` is used, feed values through a temporary provider in a copied execution and document the values introduced.
- For Plotly or HTML/JS figures, verify that the target viewer displays the visual; add a static fallback when the viewer shows a blank output.

## When To Apply This Strictly

- coursework notebooks
- economics or forecasting exercises
- admin or policy analysis notebooks
- any case where the notebook may run locally first and later move to Colab
