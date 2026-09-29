# Scientific Workbench Roadmap

This is the historical base pathway. Its completion percentages describe that
pathway, not the current product or release status. The [post-100 record](POST_100_BACKLOG.md)
and [current product improvement roadmap](docs/PRODUCT_IMPROVEMENT_ROADMAP.md)
track later work; [source validation and limits](docs/PUBLIC_READINESS.md) is a
dated evidence snapshot.

This roadmap was the execution pathway for turning Scientific Workbench into a native macOS app for AI-assisted local scientific workflows. The core product question was:

> Can the user open the app, use local AI by default or connect an optional cloud provider, attach a complex folder, ask in natural language, understand the plan, execute safely, and get reproducible results without modifying originals?

## Operating Rules

- Research must produce a concrete app decision, test, or artifact.
- Inputs are read-only by default.
- Outputs are written outside original input folders.
- Provider credentials are stored in Keychain and must never appear in logs, transcripts, stdout, stderr, or artifacts.
- Local-first is the default: the app must remain useful without paid API keys.
- Ollama is the first zero-cost AI provider path; it requires a local server and model, not a provider API key.
- The default local model must fit the user's laptop comfortably. Current recommendation: `qwen3:4b-instruct`, about 2.5 GB on disk, for a 16 GB Apple Silicon Mac. Larger local models are opt-in.
- Use official provider authentication only: API keys today for OpenAI/xAI/Gemini, OAuth where officially supported, and no browser-cookie/session scraping.
- AI plans and explains; local capabilities execute and generate provenance. Local AI should be preferred when it is adequate.
- Codex is a local coding/reporting bridge, not a replacement for deterministic workflow execution.
- DOCUS is a reference benchmark, not the only acceptance test. Every major workflow improvement must also be checked against small synthetic fixtures and at least one non-DOCUS scenario.
- Test coverage must include cheap deterministic fixtures for CSV/table, FITS, document-only, mixed folder, no-input readiness, provider failure, secrets redaction, and workflow recovery/resume. DOCUS-style tests remain regression/benchmark tests for realistic UCM complexity.

## Sprint 0: Stabilization, 1-3 Days

Goal: make the current app navigable, configurable, and verifiable.

Deliverables:
- Sidebar is fully clickable.
- Settings is visible inside the app.
- Ollama works as a local AI provider without an API key.
- OpenAI, Grok/xAI, and Gemini can be connected at the same time as optional paid/cloud providers.
- Codex bridge has timeout, clear errors, and transcript output.
- Build/run works through `script/build_and_run.sh`.
- DOCUS-style smoke test remains reproducible.
- Add `Test AI Connection` for each provider.
- Show provider state: `Connected`, `Missing key`, `Invalid key`, `Model unavailable`, `Quota/rate`, `Network`, and `Timeout`.

Gate:
- `./script/run_swift_tests.sh` passes and executes the full counted Swift Testing target.
- `./script/build_and_run.sh --verify` passes.
- Manual clicks work for Chat, Dashboard, Settings, Jobs, Results, and Maintenance.
- No original input file is modified.
- The app can make a successful real request with the selected local/provider connection when available.
- Keys do not appear in logs, transcripts, stdout/stderr, or artifacts.

## Sprint 1: Zero-Cost Local AI And Optional Cloud, Week 1

Goal: prove that the app can use AI without forcing paid API keys, while still supporting user-provided cloud connections safely.

Deliverables:
- Add Ollama provider:
  - no API key
  - configurable local endpoint
  - configurable model
  - connection test through `/api/chat`
  - balanced default model: `qwen3:4b-instruct`
- Add Local AI Setup onboarding:
  - open official Ollama download page
  - open `/Applications/Ollama.app` when present
  - detect local server and installed models
  - download the selected local model through `ollama pull`
  - test local AI from the same Settings screen
- Store provider keys in Keychain:
  - OpenAI
  - Grok/xAI
  - Gemini
- Optionally read environment variables:
  - `OPENAI_API_KEY`
  - `XAI_API_KEY`
  - `GEMINI_API_KEY`
  - `GOOGLE_API_KEY`
- Add connection test from Settings for each provider.
- Add minimal chat test: provider returns a tiny known response.
- Add minimal planner test: provider returns valid workflow JSON.
- Add clear fallback to local planner or Codex if provider fails.
- Add key redaction for logs, job records, transcripts, and errors.
- Add mocked provider tests so CI does not spend tokens. Done for request construction, provider response parsing, connection-test rejection, mocked planner JSON decoding, cloud-planner fallback, HTTP error taxonomy, and transport failure taxonomy.

Critical Gate: Successfully Using AI Without Forcing Paid Keys
- User can select Ollama in Settings.
- User clicks `Test AI Connection`.
- App confirms a real local call when Ollama is running.
- Chat mode can use Ollama.
- Workflow planning can use Ollama.
- User can still connect OpenAI, Grok/xAI, or Gemini later if desired.
- Local capability execution still works after AI planning.
- No key leakage occurs for optional cloud providers.

Critical Gate: Successfully Using The User's Optional Cloud AI Connection
- User connects a cloud provider in Settings.
- User clicks `Test AI Connection`.
- App confirms a real provider call.
- Chat mode uses the selected connection.
- Workflow planning uses the selected connection.
- Local capability execution still works after AI planning.
- No key leakage occurs.

Authentication Path:
- Ollama uses the official local HTTP API and no API key by default.
- OpenAI API and xAI/Grok API use official API-key authentication at this stage.
- Gemini starts with API-key authentication and can add official Google OAuth once the connection abstraction is stable.
- The app may support a local Codex session through official local tooling, but it must not automate consumer web login or copy browser cookies.

## Sprint 2: Professional Architecture, Weeks 1-2

Goal: make the app maintainable and understandable.

Deliverables:
- Separate responsibilities:
  - UI
  - Store/state
  - Agent/planning
  - AI providers
  - Runner
  - Artifacts
  - Security
- Maintain:
  - `ROADMAP.md`
  - `ARCHITECTURE.md`
  - `DECISIONS/`
- Define the internal workflow model:
  - plan
  - step
  - input
  - output
  - status
  - error
  - retry
- Make jobs persistent or exportable. Done for persisted job history at `<output root>/.scientificworkbench/jobs.json`, with reload/reveal/clear controls in Jobs.
- Keep user-readable and developer-readable logs.
- Write manifest for every run.

Gate:
- Every job leaves manifest, summary, stdout/stderr, and artifacts.
- The app can explain what it will do before doing it.
- Errors are understandable to a non-developer.

## Sprint 3: ChatGPT/Codex-Like UX, Weeks 2-3

Goal: make usage feel like ask, attach, review, run.

Deliverables:
- Improve composer:
  - attachments
  - provider selector
  - mode selector
  - auto-run
  - stop/cancel. Done for local capability runs and agent workflows.
- Add editable plan view before execution.
- Add clear action buttons:
  - Run
  - Cancel
  - Open Results
  - Reveal Folder
- Improve error messages.
  - done for job detail recovery advice: failed, blocked, cancelled, missing-input, timeout, permission, and structured blocked-status runs now surface next-step guidance.
- Add empty/loading/running states.
- Make inspector useful and remove duplication.

Research:
- Apple Human Interface Guidelines.
- Human-AI interaction guidelines.
- ChatGPT/Codex interaction patterns.

Gate:
- A non-technical user can attach a folder and understand what happened.
- The app never appears frozen.
- The user can cancel long local capability/workflow operations.

## Sprint 4: Agentic Orchestration, Weeks 3-5

Goal: make the agent plan and execute multiple capabilities robustly.

Deliverables:
- Multi-provider planner:
  - Ollama
  - OpenAI
  - Grok/xAI
  - Gemini
- Local planner for known workflows.
- Capability selection by:
  - extension
  - folder shape
  - prompt
  - history
- Robust chaining:
  - step output can feed later steps.
- Controlled retries.
  - individual jobs can be retried with the same input/raw-argument request and `retryOfJobID` traceability.
- Workflow resume.
  - workflow steps keep per-step execution state; after a blocked/failed step, the user can edit or disable the bad step and run only the remaining work from the last successful checkpoint.
  - active plan and per-step checkpoints persist under `<output root>/.scientificworkbench/agent_state.json`, so recovery survives app relaunches.
- Actionable failure recovery.
  - job details explain likely recovery actions before a user retries or changes inputs.
  - Chat receives structured workflow recovery context so local AI can explain where to continue and what to inspect without guessing.
- Estimated time/cost per plan.
  - done as conservative per-step runtime ranges and provider cost notes in the editable plan card.
- Dry run.
  - implemented for editable plans: builds commands and resolves placeholders without executing local processes.
- Editable and exportable plans.
  - editable plans can be exported as redacted JSON under `<output root>/.scientificworkbench/plans/`.
  - exported plans can be imported back for review/rerun; missing capabilities are disabled and existing inputs are restored conservatively.

Research:
- Multi-tool orchestration.
- MCP workflow patterns.
- Safe tool use.
- Human-in-the-loop checkpoints.

Gate:
- DOCUS completes end to end.
- Mixed PDF/FITS/CSV folders route correctly.
- User can review and modify plan before running.
- Capability failures do not silently destroy the workflow.

## Sprint 5: Safety And Trust, Weeks 5-6

Goal: make local data and secrets handling trustworthy.

Deliverables:
- Read-only inputs by default.
- Output folders are separate from inputs.
- Confirmation for risky write actions.
- Sensitive path detector.
- Summary of:
  - what was read
  - what was written
  - what was not touched
  - implemented as a Markdown workflow summary after agent workflow runs
- Redaction for:
  - API keys
  - tokens
  - sensitive paths when requested
- Clear AI data policy:
  - what stays local with Ollama/local planning/Codex
  - what goes to cloud providers
  - what remains local
- Local-only mode.
- Cloud-planning-only mode.

Research:
- Safe tool use for LLM agents.
- Data provenance.
- macOS app security.
- Keychain and secrets handling.

Gate:
- Automated test confirms original inputs are not modified.
- Keys never appear in logs.
- App clearly distinguishes local execution from cloud AI calls.
- User knows when content is sent to OpenAI, Grok, or Gemini.

## Sprint 6: Real Scientific Workflows, Weeks 6-8

Goal: produce useful scientific work, not just technical execution.

Deliverables:
- Workflow presets:
  - spectra
  - FITS
  - CSV/tables
  - documents
  - notebooks
  - reports
- Report templates.
- Result validators.
- Reference comparison.
- Export:
  - Markdown
  - PDF
  - LaTeX
- Reproducible rerun.
- AI-generated final summaries from artifacts, not raw recursive scans.

Research:
- Scientific workflow systems.
- Reproducibility.
- Astronomy data tooling.
- Report generation.

Gate:
- DOCUS produces a useful report.
- A second similar dataset runs without code changes.
- Results include limitations and quality flags.
- Artifacts are understandable and citable.

## Sprint 7: Professional Testing, Weeks 8-10

Goal: replace "it seems to work" with evidence.

Deliverables:
- Unit tests.
- Integration tests.
- Provider tests with mocks.
- Headless end-to-end tests.
  - `script/run_smoke_matrix.sh` runs deterministic headless planner smoke tests with temporary non-DOCUS fixtures.
  - `script/run_golden_transcript_gate.sh` compares sanitized planner transcripts against reviewed golden snapshots for readiness, CSV, document, mixed, and DOCUS-like report-planning cases.
  - `script/run_e2e_capability_matrix.sh` executes real guided capabilities against temporary non-DOCUS readiness, CSV, document, and mixed fixtures, then validates transcripts, run folders, summaries, manifests, artifact indexes, workflow-summary Markdown contracts, and unchanged input fingerprints.
  - `script/run_docus_benchmark.sh` runs an optional copied-input DOCUS benchmark; plan mode validates the real DOCUS planning sequence, progress mode executes until the first blocker and reports it, and full mode requires an indexed PDF deliverable.
- UI smoke tests.
  - `script/run_ui_smoke.sh` launches the packaged app, navigates with real macOS Accessibility events, checks Chat/Settings/Capabilities root-title transitions, and blocks regressions from the removed advanced-controls toggle or stale hardcoded capability counts.
- One-command quality gate.
  - `script/run_quality_gate.sh` runs Swift tests, planner smoke, golden transcripts, capability E2E, mixed benchmark, secret redaction, bundle verification, and packaged UI smoke in sequence.
- Secrets redaction gate.
  - `script/run_secret_redaction_gate.sh` launches headless automation with fake provider credentials in the environment, injects those fake secrets into a prompt, and scans generated transcripts/job outputs for leaks.
- Small dataset fixtures.
- Non-DOCUS scenario matrix:
  - CSV/table-only folder
  - FITS-only folder
  - PDF/document-only folder
  - mixed FITS/CSV/PDF folder
  - no-input readiness
  - failed provider fallback
  - failed workflow resume
- Golden transcripts.
  - reviewed snapshots live under `Tests/Fixtures/GoldenTranscripts/`; update intentionally with `UPDATE_GOLDEN_TRANSCRIPTS=1 script/run_golden_transcript_gate.sh`.
- Regression tests for DOCUS-like workflows.
  - The real DOCUS folder is benchmarked only through a safe copy under a benchmark output folder, never by passing the original folder to execution.
- Navigation tests.
- Settings tests.
- Secrets redaction tests.

Gate:
- One command runs the suite.
- UI changes do not break navigation.
- Provider failures do not break local execution.
- Critical capabilities have fixtures.

Current coverage:
- Planner-only matrix covers routing shape for no-input, CSV, FITS, document, and mixed folders.
- Golden transcript gate snapshots sanitized headless plans, including raw arguments, for no-input readiness, CSV, document, mixed, and DOCUS-like final-report planning.
- Capability E2E matrix covers real execution for no-input readiness, CSV profiling, document intake, copied notebooks, FITS inspection, mixed CSV/document inventory, and controlled missing-STILTS handling.
- Capability E2E matrix validates generated workflow summaries for read-only input evidence, enabled steps, jobs, indexed artifacts, PDF deliverable section, and safety note.
- Capability E2E matrix fingerprints attached inputs before and after execution to prove original fixtures were not modified.
- Mixed research benchmark covers a generated non-DOCUS folder containing FITS, CSV, Markdown notes, and a tiny PDF; it verifies folder-level routing through FITS, table, document, and cross-domain capabilities.
- UI smoke covers packaged-app launch, sidebar navigation to Chat/Settings/Capabilities, removal of the dead advanced-controls toggle, and stale capability-count guards.
- Provider fallback is unit-tested so a failed cloud planner returns a deterministic local plan.
- Provider error taxonomy is unit-tested for invalid keys, quota/rate limits, missing models, provider 5xx outages, network failures, and timeouts without making real provider calls.
- Optional DOCUS benchmark validates the real DOCUS folder shape; protects content and metadata/ACL/xattrs before and after even on early failure; rejects overlapping/reused output roots; neutralizes external symlinks only in the safe copy; requires exact PDF/HTML intake; checks the deterministic 16-step final-report plan; can record the first execution blocker without failing the normal suite; and has full-mode proof that all 16 DOCUS/UCM steps execute, all 4 expected documents are ingested, and an indexed PDF is produced after IRAF/path hardening.
- Secret redaction gate verifies fake provider keys do not appear in generated headless outputs.
- One-command quality gate is available through `script/run_quality_gate.sh`, including golden transcript, mixed research benchmark, and secret-redaction gates; set `RUN_DOCUS_BENCHMARK=1` to include the copied-input DOCUS benchmark.
- DOCUS remains a reference benchmark, not the only acceptance test.

## Sprint 8: Packaging, Polish, Release, Weeks 10-12

Goal: make the app installable, stable, and presentable.

Deliverables:
- Final icon.
- Polished app bundle.
  - `script/verify_app_bundle.sh` checks bundle metadata, executable, icon, bundled user guide, and packaged headless launch.
  - release packages include a verified manifest with bundle metadata, archive size, SHA-256, signing/notarization state, and quality-gate provenance.
  - release archives are extracted and the contained app bundle is verified before a package is accepted.
- Finder and Dock behavior verified.
  - `script/run_finder_dock_smoke.sh` opens the packaged app through LaunchServices, checks bundle id/icon foreground metadata, verifies a single foreground process/window, and confirms the running Dock tile exists.
- First-run onboarding.
  - implemented as a setup checklist shown in Chat when required items are missing, plus Dashboard and Settings readiness views.
  - `script/run_first_run_smoke.sh` verifies an isolated packaged first run exposes setup checklist/recovery state, creates output only under the chosen root, and leaves inputs unchanged.
- Clear Settings.
  - `script/check_settings_surface.sh` protects the Settings surface for paths, setup, local AI, optional cloud keys, connection tests, support bundles, configuration export/import, and Codex settings.
- User documentation.
  - bundled as `Guides/Scientific_Workbench_User_Guide.md` and reachable from Settings and the macOS Help menu.
- Support bundles.
  - Settings, the Workbench menu, and workflow recovery can export redacted diagnostic bundles under `<output root>/.scientificworkbench/support/`.
- Export/import configuration.
  - non-secret configuration JSON can be exported/imported from Settings and the Workbench menu; API keys are never written or overwritten.
- Signing/notarization path if distribution is desired.
  - `script/package_release.sh` supports local zip packaging, Developer ID signing, and optional notarytool submission/stapling.
  - `script/verify_release_manifest.sh` validates local release manifests and archive checksums.
  - `script/verify_release_archive.sh` validates the extracted zip contents and packaged headless launch.
- Release notes.
  - `RELEASE_NOTES.md` records the current release-candidate surface and quality gate.
- Recovery mode for failed setup.
  - Setup Checklist now shows a Setup Recovery panel when required setup items are blocked, with concrete next actions, Settings navigation, recheck, and support-bundle export.
- Real packaged run.
  - `script/run_packaged_real_run_smoke.sh` launches the packaged app with auto-run, executes a CSV workflow without Terminal, verifies jobs/artifacts/manifests/workflow summary, and fingerprints inputs before/after.
- Final pathway closure.
  - historical project records report a copied-input full DOCUS run and
    `final-100` packaging, but the retained artifact set is incomplete under the
    current release-evidence contract; see Base Pathway Status.

Gate:
- App is usable from Finder and Dock.
- Finder/Dock packaged smoke passes.
- First use is guided.
- Fresh first-run smoke passes with isolated preferences.
- Failed setup is actionable without reading terminal logs.
- Keys are configurable.
- Local AI is usable without keys.
- Connection test is visible.
- Settings surface check passes.
- Real run completes without terminal.
- Packaged real-run smoke passes.
- Full DOCUS benchmark passes for the final base-pathway milestone.
- Final release package manifest/archive verification passes.

## Weekly Cadence

- Research: 20%.
- Implementation: 55%.
- Real app testing: 20%.
- Documentation and decisions: 5%.

## Post-100 Work

The former immediate-task list is complete and remains represented by the base
pathway history below. M101–M105 are recorded in `POST_100_BACKLOG.md`;
post-publication work is tracked in `docs/PRODUCT_IMPROVEMENT_ROADMAP.md` so
completed percentages are not rewritten to hide later risk and maintenance
work.

M101 completed its implementation and validation gates on 2026-07-15: contract
integrity, hardened process/filesystem/cloud boundaries, and release evidence
semantics tied to a clean Git commit. It was deliberately not packaged. App,
integrated-release, and skill versioning are defined in
`DECISIONS/0003-versioning-and-release-evidence.md`.

## Base Pathway Status

Base pathway remains recorded as complete at 100%. The historical `final-100`
archive is
`dist/release/1.0.0/Scientific_Workbench_1.0.0_final-100_macOS.zip` with
SHA-256 `983d7cdb67ff636d2cd43ad2974512da55ab1f59ccd32cbde6b9982992defbbf`.
Its build-specific manifest did not survive: the sole schema-1 `manifest.json`
identifies `post-audit-hardening`, not `final-100`. The retained repository
therefore cannot prove the `final-100` quality/DOCUS flags or source revision,
and the historical bundle does not satisfy today's strict bundle verification.
Preserve these artifacts unchanged as historical evidence, not as a current
release candidate. No M101 package has been produced.
