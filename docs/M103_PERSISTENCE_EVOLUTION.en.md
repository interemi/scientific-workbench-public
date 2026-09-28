# M103: persistence evolution and recovery

English publication edition of the private record
`docs/M103_PERSISTENCE_EVOLUTION.md` at commit
`457ca65`. Original SHA-256:
`ee46e340f20a2d415a828926a0b70f56af073c637a9f3d4aab983520f03083ae`.
The Spanish original is preserved privately. The results below remain dated
evidence, not a new validation run.

Recorded status: completed in the local `codex/public-readiness-foundation`
tree on 2026-09-21. This does not replace the final commit's quality gate or
imply a release or push.

## Scope

Scientific Workbench stores user state beneath the output root, separate from
original scientific inputs:

| State | Path | Written schema |
| --- | --- | --- |
| Job history | `.scientificworkbench/jobs.json` | 2 |
| Active plan and checkpoints | `.scientificworkbench/agent_state.json` | 2 |
| Manually exported plan | `.scientificworkbench/plans/*.json` | 2 |

All three formats accept schema 1 through an explicit migration. Unknown future
schemas are rejected and left unchanged; the app does not interpret or downgrade
them.

## Non-destructive recovery

Before rewriting v1, partial, or corrupt state, the app copies its original
bytes into `.scientificworkbench/recovery/`. Only after preserving that copy
does it atomically write v2. Recovery copies are not automatically deleted or
overwritten and can be opened from Jobs.

The loader follows these rules:

1. Read only regular files, never symlinks, and limit automatic recovery to
   128 MiB.
2. Decode each `jobs.json` job separately, retaining valid jobs and dropping
   only unreadable records.
3. Resolve duplicate job IDs using the record with the newest time evidence.
   Within each job, remove duplicate artifact and next-action IDs.
4. In `agent_state.json`, remove duplicate steps before building dictionaries,
   discard orphaned/incompatible executions, and retain one execution per step.
   Ties favor conservative state to avoid claiming completion without evidence.
5. Restore jobs/steps previously `queued` or `running` as `cancelled`.
   They never resume automatically.
6. For wholly unreadable JSON, preserve the exact copy and start empty v2 state.
   If preservation fails or the output root is not approved, do not rewrite.
7. Imported plans never autoexecute. Normalize v1 in memory, remove duplicate
   steps, and preserve the selected source file unchanged.

A visible notification distinguishes recovery from an ordinary error and
shows the preserved copy's location. Copies may contain local paths, arguments,
and logs; they are private user state and must not enter Git or a release.

## Recorded evidence

Synthetic-state tests cover:

- v1-to-v2 migration of history and active plans;
- partial recovery with an invalid JSON record;
- duplicate job, artifact, next-action, step, and execution IDs;
- deterministic selection of the latest execution;
- recovery of wholly unreadable documents;
- byte-exact equality between originals and preserved copies;
- rejection of future schemas without mutation; and
- v1 exported-plan migration without changing the imported file.

The complete Swift suite passed 292/292 tests after these cases were added.
The same tree's quality gate passed without DOCUS on 2026-09-21, including E2E,
mixed benchmark, secret redaction, first-run, bundle verification, Finder/Dock,
packaged real execution, and UI smoke. DOCUS was unnecessary for validating
migration of isolated synthetic state.
