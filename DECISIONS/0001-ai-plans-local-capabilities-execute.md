# 0001: AI Plans, Local Capabilities Execute

Date: 2026-05-24

## Status

Accepted.

## Context

Scientific Workbench is intended to feel like ChatGPT/Codex while still doing reliable local scientific work. The app can call cloud AI providers and local tools, but those two responsibilities should not blur.

If the model is allowed to both reason and perform unbounded local actions directly, the app becomes harder to audit, harder to test, and less safe for user data. If the app only runs fixed scripts, it loses the natural-language workflow the user wants.

## Decision

Cloud AI providers are used for:

- chat answers
- workflow planning
- summarizing already-generated artifacts
- explaining errors and results

Local capabilities are used for:

- reading local scientific inputs
- executing analysis
- producing reports, manifests, tables, plots, and logs
- maintaining provenance

Codex is used as a local bridge for:

- coding tasks
- controlled report drafting
- filesystem-aware reasoning inside an output workspace

The app should prefer this chain:

1. User prompt and attachments.
2. AI or local planner creates a plan.
3. User reviews plan unless auto-run is enabled.
4. Local capabilities execute plan steps.
5. Artifacts are discovered.
6. AI may summarize artifacts.

## Consequences

Positive:

- Safer local execution.
- Better reproducibility.
- Easier testing.
- Better provenance.
- Lower chance of cloud providers receiving unnecessary raw data.

Tradeoffs:

- More architecture work.
- Planner and runner contracts must stay clean.
- Some tasks need explicit guided capability support before they feel effortless.

## Required Follow-Up

- Add `Test AI Connection`.
- Add systematic key redaction.
- Add provider mocks.
- Add explicit user-facing data policy for cloud calls.
- Add persistent workflow plans.
