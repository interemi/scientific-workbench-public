# v2.1 Skill Compaction

Status: v2.1 maintenance release note.

v2.1 keeps the v2.0 integrated skill + ScientificWorkbench contract but reduces the activation cost of the skill itself. The public capabilities, registry ids, command contracts, run bundles, and ScientificWorkbench boundary are unchanged.

## Goals

- Keep `SKILL.md` as a compact router.
- Move long routing detail and generated tables into references.
- Preserve generated public-surface validation through `sync_public_surface_docs.py --check`.
- Add pytest-style wrappers so external evaluators can see that the existing `audit_*` regression family is intentional test coverage.
- Keep the installed skill synchronized only after editable checks pass.

## Non-Goals

- Do not edit or synchronize ScientificWorkbench.
- Do not rename public capabilities.
- Do not change scientific outputs merely to improve plugin-eval score.
- Do not make optional or legacy backends core dependencies.

## Moved Detail

- Expanded routing compatibility stub: `references/v2-1-expanded-skill-routing.md`
- Generated public surface: `references/public-surface-snapshot.md`
- Active compact router: `SKILL.md`

v2.2 moved the bulky historical expanded routing text outside the active skill bundle. The in-bundle v2.1 path remains as a short compatibility stub so old references still resolve without increasing normal deferred evaluation cost.

## Closure Criteria

- `SKILL.md` remains below 220 lines.
- `sync_public_surface_docs.py --check` passes against README, RELEASE, and the generated public-surface reference.
- `skill_surface_audit.py` passes.
- Representative pytest wrappers around `audit_*` regressions pass.
- `guia_scientific_data_analysis_v2_1.tex` and `.pdf` exist.
- Installed skill is synchronized only after editable validation.
- plugin-eval is rerun after synchronization.
