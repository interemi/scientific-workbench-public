# Phase 5 performance budgets

The reference machine is a MacBookPro18,3 with Apple M1 Pro, 16 GiB
RAM, macOS 27.0.1 (26A434), Swift 6.4 and the macOS 26.5 SDK. These
are local debug-build measurements with synthetic inputs. The timing
limits apply to the named workloads on this machine.

| Workload and metric | Limit | Observed | Result |
| --- | ---: | ---: | --- |
| Start with 250 jobs, Swift entry to visible key window, 24 measured launches | Median 500 ms, p95 550 ms | Median 362.3 ms, p95 401.8 ms | Pass |
| First indexed search of 10,000 hydrated jobs, five fresh indexes | Max 300 ms | 172.6 ms | Pass |
| Prepared search of the same 10,000 jobs, 30 queries | p95 50 ms | 20.9 ms | Pass |
| Catalog search from text binding update to AppKit marker draw, 24 queries | p95 250 ms | 164.4 ms | Pass |
| Navigation between Jobs and Capabilities, 22 transitions | Provisional p95 150 ms | 214.9 ms | Open |
| Load a synthetic 8,192 × 8,192 raster and draw a 1,280 × 1,280 preview | Peak process RSS 96 MiB | Max 68.9 MiB over 15 processes | Pass |
| Raster thumbnail and retained preview cache | Maximum side 1,600 px, cache 12 MiB | 1,600 px and 10,240,000 cached pixel bytes in the raster probe | Pass |
| Displayed recent log excerpt per stream | 16 KiB and 120 lines | Covered by Swift tests with Unicode and long input | Pass |

## Startup and release checks

From a clean checkout on a Mac with an open graphical session and the
[Core environment](../INSTALL.md), run:

```bash
python3 script/check_reference_startup_budget.py \
  --python "${CORE_PYTHON:?Set CORE_PYTHON to the installed Core interpreter}" \
  --sdk "${PERFORMANCE_SDK:?Set PERFORMANCE_SDK to the macOS 26.5 SDK directory}"
```

The script builds an isolated debug app from the recorded Git revision,
generates 250 synthetic jobs, and records two warmups and 24 fresh
launches. Every measured launch must show the Chat key window before
environment checks finish and restore all 250 jobs with the expected
selection. It reports a nearest-rank p95 and preserves the traces,
fixture inventory, and binary SHA-256. Runs on other configurations
produce an observation. The benchmark uses a test-only compilation
flag. The first key-window event measures AppKit state at startup.

The thresholds allow margin above the
[previous 12-launch baseline](PHASE5_WINDOW_TIMING_2026-11-06.md), which
observed a median of 422.9 ms and a maximum of 433.6 ms. The maintained
check passed on `54259d3` with all 1,251 synthetic file hashes intact.
The normal [Swift test runner](../script/run_swift_tests.sh) checks the
portable thumbnail and log limits. All 411 Swift tests passed.

## Search and navigation

The component search used the
[10,000-job fixture](PHASE5_HISTORY_SCALE_2026-11-08.md), with a unique
CSV in the oldest run. Each query returned that record. Prepared
queries exclude construction and UI scheduling. The first-index
limit gives approximately 50% headroom over the earlier 199.1 ms
observation. The prepared limit covers variation around the earlier
22.4 ms median.

The graphical search alternated between `profile csv` and
`inspect fits`. Every sampled result matched the visible query and
had the expected one or two routes out of 55. A separate rapid query
replacement ended on the one matching CSV route. The search timing
includes the 75 ms debounce. The marker is an AppKit draw associated
with the matching SwiftUI state. It provides a repeatable local
observation of app drawing without measuring compositor presentation.

Navigation alternated between the capability catalog and the same
250-job history. A second trace of five warm samples per direction
measured medians of 58.3 ms (Jobs) and 60.9 ms (Capabilities) from
button action to representable update. Median time from update to
marker draw was 155.1 and 102.0 ms respectively. Keep the 150 ms
navigation target provisional while comparing the draw path against
the pre-Phase-5 source under the same conditions.

## Preview memory and backend observations

Each raster format ran in five separate processes. Maximum peak RSS
was 67.6 MiB (PNG), 58.1 MiB (TIFF) and 68.9 MiB (JPEG). The 96 MiB
limit allows headroom above the
[earlier component measurements](PHASE5_RASTER_PREVIEWS_2026-11-06.md)
and still detects a return to full-size decoding for the synthetic
PNG and TIFF. Preview files retained their original hashes.

The [scientific known-answer check](../script/check_scientific_known_answers.py)
passed in three fresh Core runs. The FITS case with preview generation
peaked at 157.1 MiB RSS and 15.47 s with a new plotting cache. The
two-table sky crossmatch peaked at 92.6 MiB and 0.88 s. These are
backend process measurements on small fixtures. They establish
initial reference cases for the single-job policy. Larger backend
workloads and physical I/O budgets remain open.

Ordinary application preferences and state matched the pre-test
inventory. Both graphical interaction copies retained all 1,251
synthetic file hashes.
