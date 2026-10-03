# Scientific Workbench User Guide

This guide explains how to use Scientific Workbench while preserving original
inputs, and how to continue when a run stops.
Build and configure the app from [INSTALL.md](../INSTALL.md); there is no
signed or notarized downloadable release. For a description of each skill and
capability, see [skills and capabilities](../docs/SKILLS_AND_CAPABILITIES.md),
then use the [setup matrix](../docs/CAPABILITY_SETUP_MATRIX.md) to choose the
requirements for one route.

## 1. What the app does

Scientific Workbench connects a macOS interface for files, folders, and prompts
to the capabilities of the scientific-data skill family. Ollama supplies local
AI, with OpenAI, Grok, and Gemini available as optional cloud providers.

Inputs are treated as read-only. By default, results go to
`~/Documents/Scientific Workbench Runs`; you can change the destination in Settings.

## 2. What integrated v2.0 means

Scientific Workbench consumes the skills as a deterministic backend:

- Skills route and execute reproducible capabilities.
- Skills write `summary.json`, `manifest.json`, stdout, stderr, logs, typed
  artifacts, and `next_steps.md`.
- The app plans, reviews, executes, presents Jobs/Results, supports recovery,
  exports support bundles, and provides guided controls.
- The app accepts v1.8/v1.9 and v2.0 contracts.
- `PASS`, `WARNING`, `BLOCKED_CONTROLADO`, and `FAIL` remain distinct.
  A controlled block is never presented as success.

Local operation is the default. Ollama avoids paid cloud APIs. OpenAI,
Grok/xAI, and Gemini require configured credentials and acceptance of API
charges. The optional Codex bridge supports longer reasoning, code work, and
reporting with local context; it does not replace verifiable skill commands.

App version, integrated `v2.0`, and skill compatibility are separate version
axes. Registry labels alone do not establish validated synchronization; gates
must check the actual roots used. The app resolves a multi-root catalog and
executes each capability from its owning skill, without copying skills into
the app bundle.

`WARNING` retains a successfully finished job with a visible warning badge.
It is not `PASS`. `FAIL`, `ERROR`, and `ROTO` stop the workflow. Maintenance
actions are outside normal plans. Importing or restoring a plan rechecks catalog
policy; restricted steps require fresh review and explicit enablement.

## 3. First launch

Open Settings and inspect the Setup Checklist:

- **Scientific environment:** Python and `datanalysis_env.py` respond.
- **Capabilities loaded:** the app can see the available tools.
- **Output folder:** an output directory exists.
- **Local AI:** if you want chat or AI planning, Ollama is running and the
  selected model responds. Local capability commands do not require a model.

OpenAI, Grok, and Gemini are optional. Gemini currently supports API-key
authentication; OAuth is not implemented. Connection status is evidence for
the current session and resets on restart. Leave Ollama selected to avoid paid
provider APIs.

### Choose Core or Full

Start with **Core** for the five synthetic examples and common table, FITS,
and document workflows. Core uses a dedicated Python environment. The
reviewed locked Core setup currently targets native Apple Silicon, Python
3.11, and macOS 14 or later. Ollama and cloud accounts are optional for these
deterministic workflows.

**Full** adds Python packages for advanced routes such as notebooks and
presentations. Its reviewed locked setup currently targets Apple Silicon,
Python 3.11, and macOS 15 or later. A working Core environment does not prove
that Full is installed or ready. Intel uses an unpinned compatibility route;
check the exact-commit validation before relying on it.

Neither profile installs external applications or Ollama models. TeX,
LibreOffice, IRAF, astronomy backends, and other optional tools need separate
setup only for the workflows that use them. Check the selected capability's
requirements and preflight rather than assuming a profile supplies every
backend. The source repository's `INSTALL.md`, `docs/WORKFLOW_REQUIREMENTS.md`,
and `docs/OPTIONAL_BACKENDS.md` give the exact commands and limits.

## 4. Normal workflow

1. Open Chat.
2. Attach files/folders with Files/Folder or drag them into the composer.
3. Describe your objective.
4. Select a mode:
   - **Auto:** the app chooses a response, plan, or workflow. It does not invoke
     Codex in the background.
   - **Chat:** conversation and guidance.
   - **Workflow:** an editable capability plan.
   - **Codex:** explicit delegation to Codex CLI for longer reasoning or code work.
5. Review the plan.
6. Use Dry Run to inspect commands without executing them.
7. Select Run Enabled when the enabled steps are ready.

For complex work, initially leave Auto-run off and review the plan before
enabling it.

### Guided radial-velocity inspection

Select the expert spectroscopy/RV route `radial_velocity_workbench.py inspect`
in Capabilities:

1. Add an RV table in text, CSV, TSV, or `.vels` format.
2. Select `Inspect Columns`.
3. Review the time, radial-velocity, and uncertainty columns.
4. Confirm JD/BJD/HJD/MJD and km/s or m/s.
5. Select `Run Reviewed Inspection`.

The app creates a normalized `.vels` copy inside the run, converting MJD to JD
and m/s to km/s. The original table is unchanged. Missing columns, ambiguous
units, or insufficient numeric data produce next actions; the backend waits
until the mapping is valid.

### Guided photometric calibration

The expert route `photometric_solution.py` fits a first-order photometric
solution from standard stars:

1. Add a CSV, TSV, or delimited text table.
2. Select `Inspect Columns`.
3. Confirm `Instrumental mag`, `Catalog mag`, and `Airmass`.
4. Choose a filter if multiple bands are present.
5. Select uncertainty and, when applicable, color index.
6. Review the preview, ranges, and excluded rows.
7. Select `Fit Reviewed Calibration`.

The app saves a canonical copy and column mapping in the run. NaN, Inf, and
nonnumeric values are excluded only from the copy, provided at least three
valid standards remain. Suspicious ranges, narrow airmass/color coverage, and
fits without uncertainties produce warnings. The original table is unchanged;
`photometric_solution.py` owns the scientific model.

### Guided sky crossmatch

`catalog_workbench.crossmatch-sky` requires two distinct text tables, explicit
RA/Dec columns for each, confirmation of decimal degrees, and a positive match
radius in arcseconds. Review numeric fractions, ranges, and previews.
Nonfinite values, repeated columns, and coordinates outside RA `[0, 360)` or
Dec `[-90, 90]` are rejected; the backend rechecks all rows.

The guided inspector supports CSV, TSV, ECSV, and delimited text. Binary FITS
tables, Parquet, and spreadsheets require a reviewed text conversion for this
form, or the backend's expert CLI.

### Populate a legacy spectroscopy report

`legacy_spectroscopy_report_builder.populate` separates the report scaffold
from JSON evidence. Review each envelope's `tool` and status, then assign it
to envcheck, inventory, FXCOR, RV, iSTARMOD, lithium, or external-reference roles.
FXCOR and lithium accept multiple summaries. Incompatible assignments and
duplicates in single-evidence roles are blocked.

The app copies the project into the run and rejects symlinks before the backend
updates derived report sections. Original evidence and the scaffold are preserved.

### Optional APT panel

APT remains optional. In `Settings > Optional Astronomy Backends`:

1. Review `APT command`, `APT.pref`, and `Batch readiness`.
2. If installed, select `APT.csh` or `APT.bat`.
3. Select the `APT.pref` saved from the APT GUI.
4. Run `Run APT Preflight`.
5. Open Jobs for the command, stdout, stderr, and parsed status.
6. Open Results for `summary.json` and run artifacts.

Unavailable APT produces `BLOCKED_CONTROLADO` without breaking core workflows.
`Inspect FITS Instead` opens native FITS inspection; `Use Native Noise Budget`
opens noise/SNR preparation. For real APT batches, use copies of the image,
source list, and preferences. Logs and tables belong in the job directory.

### DOCX and Keynote documents

`office_roundtrip.py docx-style-inventory` and
`office_roundtrip.py docx-styled-replace` have guided review:

1. Add a DOCX.
2. Select the explicit styles to match.
3. Use `Inspect Copy` to preview text, locations, formatting, and counts by style
   and document area.
4. For replacement, enter the exact text and review the before/after diff.
5. Confirm. The app creates a new DOCX in the run, preserving the original.

The confirmed run records an approval identifier in the summary, diff, and
manifest. Replacement requires both confirmation and reviewed changes.

`keynote_export.py` also requires review. The app copies the deck, checks
macOS/AppleScript/Keynote, and enables PDF export only after explicit
confirmation. Missing Keynote produces `BLOCKED_CONTROLADO` while unrelated
workflows remain usable.

During export the app shows a working state, records an approval identifier,
and preserves the PDF, native log, summary, and manifest in the same run.
When Keynote is unavailable, recovery suggests inspecting the deck or using a
copy-based export if exact Keynote fidelity is unnecessary.

## 5. Local processing and cloud transfer

Before sending prompts or local context to a cloud provider, the app shows the
provider, model, purpose, and exact data categories leaving the Mac. Consent is
held in memory for the session; changed content requires another review.
Attachment privacy also applies to recovery context. Ollama accepts only
loopback endpoints.

Capability execution, reading original inputs, and storing run directories,
jobs, manifests, results, and support bundles happen locally. Selected excerpts,
filenames, or recovery information can nevertheless be included in a cloud
request when the configured privacy mode and consent permit them. Review that
scope before approval.

Cloud requests may contain your prompt, conversation context, planning context,
or permitted attachment/recovery content. API keys are sent to the corresponding
provider to authenticate the request; they must not be included as prompt
content or exposed in logs and support bundles. Keeping a key out of a prompt
does not mean authentication happens without transmitting it.

When a cloud provider is unavailable, use local planning, Ollama, or the skill
router. A missing optional tool should produce an actionable
`BLOCKED_CONTROLADO`, not false success.

## 6. When a workflow fails

Scientific Workbench keeps recovery context. Inspect:

1. **Recovery card in Chat:** the capability, stopped step, and next actions.
2. **Jobs:** `Parsed Status`, `Exit Code`, stdout/stderr, warnings, structured
   errors, next actions, and Command.
3. **Results:** bounded previews of images, first PDF pages, CSV/TSV, Markdown,
   JSON, notebooks, and logs where supported.
4. **Open Job Folder / Reveal Run Folder:** generated files and logs.
5. **Workflow Summary:** inputs, steps, jobs, artifacts, and original-input safety.

You can ask local AI, “Where did this fail, and what should I inspect next?”
Check its explanation against the actual job, run folder, error, and evidence.

Use Export Support Bundle from Settings, the Workbench menu, or the recovery
card to preserve a diagnostic snapshot. It includes `support_bundle.md`,
`state.json`, and the latest workflow summary when available. Configured API
keys are redacted before writing.

Each job can also export a smaller bundle containing `job_state.json` and
redacted text sidecars. Large or personal artifacts are listed rather than copied.
Always inspect a bundle before sharing it; redaction is not a guarantee that
all private content has been removed.

### Quick troubleshooting

- **Missing optional backend:** inspect its panel/preflight and next actions.
- **Missing preview:** inspect `manifest.json`, `summary.json`,
  `typed_artifacts`, and the run's `artifacts` directory.
- **Output conflict:** select a separate output directory or a new temporary run.
- **Interactive notebook:** execute only a copy with declared `input()` values,
  or block before execution.
- **Unavailable cloud provider:** use Ollama/local or the skill router.
  Never paste keys into prompts, logs, or bundles.
- **Ambiguous result:** preserve `WARNING` and inspect `next_actions`.

## 7. Resume after a failure

If earlier results remain valid, disable a nonessential failed step or correct
its arguments, inspect the new commands with Dry Run, and use Run Remaining.

Do not blindly rerun every step unless the plan is short or all artifacts must
be regenerated. `Retry Job` creates a new run linked to the previous job.
`Run Remaining` appears only for a genuinely resumable workflow with completed
earlier steps. Jobs interrupted by app shutdown are restored as
interrupted/cancelled; existing artifacts are reindexed.

## 8. DOCUS and university coursework

DOCUS is an optional private benchmark, not the only acceptance test. Its
workflow must detect the legacy spectroscopy material, prepare safe copies for
tools sensitive to spaces in paths, preserve the original directory, and produce
artifacts, a workflow summary, and a final PDF when possible.

Version comparisons using DOCUS should also include CSV-only, FITS-only,
document-only, and mixed synthetic non-DOCUS fixtures. DOCUS is not distributed
with this repository and is unnecessary for routine installation acceptance.

## 9. Where results are stored

The default is `~/Documents/Scientific Workbench Runs`, containing individual
job directories, capability artifacts, exported plans, workflow summaries, and
benchmark outputs such as `DOCUS Benchmarks`.

Settings can open the guide, reveal output/exported-plan directories, and export
support bundles. Configuration export records local paths for review alongside
models, provider selection, the Ollama endpoint, and Codex settings. Import
applies only portable preferences: local paths, executables, and the Codex
sandbox remain unchanged. API keys are excluded from configuration export/import
and remain in Keychain or environment variables.

## 10. Safety rules

Keep independent backups of important inputs and review outputs before using
them in research or decisions. A passing workflow does not certify its scientific
method or conclusions. The software is provided as is under [LICENSE](../LICENSE);
its warranty and liability limitations apply only as far as the law allows.
Nothing here excludes rights or responsibilities that cannot lawfully be excluded.

- If a tool needs a mutable workspace, give it a copy outside sensitive original
  input directories.
- Use separate output directories.
- Child processes receive a filtered environment. Variables that look like
  secrets, including `*_KEY`, `*_TOKEN`, `*_SECRET`, and `*_PASSWORD`,
  are removed by default.
- A capability may declare required nonsecret `allowed_environment_keys`.
  Invalid or sensitive names are rejected before execution.
- For legacy diagnosis, `SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV=VAR1,VAR2`
  allows specific additional variables. As a last resort,
  `SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV=1` inherits the parent's nonsecret
  environment.
- External runs have a global safety timeout. Inspect Recovery and stdout/stderr,
  then reduce inputs or split the workflow before retrying.
- The Codex integration enforces a read-only sandbox and rejects attempts to
  broaden it through prompts or additional configuration.
- Review large plans before enabling Auto-run.

These controls do not provide a dedicated OS sandbox for all external tools.
See [SECURITY.md](../SECURITY.md) for trust boundaries and known limits.

## 11. Development verification

The E2E matrix covers readiness, tables, documents, copied-notebook execution,
FITS, mixed data, and controlled absence of STILTS. It uses synthetic fixtures
and compares input hashes before and after.

The dual gate runs from the maintenance workspace outside this distributable
repository; it is not a normal user setup step. Read `RELEASE_CHECKLIST.md`
before consolidating compatibility claims or preparing a release.

On a configured development Mac, the full local gate is:

```bash
./script/run_quality_gate.sh
```

It builds and opens the app and can take time; preserve active work first.
Historical dual-validation evidence remains in checkpoints. Do not copy
maintainer paths or use historical test counts as a substitute for current
execution on the reviewed commit. DOCUS remains optional for major milestones.

See [workflow requirements](../docs/WORKFLOW_REQUIREMENTS.md) and
[troubleshooting](../docs/TROUBLESHOOTING.md) before changing the environment or
retrying a failed job.

## 12. What to expect from local AI

The app's balanced model profile selects `qwen3:4b-instruct`. Confirm that the
model is installed and responds before relying on it. Local AI can help route
capabilities, explain failures, summarize results, and converse in English or
Spanish.

It may struggle with long scientific reasoning or suggest unnecessary steps
for ambiguous prompts. Review final tables, figures, and reports against the
underlying evidence. Model output does not replace verifiable capability
results. Jobs, artifacts, manifests, and summaries provide the operational
record.
