# M104 Architecture And UX Evidence

Date: 2026-09-21
Branch: `codex/public-readiness-foundation`

This is a dated engineering record. Its prospective outside-user acceptance
criterion was revised on 2026-09-30 by the
[research-led acceptance decision](RESEARCH_LED_ACCEPTANCE.md). The historical
test counts and the fact that no outside session occurred remain unchanged.

M104 improves the app structure and the most important navigation and recovery
paths without changing persisted schemas, scientific workflow contracts, or the
read-only treatment of original inputs. This document records what is proved in
the current tree and what still needs an external user session.

## Store decomposition

Provider connection checks are now owned by `AIConnectionService`. The service:

- validates whether a cloud credential is present before any request;
- calls the provider client and maps transport/provider failures to connection
  states;
- formats provider-specific recovery guidance; and
- redacts the active credential and every configured provider secret from
  success and failure messages.

`WorkbenchStore` remains the `MainActor` orchestration and UI-state owner. It
builds an immutable `AIConnectionRequest`, publishes the short-lived testing
state, and applies the service result. Chat and the Settings connection test use
the same error interpretation instead of maintaining two mappings.

This is an incremental boundary, not a claim that the store is fully decomposed.
Workflow planning/execution and persisted-state coordination remain large areas
for later focused extraction.

## Provider state and Gemini authentication decisions

Connection evidence is deliberately session-only. A successful probe is a fact
about one credential, model, endpoint, network state, and point in time. It is
therefore reset to `unknown` when the user edits a credential, model, or local
endpoint, and every app launch starts at `unknown`. Models and endpoints remain
portable preferences; credentials remain in Keychain; connection evidence is
not written to `UserDefaults` or the schema-2 state files.

If configuration changes while a probe is in flight, its result is discarded
instead of marking the new configuration as connected.

Gemini currently uses the official model API with an API key. The interface says
this explicitly. OAuth is deferred until Scientific Workbench has an owned
Google Cloud OAuth client, registered redirect handling, Keychain-backed token
storage and refresh/revocation behavior, consent-screen/privacy documentation,
and integration tests. The app does not present an OAuth control or imply that
OAuth tokens are stored today.

## Accessibility and navigation

The seven primary sidebar destinations have stable accessibility identifiers,
labels, hints, and selected traits. Main toolbar, agent routing, provider
connection, input, job-history, cancellation, and summary controls expose
identifiers or explicit labels where their visual presentation alone was
ambiguous.

The packaged UI smoke no longer clicks sidebar buttons by position. It finds and
clicks every destination by its accessibility identifier, then verifies the
corresponding title:

1. Chat
2. Dashboard
3. Capabilities
4. Jobs
5. Results
6. Maintenance
7. Settings

This catches missing identifiers, controls that cannot be activated through the
macOS accessibility tree, and navigation regressions caused by reordering.

## Empty, error, and cancellation paths

- Empty Jobs explains where runs originate and offers an accessible **Open
  Chat** action.
- Empty Results explains artifact provenance and offers **Open Chat** and
  **Browse Capabilities** actions.
- Job rows expose capability, status, creation time, and selection guidance to
  assistive technology.
- Cancellation controls have stable identifiers and explain that cancellation
  targets the active workflow or capability process tree.
- Provider failures retain their existing actionable status categories while
  using one redacting formatter.

## Automated evidence

Run from the repository root:

```bash
./script/run_swift_tests.sh
./script/check_release_readiness.sh
./script/check_git_publication_readiness.sh
env -u RUN_DOCUS_BENCHMARK -u DOCUS_BENCHMARK_MODE ./script/run_quality_gate.sh
```

The quality gate builds the packaged app and runs the identifier-based UI smoke.
DOCUS is not required for this UI/service milestone and the original DOCUS tree
must remain untouched.

Verified on 2026-09-21 from the M104 working tree:

- Swift Testing: 299/299 passed;
- release readiness: passed;
- Git publication readiness: passed over 2,121 objects, with 0 potential
  secrets, 17 reviewed fixture matches, 181 previously documented historical
  privacy findings, 28 binary objects, and 0 oversized objects;
- normal quality gate: passed, including the process-group, planner, golden
  transcript, capability E2E, M102 guided, mixed-research, secret-redaction,
  Settings, first-run, bundle, Finder/Dock, packaged real-run, and packaged UI
  checks;
- mixed-research benchmark: 3 jobs and 24 artifacts;
- packaged real-run smoke: 3 jobs and 20 artifacts; and
- DOCUS benchmark: deliberately skipped because this milestone changes no
  scientific workflow or copied-input contract.

## External usability session still required

Automated checks do not establish that a new user understands the product. M104
is not fully closed until a person other than the author completes and records a
session using the packaged app. The observer should record, without changing the
participant's words:

- Mac model, architecture, macOS version, app commit, and installation method;
- whether the participant can reach all seven sections without coaching;
- whether they can identify which operations are local and which may contact a
  cloud provider;
- whether they understand that inputs remain untouched and where outputs go;
- whether they can start a synthetic workflow, find its job, cancel or recover
  it, and locate its artifacts;
- any inaccessible control, unclear status, unexpected error, or missing empty
  state; and
- the changes made in response, followed by the same automated gates.

Use synthetic fixtures only. Do not use DOCUS, private scientific documents, or
real credentials for this session unless the participant explicitly owns and
authorizes them.
