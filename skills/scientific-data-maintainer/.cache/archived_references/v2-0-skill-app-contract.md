# v2.0 Skill + App Contract

Status: Phase 1 contract for the v2.0 integrated release.

This document defines the contract that ScientificWorkbench consumes from the
installed `scientific-data-analysis` skill in v2.0. It extends the v1.8
app-ready envelope and the v1.9 artifact/error hardening without breaking
existing `contract_version: "1.8"` or v1.9-compatible payloads.

## Compatibility Rule

ScientificWorkbench must keep accepting:

- legacy payloads with top-level `tool` and `status`;
- v1.8 app-ready payloads with `contract_version: "1.8"`;
- v1.9 hardened payloads that still use the v1.8 envelope shape;
- v2.0 integrated payloads with `contract_version: "2.0"`.

v2.0 is therefore an additive contract. It must not rename frozen v1.8/v1.9
artifact types, error kinds, or top-level compatibility fields.

## Minimum v2.0 Envelope Fields

| Field | Required | Meaning |
|---|---:|---|
| `contract_version` | yes | `"2.0"` for new integrated envelopes; app still accepts `"1.8"` and omitted legacy contracts. |
| `tool` | yes | Stable tool name used by legacy parsers and logs. |
| `capability_id` | yes when registry-backed | Registry id such as `profile_table` or `radial_velocity_workbench.inspect`. |
| `capability_label` | yes when known | Human-facing capability label. |
| `status` | yes | Canonical status or legacy-compatible status. |
| `app_status` | recommended | Canonical app status if different from `status`; app normalizes both. |
| `command` | yes | Redacted command object with `argv`, `cwd`, and `redacted=true`. |
| `inputs` | yes | Inputs inspected or copied; may be empty for environment/preflight tools. |
| `outputs` | yes | Direct output records expected from the command. |
| `typed_artifacts` | yes | Primary app-facing artifact list. |
| `artifacts` | compatible | Legacy list/object accepted; prefer `typed_artifacts`. |
| `warnings` | yes | User-facing warnings; empty list if none. |
| `errors` | yes | Structured errors with `kind` and `message`; empty list if none. |
| `qa` | yes | QA status/findings/metrics. |
| `provenance` | yes | Creator, skill contract/version, backend and original-policy metadata. |
| `next_actions` | yes | Practical next steps for a user or UI. |
| `original_modified` | yes | `false`, `true`, or `"unknown"` with explanation. Normal routes should be `false`. |
| `app_hints` | yes | Short summary, severity, preview artifact types, and tags. |
| `job_metadata` | v2.0 recommended | Retry/cancel/exposure hints for ScientificWorkbench job UI. |
| `safety` | v2.0 recommended | Input/output policy and secret-redaction state. |

## Status Mapping

| Skill status | App `JobStatus` | UI severity | Meaning |
|---|---|---|---|
| `PASS`, `ok`, `pass`, `success`, `ready` | `succeeded` | `ok` | Output is usable. |
| `WARNING`, `warning`, `skip`, `skipped` | `succeeded` with warning badge | `warning` | Output is useful but needs review. |
| `BLOCKED_CONTROLADO`, `blocked` | `blocked` | `blocked` | Preconditions, inputs, optional backend, or safety state prevented execution cleanly. |
| `FAIL`, `fail`, `failed`, `error` | `failed` | `error` | Tool failed cleanly and should not present products as valid. |
| `ROTO` | `failed` plus release-blocker marker | `error` | Audit-only classification for raw traceback, false success, misleading output, or original mutation. It should not be a normal user-facing success path. |

If both `status` and `app_status` exist, ScientificWorkbench should prefer the
canonical `app_status` for job state while retaining `status` for provenance and
legacy display.

## Required Artifact Types

v2.0 keeps all frozen v1.8/v1.9 types and requires ScientificWorkbench to
recognize at least:

| Artifact type | App behavior |
|---|---|
| `summary_json` | Parseable run/tool summary. |
| `manifest_json` | Provenance/run manifest. |
| `report_md` | Markdown/text report preview. |
| `preview_png` | Image preview. |
| `table_csv` | Table preview or open externally. |
| `notebook_ipynb` | Notebook artifact / executed copy. |
| `log_txt` | Stdout/stderr/command/runtime logs. |
| `qa_report` | QA report preview. |
| `handoff_bundle` | Folder or package reveal/open action. |
| `edited_document` | Edited copy produced after confirmation; never the original. |
| `app_preview` | App-specific preview sidecar, such as visual diff metadata. |
| `unknown` | Explicit fallback when type cannot be inferred honestly. |

Compatibility additions from v1.9, such as `fits_product`, `fits_visual`,
`metadata_json`, and `preview_pdf`, remain valid. v2.0 app discovery must not
reject them.

## Run Bundle Shape

v2.0 keeps the v1.8 run bundle:

```text
run/
  manifest.json
  summary.json
  stdout.txt
  stderr.txt
  command.txt
  artifacts/
  previews/
  reports/
  tables/
  logs/
  next_steps.md
```

ScientificWorkbench may discover recursively for compatibility, but it should
prefer explicit `typed_artifacts` from `summary.json` and `manifest.json` when
present.

## App Hints

Minimum `app_hints`:

| Field | Meaning |
|---|---|
| `short_summary` | One-line user-facing summary for job rows and notifications. |
| `severity` | `ok`, `warning`, `blocked`, or `error`. |
| `preview_artifact_types` | Ordered artifact types worth previewing first. |
| `tags` | Search/filter tags for capability, domain, or workflow family. |

The app should treat hints as display guidance, not as scientific truth.

## Error Contract

Each error object should contain:

- `kind`;
- `message`;
- optional `recovery_hint`;
- optional path/backend fields when safe.

Allowed v1.9 kinds remain valid:

- `missing_input`;
- `output_conflict`;
- `corrupt_input`;
- `missing_optional_backend`;
- `invalid_argument`;
- `unsupported_format`;
- `permission_denied`;
- `timeout`;
- `dependency_error`;
- `execution_error`;
- `tool_error`.

v2.0 may add narrower kinds only after documenting them and proving app-side
fallback behavior.

## Job Metadata

`job_metadata` is a v2.0 additive object for UI behavior:

| Field | Values | Meaning |
|---|---|---|
| `safe_to_retry` | boolean | Whether retrying unchanged is reasonable. |
| `supports_cancel` | boolean | Whether app cancellation should be presented as normal. |
| `recommended_exposure` | `normal`, `expert`, `optional`, `legacy`, `maintainer` | Where the app should expose the workflow. |
| `estimated_runtime_seconds` | number/object optional | Optional local estimate, not a guarantee. |

## Safety Policy

`safety` must support product trust:

| Field | Meaning |
|---|---|
| `input_policy` | Usually `read_only_or_copied`. |
| `output_policy` | Usually `separate_run_directory`. |
| `secrets_redacted` | Boolean. Must be true for app-facing outputs. |
| `requires_confirmation` | Optional boolean for edited-document or GUI automation flows. |

If a script cannot prove whether originals were modified, it must set
`original_modified: "unknown"` and include a warning/next action. v2.0
ScientificWorkbench should treat that as requiring human review.

For confirmed edited-document workflows, the result should also preserve an
auditable confirmation record:

| Field | Meaning |
|---|---|
| `confirmation.required` | The workflow requires explicit approval. |
| `confirmation.enforced_by_backend` | The backend was invoked in strict confirmation mode. |
| `confirmation.recorded` | A non-empty approval identifier was received. |
| `confirmation.confirmation_id` | Opaque app-generated approval identifier; it must not contain secrets. |

ScientificWorkbench must validate the reviewed diff before launch. When strict
confirmation is requested, the backend must reject a missing identifier before
creating an edited artifact.

The same confirmation record applies to GUI automation. A controlled Keynote
export must perform preflight without opening the app, require an app-generated
identifier before activation, expose visible running state app-side, and retain
the native execution log as `log_txt` beside the `preview_pdf`, summary, and
manifest. Failed automation must not leave a partial PDF that looks valid.

## Contract Fixtures

Minimum fixtures live under:

```text
examples/contracts/v2_0/
  pass_envelope.json
  warning_envelope.json
  blocked_envelope.json
  fail_envelope.json
```

They prove that the skill can express:

- a normal successful run;
- a useful warning;
- a controlled optional-backend block;
- a clean failure on corrupt input.

## Validation Requirements

The v2.0 Phase 1 regression must validate:

- this document contains the field table, status mapping, artifact vocabulary,
  error contract, job metadata, and safety policy;
- all four fixtures parse as JSON;
- fixtures include required v2.0 fields;
- fixture statuses cover `PASS`, `WARNING`, `BLOCKED_CONTROLADO`, and `FAIL`;
- fixture artifact types are in the frozen/allowed vocabulary;
- blocked and failed fixtures include parseable `errors[].kind`;
- all fixtures include `next_actions`, `app_hints.short_summary`,
  `original_modified`, `job_metadata`, and `safety`;
- ScientificWorkbench has a parser test for these v2.0 fields.

## Phase 1 Boundary

Phase 1 defines and proves the contract. It does not complete the eight deferred
P1 workflows. Those remain scheduled for later v2.0 phases.

## Joint Documentation Boundary

The v2.0 contract is also a documentation promise. User-facing docs must keep
these boundaries clear:

- the skill is the deterministic backend and keeps owning public capabilities,
  envelopes, run bundles, typed artifacts, warnings, errors, provenance, and
  original-modified policy;
- ScientificWorkbench is the macOS product surface and owns provider choice,
  plan review, guided controls, job state, previews, support bundles, optional
  panels, and confirmation UI;
- local-first execution is the default;
- Ollama is the no-paid-API local AI path;
- OpenAI, Grok/xAI, and Gemini are optional cloud providers and may cost money;
- Codex bridge is for coding, reporting, or long local reasoning, not for
  replacing deterministic capability execution;
- any missing optional backend, unsafe interactive notebook, ambiguous input, or
  GUI prerequisite must be documented as `WARNING` or `BLOCKED_CONTROLADO`
  rather than success.

Documentation must not claim v2.0 is installed until the final sync and
post-sync validation phase passes.
