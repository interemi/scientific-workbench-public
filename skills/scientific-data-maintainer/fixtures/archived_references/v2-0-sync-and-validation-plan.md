# v2.0 sync and validation plan

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-maintainer/fixtures/archived_references/v2-0-sync-and-validation-plan.md`.
> Original SHA-256: `5990c5b3ce484dade3230496717fe05b4cdc5a3fff99b4b2d83e10de55d2be57`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Status: Phase 9 joint documentation plan. This document defines how v2.0 will
move from editable trees to installed skill plus Scientific Workbench validation.

## Current state

- Editable skill:
  `$PRIVATE_WORKSPACE/skill_work/scientific-data-analysis`
- Installed skill:
  `$HOME/.codex/skills/scientific-data-analysis`
- Scientific Workbench:
  `$PRIVATE_WORKSPACE/ScientificWorkbench`
- Installed skill remains `v1.9 stable` until the final sync phase passes.
- Phase 8 passed in the editable trees with decision `LISTO_PARA_FASE_9`.

## Product boundary

The skill remains the deterministic backend. Scientific Workbench remains the
native macOS product surface. v2.0 is not declared installed until both sides
are validated after synchronization.

## Pre-sync gates

Before synchronization:

1. Run skill documentation checks.
2. Run skill v2.0 regressions affected by documentation and contract changes.
3. Run the dual gate:

```bash
./run_v2_0_dual_gate.sh
```

4. Confirm `dual_gate_summary.json` reports `PASS` and `LISTO_PARA_FASE_9`.
5. Confirm no `FAIL`, `ROTO`, raw traceback, secret leak, or original mutation
   is present.
6. Confirm documentation states that v2.0 is editable/release-candidate until
   final sync.

## Synchronization scope

Final v2.0 synchronization should copy the editable skill to the installed
skill with `rsync`, preserving public scripts, references, examples, contract
fixtures, guides, and release artifacts that are part of the skill. It must
exclude generated residue:

```text
tmp/
__pycache__/
*.pyc
.DS_Store
```

Scientific Workbench is not copied into the skill. It is validated beside it.

## Post-sync validation

After synchronizing the installed skill:

1. Run `scripts/sync_public_surface_docs.py --check` in the installed skill.
2. Run v2.0 essential regressions against the installed skill where paths allow.
3. Run v1.9/v1.8 affected regressions.
4. Run `portable_smoke_test.py --profile core`.
5. Run Scientific Workbench with the installed skill path and execute the dual
   quality gate or its installed-skill equivalent.
6. Confirm packaged/headless smoke still discovers artifacts, summaries,
   manifests, command sidecars, and workflow summaries.

## Rollback rule

If post-sync validation fails, do not declare v2.0 installed. Do not use
`git reset --hard`. Identify the exact file or step that failed. If the problem
is sync-only, restore only the affected installed files from the validated
editable tree. If the editable tree is wrong, stop and reopen the release
candidate phase.

## Accepted warnings

Warnings are acceptable only when they are explicit and useful:

- ambiguous administrative documents;
- incomplete WCS in FITS/RGB fixtures;
- suspicious sensor or physical ranges;
- ambiguous dates in time series.

`BLOCKED_CONTROLADO` is acceptable for unsafe interactive notebook execution,
missing optional backends, or missing GUI prerequisites.

## Not accepted

- raw traceback;
- false success;
- misleading artifacts;
- secret leakage;
- original input mutation;
- untyped public artifacts when a typed contract is promised;
- app docs claiming v2.0 installed before post-sync validation.
