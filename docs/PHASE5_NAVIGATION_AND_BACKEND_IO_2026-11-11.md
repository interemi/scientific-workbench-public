# Navigation comparison and backend I/O

This follow-up compares the source immediately before Phase 5
(`a5a48e3`) with the Phase 5 candidate (`32dd270`). Both debug
builds used Swift 6.4, SDK 26.5 and an Apple M1 Pro Mac with 16 GiB
RAM running macOS 27.0.1. The builds ran in separate isolated
preferences sessions with the same 250 synthetic jobs, 55 catalog
routes, Core interpreter and AppKit trace.

## Navigation

The user path alternated from Jobs to the unfiltered capability
catalog. The observation checked the visible destination and its
expected job or route count after every action. The capture order
was reference, candidate, candidate, reference in blocks of six
round trips. The first round trip per build was a warmup.

| Action to event | Reference median | Candidate median | Reference p95 | Candidate p95 |
| --- | ---: | ---: | ---: | ---: |
| SwiftUI representable update, 22 transitions | 59.8 ms | 59.4 ms | 61.2 ms | 63.8 ms |
| AppKit marker draw, 22 transitions | 190.5 ms | 191.9 ms | 221.2 ms | 219.3 ms |

The maximum marker-draw interval was 222.1 ms in the reference
and 223.2 ms in the candidate. The observed p95 remained within
the variation observed in the two series. The previous 150 ms
exploratory target remains an improvement target. The reference
comparison supports a 250 ms p95 regression limit for this
workload on this Mac, with approximately 13% margin above the
reference. The candidate passed that limit. The marker measures
an AppKit drawing event associated with the destination state.
Actual compositor presentation timing remains unmeasured.

Both sessions preserved all 1,251 synthetic file hashes. Ordinary
application state and preferences matched the pre-test inventory.

## Backend I/O on synthetic Core cases

The [known-answer workflow](../script/check_scientific_known_answers.py)
ran three more times with fresh generated inputs and plotting
directories. A wrapper read the macOS process counters
(`RUSAGE_INFO_V6`) immediately after the Python command returned,
before process exit. All three runs passed the existing scientific
and artifact-hash assertions.

| Case | Maximum physical footprint | Maximum disk read | Maximum disk write | Local regression limits for read and write |
| --- | ---: | ---: | ---: | ---: |
| FITS 8 × 8 with a generated PNG | 119.4 MiB | 21.4 MiB | 344 KiB | 32 MiB / 1 MiB |
| Sky crossmatch of two 2-row CSVs | 70.5 MiB | 13.9 MiB | 16 KiB | 24 MiB / 128 KiB |

The two later runs of each case reported zero attributed disk reads
with system caches warm. Writes were identical across the three
observations. The thresholds include margin for the observed
first-run reads and filesystem allocation differences. These
reference limits apply to the small fixtures on the development Mac.
They measure attributed physical I/O of the selected processes.
Logical bytes, larger datasets and optional backends need separate
measurements. The app runs one scientific job at a time and
retains the existing per-stream capture limits.
