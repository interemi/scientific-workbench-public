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

## Large recovery rewrites

The graphical restore path now encodes, archives and replaces a
recoverable history off the main actor. It compares the source bytes
with the file before replacement and verifies the archive matches.
If the file changed after the read, recovery leaves it in place and
reports that the history should be reloaded.

Three paired component observations used a 5,470,059-byte schema-1
copy of the same 10,000-job fixture. The reference was `1c9c292`.

| Path | Median time to restore | Largest main-actor heartbeat gap |
| --- | ---: | ---: |
| Reference migration | 2,169.4 ms | 194.4 ms |
| Background migration | 2,151.2 ms | 18.6 ms |

Every migrated index reopened with 10,000 records and the archive
matched the input bytes. A separate malformed-index variant also
kept an exact archive before starting an empty history. That variant
took approximately 42 ms to recover with a maximum 8.0 ms heartbeat
gap across the reference and candidate. The 408 Swift tests passed,
including graphical-path migration and protection for a newer file
written after the migration read.

## Other persisted state

The active plan and step outcomes are saved on plan changes and
workflow progress. A successful step checkpoints its outcome, and
workflow summary generation checkpoints the final state. Seven
repeated writes and reads per synthetic plan measured the current
agent state store:

| Steps with outcomes | Bytes | Median atomic save | Median decode |
| --- | ---: | ---: | ---: |
| 4 | 2,989 | 0.33 ms | 0.17 ms |
| 32 | 20,819 | 0.77 ms | 0.62 ms |
| 250 | 159,835 | 2.69 ms | 4.20 ms |

Run-bundle finalization writes a manifest for the run and includes
the child tool's provenance when available. The backend builds and
writes that manifest in its subprocess. Three known-answer Core
manifests were 1,869 to 2,000 bytes. In seven runs per synthetic
case, building and writing manifests for 4, 64 and 512 generated
artifacts took median times of 1.2, 8.0 and 54.3 ms. Those manifest
files were 4,109, 25,840 and 188,535 bytes. The measurements include
hashing the small fixture artifacts.

The agent state and manifest measurements support keeping the
current checkpoint schedule for the observed workloads. The job
history retains its queue, start and terminal checkpoints. Batching
or compacting those writes would need measurements of workflow start
latency and a recovery test for the proposed checkpoint boundaries.
