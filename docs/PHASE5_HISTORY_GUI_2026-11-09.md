# Large history graphical verification

This check completes the local PERF.09 scenarios left open in the
[history scale measurement](PHASE5_HISTORY_SCALE_2026-11-08.md) and
[deferred capture comparison](PHASE5_DEFERRED_CAPTURE_2026-11-08.md).
It used the debug app at `687cf8d` on an Apple M1 Pro with macOS
27.0.1. The isolated output directory contained a copy of the 10,000-job
schema-2 fixture. Three synthetic jobs had distinct commands and logs.

| Scenario | Observed result |
| --- | --- |
| Open Jobs | The first 100 rows were visible and the total was 10,000. |
| Switch between deferred details | Job 00001 showed its own command, stdout and stderr. After switching 00000, 00001, 00000, the settled detail showed all three capture fields for 00000. |
| Open Results from job 00000 | Results listed 2,005 artifacts. Page two showed rows 101–200. Selecting `wide-0096.csv`, returning to page one and opening page two again preserved its preview and restored the row selection. |
| Find the oldest job | Searching for `sample-09999.csv` returned job 09999. Clearing the search preserved the detail and opened rows 9,901–10,000. |
| Navigate during reload | Dashboard opened after pressing Reload. Returning to Jobs showed the final page, the same job and its captures. |
| Confirm a fresh disk read | A new synthetic CSV in the copied run folder did not match the search until Reload. It then appeared under the selected job and opened in Results. |

The navigation observation includes automation and accessibility snapshot
time. It does not measure frame timing or set a latency budget. The prior
component comparisons quantify the indexed query and hydration costs.
The suite for this build passed all 402 Swift tests.

SHA-256 verification found no changes to the 12,004 files in the original
synthetic fixture. The 12,013 existing files in the test copy, including
the job index, kept their hashes. Its only new file was the synthetic CSV
added for the reload check. The 22 ordinary application state files and
preferences also matched. Full-index write latency remains part of PERF.14.
