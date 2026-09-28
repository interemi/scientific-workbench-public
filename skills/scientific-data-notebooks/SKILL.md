---
name: scientific-data-notebooks
description: Use when working with tables, mixed data packages, notebooks, containers, forecasting time series, DuckDB exploration, and general physical or sensor QA. Do not use for document-only workflows or astronomy-specific FITS/RV work unless routed by the mother skill.
---

# Scientific Data Notebooks

This child skill owns general tabular, notebook, container, time-series,
DuckDB, and cross-domain package workflows for the modular
scientific-data-analysis family.

v2.8 keeps this child as an independent ScientificWorkbench skill root for
tables, notebooks, containers, forecasting, DuckDB, and cross-domain package
workflows. App consumers must resolve its compact `public_surface_registry.yaml`
through `canonical_registry` and execute owned capabilities from this root.
Copied notebook execution must remain inside its run-owned workspace.

Use it for table profiling, mixed package summaries, notebook scaffolds,
read-only notebook checks, copied notebook execution, branch comparison,
container inspection, forecasting notebook generation, and light measurement QA.

## Safety

- Work on copied inputs or generated outputs.
- Do not execute original notebooks directly.
- Treat DuckDB as optional when the backend is unavailable.
- Keep historical mother wrapper commands compatible.

## Common Commands

```bash
python scripts/profile_table.py <table> --summary-json <run>/summary.json
python scripts/notebook_workbench.py inspect <notebook.ipynb> --summary-json <run>/summary.json
python scripts/notebook_workbench.py execute-copy <notebook.ipynb> --output-dir <run>/notebook --stage-extra <required-input>
python scripts/duckdb_workbench.py --help
```

## v2.8 Boundary

`catalog_workbench.py crossmatch-sky` remains shared/mother-routed for now, and
`spectra_ascii_coursework_workbench.py` stays with the astronomy split.
