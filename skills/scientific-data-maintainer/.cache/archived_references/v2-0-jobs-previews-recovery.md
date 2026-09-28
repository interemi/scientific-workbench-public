# v2.0 Jobs, Previews, Recovery, And Support

Status: Phase 7 integration contract for ScientificWorkbench and the editable
`scientific-data-analysis` skill.

## Goal

ScientificWorkbench treats each skill run directory as a recoverable job
record, not merely as a process exit code. The app consumes the run bundle,
persists app-facing metadata, previews bounded artifacts, keeps useful products
after cancellation or failure, and offers honest retry or workflow-resume
actions.

## State Mapping

| Skill/app signal | Job state | User action |
|---|---|---|
| queued | Queued | Wait or cancel before process start when supported |
| running | Running | Inspect live state and cancel |
| PASS / WARNING with exit 0 | Succeeded | Inspect previews, artifacts, warnings, and next actions |
| BLOCKED / BLOCKED_CONTROLADO | Blocked | Fix the documented precondition, then retry |
| FAIL / ROTO, including exit 0 | Failed | Inspect structured error and logs before retry |
| user cancellation | Cancelled | Keep captured logs/artifacts and retry if appropriate |
| timeout | Timed Out | Keep captured logs/artifacts; reduce inputs or increase the configured timeout |
| persisted queued/running job after restart | Cancelled / interrupted | Re-index its run folder and expose recovery advice |

`FAIL` and `ROTO` must never become a succeeded job solely because the child
process returned exit code 0.

## Run-Bundle Consumption

The app reads, when present:

- `summary.json` as the canonical envelope;
- `manifest.json` as a compatible fallback;
- `stdout.txt`, `stderr.txt`, and `command.txt`;
- `next_steps.md`;
- typed artifacts from `summary.json` and `manifest.json`;
- recursive files under `artifacts/`, `previews/`, `reports/`, `tables/`, and
  `logs/`.

On history reload or **Refresh Bundle**, the bounded contents of
`command.txt`, `stdout.txt`, and `stderr.txt` rehydrate the visible job record
after secret redaction. If the JSON envelope has no structured `next_actions`,
bullet entries from `next_steps.md` become visible next actions. This keeps a
persisted or externally completed run useful without trusting raw sidecar text
as unredacted UI state.

Every completed app run writes redacted top-level `stdout.txt`, `stderr.txt`,
and `command.txt`. If the backend did not create `next_steps.md`, the app writes
a narrow file from structured `next_actions` or recovery advice. Existing
backend summaries, manifests, and scientific products are preserved.

Persisted jobs store:

- contract and app status;
- short summary and severity;
- original-modified declaration;
- warnings and structured errors;
- next actions;
- preview artifact preferences and tags;
- typed artifact index.

On app restart, interrupted jobs become Cancelled and their run directories are
re-indexed. This preserves partial artifacts without claiming that the
scientific run completed.

## Preview Policy

| Artifact | App preview |
|---|---|
| PNG/JPEG/TIFF | Native bounded image |
| PDF | First-page thumbnail plus page count |
| CSV/TSV | Bounded monospaced table excerpt |
| Markdown | Bounded readable text |
| Notebook | Cell count and bounded markdown/code excerpts |
| JSON | Bounded structured text |
| TXT/log | Bounded redacted log excerpt |
| Unsupported/binary | Honest unavailable state plus Open/Reveal actions |

Text previews are byte- and line-bounded. Configured provider secrets are
redacted before display. The app never interprets a preview as scientific
validation.

## Recovery And Controls

- **Cancel Run** stops the active process tree.
- **Retry Job** creates a new run with the same capability, inputs, and
  arguments and records `retryOfJobID`.
- **Run Remaining** appears only when a multi-step workflow has prior
  successful steps and a recoverable stopped step.
- **Refresh Bundle** re-reads envelope metadata and artifacts from disk.
- **Reveal Run Folder** and **Reveal Artifact** use Finder without editing the
  input.
- **Support Bundle** exports redacted job state and safe text sidecars. Heavy or
  personal artifacts remain in the original run folder and are only indexed.

Retry is not labelled resume. Resume is reserved for a workflow that can
continue after its last successful step.

## Safety

- Original inputs remain read-only.
- No provider secret may appear in stored logs, previews, transcripts, or
  support bundles.
- Cancellation, failure, timeout, and controlled blocking retain useful
  artifacts.
- Support bundles omit heavy/personal artifacts by default.
- Missing or corrupt previews show an unavailable state instead of a false
  success.

## Verification

- `JobRunBundleAndPreviewTests.swift` covers status mapping, run-bundle
  hydration, redacted sidecar reload, `next_steps.md` fallback, interrupted-job
  recovery, canonical capture files, image/PDF/table/Markdown/notebook/log
  previews, preview redaction, and per-job support bundles.
- `scripts/audit_v2_0_phase7_jobs_previews_regression.py` validates the dual
  skill/app contract, builds ScientificWorkbench, runs the focused Swift tests,
  and writes a technical summary under `tmp/v2_0_phase7_jobs_previews/`.
- Existing retry, workflow recovery, process cancellation, persistence, and
  secret-redaction tests remain required.
