# Workflow context: local technical review, 2026-11-04

Source `d27106540f6677ac4e8d3d18d774daff32cb4478` was exercised in an
isolated, ad hoc signed test bundle on the maintainer's macOS 27.0.1 Apple
Silicon Mac. Its executable SHA-256 was
`12bd7a547af5acb3d9812011ae154ff533804312d90ec4d9a15da7905ec15452`.
The build used Apple Swift 6.4, the available macOS 26.5 SDK, and the SwiftPM
native build system with the repository's CLT testing fallback. The previously
observed failure of the default build path remains a separate toolchain limit.

## Finding and correction

Creating a new FITS plan after completing a table workflow left **Summary**
enabled and opened the older table summary. The same stale association existed
when importing another plan. Two regression tests failed before the fix.

Plan replacement now clears the previous step executions, active execution
identity, and summary reference together. It preserves the jobs, run folders,
logs, and summary files. Failed imports preserve the existing context. Both
tests pass after the fix, including a reload of the replacement plan. The full
suite passed **380/380 tests in three suites** and release readiness passed.
No persisted schema or skill snapshot changed.

The corrected GUI disabled Summary on the new, unexecuted FITS plan. After
execution it opened that FITS workflow's own summary. The original table
summaries remained on disk.

## Observed workflow attempts

These are **five scripted author-run attempts**, not five independent user
sessions. The last two deliberately share the same app session and plan to
test repetition. No claim of independent usability or second-Mac manual
acceptance is made.

| Case | Workflow Run ID | Observed result |
| --- | --- | --- |
| FITS | `A0C24A3D-4004-4C05-8355-74C4CB5198E1` | Environment check and explicitly enabled Expert FITS inspection completed, 2/2. |
| Mixed folder | `9D6C5C48-2AAE-459A-A26C-C55CFD30352F` | Environment check, document intake, and separate data inventory completed, 3/3. |
| Cancel FITS | `7971A29D-D648-471F-8279-DBD5DB2EC885` | Environment check completed; the actual FITS process was cancelled. Four partial artifacts and the stopped-workflow summary were retained. |
| Table | `1B0075B0-B88C-446E-8C06-132456EBD0C1` | Environment check and table profile completed, 2/2. |
| Repeat table | `7A3C6347-76C5-47EC-88A7-03677E5BC313` | The same reviewed plan completed again, 2/2, with a new Run ID and a separate summary. |

Each attempt used **Auto-run off**, explicit enabled-step review, and a passing
**Dry Run** before **Run Enabled**. Additional suggested table inventory and
physical-QA steps were disabled for the table and FITS cases respectively.
The FITS Expert step was initially disabled and was enabled explicitly after
review. The mixed workflow retained all three reviewed steps. Inputs and
outputs were separate, and the backend was a copy of the five bundled skills
with an existing Python 3.11.15 Core environment; no dependencies were installed.

For all five attempts, Jobs and Results showed the same Workflow Run ID, and
the retained summary recorded its Plan ID, exact Step IDs and Job IDs. A
post-run check verified **11 step-to-job links**, existing command/stdout/stderr
files, and every indexed artifact's continued presence. Four attempts completed;
the fifth retained the cancellation status rather than reporting success.

Results preserved the table's selected `summary.json` after switching to Jobs
and back. Edit Plan returned to the existing plan without rebuilding its
inputs. Exit to Dashboard retained the selected FITS input. After cancellation,
New Workflow archived the draft; Restore Previous Draft restored its input
and plan with Auto-run off and fresh review required. Restoration started no
new job. The five generated inputs still matched their `expected.json`
SHA-256 values after every runtime checkpoint.

## Retained scope and remaining work

The [illustrated tours](WORKFLOW_TOURS.md) are separately identified captures
from source `ce38859`; they do not imply that every later source change was
captured. Raw screenshots, accessibility observations, launch records,
regression logs, and fingerprinted runtime archives for this review remain
outside Git. Historical reports and summaries were preserved.

This is local technical evidence for P1.15, including the stale-summary fix.
It does not close the whole Phase 4 gate. Recovery acceptance P1.13, local-model
download/progress/cancellation P1.11, production-bundle validation, coherent
public integration, and hosted CI for the exact candidate remain pending.
The five attempts do not constitute independent novice-user evaluation.
Human scientific review of generated results remains incomplete.
