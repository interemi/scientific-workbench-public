# First-window startup measurement

This follow-up measures graphical launch of Scientific Workbench from
source `ef1adee`. It uses the same 250-job scenario as the
[startup component measurement](PHASE5_STARTUP_HISTORY_2026-11-06.md).

## Setup and method

- Test machine was a MacBookPro18,3 with 16 GiB RAM, macOS 27.0.1
  (26A434), Swift 6.4 and macOS SDK 26.5.
- One locally instrumented debug executable and one isolated app
  bundle ran both modes. The only runtime difference was whether the
  existing graphical launch path restored the job bundles synchronously
  or deferred their reads. Both modes used the same preferences suite,
  bundled skill root, existing Core Python environment and copied
  schema-2 history. The 250 jobs had five small synthetic files each.
- Finder reopened the app after each process quit. Two warmup pairs
  preceded 12 measured pairs. The first mode alternated by pair to
  reduce sensitivity to order. Filesystem caches were warm.
- A monotonic clock recorded elapsed time from the Swift entry point
  to the first visible AppKit key window, the root SwiftUI
  `onAppear` callback, restoration of the selected job and history,
  and completion of the startup registry and environment checks.
  Store initialization is timed from the app initializer to the
  store factory return.
- The test required the Chat window and workflow controls in every
  accessibility observation. Each log had one visible key-window
  event for the main Chat window and one history-ready event with the
  same selected job ID and count. Timing comes from in-process events.

## Results

Positive paired differences mean the deferred mode reached the
event earlier. All times are in milliseconds.

| Event | Synchronous median (range) | Deferred median (range) | Median paired difference | Deferred earlier |
| --- | ---: | ---: | ---: | ---: |
| Store initialization span | 159.9 (154.7–163.7) | 14.4 (14.1–15.3) | 145.2 | 12/12 |
| Main window visible and key | 540.6 (521.8–561.7) | 422.9 (411.7–433.6) | 118.5 | 12/12 |
| Root view appearance callback | 577.4 (558.6–598.8) | 461.1 (445.9–468.3) | 118.8 | 12/12 |
| Restored history and selection | 159.4 (154.2–163.2) | 201.3 (193.0–207.8) | -41.3 | 0/12 |
| Registry and environment checks complete | 1224.7 (1132.6–1253.2) | 1109.8 (996.3–1222.3) | 74.5 | 11/12 |

The deferred mode moved the key-window event forward by 88.1–140.6 ms
across the 12 pairs. History readiness took 31.9–53.5 ms longer in
the graphical launch, with the 250 jobs ready before the key-window
event in all measured runs. The separate component benchmark left out
other startup work scheduled on the main actor.

All 24 measured windows appeared before registry and environment
checks finished, and the configured environment returned `ok` in
every trial. This verifies PERF.04 for the tested graphical launch.
For PERF.17, the working local target is a median of at most 500 ms
from Swift entry to a visible key window for this fixture and machine,
using the same 12-pair procedure. That target covers one startup
scenario. Larger histories, cold caches and other machines need
their own measurements.

The visible key-window event describes AppKit state. The test did
not time the first painted frame or keyboard response under load.
The raw observations and temporary instrumentation remain in local
evidence. Hashes matched for all 1,251 copied fixture files and the
22 ordinary app-state files, and ordinary preferences matched.
