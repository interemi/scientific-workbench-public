# Real-World Use Cases v1.7

Use this reference when the task is not mainly astronomy but still needs the strengths of this skill: safe intake, reproducible local execution, careful QA, manifests, and a clear handoff.

## Fase 1 Intake Targets

The first v1.7 real-world intake phase covers these existing capabilities:

| Need | Primary capability | Real-world example |
|---|---|---|
| Profile one table before cleaning | `scripts/profile_table.py` | Anonymous support tickets with a broken `inf` finance placeholder. |
| Inventory a mixed tabular folder | `scripts/cross_domain_data_workbench.py` | CSV plus JSONL operations project folder. |
| Inspect an archive or technical container | `scripts/inspect_data_container.py` | ZIP package containing tables, events and a README. |
| Inspect administrative documents | `scripts/document_intake_workbench.py` | Markdown, TXT and DOCX handoff notes. |
| Compare two versions semantically | `scripts/semantic_diff.py` | Weekly metric baseline vs candidate export. |
| Create a handoff/status deliverable | `scripts/deliverable_factory.py scaffold` | Operations status-report scaffold. |
| Execute a received notebook safely | `scripts/notebook_workbench.py execute-copy` | Inherited notebook staged with its CSV dependency. |
| Query a local table with explicit aliases | `scripts/duckdb_workbench.py` | SQL rollup over `source0` without renaming ambiguity. |

## Operating Rule

- Work on copies or generated fixtures, not user originals.
- Record command, input, output, warning/error and whether the result helps a real person decide the next step.
- A warning is acceptable when it is honest and actionable, such as detecting an infinite numeric value.
- Optional backends may block cleanly; do not fake success when DuckDB or another dependency is absent.

## Regression

The phase-level regression is:

```bash
python3 scripts/audit_v1_7_phase1_real_world_intake_regression.py
```

For persistent review artifacts:

```bash
python3 scripts/audit_v1_7_phase1_real_world_intake_regression.py \
  --output-dir tmp/v1_7_phase1_real_world_intake
```

Run it with the `datanalysis` environment in official phase closures because `duckdb_workbench.py` and notebook execution are optional-heavy paths.

## Fase 4 Professional And Personal Packages

The fourth v1.7 real-world phase broadens intake from isolated examples to packages that resemble ordinary work and life:

| Family | Professional route | Personal route |
|---|---|---|
| Tables | Mixed operations CSV folder through `cross_domain_data_workbench.py`. | Household budget CSV through `profile_table.py`. |
| Documents | Vendor/release/DOCX handoff folder through `document_intake_workbench.py`. | Home/travel/admin notes through `document_intake_workbench.py`. |
| Notebooks | Inherited KPI notebook through `notebook_workbench.py execute-copy`. | Personal budget notebook through `notebook_workbench.py execute-copy`. |
| Containers | Operations ZIP through `inspect_data_container.py`. | Home admin ZIP through `inspect_data_container.py`. |
| Time series | Daily demand forecast scaffold through `timeseries_forecasting_workbench.py`. | Household energy forecast scaffold through `timeseries_forecasting_workbench.py`. |
| Measurement/sensor | Professional sensor ROI sanity checks through `physical_qa.py`. | Home sensor sanity checks through `physical_qa.py`. |

See `references/real-world-package-playbooks.md` for the operating rule and limits.

The phase-level regression is:

```bash
python3 scripts/audit_v1_7_phase4_professional_personal_packages_regression.py \
  --output-dir tmp/v1_7_phase4_professional_personal_packages
```
