# Cross-Domain Workflows

Use this reference when the task is not mainly astronomy or lab science, but the user still needs the same strengths of this skill: safe inspection, mixed formats, reproducible outputs, and bilingual explanation.

For the v1.7 intake coverage matrix and persistent regression command, see `real-world-use-cases.md`.

## 1. Operational Or Business-Like Tables

Primary entrypoint:

```bash
python3 scripts/cross_domain_data_workbench.py /path/to/folder --output-dir out
```

What it does:

- discovers mixed tabular files such as CSV, TSV, JSONL, XLSX, XLSB, ODS, parquet, or feather
- profiles each file with the same core profiling stack used elsewhere in the skill
- creates an inventory CSV plus a markdown report
- can optionally run one DuckDB SQL query across all discovered inputs

Useful example:

```bash
python3 scripts/cross_domain_data_workbench.py sales.csv ops.xlsx events.jsonl --sql "SELECT * FROM source0 LIMIT 20" --output-dir out
```

Use it for:

- operations and logistics datasets
- finance-like tabular review
- education/admin spreadsheets
- mixed CSV or spreadsheet intake before deeper work
- small QA or project-tracking datasets where the user wants inventory, profiling, and one SQL pass without building a custom pipeline

## 2. Mixed Document Intake

Primary entrypoint:

```bash
python3 scripts/document_intake_workbench.py /path/to/folder --output-dir out
```

What it does:

- inventories PDFs, DOCX, PPTX, XLSX, iWork, ODF, text, LaTeX, and related document formats
- runs semantic extraction without touching originals
- inspects presentation decks through the presentation workbench when appropriate
- can optionally run deeper PDF recovery and OCR for scanned material
- exports an inventory CSV plus a markdown report

Useful example:

```bash
python3 scripts/document_intake_workbench.py proposal_pack/ --deep-pdf --output-dir out
```

Use it for:

- project folders and proposal bundles
- meeting packs and executive materials
- teaching or admin archives
- mixed office and PDF handoff folders
- first-pass intake before deciding whether a folder needs the `doc`, `pdf`, `slides`, or `spreadsheet` skills in a more specialized follow-up

## 3. General Time-Series Forecasting Coursework

Primary entrypoint:

```bash
python3 scripts/timeseries_forecasting_workbench.py --output-dir out
```

What it does:

- scaffolds a notebook for general monthly or regularly sampled forecasting work
- is prepared for train/test evaluation instead of only in-sample fitting
- includes a clean route for ARIMA plus simple benchmark comparisons
- leaves space for narrative, metrics, figure export, and one combined PDF of plots
- supports a local runtime profile and a cleaner Colab-style profile

Useful example:

```bash
python3 scripts/timeseries_forecasting_workbench.py \
  --output-dir out \
  --runtime-profile colab \
  --data-path spain_ipc_yoy_annualrate_2015_2026.csv \
  --date-column date \
  --value-column annual_rate \
  --test-horizon 12
```

Use it for:

- economics or policy coursework built around one main time series
- forecasting exercises with a notebook as the main deliverable
- reproducible CSV plus notebook plus graphics bundles
- cases where the user needs local and Colab-friendly notebook scaffolds without rewriting paths by hand

## Working Rule

- Keep astronomy-specific workflows on the astronomy routing path.
- Use these workflows when the input is mostly tables, spreadsheets, reports, office files, or PDFs rather than FITS or reduction pipelines.
- Use the time-series forecasting path when the main deliverable is a notebook with model comparison, evaluation, and exported figures rather than only one cleaned table.
- Keep DuckDB, OCR, and deep PDF recovery optional so the light path stays fast and portable.
- Do not oversell these paths as a full business-automation suite; they are careful inspection, reporting, and handoff workflows built on the same reproducible stack as the science paths.
