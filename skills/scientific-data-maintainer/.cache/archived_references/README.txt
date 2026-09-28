SCIENTIFIC-DATA-MAINTAINER SKILL
v2.5 maintainer budget-deferral child for scientific-data-analysis

Purpose
- Maintainer-only child for the scientific-data-analysis skill family.
- Use it for release gates, public-surface validation, smoke tests, migration regressions, archived historical bodies, and plugin-eval follow-up.
- Do not use it as a normal data-analysis surface; route normal user work to scientific-data-analysis, scientific-data-astro, scientific-data-documents, or scientific-data-notebooks.
- v2.5 keeps maintainer script paths stable while dispatching heavy bodies from fixtures and archived references.

Safe use
- Work in temporary folders for generated outputs.
- Do not edit user originals or scientific input data.
- Treat scripts/*.py as stable thin entrypoints unless the task is specifically about wrapper compatibility.
- Patch same-named fixtures/*.py files for implementation changes.
- Keep historical mother wrappers in scientific-data-analysis/scripts/ compatible.

Common checks
- python scripts/sync_public_surface_docs.py --check
- python scripts/skill_surface_audit.py --skip-hygiene
- python scripts/portable_smoke_test.py --profile core --output-dir <tmp>
- python scripts/audit_v2_5_budget_deferral_regression.py
- python scripts/audit_v2_4_budget_architecture_regression.py
- python scripts/audit_v2_3_release_candidate_regression.py

Canonical heavy material
- Full historical regression bodies: fixtures/*.py
- Archived ownership matrix: fixtures/archived_references/v2-3-module-ownership-matrix.json
- Active ownership matrix stub: references/v2-3-module-ownership-matrix.json
- Normal public entrypoint: scientific-data-analysis
