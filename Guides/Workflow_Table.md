# Profile a table

**Purpose:** inspect columns, missing values, ranges, and a small preview before
cleaning or modelling. Profiling does not establish scientific correctness.

1. On Dashboard, choose **Open task** for your data or **Try example** for a new
   synthetic CSV. Replacing the selection leaves the previous files untouched.
2. Review **Profile a CSV table**, its Core requirements, input path, and
   dedicated output folder. The small example expects **3 rows and 4 columns**.
   Core needs its documented table packages; no model or API key is required.
   Review advanced arguments if you use them.
3. Select **Run Capability** for the guided route. A multi-step Chat workflow
   requires plan, scope, and permissions review, **Dry Run**, then **Run Enabled**.
   Cloud-assisted planning has separate consent.
4. In **Run & Logs**, inspect status, command, stdout/stderr, and recovery advice.
   Finer tool progress may be unavailable. **Cancel Run** stops the owned process
   group and retains captured logs and partial files.
5. In **Results**, check `summary.json` and `manifest.json`: counts, warnings,
   input hash, and output files. Process, tool, artifact contract, and automatic
   QA are separate findings. Human scientific review remains your responsibility.
6. A Chat workflow's **Summary** connects its Workflow Run ID to steps, jobs,
   logs, and artifacts. Direct capability jobs use a Job ID and tool summary.
   **Back**, **Edit Plan**, and **Exit to Dashboard** preserve session context.
   Exiting does not cancel a process. **New Workflow** archives the draft before
   clearing it; restoration is available in the current session.

The **Synthetic spectrum** example uses this same profiling route and expects
**5 samples**, wavelength in **nm**, and **relative flux**. It does not fit lines
or measure radial velocity. The operational CSV has no physical units.

## CLI equivalent

From the checkout, set the existing Core Python and the CSV path shown in the
app. The command creates new evidence in a fresh directory:

```sh
SCIWB_PYTHON="/absolute/path/to/datanalysis/bin/python"
SCIWB_INPUT="/absolute/path/to/the/generated/input/ops.csv"
SCIWB_RUN="$(mktemp -d /tmp/scientific-workbench-table.XXXXXX)"
"$SCIWB_PYTHON" skills/scientific-data-notebooks/scripts/profile_table.py \
  "$SCIWB_INPUT" --summary-json "$SCIWB_RUN/summary.json" \
  --manifest-json "$SCIWB_RUN/manifest.json"
```

Keep the input and evidence for comparison. Use a new run directory for retries.
See the [user guide](Scientific_Workbench_User_Guide.md) for setup and recovery.
