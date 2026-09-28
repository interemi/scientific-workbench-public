# 0002: Local-First Zero-Cost AI Default

Date: 2026-05-25

## Status

Accepted.

## Context

OpenAI, xAI/Grok, and many production cloud model APIs require separate billing from consumer chat subscriptions. The app should not depend on paid API usage to be useful.

The current target Mac is an Apple M1 Pro with 16 GB RAM, arm64, and roughly 85 GiB free disk. It can run small-to-medium local models, but the default must stay conservative because the app also needs memory for SwiftUI, Python tools, PDFs, FITS processing, and report generation.

## Decision

Scientific Workbench will be local-first and zero-cost-first:

- Ollama is the default AI provider.
- Ollama requires no API key.
- OpenAI, Grok/xAI, and Gemini remain optional cloud providers.
- The default Ollama model is `qwen3:4b-instruct`.
- Local Ollama calls use a short timeout so a missing local server fails fast and falls back to deterministic planning.
- Settings includes a Local AI Setup panel for opening the official download page, checking the local server, pulling the selected local model, and testing local AI.
- Larger local models are opt-in upgrades, not defaults.
- Deterministic local capability execution remains the source of truth for scientific outputs.

`qwen3:4b-instruct` is the starting model because it is about 2.5 GB on disk through Ollama, offers a much stronger planning/reasoning baseline than sub-2B models, returns direct assistant content reliably for the app's chat/planning API path, and is still reasonable for the target 16 GB Apple Silicon laptop.

## Consequences

Positive:

- The project can continue without paid API keys.
- The app remains useful offline or with local-only data.
- Cloud data exposure becomes optional.
- Tests can mock provider calls without token spend.

Tradeoffs:

- Local model quality will be below frontier cloud models.
- The user must install Ollama and pull a model for local AI chat/planning.
- Complex DOCUS-style work still needs deterministic local capabilities and possibly Codex/report tooling for best results.

## Required Follow-Up

- Keep improving the friendly error when Ollama is not installed, not running, or missing the selected model.
- Add model profile presets: compact (`qwen3:1.7b`), balanced (`qwen3:4b-instruct`), stronger.
- Keep cloud providers available but clearly marked as optional and potentially billable.
