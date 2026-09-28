---
name: "scientific-data-maintainer"
description: "Use when maintaining or releasing the scientific-data-analysis skill family: gates, audits, registry validation, smoke tests, and migration regressions. Do not use for normal data analysis."
---

# Scientific Data Maintainer

Use this child skill only for maintenance, release validation, public-surface
checks, regression wrappers, smoke tests, and modular-migration audits in the
scientific-data-analysis skill family.

v2.8 keeps this child as the maintainer/control-plane root. It owns canonical
registries, archived matrices, release regressions, and senior integration
hardening checks. App consumers may read selected metadata from this root but
must not expose maintainer commands as normal user actions.

For normal user analysis, route back to `scientific-data-analysis` or one of the
domain child skills. This skill is intentionally not a general analysis surface.

## Safe Use

- Treat all commands as maintainer-only unless a release prompt says otherwise.
- Do not edit user originals or scientific data.
- Prefer temporary folders for generated outputs.
- Keep historical wrappers in `scientific-data-analysis/scripts/` compatible.
- Use this child as the home for full maintainer script bodies while the mother
  skill keeps stable public paths.
- In v2.5, treat maintainer `scripts/*.py` as thin entrypoints and patch
  same-named `fixtures/*.py` files for implementation changes.

## Common Commands

```bash
python scripts/sync_public_surface_docs.py --check
python scripts/audit_v2_8_family_integrity_regression.py
python scripts/skill_surface_audit.py --skip-hygiene
python scripts/portable_smoke_test.py --profile core --output-dir <temporary-directory>
```

## Current And Historical Gates

`audit_v2_8_family_integrity_regression.py` is the current structural gate. It
validates exact registry cardinality and uniqueness, recursive canonical
resolution, all 61 router metadata rows, owning-root scripts, agent invocation
policy, fail-closed module-map behavior, symlinks, active-path portability, and
registry-helper safety. See `references/v2-8-current-release-gates.md`.

Older `audit_v1_*`, `audit_v2_3_*`, `audit_v2_4_*`, `audit_v2_5_*`, and v2.7
commands remain traceable historical snapshots. A failure caused only by an old
file inventory, compacted prose location, or retired evaluation threshold is not
a current release failure; migrate any still-relevant invariant into v2.8.

This child remains maintainer-only. Coverage summaries and plugin-eval scores
are scoped evidence, not exhaustive coverage or release authority. The
installed production entrypoint remains `scientific-data-analysis`.
