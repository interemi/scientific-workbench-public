# Inspect a mixed research folder

**Purpose:** inventory documents and table data in two separate, reviewable
runs. These inventories do not produce a combined scientific conclusion.

1. On Dashboard, choose **Open task** for your folder or **Try example** for a
   new bundle of `notes.md`, one-page `observing_note.pdf`, and `measurements.csv`.
2. Review `document_intake_workbench`, its input, Core requirements, and an output
   folder outside the input tree. This example needs no cloud account or external
   document application; other formats can have additional requirements.
3. Select **Run Capability**. In **Run & Logs**, inspect status, command, errors,
   and recovery. **Cancel Run** retains logs and partial output; keep that folder.
4. In **Results**, inspect document artifacts, `summary.json`, and `manifest.json`.
   Check the Markdown/PDF inventory and extracted text. This job does not profile
   the CSV.
5. Select **Inspect folder data** to prepare `cross_domain_data_workbench` with
   the same folder. It creates no job yet. Review it, then **Run Capability**.
   The example's table inventory expects **3 rows and 3 columns**. Each job keeps
   a separate run folder; their retained input path connects them.
6. A Chat plan requires step, scope, permissions, and **Dry Run** review before
   **Run Enabled**. Its **Summary** links the Workflow Run ID to steps and jobs.
   Direct jobs have Job IDs and tool summaries. **Back**, **Edit Plan**, and
   **Exit to Dashboard** preserve context; leaving a view does not cancel a run.

For **One-page PDF**, follow only the document-intake part. Readable extraction
does not establish semantic accuracy. Scans/OCR, notebooks, proprietary formats,
and exports may need more than Core. Review joins, units, dates, and provenance
before drawing a conclusion from real material.

## CLI equivalent

From the checkout, set the existing Core Python and generated `mixed_bundle`
folder. The two inventories write to different new directories:

```sh
SCIWB_PYTHON="/absolute/path/to/datanalysis/bin/python"
SCIWB_INPUT="/absolute/path/to/the/generated/input/mixed_bundle"
SCIWB_DOC_RUN="$(mktemp -d /tmp/scientific-workbench-documents.XXXXXX)"
"$SCIWB_PYTHON" skills/scientific-data-documents/scripts/document_intake_workbench.py \
  "$SCIWB_INPUT" --output-dir "$SCIWB_DOC_RUN/artifacts" \
  --summary-json "$SCIWB_DOC_RUN/summary.json" \
  --manifest-json "$SCIWB_DOC_RUN/manifest.json"
SCIWB_DATA_RUN="$(mktemp -d /tmp/scientific-workbench-data.XXXXXX)"
"$SCIWB_PYTHON" skills/scientific-data-notebooks/scripts/cross_domain_data_workbench.py \
  "$SCIWB_INPUT" --output-dir "$SCIWB_DATA_RUN/artifacts" \
  --summary-json "$SCIWB_DATA_RUN/summary.json" \
  --manifest-json "$SCIWB_DATA_RUN/manifest.json"
```

Keep input hashes and both run folders. See the
[user guide](Scientific_Workbench_User_Guide.md) for installation and recovery.
