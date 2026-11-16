# History and artifact paging

This checkpoint covers history reading, list paging, indexed search and
retention within PERF.09. The reference was `8fd5b2a`.

Jobs and Results present collections of up to 250 items without paging.
Larger collections show 100 items per page and an explicit range and
total. The threshold keeps the previously tested small history on its
existing interaction path. Search still addresses all jobs and their
artifact metadata. A search actor prepares text and artifact categories
once per job revision and discards superseded requests.

GUI launch and manual reload now decode and hydrate history off the
main actor. Reload preserves an existing job selection. Results uses
the existing path-based artifact selection and shows its page when the
selected run changes. The history stays at schema 2. Persisting no
longer discards all records beyond the first 250. A save that exceeds
the existing 128 MiB read limit leaves the existing index in place and
reports an error.

## Local scale measurements

A debug component probe used the production stores and filters with
synthetic schema-2 histories on an Apple M1 Pro, macOS 27.0.1, and
SDK 26.5. Each run had a CSV. The 10,000-job fixture also had one run
with 2,002 artifacts. Search measured the unique CSV match in the
oldest job. The reference search and the prepared-index search use
medians of three queries on already hydrated records. The first
indexed query includes construction. Read and hydrate are a single
observation per workload.

| Jobs | Reference JSON decode | Reference sidecar hydration | Reference query | First indexed query | Prepared-index query |
| --- | ---: | ---: | ---: | ---: | ---: |
| 250 | 8.5 ms | 54.2 ms | 5.1 ms | 4.7 ms | 0.6 ms |
| 1,000 | 23.1 ms | 199.0 ms | 20.4 ms | 18.8 ms | 2.3 ms |
| 10,000 | 221.5 ms | 2,260.6 ms | 224.8 ms | 199.1 ms | 22.4 ms |

The reference saved 250 of the 10,000 records. The candidate saved
and reopened all 10,000 IDs in the same order. That candidate write
took 206 ms, versus 45 ms for the truncated reference write. The
comparison used separate disposable output files. Synchronous writes
remain a PERF.14 concern.

In the isolated GUI, the reference reload action and accessibility
snapshot took approximately 2.8 seconds in one observation. The
candidate displayed 10,000 jobs, moved to rows 101–200, scrolled
within that page, and found the oldest run by its artifact filename.
The first snapshot showing that search result took approximately
0.9 seconds, versus 2.0 seconds in the reference. Those observations
include automation overhead and are separate from query timing.
The display locked before verification of the graphical reload and
Results pages finished.

The 400 Swift tests passed. They cover page boundaries, query
equivalence and invalidation, and selection and byte preservation
after reloading a 301-record history. All synthetic fixture files,
ordinary app-state files and preferences matched their pre-test hashes.
PERF.09 remains open for demand-loaded details and completion of the
10,000-job GUI checks. The restore still hydrates sidecars in the
background before presenting the complete searchable history.
