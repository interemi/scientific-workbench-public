# v2.8 Family Integrity Hardening

## Purpose

v2.8 defines a current, machine-verifiable integrity boundary for the modular
scientific-data skill family and its ScientificWorkbench integration. It does
not revive obsolete whole-tree snapshots or treat an evaluator score as proof
that runtime or scientific contracts are correct.

The mother remains the compact user router. Astronomy, documents, and notebooks
remain domain execution roots. Maintainer owns canonical registry/map data and
release gates, and must not appear as a normal analysis action.

## Current Structural Gate

Run from either the mother or maintainer root:

```bash
python scripts/audit_v2_8_family_integrity_regression.py
```

The gate requires:

- valid frontmatter and explicit invocation policy for all five skills;
- recursive, cycle-safe, depth-bounded, family-confined registry resolution;
- exactly 61 unique registry IDs with one canonical fingerprint;
- exact registry, module-map, router, owning-root, and metadata parity;
- fail-closed routing when canonical metadata is missing or invalid;
- the six maintainer-only IDs remaining outside ordinary user exposure;
- identical shared contract and path-safety helpers across all five roots;
- atomic JSON emitters that preserve existing symlink and hardlink targets;
- exact, symlink, hardlink, protected-tree, output-tree, and output/output
  collision checks, with bounded directory scans failing closed;
- strict JSON, redacted secrets, preserved warning severity, and complete
  app-facing blocked/failure envelopes;
- no broken symlinks, active hard-coded user paths, or generated residue.

## Notebook Execution Boundary

Notebook execution is arbitrary-code execution. Public notebook executors are
blocked by default and require the explicit `--trust-notebook-code` flag after
human review. ScientificWorkbench adds that flag only after its confirmation
flow. This confirmation is not an operating-system sandbox: trusted notebook
code can still open network connections or write absolute paths if the host
process permits it.

## Output/Input Collision Boundary

Public wrappers preflight known inputs, inferred inputs, fixed generated
artifacts, output directories, auxiliary summaries/manifests/reports/logs, and
selected environment/PATH dependencies before the tool body or an emitter can
run. Failure emitters use stdout-only controlled envelopes when a requested
control artifact is itself unsafe.

The final independent replay used a byte-stable snapshot of 947 Python,
registry, and module-map files and passed 61/61 mutation cases:

- 41 public cases: astro 28, documents 5, notebooks 6, mother 2;
- 20 maintainer cases: five tools through both owner and mother entrypoints,
  each with exact aliases and hardlinks.

Every case required return code 2, one strict JSON object on stdout, empty
stderr, `status=blocked`, `app_status=BLOCKED_CONTROLADO`, `artifacts={}`,
no traceback, identical trees before/after, and unchanged input SHA-256 hashes.

This is strong regression evidence, not a claim that every possible option
combination of every script has been exhaustively enumerated. Direct invocation
of an internal fixture bypasses the public-wrapper boundary, and path checks
remain subject to the usual check/use race if another process changes the
filesystem concurrently.

## Scientific Corrections

- IRAF MULTISPEC dispersion types 0 and 1 follow the documented linear and
  log-linear laws; unsupported nonlinear type 2 is blocked rather than guessed.
- FITS table columns retain relevant units and image/RGB products preserve
  channel metadata and WCS where valid.
- Experimental profile extraction is labelled honestly and is not described as
  a complete Horne implementation.
- CCD reduction avoids implicit crops; dark scaling, photometric covariance,
  RV/SB2 domain checks, and Li I equivalent-width windows have targeted tests.
- Non-finite values and scientifically material warnings cannot silently become
  successful app states.

## Validation Evidence

The editable and installed families each passed 118/118 Python tests:

- mother 14;
- astro 31;
- documents 36;
- notebooks 27;
- maintainer 10.

Both editable and installed trees passed public-surface sync check, v2.8 family
integrity, v2.7 senior-integration compatibility, surface hygiene, and portable
core smoke. ScientificWorkbench passed 267/267 Swift tests, the five-scenario
executing E2E capability matrix, and the six-scenario planning smoke matrix,
including CSV/table, document, notebook, mixed package, and FITS routes. A
sanitized STILTS preflight returned the expected nonzero
`BLOCKED_CONTROLADO`/`missing_optional_backend` envelope without artifacts.

## Validation Sequence

Use explicit temporary output directories and the intended scientific Python
environment:

```bash
python -m unittest discover -s tests -p 'test_*.py'
python scripts/sync_public_surface_docs.py --check
python scripts/audit_v2_8_family_integrity_regression.py
python scripts/audit_v2_7_senior_integration_regression.py
python scripts/skill_surface_audit.py --root ../scientific-data-analysis
python scripts/portable_smoke_test.py --profile core --output-dir <temporary-directory>

cd ScientificWorkbench
./script/run_swift_tests.sh
KEEP_E2E_MATRIX=1 ./script/run_e2e_capability_matrix.sh
KEEP_SMOKE_MATRIX=1 ./script/run_smoke_matrix.sh
```

Any `FAIL` or `ROTO` blocks release. Optional backend absence may produce
`BLOCKED_CONTROLADO`; that is an honest unavailable route, not a false success
or contract failure.

## Plugin-eval Snapshot

With plugin-eval 0.1.2, the final editable snapshot scores:

- mother: 91/B (deferred budget, long Python lines);
- astro: 87/B (deferred budget, aggregate complexity, long Python lines);
- documents: 91/B (aggregate complexity, long Python lines);
- notebooks: 91/B (aggregate complexity, long Python lines);
- maintainer: 91/B (deferred budget, aggregate complexity).

There are no evaluator failures. These warnings remain advisory and were not
allowed to expand the frozen v2.8 scope after functional and safety closure.
Ratings never supersede dynamic gates, scientific regressions, or app tests.

## Known Limits

- nonlinear MULTISPEC type 2 remains intentionally unsupported;
- spectral extraction is not a full Horne implementation;
- trusted notebook code is not OS-sandboxed;
- public wrappers are the supported safety entrypoints; internal fixtures are
  implementation details;
- directory hardlink scans are bounded at 100,000 entries and fail closed when
  they cannot prove safety;
- preflight checks cannot eliminate a concurrent filesystem TOCTOU race;
- coverage statements refer to measured tests and smoke scenarios, not an
  exhaustive Cartesian product of scripts, flags, filesystems, and backends.

## Historical Snapshot Boundary

Historical release regressions remain useful for provenance and targeted
investigation. They are not automatically v2.8 blockers when they assert an old
inventory, compacted document location, literal legacy prose, or obsolete
evaluation budget. Move any still-current invariant into the current gate.

The v2.7 TeX and PDF guides remain byte-preserved as historical evidence. The
active human-readable release guide is:

- `references/guia_scientific_data_analysis_v2_8.tex`
- `references/guia_scientific_data_analysis_v2_8.pdf`
