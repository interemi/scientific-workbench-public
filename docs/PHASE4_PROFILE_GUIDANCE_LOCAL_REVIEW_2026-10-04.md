# P1.03 Core and Full guidance: local technical review

- **Date:** 2026-10-04
- **Source commit:** `6255679` on `codex/phase4-dashboard-journey`
- **Scope:** local guidance, diagnostic routing, and existing-environment probes;
  public integration pending

Settings now presents Core as the first choice and Full as a separate, larger
Python environment for workflows that need it. The two cards state example
routes, reviewed lock/platform boundaries, the exact lock requirement counts,
and one measured installed size for each profile. The surrounding copy states
that the sizes are observations, not download sizes or guarantees. It also
names external tools and models that neither profile installs. The bundled
user guide repeats the choice and the safe recovery sequence.

**Check Core and Full readiness** opens the existing `env_doctor` capability.
It does not run a command until the user selects **Run Capability**. A run
creates a new diagnostic job with package and optional-backend findings;
installing or repairing packages remains a separate, explicit action. The
Settings surface check now compares the displayed requirement counts with the
three tracked lock files, so a future lock change cannot silently leave those
counts stale.

## Verification

| Check | Observed result |
| --- | --- |
| Lock and copy counts | Core lock: 32 runtime requirements. Full locks: 200 runtime requirements and 3 build tools. The Settings surface check passed against both the view and bundled guide. |
| Existing isolated Core environment | Starting `datanalysis_env.py status` with its Python selected that environment. A read-only `doctor` call reported `core_ready=true`, `full_ready=false`, no missing Core modules, and six optional Python package groups with missing modules. |
| Existing isolated Full environment | The same calls selected the Full environment and reported `core_ready=true`, `full_ready=true`, no missing Core modules, and no missing optional Python groups. These are the previously installed local environments measured in the [installation baseline](LOCAL_INSTALLATION_COST_BASELINE_2026-10-03.md); no package installation or environment repair was performed for this check. |
| Swift tests | 320/320 passed in three suites on this Mac with the already-installed macOS 26.5 SDK and SwiftPM native build setting. |
| Static checks | `check_settings_surface.sh`, `check_release_readiness.sh`, and `git diff --check` passed. |
| GUI | The cards and limits were readable in Settings. Selecting the diagnostic button opened `env_doctor` in Capabilities with no run started or new job created. The test app was then closed. |

The GUI review used the development Mac's existing skill installation and
history. It did not test a fresh install, a second Mac, or whether an unfamiliar
person understands the profile choice. The exact-hosted-commit checks, full
phase quality gate, and public merge remain pending. P1.03 therefore remains
open under the [research-led acceptance protocol](RESEARCH_LED_ACCEPTANCE.md).
