# Guided input review responsiveness

Sky Crossmatch and Legacy Report Evidence Mapping previously
classified attached paths while SwiftUI evaluated the forms. The
crossmatch form also parsed its catalog samples when the selection
changed. The report form parsed every attached evidence JSON and
checked for `main.tex` on the main actor.

The forms now await a serial background actor for those reads and
display the review for the current attachments and selection. A
superseded request discards its result. The report form rechecks the
selected scaffold on that actor before launching a run. Coordinate
mapping, units confirmation, provenance and role validation retain
their existing checks.

## Local component comparison

The reference was `a0b97fc`. Debug probes linked the corresponding
SwiftPM objects and ran seven trials per version on the same Apple
M1 Pro with 16 GiB of RAM, macOS 27.0.1, Swift 6.4 and SDK 26.5.
The reference probe called the synchronous inspection services on
the main actor. The revised probe awaited classification and review
through the new loader and measured a task scheduled on the main
actor at 5 ms intervals.

| Synthetic workload | Reference median, synchronous | Revised median, elapsed | Longest revised heartbeat interval |
| --- | ---: | ---: | ---: |
| Two 2,038,924-byte CSVs, 25,845 sampled rows each | 242.17 ms | 248.70 ms | 7.65 ms |
| Three 2,938,946-byte evidence JSONs | 77.61 ms | 89.26 ms | 7.65 ms |

The revised elapsed times include classification and actor dispatch.
The main-actor task executed 32 to 36 times during catalog review
and 11 to 13 times during evidence review. These measurements cover
component scheduling. Display presentation timing remains unmeasured.
Both versions returned the expected columns, row counts and provenance.

## Verification

- All 411 Swift tests passed. The catalog test checked cancellation
  and the report test checked that preparation rejects a scaffold
  whose `main.tex` disappeared after inspection.
- In the isolated app, both CSVs showed 25,845 sampled rows. Selecting
  the coordinate columns and confirming decimal degrees enabled the
  run control. Detaching a catalog cleared the confirmation and
  disabled execution.
- In the report form, the selected scaffold and evidence provenance
  appeared. Detaching one evidence JSON removed its row and cleared
  confirmation. The form continued to require a valid role mapping.
- SHA-256 checks matched for the five benchmark files, all six GUI
  input files, the 22 ordinary app-state files and the ordinary
  preferences.
