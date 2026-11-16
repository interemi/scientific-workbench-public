# Bounded table artifact previews

This checkpoint verifies the PERF.07 preview path for UTF-8 CSV and TSV
and for the supported Astropy ECSV header form. It also moves table
parsing off the UI actor, one part of PERF.02.

Results and artifact comparison open a sequential sample. Next Page
reads the next records from a byte offset. First Page starts again.
The preview reads at most 128 KiB per page, retains up to 80 complete
records, and displays the first 16 columns with lazily rendered rows.
It keeps quoting, empty cells and multiline fields together. The UI
labels the range and the column and cell limits when they apply.
Numbered records include any header. Use the workflow output for the
full data-row count.

An ECSV disclosure shows the source metadata, including units when
present. The reader supports the standard comment header produced by
Astropy with its space or comma delimiter. Text Sample preserves a
bounded textual route for metadata, unsupported dialects and very long
records. Reveal opens the containing folder for full-file inspection.
Cursor reuse checks the file identity, size and modification time.
When the file changes, First Page reads the current file. Preview text
uses the existing configured-secret redaction policy. If a configured
secret is present in a raw table record, the preview hides that record's
values before displaying cells.

## Local measurements

The reference was `65e7b2e`. The benchmark used the production loaders
in optimized Swift component probes on an Apple M1 Pro with macOS
27.0.1 and the macOS 26.5 SDK. Each fixture and loader had five fresh
processes, alternating the loader order. The reference produces a
text excerpt. The candidate produces a structured page and validates
its resolved path. Values below exclude view layout, text selection and
time to first frame.

| Synthetic CSV | Reference median load | Candidate median first page | Reference text bytes | Candidate cell text bytes |
| --- | ---: | ---: | ---: | ---: |
| 1,000 data rows, LF | 1.189 ms | 2.456 ms | 2,304 | 2,075 |
| 1,000,000 data rows, LF | 1.436 ms | 2.441 ms | 2,304 | 2,075 |
| 1,000,000 data rows, CRLF | 1.755 ms | 2.724 ms | 80,000 | 2,075 |

The candidate does more parsing work. Its bounded record count and
cell payload are stable across these fixtures. The previous CRLF
sample contained 2,493 newline bytes despite the intended 80-line
limit. Text Sample now applies that limit to CRLF as well.

An independent Python CSV reader and the bundled table-profile workflow
both returned exactly 1,000,000 data rows and three columns for each
large fixture. The profile retained its summary and manifest.
An isolated app on the same Mac displayed records 1–80 and 81–160,
then returned to the first page. It showed the third column by
horizontal scrolling, the ECSV unit `Jy`, the text-sample truncation
message, and the end of the small CSV. The two comparison panes kept
their pages independent.

The 391 Swift tests passed, including record boundaries, file replacement,
outside-folder links and configured-secret redaction. Synthetic inputs,
the ordinary app state and preferences matched their pre-test hashes.
The GUI check was on the development Mac. Timing and memory bounds for
live process logs are separate PERF.08 work.

Format references

- [CSV record and field quoting](https://www.rfc-editor.org/rfc/rfc4180.html)
- [Astropy ECSV metadata and delimiter](https://docs.astropy.org/en/stable/io/ascii/ecsv.html)
