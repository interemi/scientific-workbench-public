# Real-World Package Playbooks v1.7

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-notebooks/.cache/archived_references/references/real-world-package-playbooks.md`.
> Original SHA-256: `5a81270001d3b94bf2050416165dcc12a8d87d103f08938b0f9d68cba2226a53`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Use this note when the user brings a professional or personal package rather than an academic or astronomy dataset.

The operating rule is simple:

- anonymize or copy before running tools
- preserve originals
- record command, input, output, warning/error, and diagnosis
- decide whether the output helps a real person choose the next step
- do not oversell first-pass inspection as full automation

## Families Covered In Phase 4

| Family | Professional package | Personal package | Primary capabilities |
|---|---|---|---|
| Tables | Anonymous support/operations tables with an `inf` finance placeholder. | Household budget table with planned vs actual values. | `cross_domain_data_workbench.py`, `profile_table.py` |
| Documents | Vendor handoff notes, release note, and DOCX summary. | Home project plan, travel/admin note, and DOCX summary. | `document_intake_workbench.py` |
| Notebooks | Inherited KPI notebook staged with its CSV dependency. | Household-budget notebook staged with its CSV dependency. | `notebook_workbench.py execute-copy` |
| Containers | ZIP with tables, README, and SQLite task metadata. | ZIP with budget table and small sensor snapshot. | `inspect_data_container.py` |
| Time series | Daily order/demand series for a forecast scaffold. | Monthly household energy series for a forecast scaffold. | `timeseries_forecasting_workbench.py` |
| Measurement/sensor | Sensor ROI table with non-finite signal and negative uncertainty. | Home sensor table with non-monotonic time and negative counts. | `physical_qa.py` |

## What Counts As Useful

A result is useful when it tells the user what to do next:

- clean bad values before reporting
- sort or split document bundles before editing
- execute a notebook copy before trusting inherited calculations
- inspect an archive before extraction
- scaffold a forecast notebook with explicit date/value columns
- stop interpreting a sensor table until warnings are resolved

Warnings are acceptable when they are visible and actionable. For example, Phase 4 expects `physical_qa.py` to warn on non-finite or physically suspicious sensor values, and `cross_domain_data_workbench.py` to propagate child `profile_table.py` warnings such as infinite numeric values.

## Boundaries

- These are first-pass workbench routes, not replacements for domain specialists.
- Personal use still needs privacy care: anonymize names, addresses, accounts, and health identifiers before making durable artifacts.
- Professional use still needs governance: confirm data freshness, access rights, and reporting context before sending results onward.
- Forecast scaffolds are notebooks for reproducible analysis, not automatic business predictions.
- Container inspection is not extraction approval; inspect archive warnings before unpacking.

## Regression

Run the maintained phase regression with the `datanalysis` environment:

```bash
python3 scripts/audit_v1_7_phase4_professional_personal_packages_regression.py \
  --output-dir "${RUNS_DIR:?Set RUNS_DIR to a fresh output root}/v1_7_phase4_professional_personal_packages"
```

Expected shape:

- 6 families
- 12 cases
- professional and personal coverage for each family
- copied temporary inputs
- no installed-skill sync
