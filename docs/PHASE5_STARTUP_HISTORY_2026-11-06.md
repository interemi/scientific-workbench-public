# Startup job history measurement

Measured on 2026-11-06 against public base `a5a48e3`, on an Apple silicon
Mac running macOS 27.0.1 (26A434), Swift 6.4 and macOS SDK 26.5. The timed
component was a debug SwiftPM build. This advances PERF.02 and PERF.17
for startup run-bundle reads.

## Change

The graphical launch reads and, if required, recovers the persisted job
index before handing off the per-run bundle reads to a background task.
The app publishes the restored jobs and their selection together when
the reads finish. Jobs, Results and Dashboard distinguish loading from
empty history. Headless startup and explicit history reload keep their
synchronous behavior.

A capability submitted during restoration waits before creating or
persisting its job. It checks its input selection and execution settings
again after the wait. A changed selection or execution configuration
requires review before retrying. Clear and reload are unavailable during
the initial restore. The initial bundle reads use the same configured
secret redaction as the synchronous path.

## Paired component timings

Each job had five small synthetic files (command, stdout, next steps,
summary and CSV). Each history used the existing schema-2 writer.
The same compiled test runner initialized the store in synchronous and
deferred modes against the same files. It used `ContinuousClock`, two
warmups and 12 recorded observations per mode and size, rotating sizes and
alternating mode order. Init ends when the initializer returns. Ready
includes awaiting the restore on the main actor. Each trial checked
ordered job IDs, the selected job, and restored summary, log and CSV
metadata. The fixture hashes matched before and after.

| Jobs | Synchronous init median (ms) | Deferred init median (ms) | Synchronous ready median (ms) | Deferred ready median (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 2.833 | 2.899 | 2.835 | 2.902 |
| 25 | 15.779 | 3.605 | 15.783 | 14.397 |
| 100 | 52.720 | 5.242 | 52.725 | 51.629 |
| 250 | 128.603 | 8.617 | 128.608 | 127.610 |

At 250 jobs, synchronous initialization ranged from 125.843 to 134.144 ms,
and deferred initialization from 8.565 to 9.427 ms. A separate earlier
profile identified sidecar reads and artifact discovery in the
main-thread startup stack. The paired measurements use warm caches and
quantify the time removed from the initializer. Time to first rendered
window and performance with larger scientific artifacts remain unmeasured.

## Verification

- Swift suite passed 381 tests in three suites. The new regression
  submitted a capability while restoration was pending, verified both
  job IDs remained in the saved index, and checked redaction of a
  synthetic key with the original log unchanged.
- The app launched with a copied 250-job history in an isolated session.
  Jobs showed 250 of 250 entries. Results opened the latest job's
  `result.csv` and displayed the expected synthetic row `1,4.2`.
  The run verified navigation after restoration and did not measure
  the loading indicator's duration.
- All 1,251 copied fixture files and the 22 ordinary app-state files
  matched their pre-test hashes. The ordinary app preferences also
  matched. The detailed timing logs and synthetic test bundle remain in
  local evidence.
