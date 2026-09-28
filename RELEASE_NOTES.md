# Scientific Workbench Release Notes

## v2.0 Integrated Release Candidate

Scientific Workbench is a local-first macOS control center for the installed
`scientific-data-analysis` skill. This release candidate focuses on making real
scientific workflows usable without paid AI APIs, while preserving a path to
cloud providers and Codex when the user explicitly configures them.

v2.0 is the integrated app + skill compatibility line. The skill remains the
deterministic backend; Scientific Workbench owns planning, guided controls, job
state, previews, recovery, optional panels, and product packaging. It is a
compatibility claim proven by the dual gate, not an installed skill-version
label.

### Highlights

- Local Ollama planning/chat with `qwen3:4b-instruct` as the balanced default.
- OpenAI, Grok/xAI, and Gemini remain optional API-key providers.
- Chat, Workflow, Auto, and Codex modes in one user-facing surface.
- Editable workflow plans with enable/disable, dry run, run enabled, and resume.
- Recovery card for failed workflows with Open Job, Dry Run, Run Remaining,
  Open Summary, and Support Bundle actions.
- Redacted support bundles for diagnostics.
- Export/import configuration without exporting or overwriting API keys.
- Schema-2 job and workflow persistence with explicit v1 migration, partial
  record recovery, duplicate-ID normalization, and preserved original state.
- Guided UI coverage for all 55 public capabilities, including reviewed sky
  crossmatch mapping and isolated legacy-report evidence population.
- Bundled user guide reachable from Settings and the macOS Help menu.
- Polished app name, icon, Finder/Dock bundle metadata, and packaged app smoke.

### M101 Trust-Boundary Hardening (Validated, Not Packaged)

The current source tree contains the implemented M101 hardening listed below.
The release/readiness smokes, full quality gate with copied-input DOCUS, dual
app + skill gate, and installed-skill checks passed. These changes are not a
packaged release, and no M101 archive or manifest has been created.

- Cloud requests to OpenAI, Grok/xAI, and Gemini pause before first network use
  of prompt/local context and show a native consent sheet with provider, model,
  purpose, privacy mode, and exact data categories. Consent is session-only and
  category-scoped; cancelling sends nothing and leaves the draft intact.
- Attachment privacy now also governs workflow recovery. `none` excludes local
  names, paths, previews, and logs; `filenamesOnly` excludes content and absolute
  paths; `previews` withholds absolute local paths. Ollama and deterministic
  planning do not enter the cloud-consent flow.
- Cloud HTTP uses an ephemeral session that rejects redirects. Ollama endpoints
  are validated before preview access and restricted to HTTP(S) loopback hosts.
  Confirmation re-fingerprints the exact request; changed data requires a fresh
  review instead of being sent under stale approval.
- Contractual `ERROR` results can no longer become successful jobs solely
  because the process exited with code 0. Duplicate modular capabilities must
  agree in metadata and registry fingerprint; absent optional modules degrade
  explicitly without discarding the mother catalog, while broken installed
  registries remain errors.
- Capabilities, Codex, and Ollama model pulls share restricted process
  environments, timeout/cancellation handling, `/dev/null` stdin where needed,
  and owned process-group termination. Each output stream has a 256 MiB
  temporary limit and 4 MiB retained head/tail diagnostic budget with explicit
  truncation metadata.
- New filesystem containment canonicalizes paths and rejects protected roots,
  output/input overlap, run folders outside approved roots, unsafe raw path
  arguments, transcript overwrites, and symlink-bearing legacy report projects.
  Explicit workflow placeholders authorize only their recorded derived runs.
- Quoted argument parsing now preserves literal backslashes in filenames.
  DOCUS requires exact planned/executed PDF and HTML intake, rejects overlapping
  or reused benchmark roots, neutralizes external symlinks only in its safe copy,
  and verifies content plus metadata/ACL/xattrs even after an early app failure.
- Legacy IRAF/fxcor runs use an ASCII/no-space/length-bounded workspace, seed a
  private `rvfxcor.par` from the installed IRAF tree, and treat native IRAF
  `ERROR`/segmentation markers or header-only results as controlled failure.
- ADR 0003 separates app `1.0.0`, integrated release `2.0`, and the declared
  skill compatibility axis.
  Schema-2 release manifests are build-specific, tied to a clean Git revision,
  non-overwriting, and explicit about environment and which gates actually ran.

### Scientific Workflow Coverage

- Readiness and environment checks.
- CSV/table profiling.
- FITS inspection.
- Document intake.
- Mixed research bundle routing.
- DOCUS/UCM legacy spectroscopy workflow planning and optional full benchmark.

### Safety

- Original inputs are treated as read-only.
- Outputs write under `~/Documents/Scientific Workbench Runs` by default.
- Support bundles, workflow summaries, transcripts, and job records are redacted
  against configured API secrets.
- Local-first mode avoids paid cloud API usage.
- Cloud disclosure is explicit and just-in-time; local attachment and recovery
  context is reduced according to the selected privacy mode before transmission.
- Run/output containment prevents original inputs and protected local locations
  from becoming capability output destinations.

### Quality Gate

The release candidate is ready only when its exact source revision is validated
by the following evidence set. This list is the required gate contract, not a
substitute for the gate outputs themselves:

- Swift unit/integration tests.
- Headless planner smoke matrix.
- Golden transcript regression gate.
- Headless capability E2E matrix.
- Mixed non-DOCUS benchmark.
- Secret redaction gate.
- Settings surface checks for local AI, optional cloud keys, connection tests,
  configuration, and support bundle actions.
- Fresh first-run packaged smoke with isolated preferences.
- Packaged app bundle verification.
- Finder/Dock packaged smoke.
- Packaged real-run smoke with auto-run, artifacts, manifests, workflow summary,
  and unchanged inputs.
- Packaged UI smoke.
- Dual skill + app Phase 8 gate through `../run_v2_0_dual_gate.sh`, covering
  ten workflow families with zero FAIL/ROTO and unchanged originals.
- Release package manifest verification.
- Release archive extraction and packaged app verification.
- Final milestone gate with `RUN_DOCUS_BENCHMARK=1 DOCUS_BENCHMARK_MODE=full`
  against a safe copy of DOCUS, requiring the 16-step workflow and indexed PDF
  output before closure.

Run:

```bash
./script/run_quality_gate.sh
```

For the heavier copied-input DOCUS proof:

```bash
RUN_DOCUS_BENCHMARK=1 DOCUS_BENCHMARK_MODE=full ./script/run_quality_gate.sh
```

M101 verification completed with 266 Swift Testing tests, the normal and
post-fix DOCUS-enabled quality gates, and two post-fix copied-input DOCUS runs
with 16/16 jobs, 4/4 expected documents, an indexed PDF, identical original
fingerprints, and empty metadata differences. Earlier same-day reports that
completed 16 jobs but ingested only 3/4 documents remain unchanged as historical
evidence and are not closure evidence. The workspace-skill dual gate decision is
`LISTO_PARA_FASE_9`. Separate public-surface, senior-integration, and ten-family
E2E checks passed against the current installed skill family with originals
unchanged. Its broad documentation and registry labels remain on mixed
historical releases, so this evidence does not claim that `v2.8` is installed.
This is validation evidence, not release packaging.

### Packaging

Local package. Keep the app version numeric; use the build number or notes to
mark release-candidate status.

```bash
./script/package_release.sh --local --version 1.0.0 --build 1
```

`final-100` is preserved as a historical build identifier and must not be
reused. Future packaging requires a new unique build identifier, committed clean
source, completed gates, and explicit authorization. No M101 package exists.

The package manifest records the bundle identifier, minimum macOS version,
archive size, SHA-256, signing/notarization state, and whether the quality gate
was run during packaging. New packages use schema 2, record the app/integrated/
skill version axes, source commit and branch, environment metadata, validation
flags, and the complete installed registry-resolution chain, and refuses
dirty-tree or overwrite-prone packaging.

Signed/notarized public package requires Apple Developer ID credentials. See
`RELEASE_CHECKLIST.md`.

### Known Limits

- Public distribution still requires Developer ID signing and notarization.
- Local LLM quality depends on installed Ollama model size and laptop resources.
- Cloud providers require separately provisioned credentials/quota and may incur
  cost; core functionality does not depend on them.
- No M101 package exists. Packaging requires a clean committed source revision,
  a new unique build identifier, and explicit authorization.
- Process-group cancellation cannot contain a child that deliberately creates a
  new session; attached code execution is not an OS sandbox.
- DOCUS is a benchmark and reference workflow, not the only supported scenario.
- Optional STILTS/TOPCAT, APT, Keynote, TEAREDUCE, IRAF, and iSTARMOD routes may
  block cleanly when their backend or GUI prerequisites are absent.
- Registry stubs retain mixed historical release labels. Manifest
  `skill_release` is a declared compatibility axis; the complete registry chain
  and SHA-256 evidence bind the content actually packaged against.
- The workspace/release pipeline declares skill compatibility `2.8`, but the
  installed family was not mechanically promoted as part of M101. Before a
  future package declares `skill_release=2.8`, review or synchronize the exact
  installed family deliberately and rerun its gates plus the dual gate against
  that installed root.
