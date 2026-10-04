# P0.04 and P1.10: local M104 and accessibility review

**Date:** 2026-10-04
**Scope:** author-run technical review on one Mac, with synthetic inputs
**Candidate:** [PR #24](https://github.com/interemi/scientific-workbench-public/pull/24)

This record closes the roadmap's **local scripted walkthrough** criterion for
P0.04 and records substantial but incomplete P1.10 review. It does not claim
that an unfamiliar person completed the journeys, that VoiceOver speech was
audited, that contrast meets a numerical standard, or that the GUI was used on
another Mac. Those are not inferred passes.

## Starting state and method

The first M104 walkthrough used the app source at `2d5f7d3` in a test-only,
unsigned bundle. A later build of this PR retested the accessibility fixes;
its executable SHA-256 was
`6ec7ade8f8c0b684f79189a8552458dc8a56d24d6f1252bdd6a82135d7bf175c`.
Both used isolated app preferences, the skill roots bundled with this source,
a locked Core Python 3.11.15 environment, and a scratch output root outside
the checkout and example inputs. The available machine was an Apple-silicon
MacBookPro18,3 running macOS 27.0.1 with Swift 6.4. The app showed Core ready
and 55 user-facing capabilities. No cloud account, optional external backend,
real research input, or DOCUS file was used.

The private run folders retain the jobs, summaries, manifests, logs, and
synthetic fixtures. They are not committed because the diagnostics include
local machine paths. The table below records rounded process durations from
job start and finish timestamps; these are not measured human task times.

| GUI journey | Observed result | Process time |
| --- | --- | ---: |
| Dashboard small table → Capabilities → Jobs → Results | Guided `profile_table` passed: 3 rows, 4 columns, summary and manifest accessible. | 2 s |
| Dashboard FITS image → Expert review → Jobs → Results | `inspect_fits` passed: one 8 × 8 HDU, 63 finite pixels, reference position (150°, −30°), and a 36,239-byte display-only WCS PNG. The result did not claim calibration. | 2 s |
| Dashboard mixed folder → document intake → Results → Inspect folder data | Intake passed for one Markdown note and one one-page PDF; the separate cross-domain job passed for one CSV with 3 rows and 3 columns. No combined scientific conclusion was produced. | 1 s + 2 s |

All accepted jobs retained separate output directories, reported
`original_modified: false`, and showed Process, Tool outcome, Artifact
contract, and Automatic QA as PASS. Human scientific review remained
INCOMPLETE, as it should for automatic checks.

## Error, cancellation, and restart

A deliberate advanced `--unknown-acceptance-flag` on the synthetic table
failed with exit code 2 and retained `unrecognized arguments` in stderr.
Jobs showed recovery advice. Removing that argument and running the guided
command produced a successful job in 3 s; the input hash stayed unchanged.

The first cancellation attempt ended before the button could be used, so it
was excluded. A separate test-only wrapper then delayed the same Core table
tool for 30 s. The GUI showed the job running; **Cancel Run** ended it after
7 s with job status CANCELLED and exit code 15. No delayed child process
remained. `command.txt`, `next_steps.md`, and stdout/stderr were retained;
there was no summary or manifest because the tool had not begun. Results
showed the process stage as FAIL and downstream stages as INCOMPLETE. That
distinction is technically accurate but could be clearer to new users.

For restart, a two-step table workflow completed step 1 and deliberately
failed step 2 with the invalid flag. Closing and reopening the isolated app
restored the plan and jobs, displayed **Completed 1/2** and **Run Remaining**,
and preserved the successful first job ID. After correcting step 2, manually
reattaching the same synthetic CSV, and passing Dry Run, **Run Remaining**
created exactly one new successful job. Attachments are not restored after
process restart; the user must reattach them before resuming. This is a
documented usability limitation, not loss of the original input.

Read-only SHA-256 checks after these journeys matched the generated originals:

| Synthetic input | SHA-256 |
| --- | --- |
| `ops.csv` | `a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72` |
| `synthetic_wcs_8x8.fits` | `c40732799d2792ed9131899c2ad5a3b13317004a96e4d40a0d6aa959afc740de` |
| `measurements.csv` | `0801bbdf8ee590c0ec6138ece0f22502f7987a8b20928aa524eff8129da59876` |
| `notes.md` | `7458b9e16eaf119f6bc4f259f10187e5988c49c53cd5e9c40394ffe51daec98d` |
| `observing_note.pdf` | `a80cc3e7d5df9c5e9819774a1ac273f16064570ccc1743a0b332357daa42f126` |

## Interface and accessibility review

Dashboard, Capabilities, Jobs, Results, and Chat were inspected through
screenshots and the macOS accessibility tree. Dark and light appearances were
checked; both kept the main text and controls visually readable on this
display. The app's initial compact window and the expanded **Window → Zoom**
layout were checked; Zoom exposed the inspector, and a second use restored
the compact window. Primary controls and scrollable content remained
available in the compact views. This was visual inspection, not a measured
contrast ratio or a sweep of every possible display size.

The initial tree exposed ambiguous removal and artifact buttons. This PR
added contextual labels and non-deleting removal hints. A fresh build then
exposed **Clear selected inputs**, **Remove input ops.csv**, **Remove
attachment ops.csv**, **Open artifact manifest.json**, and **Reveal artifact
manifest.json** in the tree. The attachment path tooltip was limited to its
filename text so it no longer replaced the remove button's hint.

With the user's permission, macOS Full Keyboard Access was enabled
temporarily. Repeated Tab traversal reached the reviewed action buttons in
all five views, including the Jobs history controls when traversing from the
start of that view. The File, View, Workbench, Window, and Help menus were
inspected; the project-specific refresh, registry, configuration, support,
guide, and output-folder entries were present. VoiceOver was briefly enabled
for an accessibility-tree check. Its spoken output could not be captured or
assessed in this session. Dark appearance, VoiceOver off, and Full Keyboard
Access off were verified restored to their initial system states.

## Verification and limits

The final local source passed **318/318 Swift tests**, release-readiness, and
the full local quality gate with the available macOS 26.5 SDK and SwiftPM
native build system. DOCUS full benchmarking was not requested for this
review. The default Swift Build path on this macOS 27 toolchain failed before
compilation with a property-list parser error, and the native build without
that SDK failed to load SwiftUI macros; these are local toolchain observations,
not hidden application tests. Hosted CI must be repeated on the eventual
committed head before integration. The original DOCUS directory was not
accessed for this review.

P0.04 meets its scripted, available-Mac walkthrough criterion. P1.10 remains
open: the macOS accessibility tree exposed the revised labels and hints, but
spoken VoiceOver announcements were not captured or assessed. Contrast was
visually reviewed in light and dark mode, not measured to a numerical
threshold. Independent users, other window configurations, and interactive
use on another Mac also remain unverified.
