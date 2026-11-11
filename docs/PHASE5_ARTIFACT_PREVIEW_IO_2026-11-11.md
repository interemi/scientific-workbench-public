# Results preview responsiveness

Results previously inspected the selected artifact in the SwiftUI body
and again before loading a non-image preview. Both operations could parse
the run manifest on the main actor. PDF preview creation also rendered
the first page on the main actor and encoded the thumbnail as TIFF.

The preview loader now inspects the artifact and prepares its preview
away from the main actor. SwiftUI displays the metadata and thumbnail
for the current request, and discards a canceled or superseded request.
The PDF thumbnail is passed as a `CGImage`. The comparison summary also
reads its metadata away from the main actor. Table paging and the
explicit Finder and TextEdit actions check file eligibility without
reparsing the manifest. Preview eligibility still requires a regular
file whose resolved path is within its run directory.

## Local comparison

Two debug probes exercised the previous Results preview path
and the revised loader. The reference probe used objects built at
`d1b0c39`. The Results view and the two preview services were
identical through `626540c`. Both probes used an Apple M1 Pro with
16 GiB of RAM, macOS 27.0.1, Swift 6.4 and SDK 26.5. Each probe
loaded the same synthetic three-page, 990,926-byte PDF seven times.
The PDF was the last of 2,001 outputs in a 250,137-byte manifest.
The previous probe called both metadata inspections and built the PDF
payload on the main actor. The revised probe awaited the new snapshot
and checked the recorded hash, first-page note, and thumbnail dimensions.

| Measurement | Previous path | Revised loader |
| --- | ---: | ---: |
| Median request duration, seven trials | 99.51 ms | 56.97 ms |
| First request | 189.55 ms | 112.89 ms |
| Maximum observed main-actor heartbeat gap | Synchronous operation | 6.37 ms |

The revised median was 42.7% lower. A task scheduled on the main actor
at 5 ms intervals ran 9 to 18 times during each revised request. The
heartbeat measures whether the main actor serviced the task during the
component probe. Display presentation timing and larger documents
remain unmeasured.

## Verification

- All 411 Swift tests passed, including the tests for PDF thumbnail
  creation, file preservation, run containment, and cancellation.
- In an isolated app session, Results showed the first page and
  recorded hash of the PDF and switched to the expected Markdown
  content when selected. The comparison sheet displayed both previews
  and reported their differing recorded hashes.
- SHA-256 inventories matched before and after for the benchmark
  inputs, the four files in the isolated app session, and the ordinary
  application state and preferences.
