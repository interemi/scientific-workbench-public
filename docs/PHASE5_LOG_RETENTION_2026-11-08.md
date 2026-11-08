# Full redacted run log retention

This checkpoint adds retained process streams to the bounded log views
introduced in `af13b7f`. A workflow process writes stdout and stderr to
private temporary files. After the process stops, the app reads and
redacts those files in 64 KiB blocks on a utility task. The resulting
run logs are installed atomically inside the opened run directory.
The same capture path retains partial output after interruption. The
in-memory diagnostic excerpt and the rendered tail remain bounded.

The redactor uses the configured values from launch and finalization.
It holds an overlap across chunks for matching known values, including
canonically equivalent Unicode text. When configured redaction is
active, invalid UTF-8 is decoded with replacement, as in the earlier
text capture. The existing 256 MiB raw output threshold per stream
still stops a noisy run. A stream beyond that threshold retains a
bounded prefix with an explicit notice. New files have user-only
permissions. Historical run files are read as they were saved.

Jobs and the Results summary keep their recent-output notice. The
Log File menu opens the retained file in TextEdit for search and
selection, or reveals it in Finder for a file copy. A Support Bundle
continues to use bounded diagnostic sidecars.

## Local evidence

An optimized component probe linked the production ProcessRunner and
archiver on an Apple M1 Pro with macOS 27.0.1 and SDK 26.5. Three
fresh Swift processes per workload emitted fixed ASCII output with a
synthetic key crossing a chunk boundary. The retained stream matched
the independently computed redacted SHA-256 in every trial.

| Stdout emitted | Stdout retained | Swift peak RSS range | Median process and retention time |
| --- | ---: | ---: | ---: |
| 8 MiB | 8,388,598 bytes | 20.77–20.80 MiB | 300 ms |
| 64 MiB | 67,108,854 bytes | 20.77–21.08 MiB | 1,521 ms |
| 192 MiB | 201,326,582 bytes | 21.05–21.14 MiB | 4,335 ms |

The first implementation's RSS rose from approximately 29 MiB at
8 MiB of output to 85 MiB at 64 MiB. Draining Foundation's autorelease
pool after each block removed that growth in the repeated probe. The
timings and RSS are for the local component protocol.

The isolated app navigated from a running synthetic capability to
Dashboard and back to Jobs while stdout was being emitted. After the
run succeeded, Jobs showed the excerpt notice. TextEdit found the
synthetic marker from the middle of the retained 67,108,969-byte
stdout, beyond the in-app excerpt, and enabled Copy. The retained
file and a byte-for-byte copy matched the independently computed
digest. The test did not measure frame latency at finalization or
memory used by the external editor.

All 397 Swift tests passed. The integration test compared both output
files to expected bytes and recovered the final tool envelope. Other
checks covered a Unicode scalar and a secret across chunk boundaries,
destination links, output limits and the existing cancellation path.
The ordinary app-state hashes and preferences matched before and after.
