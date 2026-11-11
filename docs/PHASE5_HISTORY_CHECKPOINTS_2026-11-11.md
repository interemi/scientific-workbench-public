# Job history checkpoints

PERF.14 moves normal job-history writes off the main actor. Each
write captures its records and destination. Writes complete in
submission order, including during Quit. Each snapshot still uses
the schema-2 format, the 128 MiB size limit and atomic replacement.
Queue, start and terminal transitions keep separate checkpoints.

Clearing history changes the visible list only after the empty
checkpoint is saved. A failure leaves the list, selection and
previous file available and displays the save error in Jobs. Refresh
Bundle also reads the run's evidence off the main actor and discards
its result if the history or its context changed during the read.

## Local verification

Five paired observations used a synthetic 10,000-job history on an
Apple M1 Pro with macOS 27.0.1, SDK 26.5 and a debug build. The input
index was 5,390,060 bytes. The paired runs used the same hydrated
records, including a job with 2,002 artifacts, and saved a
12,315,503-byte index. Each candidate file reopened with all 10,000
job identifiers in order. The fixture index hash matched before and
after.

| Path | Median elapsed | Main-actor heartbeat during the write |
| --- | ---: | --- |
| Synchronous encode and atomic write | 197.1 ms | Zero callbacks in each of five writes |
| Refresh Bundle with background read and write | 317.6 ms | 27 to 29 callbacks per write |

The heartbeat requested a callback every 5 ms. The longest interval
during the entire candidate action was 7.6 ms in these observations.
The candidate time includes rereading the selected job's evidence.
The timings measure a component using the app store, with no window
rendering or interaction latency measurement.

All 407 Swift tests passed. The history test denied writes to a
temporary history directory, checked that its bytes and selection
were preserved, then restored permissions and verified the clear
on retry. Recovery tests also verified schema-1 migration and
retention of the exact original bytes for malformed history.

PERF.14 remains open for measuring agent state and run manifests,
timing large recovery rewrites, and determining whether batching or
compaction is justified.
