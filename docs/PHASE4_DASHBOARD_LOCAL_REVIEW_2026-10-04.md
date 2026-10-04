# P1.01 Dashboard: local task-launch and return review

- **Date:** 2026-10-04
- **Source commit:** `63dee8a76201a77a7d3359a93b611812e958d4bf`
- **Scope:** internal technical review on one Mac; public integration pending

The Dashboard now puts three named tasks first: profile a table, inspect a
FITS image, and explore a mixed folder. Each task opens the corresponding
capability for review or prepares a new synthetic example copy. An existing
job appears near the top with a link back to its persisted Jobs detail. This
link does not retry or resume execution automatically. The setup checklist
appears when Core is not ready; detailed counters and older jobs remain
available in an expandable section.

This implements the local technical part of P1.01. It does not establish that
unfamiliar users can choose the right path without help. The project uses the
[research-led acceptance protocol](RESEARCH_LED_ACCEPTANCE.md) in place of an
unavailable external-user success rate.

## Verification

| Check | Result |
| --- | --- |
| Exact source | Local commit `63dee8a`; no tracked changes at the first evidence check. |
| Machine | Apple silicon, macOS 27.0.1 (26A434), Swift 6.4. |
| Build | `swift build` failed before source compilation with `Unknown error parsing property list`; the already-installed SDK 26.5 with `swift build --build-system native -j 4` passed. The native build-system flag is deprecated, so this remains a local toolchain limitation. |
| Swift tests | 320/320 passed in three suites with the same SDK/native-build settings. The new tests verify table, FITS, and mixed-task routing, preserved input selection, no automatic job creation, and safe return to an existing job. |
| Static release readiness | `./script/check_release_readiness.sh` passed. |
| GUI and accessibility tree | A locally assembled test bundle with executable SHA-256 `b43cd7d91491c9ae890c92fb59effd00e38353c83db6d0f3b4ab9d6a9436cee9` showed the three task cards and a recent blocked job on Dashboard. Its FITS card opened `inspect_fits` in Expert mode with no run started. The latest-run button opened that existing job's status and evidence in Jobs without retrying it. The final card wording and expanded window were reviewed visually; window size was restored. |

The GUI review read previously persisted local job history, created no job,
and did not run a workflow. The test bundle and build logs stay outside Git.
No real scientific input or original DOCUS file was used or modified.

## Limits and next check

The GUI review used the available development Mac and an existing history, so
it did not simulate a genuinely fresh installation or another person's Mac.
Task routing in a store with no jobs is covered by tests; the conditional setup
presentation was not visually exercised from a fresh installation. Hosted
validation on the exact candidate and public merge remain pending. P1.10's
spoken VoiceOver and
measured-contrast checks remain open. The full local quality gate was not run
for this individual Phase 4 change; its bundle step would replace the checkout's
existing `dist` app and terminate app processes. It remains a phase-level
check before publication of the grouped changes.
