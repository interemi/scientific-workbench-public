# v2.3 Mother Router Contract

Scientific-data-analysis v2.3 keeps the installed production skill whole while
preparing a modular architecture. The mother skill remains the public entrypoint
and routes work to future child skills by contract, not by moving production
files prematurely.

## Scope

- Preserve historical CLI paths until a wrapper has a regression gate.
- Expose module ownership in router outputs so an app or agent can plan without
  scanning the full repository.
- Keep ScientificWorkbench compatibility explicit: the app can read ownership
  metadata, but v2.3 does not require the app to consume child skills yet.
- Treat optional, legacy, and maintainer routes as gated workflows.

## Non-goals

- No production split of the installed skill before the final v2.3 gates pass.
- No blind rsync of child skill prototypes.
- No hidden behavior change in scientific commands.
- No generalization of domain-specific or legacy routes.

## Router Fields

The router keeps the existing v1.8/v1.9 app-ready envelope and adds the
following fields to recommended capabilities, rejected capabilities, exposure
records, plan steps, and explain responses when a capability is known:

| Field | Meaning |
| --- | --- |
| `owner_module` | Proposed module owner: `mother`, `astro`, `documents`, `notebooks`, `maintainer`, or `shared`. |
| `child_skill_path` | Future child skill name or the mother skill when the route remains local. |
| `delegation_mode` | Routing state used by the mother router. |
| `wrapper_status` | Whether the historical path is active or a wrapper is required before migration. |

The authoritative compact map is
`references/v2-3-mother-router-module-map.json`, derived from
`references/v2-3-module-ownership-matrix.json`.

## Routing States

| State | Contract |
| --- | --- |
| `direct` | The mother skill owns the route and can keep invoking the historical command. |
| `delegated` | The route belongs to a child module; the historical wrapper remains active until migration is verified. |
| `multi_module_plan` | The route composes shared behavior across modules and should be planned by the mother. |
| `blocked_optional` | Optional backend route; preflight first and block cleanly if unavailable. |
| `maintainer_only` | Release or maintenance route; never expose as a normal user action. |

## Compatibility

The added fields are informational and additive. Existing consumers may ignore
them safely. A v2.3-aware consumer should prefer these fields over filename
heuristics when deciding whether a route is normal, expert, optional, legacy, or
maintenance-only.

## App-facing Rules

- `direct` and selected `delegated` normal routes can appear in ordinary app
  workflows.
- `blocked_optional` routes must show preflight and next actions before any
  execution attempt.
- `maintainer_only` routes belong to a maintenance surface, not to ordinary
  analysis.
- `wrapper_required` does not mean broken; it means the historical CLI path
  remains the safe production entrypoint until the child module has a wrapper
  smoke.

## Closure Criteria

- The module map has one row per public capability in registry order.
- Router outputs include module metadata for recommended routes and exposure
  rejections.
- Missing paths, empty folders, optional routes, and maintainer routes retain
  clean app-facing statuses.
- The v2.3 router regression passes without requiring optional backends.
