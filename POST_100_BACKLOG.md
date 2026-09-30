# Scientific Workbench Post-100 Backlog

This file records the backlog after completion of the original base
pathway. `ROADMAP.md` remains the historical pathway record; new work must not be
hidden by rewriting completed percentages.

The source repository is now public. M101–M105 below record the earlier
development and publication pathway, including dated evidence and unfinished
independent usability acceptance. The current post-publication work is tracked
in the [product improvement roadmap](docs/PRODUCT_IMPROVEMENT_ROADMAP.md) and
GitHub Issues; this historical record is not a live release-status dashboard.

## Historical Milestone: M101 — Trust Boundaries And Release Evidence

### Contract integrity

- [x] Treat every contractual failure status, including legacy `error`, as a
  failed job even when a process exits with code 0.
- [x] Reject divergent duplicate capability metadata and incompatible registry
  fingerprints across modular registries.
- [x] Preserve a usable mother-skill catalog when an optional module is absent,
  while surfacing the degraded state explicitly.
- [x] Verify capability ownership, including shared and maintainer-only entries,
  and reject ambiguous ownership.

### External execution boundary

- [x] Apply filtered environments, timeout, cancellation, and process-tree
  termination consistently to capabilities, Codex, and Ollama setup work.
- [x] Prevent stdout/stderr pipe deadlocks by redirecting running-process output
  to temporary files.
- [x] Bound final stdout/stderr retention: enforce a 256 MiB temporary cap per
  stream and retain at most 4 MiB head/tail with explicit truncation metadata.
- [x] Make every run directory collision-resistant.
- [x] Reject output destinations that overlap original inputs or sensitive
  locations, including unsafe destinations introduced through raw arguments.

### Cloud privacy boundary

- [x] Show the selected cloud provider, model, purpose, privacy mode, and exact
  data categories before sending.
- [x] Require session-only, category-scoped just-in-time consent for cloud
  requests with prompt or local context; cancellation sends nothing.
- [x] Apply attachment privacy modes to recovery context as well as attachments,
  with a second filter at the final cloud payload boundary.
- [x] Avoid sending automatically gathered absolute local paths to cloud
  providers in attachment, recovery, capability, and router-plan context.
- [x] Keep Ollama and deterministic planning free of cloud-consent prompts.

### Release truth

- [x] Define app, integrated-release, and skill version axes in ADR 0003.
- [x] Design build-specific schema-2 manifests tied to a clean Git commit.
- [x] Revalidate all release scripts after the implementation changes settle.
- [x] Run the normal quality gate.
- [x] Run the dual app + skill gate.
- [x] Run the copied-input DOCUS full gate only for milestone closure.
- [x] Record current evidence without rewriting historical manifests or reports.

### Current verification status

M101 passed 266 Swift Testing tests; release-script contract smokes/readiness;
the normal and DOCUS-enabled quality gates; the dual app + skill gate with
`FAIL=0`, `ROTO=0`, unchanged originals, and decision
`LISTO_PARA_FASE_9`; and installed-skill public-surface, senior-integration, and
ten-family E2E validation. The two post-fix copied-input DOCUS proofs completed
16/16 jobs, ingested 4/4 expected documents, indexed a PDF, confirmed identical
content fingerprints, and produced empty metadata/ACL/xattr differences. Earlier
same-day 3/4 intake reports remain unchanged as historical, non-closure evidence.
Evidence is under
`~/Documents/ScientificWorkbenchRuns/DOCUSBenchmarks/` and the controlled skill
`tmp/` gate directories. No M101 package was created, no historical manifest or
benchmark report was rewritten, and `$HOME/Desktop/DOCUS` remained
unchanged.

The dual gate used the reviewed `skill_work` family for the declared `v2.8`
compatibility line. Installed-skill checks used the current installed roots,
whose broad documentation and registries retain mixed historical labels; this
is not a claim that `v2.8` is installed. A deliberate installed-family review or
promotion, followed by installed and dual gates against that exact root, is a
precondition for any future package declaring `skill_release=2.8`.

## Later Milestones

### M102 — Guided Scientific Coverage

- [x] Inventory user-facing capabilities without safe guided builders: 55
  visible capabilities and 55 reviewed guided routes.
- [x] Add conservative guided support only after reviewing each current CLI
  contract; keep arbitrary SQL, OCR, notebook execution, LaTeX compilation,
  external probes and overwrite flags out of defaults.
- [x] Keep optional and legacy dependencies non-blocking for the core app and
  retain their explicit confirmation requirements.
- [x] Add reviewed forms for `catalog_workbench.crossmatch-sky` and
  `legacy_spectroscopy_report_builder.populate`, with synthetic E2E cases and
  unchanged-input fingerprints in `script/run_m102_guided_smoke.sh`.

The current inventory, reviewed defaults and closure criteria are recorded in
[`docs/M102_GUIDED_COVERAGE.en.md`](docs/M102_GUIDED_COVERAGE.en.md).

### M103 — Persistence Evolution

- [x] Define schema-2 migrations for persisted agent plans and job records,
  retaining explicit compatibility with schema 1 and rejecting future schemas.
- [x] Preserve the exact original before rewriting, quarantine unreadable state,
  and recover valid records from partially corrupt collections.
- [x] Remove duplicate job, artifact, plan-step and execution identifiers before
  they reach SwiftUI or dictionary construction.

The format contract, conservative conflict rules and recovery evidence are
recorded in [`docs/M103_PERSISTENCE_EVOLUTION.en.md`](docs/M103_PERSISTENCE_EVOLUTION.en.md).

### M104 — Architecture And UX Polish

- [x] Extract provider connection testing, failure mapping, and message redaction
  from `WorkbenchStore` into a focused service.
- [x] Invalidate session connection evidence when credentials, models, or local
  endpoints change; deliberately start every launch at `unknown`.
- [x] Expand navigation/UI accessibility coverage and navigate all seven primary
  destinations by accessibility identifier in the packaged smoke.
- [x] Add actionable Jobs/Results empty states and explicit cancellation labels.
- [x] Record the Gemini API-key-only boundary and the prerequisites for any
  future OAuth implementation.
- [ ] Complete and document a packaged-app usability session with a person other
  than the author.

Implementation decisions, automated evidence, and the external-session protocol
are recorded in
[`docs/M104_ARCHITECTURE_AND_UX.md`](docs/M104_ARCHITECTURE_AND_UX.md).

### M105 — Publication

The source-publication checkpoint was completed in September 2026. The
repository is public as source; this did not create a signed or notarized app
release. Its completed source-publication scope was:

- [x] Choose a new public repository while retaining the prior private record.
- [x] Add a README and review the PolyForm Noncommercial license and notices.
- [x] Retain English public documentation, including source for generated guides;
  run the language, local-path, and link audit without deleting private history.
- [x] Review Git identity, ignore rules, secrets, staging, and the exact source
  snapshot before the authorized push.

Later product, usability, and binary-release work is separate; see the
[current plan](docs/PRODUCT_IMPROVEMENT_ROADMAP.md) and
[dated readiness record](docs/PUBLIC_READINESS.md).

## Closure Evidence

M101 implementation and validation are complete. The reproducible closure
command set is:

```bash
./script/run_swift_tests.sh
./script/check_release_readiness.sh
./script/run_quality_gate.sh
APP_ROOT="$PWD" "${DUAL_GATE_SCRIPT:?Set the reviewed external dual-gate script path}"
RUN_DOCUS_BENCHMARK=1 DOCUS_BENCHMARK_MODE=full ./script/run_quality_gate.sh
```

The dual gate belongs to the private integration workspace and is not included
in the public source checkout. Select its reviewed path and exact skill family
explicitly; preserve earlier outputs as described in the
[release checklist](RELEASE_CHECKLIST.md).

The DOCUS commands must continue to use copied inputs. The original tree at
`$HOME/Desktop/DOCUS` is read-only evidence and must never be modified.
