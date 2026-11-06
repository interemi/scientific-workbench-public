# P1.04 environment diagnosis and safe repair: local technical review

- **Date:** 2026-10-04
- **Source commit:** `c06ce46` on `codex/phase4-dashboard-journey`
- **Branch:** `codex/phase4-dashboard-journey`; public integration pending
- **Scope:** transient environment diagnosis, a reviewable new-environment plan,
  and installer failure logging; no persisted model changed

Settings now separates the selected interpreter and Python version from the
editable Python preference. It reports Core package readiness as a required
check, and missing Full package groups as optional until a workflow needs
them. The Setup Checklist no longer treats a successful environment lookup as
proof that Core packages are installed. A failed diagnostic process cannot
claim readiness even if its output contains a plausible JSON object.

**Prepare a new environment** shows a unique external destination, the
profile's one-Mac disk/time measurement, a plan-only command, and a separate
`--install` command. The app does not execute either command. The source
installer rejects an existing destination and keeps its plan, package
inventory, diagnostic report, and `installation.log` in the new destination.
The log records each invoked command, combined process output, and an error
line when setup stops. It is local evidence and can include private paths.

## Observed verification

| Check | Result |
| --- | --- |
| Swift unit and integration tests | 324/324 passed in three suites with Swift 6.4 and the installed macOS 26.5 SDK. The new tests cover Core/Full separation, invalid diagnostic output, a failed process that emits ready-looking JSON, and new-destination plan semantics. |
| Python distribution tests | 67/67 passed in the complete distribution test directory (including the nine focused installer safety tests). A simulated failed diagnostic retained `installation.log` with its command and failure line. |
| Actual installer preview | The reviewed locked Core preview exited 0; the proposed destination did not exist before or after. No packages were downloaded or installed. |
| Existing isolated Core Python | The app displayed the Core interpreter, `core_ready=true`, `full_ready=false`, and six missing optional Full groups. Core remained ready in the Setup Checklist. |
| Existing Full Python | The app displayed the selected interpreter and version, with Core and Full verified. |
| GUI repair plan | Core and Full selections produced different unique destinations; the preview command omitted `--install`, and only the separately labeled install command contained it. The commands and local measurement caveat were visible in Settings. |
| Static checks | Settings surface check, release readiness, public documentation audit, and `git diff --check` passed. The public documentation audit reported zero Spanish candidates, zero broken local links, and zero unsafe active guidance findings. |

The GUI tests used an isolated output root for the test app. Its temporary
Python and output-root preferences were restored afterwards. An initial test
launch against the ordinary Documents output root stalled while opening its
job-history file; switching the **test app only** to the isolated output root
allowed the visual review to finish. That launch behavior is not evidence of
a product fix and remains worth checking during later app-startup work.

No fresh installation, actual package failure, second Mac, end-user study,
external application check, or DOCUS benchmark was run for this local review.
The previous [single-Mac installation baseline](LOCAL_INSTALLATION_COST_BASELINE_2026-10-03.md)
supports only the displayed approximate disk/time figures. P1.04 remains open
until phase integration and exact-hosted-commit checks are complete.
