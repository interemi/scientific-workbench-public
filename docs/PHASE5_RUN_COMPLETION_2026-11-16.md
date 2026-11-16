# Run completion and evidence writes

After the subprocess returns or is interrupted, Scientific Workbench
now writes capture files, reads the run bundle and prepares recovery
guidance on a background task. The job remains active until the app
can publish the terminal record. Jobs shows a saving indication
while that evidence is being prepared. Quit waits for capture and
job history persistence. The single-job guard also covers this work.

Cancellation can still stop an active subprocess or the remaining
steps of a workflow. Once the subprocess finishes, a standalone
job saves its evidence with the outcome known at completion. Any
cancelled or interrupted process retains the logs and files it
produced before stopping.

## Local comparison

The reference source was `197bfe6`. The reference probe used
debug product objects built at `b88f0e8`, which has the same
application source. Two probes ran on an Apple M1 Pro with 16 GiB
RAM, macOS 27.0.1, Swift 6.4 and SDK 26.5. Each probe completed
seven separate copies of a synthetic run with 1,500 small CSVs,
a summary and a manifest.

| Measurement | Reference | Revised |
| --- | ---: | ---: |
| Median completion work elapsed | 107.81 ms | 110.30 ms |
| Maximum observed main-actor heartbeat interval | Synchronous operation | 7.62 ms |
| Artifact records after finalization | 1,506 | 1,506 |

The revised elapsed time includes background task dispatch. A
task scheduled on the main actor at 5 ms intervals executed 14 to
19 times during each revised request. This measures scheduling
while the run bundle is processed. Display presentation and
subprocess execution are outside this measurement.

The 1,502 existing files in each copy preserved their SHA-256
values. The command, stdout, stderr and next-steps files had
identical bytes across the seven reference and revised pairs.
All 411 Swift tests passed, including cancellation, evidence
retention during quit, and complete redacted log retention.
