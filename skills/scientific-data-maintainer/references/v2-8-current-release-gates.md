# v2.8 Current Release Gates

The current structural release gate is:

```bash
python scripts/audit_v2_8_family_integrity_regression.py
```

It validates the five-skill frontmatter and agent policies, the exact 61-row
canonical registry, the exact 61-row module map and router parity, owning-root
scripts, maintainer-only exposure, fail-closed routing, symlink integrity,
portable active paths, and registry resolver safety.

Run the portable smoke separately with an explicit temporary output directory:

```bash
python scripts/portable_smoke_test.py --profile core --output-dir <temporary-directory>
```

Historical regression files remain preserved and executable for traceability.
They are snapshot evidence, not current blockers merely because an old file
inventory, documentation location, literal prose check, or evaluation threshold
has changed. Current runtime/contract invariants belong in the v2.8 gate.

Coverage summaries and plugin-eval scores are scoped evidence. Neither is an
authoritative substitute for the current structural gate, portable smoke, and
the relevant ScientificWorkbench tests.
