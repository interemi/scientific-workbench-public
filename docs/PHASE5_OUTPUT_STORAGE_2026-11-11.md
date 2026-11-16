# Output storage and preview cache

Settings → Output Storage measures logical file sizes for known runs
inside the selected output folder. It reports retained stdout and
stderr, files under each run's `logs/` folder, and files under
`previews/`. The scan reads file metadata on demand off the main actor.
Repeated history entries for the same folder count once. The measure
skips missing and out-of-scope folders, and ignores symbolic links
inside the measured folders. The totals describe the files reviewed.
Free space on an APFS volume also depends on allocation, compression
and shared blocks.

Each process stream has a 256 MiB temporary output threshold. The
runner stops a process that exceeds its capture limit and retains a
bounded prefix with a notice. Completed and interrupted redacted logs
stay with the run folder, including the log for an unresolved failure.
Saved quicklooks, PDFs and other workflow products also stay with
their runs.

The app can reuse one decoded raster thumbnail in memory, with a
12 MiB cache limit. It checks the source file identity and version
before reuse. Settings shows the cached byte count and the change
after clearing it. The confirmation targets the entry the user
reviewed. When that entry changes before confirmation, the app shows
the current size for a new review. Reopening an artifact recreates
its thumbnail as needed.

## Local verification

A debug component probe used three synthetic 8,192 × 8,192 images
on an Apple M1 Pro, macOS 27.0.1 and SDK 26.5. It compared one cold
decode and the median of five repeat requests in each build.

| Source | Reference cold | Candidate cold | Reference repeat | Candidate repeat |
| --- | ---: | ---: | ---: | ---: |
| PNG | 429.7 ms | 431.9 ms | 391.9 ms | 0.112 ms |
| TIFF | 146.6 ms | 147.7 ms | 146.2 ms | 0.092 ms |
| JPEG | 99.5 ms | 100.3 ms | 65.4 ms | 0.089 ms |

Repeated requests returned matching thumbnail bytes within each
build and left the sources byte-identical. Each candidate thumbnail
used 10,240,000 cached pixel bytes. These observations measure the
loader and exclude window rendering. The cache byte count describes
its retained pixel data. Visible views can also retain a thumbnail.

In an isolated SwiftUI app, one synthetic failed run reported 53 bytes
of retained process logs, 24 bytes of additional logs and a saved
preview displayed as 2 MB (1,966,144 file bytes). Cancel preserved the
displayed 9.8 MB cache. Confirmation reduced the cache to zero while
the file totals stayed stable. Reopening the preview regenerated the
1,600 × 1,600 thumbnail and restored the displayed cache size.

All 411 Swift tests passed, including live file-size measurement,
protected input and link handling, versioned reuse, confirmation
against the reviewed entry, and preservation of a retained failure
log. The six synthetic GUI file hashes and ordinary app state and
preferences matched before and after.
