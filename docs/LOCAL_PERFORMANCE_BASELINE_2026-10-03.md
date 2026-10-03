# Local startup and first-use performance baseline

- **Measured:** 2026-10-03, 00:40–00:48 and 09:09–09:10 UTC
- **App source commit:** `5f996e62b832becebe8aaec72ae9531af0379cbb`
- **Scope:** one available Mac, synthetic Core-profile first use

This is a repeatable local observation for roadmap item PERF.01, not a
performance promise for other Macs. The measurements include computer-use
automation and accessibility-tree capture. They are not frame-paint times,
CPU profiles, or a clean-machine installation test.

## Environment and retained evidence

| Item | Recorded value |
| --- | --- |
| Machine | `MacBookPro18,3`, Apple silicon (`arm64`), 16 GiB RAM |
| OS | macOS 27.0.1, build `26A434` |
| Toolchain | Apple Swift 6.4; Command Line Tools macOS 26.5 SDK; SwiftPM native build system |
| App binary | Scratch-built from the source commit above; SHA-256 `b6cfc6cc928f3dcc125cd48b2cf42a8c8687737df43123daf588a0d46cbc7003` |
| Scientific environment | Startup and capability browsing used the detected installed skill root (55 visible tools). The separate synthetic run used the bundled skill tree and dedicated Core Python 3.11.15 with pandas. Full profile and external tools were not measured. |
| Synthetic input | App-generated `ops.csv`, 85 bytes, 3 data rows × 4 columns; SHA-256 `a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72` |
| Trace | 42 timestamped JSONL events retained outside Git, SHA-256 `24bc33aa42166d4f9af80d5fde4086a727f2fb230d504015437e096eaff734d3` |
| Scientific run | `profile_table` through the app, run-folder suffix `20261003_024422_profile_table_3d159bab-9559-4cf3-898e-e0ff6c713d32` |

The scratch app and trace are local measurement artifacts, not release
packages. The raw JSONL, synthetic input, run folder, and manifest remain in
the maintainer's external run directory. They are intentionally absent from
the public repository because nearby run evidence contains local environment
paths. The trace has `run`, `event`, `start_epoch_ms`, `end_epoch_ms`, and
`elapsed_ms`; some events add readiness or outcome fields. All recorded
durations equal the difference between their epoch timestamps.

The profiler finished with exit code 0, tool status `ok`, QA status `ok`,
3 rows, and 4 columns. The input still matched its recorded 85-byte size and
SHA-256 after the run. The output `summary.json` still matched the manifest's
7,213-byte size and SHA-256
`aa37513c5e62751c462e323a076555ab96df10722857ca451220193d9a888b48`.
The summary reported `original_modified: false`. This checks evidence
integrity for the synthetic example; it does not validate a research result.

## Measurement method

The operator used an isolated wrapper around the exact scratch-built app to
avoid reusing normal job history and settings. The app-created synthetic example
was still written under its normal Application Support examples directory.
For each of the three comparable startup trials, the isolated process was
closed before calling
`cua.getApp` with its bundle path. `Date.now()` was sampled immediately before
that call, after its first accessibility state, and after the Dashboard showed
its usable controls. The app opens in Chat, so the last interval includes
navigating to Dashboard. “Cold” means a new app process; the filesystem and
OS caches were not cleared. The first exploratory startup has a gap between
observations and is excluded from the continuous launch-to-Dashboard sample.

Navigation measurements start before a UI action and end when the
accessibility observation confirms the target view. Search and selection were
repeated three times with the exact query `profile_table`: clear the search,
select `datanalysis_env.py status` as the control row, enter the query, confirm
the `profile_table.py` result, select it, and confirm its detail pane. These
standardized search trials use a full accessibility tree. The earlier generic
search trials remain in the raw trace but are excluded from the primary table
because their query was not recorded. Jobs, Results, and `summary.json`
inspection each had three repeated observations in the same configured
session. All timings include automation dispatch and accessibility work.

The optional local-AI probe was measured separately when Settings explicitly
initiated its check. A 10-second exploratory wait in Chat is excluded: it did
not initiate a probe and cannot represent Ollama latency. The first scientific
run measures from the app's Run action until Jobs reported a terminal
`SUCCEEDED` state; it includes polling and Python startup and has only one
sample. No manual use by another person or another Mac was measured.

## Results

Times are milliseconds. “SD” is the sample standard deviation; the range is
the minimum and maximum of the included observations.

| Event | n | Median | Mean | SD | Range |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh app call → initial accessible window | 3 | 1,369 | 1,382.7 | 131.0 | 1,259–1,520 |
| Initial window → usable Dashboard | 3 | 652 | 729.0 | 146.6 | 637–898 |
| Fresh app call → usable Dashboard, continuous trials | 3 | 2,006 | 2,111.7 | 269.5 | 1,911–2,418 |
| Navigate to Capabilities | 3 | 583 | 641.0 | 107.5 | 575–765 |
| Search `profile_table`, full accessibility check | 3 | 834 | 831.0 | 11.8 | 818–841 |
| Select `profile_table.py`, full accessibility check | 3 | 767 | 771.7 | 9.0 | 766–782 |
| Navigate to Jobs | 3 | 586 | 582.7 | 6.7 | 575–587 |
| Navigate to Results | 3 | 632 | 638.3 | 16.4 | 626–657 |
| Inspect `summary.json` in Results | 3 | 564 | 563.3 | 3.1 | 560–566 |
| Explicit optional local-AI Settings probe | 3 | 1,057 | 1,083.0 | 45.0 | 1,057–1,135 |
| First synthetic table-profile run → terminal job | 1 | 2,673 | 2,673.0 | n/a | 2,673 |

The trace uses wall-clock milliseconds around UI calls. To recalculate each
row, select its named event (and startup runs 2–4), then compute the median,
arithmetic mean, sample standard deviation, and minimum/maximum of
`elapsed_ms`. The scientific-run row has no meaningful variance with `n=1`.

## Decision and limits

No code optimization is justified from this baseline alone. The largest
continuous observation is about two seconds from a fresh launch call to a
usable Dashboard, but automation dispatch, accessibility capture, and the
Chat-to-Dashboard action are inside that number. The optional probe and the
scientific run are separate costs. Three short trials on a warm filesystem
cannot identify a CPU or rendering bottleneck. `xctrace` was unavailable with
the installed Command Line Tools, so no Instruments trace was collected.

Use this baseline to choose a *specific* follow-up if a later measurement or
user-visible regression warrants it. A future comparison needs the same
machine, exact binary/profile, query and synthetic input, a monotonic clock,
more repetitions, and preferably a profiler capable of separating app work
from automation overhead. Full-profile installation, another Mac, Intel
hardware, and manual researcher experience remain unmeasured.
