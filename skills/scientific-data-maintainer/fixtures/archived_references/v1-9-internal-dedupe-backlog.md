# v1.9 Internal Dedupe Backlog

Scope: narrow consolidation for app-facing helpers in the editable skill tree.
This is not a broad refactor and does not change ScientificWorkbench.

## Shared Helpers

| Family | Shared helper | v1.9 status |
| --- | --- | --- |
| Blocked envelopes | `scripts/_internal/public_contract.py::build_blocked_payload` | Active |
| Summary writers | `scripts/_internal/public_contract.py::emit_payload_best_effort` | Active |
| Typed artifacts | `scripts/_internal/provenance_utils.py::typed_artifacts_from_legacy` | Active |
| App next actions | `scripts/_internal/provenance_utils.py::default_next_actions` | Active |
| Manifests | `scripts/_internal/provenance_utils.py::write_manifest` | Active |
| Run-bundle next steps | `scripts/_internal/run_bundle.py::write_next_steps_md` | Active |

## Phase 3 Migrated Targets

| Target | Change | Regression coverage |
| --- | --- | --- |
| `photometric_solution.py` | Blocked payload now uses shared helper and best-effort summary writer. | `audit_v1_9_dedupe_regression.py`; v1.6 photometric regression |
| `li6708_equivalent_width_workbench.py` | Blocked payload now uses shared helper and best-effort summary writer. | `audit_v1_9_dedupe_regression.py`; v1.6 Li6708 regression |
| `echelle_multispec_inventory.py` | Blocked payload now uses shared helper and best-effort summary writer. | `audit_v1_9_dedupe_regression.py`; v1.6 echelle regression |
| `spectra_ascii_coursework_workbench.py` | Local payload writer removed; blocked and success summaries use shared best-effort writer. | `audit_v1_9_dedupe_regression.py`; v1.6 spectra ASCII regression |

## Backlog Not Migrated

| Area | Reason |
| --- | --- |
| Platform and preview scripts: `quicklook_bridge.py`, `keynote_export.py`, presentation deck routes | Their blocked payloads carry platform, preview, GUI, and renderer context; migrate only with platform-specific regressions. |
| Legacy/maintainer scripts: `external_astro_tools_local_validation.py`, `legacy_spectroscopy_envcheck.py` | Their local helpers carry maintainer or legacy environment metrics; migrate in a dedicated legacy/maintainer pass. |
| FITS/RGB batch routes | Some manifests and artifacts are domain-specific and should stay local until a targeted FITS/RGB regression owns the schema. |
| Maintainer stdout emitters | Several maintenance scripts intentionally support quiet or partial stdout policies; migrate only when their public stdout contract is explicit. |
| Run-bundle adoption | Keep gradual. Do not force every script into run bundles before app consumption needs it. |

## Guardrails

- Migrate 3-6 scripts per pass.
- Do not remove domain-specific manifest content.
- Do not convert honest `WARNING` or `BLOCKED_CONTROLADO` into `FAIL`.
- New helpers must preserve `typed_artifacts`, `errors.kind`, `next_actions`, `app_hints`, and `original_modified=false`.
- Regressions must include at least one broken command per migrated family and reject raw tracebacks.
