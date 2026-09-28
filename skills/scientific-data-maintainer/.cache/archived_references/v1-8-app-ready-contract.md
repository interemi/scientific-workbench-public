# v1.8 App-Ready JSON Contract

Status: Fase 1 contract for the editable v1.8 workstream.

This reference defines the app-ready JSON envelope that
`scientific-data-analysis` should expose progressively in v1.8. It is a
compatibility contract for local app invocation, especially by
`ScientificWorkbench`; it is not a demand to rewrite every existing capability
in one pass.

## Design Goals

- Keep existing v1.6/v1.7 standard envelopes valid.
- Let an app understand the most important facts without custom parsing per
  script.
- Preserve deterministic local execution and provenance.
- Keep warnings and controlled blocks visible, not collapsed into failures.
- Make artifact discovery less heuristic over time.
- Give humans useful next actions, not only machine metadata.

## Existing Compatibility Layer

The current helper layer already provides:

- `scripts/_internal/public_contract.py`
  - `build_tool_payload`
  - `build_preflight_payload`
  - `emit_payload`
  - `validate_standard_envelope`
- `scripts/_internal/provenance_utils.py`
  - `standard_tool_payload`
  - `standard_qa_payload`
  - `public_path`
  - `sanitize_payload`
  - `write_manifest`

Existing v1.6/v1.7 envelopes generally use:

```json
{
  "tool": "profile_table",
  "status": "ok",
  "notes": [],
  "artifacts": {},
  "results": {},
  "qa": {
    "status": "not_applicable",
    "findings": [],
    "metrics": {}
  }
}
```

ScientificWorkbench currently parses top-level `tool` and `status` from stdout
and discovers artifacts from the run directory. v1.8 therefore keeps those
fields top-level and backwards compatible.

## Canonical App Statuses

v1.8 defines app-facing status semantics:

| Canonical app status | Legacy accepted statuses | Meaning |
|---|---|---|
| `PASS` | `ok`, `pass`, `success`, `ready` | The run completed and the output can be used. |
| `WARNING` | `warning`, `skip`, `skipped` | The run produced useful output but found risks, caveats, or partial coverage. |
| `BLOCKED_CONTROLADO` | `blocked` | The run did not proceed because a dependency, input, backend, or safety condition was absent, and it explained that cleanly. |
| `FAIL` | `fail`, `failed`, `error` | The run failed cleanly and did not leave products that look valid. |
| `ROTO` | no normal legacy equivalent | Internal audit label for broken behavior such as raw traceback, false success, misleading output, or original mutation. A public tool should avoid emitting this as a normal user-facing status; regressions may use it to classify failures. |

New v1.8-native envelopes should use the canonical app status in `status`.
Existing v1.6/v1.7 tools may continue to emit lowercase legacy statuses until
they are migrated. App-side consumers and v1.8 validators should normalize both
forms.

## Minimum v1.8 Envelope

```json
{
  "contract_version": "1.8",
  "tool": "profile_table",
  "capability_id": "profile_table",
  "capability_label": "profile_table.py",
  "status": "PASS",
  "command": {
    "argv": ["python", "scripts/profile_table.py", "input.csv", "--summary-json", "summary.json"],
    "cwd": "/path/to/skill",
    "redacted": true
  },
  "inputs": [
    {
      "path": "/path/to/input_copy.csv",
      "role": "primary_input",
      "kind": "table_csv",
      "exists": true
    }
  ],
  "outputs": [
    {
      "path": "/path/to/run/summary.json",
      "role": "summary",
      "artifact_type": "summary_json",
      "exists": true
    }
  ],
  "artifacts": [
    {
      "path": "/path/to/run/summary.json",
      "artifact_type": "summary_json",
      "label": "Machine-readable summary",
      "preview_role": "json",
      "primary": true
    }
  ],
  "warnings": [],
  "errors": [],
  "qa": {
    "status": "PASS",
    "findings": [],
    "metrics": {}
  },
  "provenance": {
    "created_by": "scientific-data-analysis",
    "skill_version": "v1.8",
    "source_tree": "editable",
    "originals_policy": "read_only_inputs"
  },
  "next_actions": [
    {
      "label": "Review profile warnings",
      "kind": "human_review",
      "priority": "normal"
    }
  ],
  "original_modified": false,
  "app_hints": {
    "short_summary": "Table profile completed.",
    "severity": "ok",
    "preview_artifact_types": ["summary_json"],
    "tags": ["table", "profile", "app-ready"]
  }
}
```

## Field Reference

| Field | Required | Type | Notes |
|---|---:|---|---|
| `contract_version` | v1.8 native yes | string | Use `"1.8"` for app-ready envelopes. Legacy envelopes may omit it. |
| `tool` | yes | string | Stable tool name. Must remain top-level for ScientificWorkbench compatibility. |
| `capability_id` | when known | string | Registry id such as `profile_table`. |
| `capability_label` | when known | string | Public label such as `profile_table.py`. |
| `status` | yes | string | v1.8 canonical or legacy-compatible status. |
| `command` | yes for app-ready | object | Redacted argv/cwd; do not leak secrets or private machine-only details. |
| `inputs` | yes for app-ready | list | Inputs read or inspected. Use copied paths when originals were copied. |
| `outputs` | yes for app-ready | list | Direct outputs expected from the command. |
| `artifacts` | yes for app-ready | list or legacy object | Prefer list of typed artifact objects. Existing legacy object maps remain accepted. |
| `warnings` | yes for app-ready | list | Human-readable warnings; empty list if none. |
| `errors` | yes for app-ready | list | Clean failure/block details; no raw tracebacks unless explicitly wrapped as diagnostic text for maintainers. |
| `qa` | yes | object | QA status, findings, metrics. Legacy lowercase QA statuses are accepted. |
| `provenance` | yes for app-ready | object | Source tree, copied/original policy, backend versions where relevant. |
| `next_actions` | yes for app-ready | list | Practical next steps for a person or app UI. |
| `original_modified` | yes for app-ready | boolean or `"unknown"` | Must be `false` for normal read-only/copied-input routes. |
| `app_hints` | yes for app-ready | object | Short summary, severity, preview types, tags, optional display hints. |

## Artifact Taxonomy

Initial artifact types:

| Artifact type | Meaning |
|---|---|
| `summary_json` | Machine-readable summary envelope or run summary. |
| `manifest_json` | Provenance manifest with inputs, outputs, command, environment. |
| `report_md` | Human-readable markdown report. |
| `preview_png` | Static visual preview image. |
| `table_csv` | CSV table output. |
| `notebook_ipynb` | Notebook artifact or executed notebook copy. |
| `log_txt` | stdout, stderr, command log, or execution transcript. |
| `qa_report` | Dedicated quality-assurance report. |
| `handoff_bundle` | Folder/package intended for delivery or continuation. |
| `unknown` | Existing or discovered artifact that is not typed yet. |

Future phases may add types, but v1.8 should avoid renaming these once used.

## Example: PASS

```json
{
  "contract_version": "1.8",
  "tool": "profile_table",
  "capability_id": "profile_table",
  "capability_label": "profile_table.py",
  "status": "PASS",
  "command": {
    "argv": ["python", "scripts/profile_table.py", "input_copy.csv", "--summary-json", "summary.json"],
    "cwd": "/skill/root",
    "redacted": true
  },
  "inputs": [
    {"path": "input_copy.csv", "role": "primary_input", "kind": "table_csv", "exists": true}
  ],
  "outputs": [
    {"path": "summary.json", "role": "summary", "artifact_type": "summary_json", "exists": true}
  ],
  "artifacts": [
    {"path": "summary.json", "artifact_type": "summary_json", "label": "Summary", "primary": true}
  ],
  "warnings": [],
  "errors": [],
  "qa": {"status": "PASS", "findings": [], "metrics": {"row_count": 42}},
  "provenance": {"originals_policy": "read_only_inputs", "source_tree": "editable"},
  "next_actions": [{"label": "Open summary", "kind": "inspect_artifact", "priority": "normal"}],
  "original_modified": false,
  "app_hints": {"short_summary": "Profile completed.", "severity": "ok", "preview_artifact_types": ["summary_json"], "tags": ["table"]}
}
```

## Example: WARNING

```json
{
  "contract_version": "1.8",
  "tool": "physical_qa",
  "capability_id": "physical_qa",
  "capability_label": "physical_qa.py",
  "status": "WARNING",
  "command": {"argv": ["python", "scripts/physical_qa.py", "sensor.csv"], "cwd": "/skill/root", "redacted": true},
  "inputs": [{"path": "sensor.csv", "role": "primary_input", "kind": "table_csv", "exists": true}],
  "outputs": [{"path": "qa.json", "role": "summary", "artifact_type": "summary_json", "exists": true}],
  "artifacts": [{"path": "qa.json", "artifact_type": "qa_report", "label": "QA summary", "primary": true}],
  "warnings": ["Detected non-finite values in numeric columns."],
  "errors": [],
  "qa": {"status": "WARNING", "findings": ["1 Inf value detected"], "metrics": {"non_finite_count": 1}},
  "provenance": {"originals_policy": "read_only_inputs"},
  "next_actions": [{"label": "Clean non-finite values before modeling", "kind": "human_review", "priority": "high"}],
  "original_modified": false,
  "app_hints": {"short_summary": "QA completed with warnings.", "severity": "warning", "preview_artifact_types": ["qa_report"], "tags": ["qa", "sensor"]}
}
```

## Example: BLOCKED_CONTROLADO

```json
{
  "contract_version": "1.8",
  "tool": "stilts_workbench",
  "capability_id": "stilts_workbench",
  "capability_label": "stilts_workbench.py",
  "status": "BLOCKED_CONTROLADO",
  "command": {"argv": ["python", "scripts/stilts_workbench.py", "preflight"], "cwd": "/skill/root", "redacted": true},
  "inputs": [],
  "outputs": [{"path": "summary.json", "role": "summary", "artifact_type": "summary_json", "exists": true}],
  "artifacts": [{"path": "summary.json", "artifact_type": "summary_json", "label": "Preflight summary", "primary": true}],
  "warnings": [],
  "errors": [{"message": "STILTS executable was not found.", "kind": "missing_optional_backend"}],
  "qa": {"status": "BLOCKED_CONTROLADO", "findings": ["Missing optional backend: STILTS"], "metrics": {}},
  "provenance": {"originals_policy": "read_only_inputs", "backend_required": "STILTS"},
  "next_actions": [{"label": "Install/configure STILTS or use catalog_workbench.py for native crossmatch", "kind": "route_decision", "priority": "normal"}],
  "original_modified": false,
  "app_hints": {"short_summary": "Optional backend missing.", "severity": "blocked", "preview_artifact_types": ["summary_json"], "tags": ["optional-backend"]}
}
```

## Example: FAIL Limpio

```json
{
  "contract_version": "1.8",
  "tool": "inspect_data_container",
  "capability_id": "inspect_data_container",
  "capability_label": "inspect_data_container.py",
  "status": "FAIL",
  "command": {"argv": ["python", "scripts/inspect_data_container.py", "missing.zip"], "cwd": "/skill/root", "redacted": true},
  "inputs": [{"path": "missing.zip", "role": "primary_input", "kind": "archive_zip", "exists": false}],
  "outputs": [],
  "artifacts": [],
  "warnings": [],
  "errors": [{"message": "Input path does not exist: missing.zip", "kind": "missing_input"}],
  "qa": {"status": "FAIL", "findings": ["Input path does not exist"], "metrics": {}},
  "provenance": {"originals_policy": "read_only_inputs"},
  "next_actions": [{"label": "Choose an existing file or folder", "kind": "user_input", "priority": "high"}],
  "original_modified": false,
  "app_hints": {"short_summary": "Input missing.", "severity": "error", "preview_artifact_types": [], "tags": ["input-error"]}
}
```

## Migration Policy

v1.8 phases should migrate by priority, not by blanket rewrite:

1. Keep legacy envelopes valid.
2. Add `contract_version`, typed artifacts, `original_modified`, and
   `app_hints` to high-value app routes first.
3. Use wrappers or run-bundle metadata where changing a mature script is risky.
4. Leave optional/legacy/domain-specific routes as controlled blocks when their
   backend or assumptions are absent.
5. Treat raw traceback, false success, misleading artifacts, or original input
   mutation as release-blocking bugs for any route marked app-ready.

## Compatibility Decision

The v1.8 contract does not require rewriting all capabilities immediately.
A tool can be considered transition-compatible when:

- it emits top-level `tool` and `status`;
- it writes a parseable `summary.json` when requested;
- it preserves original inputs;
- it has clean failure/block behavior;
- v1.8 metadata can be supplied by a wrapper, run bundle, or future migration.
