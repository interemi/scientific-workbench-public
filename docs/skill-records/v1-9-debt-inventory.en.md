# v1.9 Debt Inventory

> English publication edition of the preserved private inventory at `766ba84`.
> Source: `skills/scientific-data-maintainer/.cache/archived_references/v1-9-debt-inventory.md`.
> Original SHA-256: `dce2ffc43af2a0065fcf197354b76caca2446612492b509b590f8f1241e455a4`.
> Row numbers, severity, family identifiers, decisions, and phase assignments
> are historical evidence, not a current backlog or a new validation run.
> The original remains unchanged privately. `duplicacion` means duplication;
> `no_procede` marks work that is not applicable within the stated scope.

Status: Phase 0 inventory for the editable v1.9 workstream.

This inventory is derived from the installed v1.8 app-readiness matrix and public registry. It closes the inherited P1/P2 list for v1.9 planning without editing Scientific Workbench or syncing the installed skill.

## Sources

- installed `references/v1-8-app-readiness-matrix.md`;
- installed `references/v1-8-app-ready-contract.md`;
- installed `references/v1-8-run-bundle-contract.md`;
- installed `references/guia_scientific_data_analysis_v1_8.tex`;
- installed `public_surface_registry.yaml`;
- read-only Scientific Workbench `ARCHITECTURE.md` and `ROADMAP.md`.

## Capability Debt Counts

| Severity | Capability rows |
|---|---:|
| `P1` | 25 |
| `P2` | 34 |
| `P0` | 0 |
| **Total** | **59** |

Cross-cutting additions: 2 P2 rows (`G1`, `G2`) for duplication and regression coverage. These do not change the 59-capability count.

## Counts By Family

| Family | P1 capability rows | P2 capability rows | Global P2 rows |
|---|---:|---:|---:|
| `artifact_types` | 12 | 5 | 0 |
| `app_hints` | 7 | 11 | 0 |
| `errors` | 3 | 1 | 0 |
| `duplicacion` | 0 | 0 | 1 |
| `regressions` | 0 | 0 | 1 |
| `exposure_modes` | 3 | 17 | 0 |

## Counts By Decision

| Decision | Capability rows | Meaning |
|---|---:|---|
| `v1_9` | 34 | Narrow consolidation action fits v1.9. |
| `v2_0` | 8 | Requires app/UI sync or broader workflow work. |
| `no_procede` | 17 | Do not generalize; document limit and exposure boundary only. |

## What Enters v1.9

- Artifact type freeze and compatible extensions where already implied by v1.8 outputs.
- App-facing error, warning, and controlled-block hardening.
- App hints and next_actions for routes that already produce useful backend output.
- Exposure-mode locks for normal, expert, optional, legacy, maintainer-only, and not-applicable routes.
- Small helper dedupe only when regression evidence shows repeated envelope/artifact/run-bundle code.
- Lightweight app-like regression expansion for families already covered by the backend.

## What Remains For v2.0

Defer to v2.0: major synchronization with Scientific Workbench; complete UI-driven workflows; an app planner with the skill as the formal execution engine; job history, previews, and statuses consumed directly by the app; and joint skill/app documentation.

Concrete examples deferred to v2.0 include progress UI, interactive column selectors, visual diff confirmation, optional-backend panels, job history, app-side parser adoption, and full Scientific Workbench workflow orchestration.

The specific Debt E guardrail is maintained in
`references/v1-9-v2-0-deferrals.md`. It freezes the 8 rows marked `decision=v2_0`
and prevents them from being scheduled as v1.9 work.

## No-Procede Rule

Rows marked `no_procede` are not failures. They are capabilities whose honest product boundary is expert, legacy, maintainer, or domain-specific. v1.9 may document and regress that boundary, but should not force a general-world analogy.

## Actionable Capability Rows

| N | Capability | Severity | Family | App readiness | Decision | Assigned phase | Narrow action | Risk | Deferred / limit |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | `datanalysis_env.py status` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 2 | `datanalysis_healthcheck.py` | `P2` | `artifact_types` | `app_ready` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 3 | `env_doctor.py` | `P2` | `errors` | `app_ready` | `v1_9` | `2-errors-blocks` | Harden app-facing messages and clean WARNING/BLOCKED/FAIL behavior; verify no raw traceback in regression output. | medium: status changes may affect legacy parsers. | None specific; reassess only if a later phase identifies UI scope. |
| 4 | `companion_route_check.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 5 | `external_astro_tools_preflight.py` | `P1` | `exposure_modes` | `blocked_optional` | `v1_9` | `5-exposure-modes` | Fix the exposure mode and block cleanly when the backend/environment is inapplicable. | low to medium: risk of promising inappropriate normal-mode exposure. | None specific; reassess only if a later phase identifies UI scope. |
| 6 | `external_astro_tools_local_validation.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 7 | `inspect_fits.py` | `P2` | `artifact_types` | `app_ready` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 8 | `fits_rgb_batch.py` | `P1` | `artifact_types` | `app_ready_partial` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | Progress UI and interactive job control remain in v2.0; v1.9 may only freeze backend types/limits if this area is touched. |
| 9 | `rgb_visual_fits_export.py` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 10 | `stilts_workbench.py` | `P1` | `exposure_modes` | `blocked_optional` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | An optional panel with a native alternative is app UX; v1.9 preserves blocking/control and documentation. |
| 11 | `astrometry_net_workbench.py preflight` | `P1` | `app_hints` | `app_ready_partial` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 12 | `astrometry_net_workbench.py verify-existing-wcs` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 13 | `radial_velocity_workbench.py inspect` | `P1` | `app_hints` | `app_ready_partial` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | The interactive column/unit wrapper belongs to app UX; v1.9 only documents limits and messages. |
| 14 | `radial_velocity_workbench.py validate-manifest` | `P1` | `app_hints` | `app_ready_partial` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 15 | `legacy_spectroscopy_envcheck.py` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 16 | `echelle_multispec_inventory.py` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 17 | `fxcor_iraf_workbench.py prepare-session` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 18 | `fxcor_iraf_workbench.py run-auto` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 19 | `legacy_rv_coursework_workbench.py analyze` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 20 | `sb2_double_gaussian_workbench.py fit` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 21 | `li6708_equivalent_width_workbench.py measure` | `P2` | `exposure_modes` | `not_applicable_to_app` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 22 | `legacy_external_reference_check.py` | `P2` | `exposure_modes` | `not_applicable_to_app` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 23 | `istarmod_workbench.py inspect-tree` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 24 | `istarmod_workbench.py prepare-copy` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 25 | `legacy_spectroscopy_report_builder.py scaffold` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 26 | `photometric_solution.py` | `P1` | `artifact_types` | `app_ready_partial` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | Interactive column selection belongs to the app; v1.9 may only harden artifacts/app_hints. |
| 27 | `photometry_noise_budget.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 28 | `apt_workbench.py` | `P1` | `exposure_modes` | `blocked_optional` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | The optional APT panel and visual alternative route belong to the app; v1.9 preserves blocking/control. |
| 29 | `teareduce_router.py` | `P1` | `app_hints` | `blocked_optional` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 30 | `document_intake_workbench.py` | `P2` | `artifact_types` | `app_ready` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 31 | `presentation_workbench.py inspect` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 32 | `presentation_workbench.py existing-deck-style-audit` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 33 | `iwork_workbench.py` | `P1` | `errors` | `blocked_optional` | `v1_9` | `2-errors-blocks` | Harden app-facing messages and clean WARNING/BLOCKED/FAIL behavior; verify no raw traceback in regression output. | medium: status changes may affect legacy parsers. | None specific; reassess only if a later phase identifies UI scope. |
| 34 | `office_roundtrip.py docx-style-inventory` | `P1` | `artifact_types` | `app_ready_partial` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | Visual style selection and match preview remain in v2.0. |
| 35 | `office_roundtrip.py docx-styled-replace` | `P1` | `artifact_types` | `app_ready_partial` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | Visual edit confirmation/diff remains in v2.0; v1.9 may freeze the edited-document type if approved. |
| 36 | `quicklook_bridge.py` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 37 | `keynote_export.py` | `P1` | `errors` | `blocked_optional` | `v2_0` | `v2_0` | Do not implement in v1.9; preserve the contract/backend and record the future app/UI integration requirement. | high if attempted without UI/app work: may violate consolidation scope. | GUI confirmation and visible automation remain in v2.0; v1.9 only provides preflight/clean blocking. |
| 38 | `latex_workbench.py scaffold` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 39 | `latex_workbench.py review` | `P1` | `artifact_types` | `app_ready_partial` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 40 | `scientific_writeup_review.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 41 | `deliverable_factory.py scaffold` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 42 | `semantic_diff.py` | `P2` | `artifact_types` | `app_ready` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 43 | `profile_table.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 44 | `duckdb_workbench.py` | `P1` | `errors` | `blocked_optional` | `v1_9` | `2-errors-blocks` | Harden app-facing messages and clean WARNING/BLOCKED/FAIL behavior; verify no raw traceback in regression output. | medium: status changes may affect legacy parsers. | None specific; reassess only if a later phase identifies UI scope. |
| 45 | `cross_domain_data_workbench.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 46 | `bootstrap_analysis_notebook.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 47 | `notebook_workbench.py execute-copy` | `P2` | `artifact_types` | `app_ready` | `v1_9` | `1-artifact-freeze/4-typed-artifacts` | Freeze or compatibly extend artifact types; validate typed artifacts with a focused regression. | medium: requires compatibility without renaming v1.8 types. | None specific; reassess only if a later phase identifies UI scope. |
| 48 | `coursework_notebook_fidelity_check.py` | `P1` | `app_hints` | `app_ready_partial` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 49 | `notebook_branch_compare.py` | `P1` | `app_hints` | `app_ready_partial` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 50 | `spectra_ascii_coursework_workbench.py` | `P2` | `exposure_modes` | `cli_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 51 | `timeseries_forecasting_workbench.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 52 | `inspect_data_container.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 53 | `catalog_workbench.py crossmatch-sky` | `P1` | `app_hints` | `app_ready_partial` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 54 | `physical_qa.py` | `P2` | `app_hints` | `app_ready` | `v1_9` | `4-app-hints` | Add or document backend app_hints/next_actions without changing scientific behavior. | low to medium: documentation/tests or a focused helper change. | None specific; reassess only if a later phase identifies UI scope. |
| 55 | `capability_probe_matrix.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 56 | `portable_smoke_test.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 57 | `validate_skill_samples.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 58 | `sync_public_surface_docs.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |
| 59 | `skill_surface_audit.py` | `P2` | `exposure_modes` | `maintainer_only` | `no_procede` | `5-limit-only` | Document the limit and keep outside normal mode; do not generalize or create a new wrapper. | low if documented; high if forced into a general action. | No justified generalization is pending; expert/maintainer mode only where applicable. |

## Cross-Cutting Rows

| N | Capability | Severity | Family | Decision | Assigned phase | Narrow action | Risk | Deferred / limit |
|---|---|---|---|---|---|---|---|---|
| G1 | `GLOBAL: envelope/artifact/run-bundle helpers` | `P2` | `duplicacion` | `v1_9` | `3-helper-dedupe` | Inventory duplicate helpers and extract only focused functions where regression evidence demonstrates repetition. | medium: an overly broad refactor could break stable routes. | A complete formal shared architecture remains in v2.0 if it requires app-side changes. |
| G2 | `GLOBAL: app-like regression coverage` | `P2` | `regressions` | `v1_9` | `6-app-like-regressions` | Create lightweight family regressions for artifact discovery, clean errors, exposure modes, and original preservation; see `references/v1-9-app-like-extended-regression.md`. | low to medium: excessively heavy tests would slow release work. | End-to-end Scientific Workbench UI coverage remains in v2.0. |

## Risks

- Biggest scope risk: treating v2.0 UI work as v1.9 consolidation.
- Compatibility risk: renaming v1.8 artifact types instead of adding aliases or extensions.
- Regression risk: making app-like tests too heavy or dependent on optional backends.
- Product risk: exposing legacy/domain-specific tools as normal actions without honest warnings.

## Decision

Phase 0 can proceed if `scripts/audit_v1_9_phase0_inventory_regression.py` validates the 59 capability rows, the required families, the v1.9/v2.0/no-procede decisions, and the absence of v2.0-only scope inside v1.9 actions.
