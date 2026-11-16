# Recent run log excerpts

This checkpoint covers log restoration and rendering within PERF.08.
The reference was `74d61de`. Jobs and the Results summary now show up to
120 recent lines within 16 KiB of text per stream. A notice indicates
when the displayed text is an excerpt. The reveal action uses the
existing artifact containment check to select the retained file in
Finder. Failure messages also have a bounded display.

The shared reader restores the beginning and end of large regular log
files using bounded reads, including the final tool envelope when one
is present in the retained tail. The run files remain untouched during
restoration. Missing and empty logs retain their distinct behavior.

## Local comparison

The same synthetic capability was run through WorkbenchStore in the
reference and candidate on Apple Silicon, macOS 27.0.1, with the macOS
26.5 SDK. It wrote fixed ASCII records and a final marker to each stream.

| Stream | Bytes emitted | Bytes retained in the run in both builds | Restored bytes before and after | Final marker restored before and after |
| --- | ---: | ---: | ---: | --- |
| stdout | 6,120,024 | 4,194,393 | 512,000 → 512,089 | absent → present |
| stderr | 680,024 | 680,024 | 512,000 → 512,088 | absent → present |

The retained stdout includes a truncation marker and omits part of the
process output. The extra bytes in the restored strings are the
bounded-read notices. The app was also opened with an isolated synthetic
history containing the complete fixture files. The Jobs accessibility
tree exposed 119 numbered lines and the final marker for each stream,
both excerpt notices, and both reveal actions. The synthetic files and
ordinary app state matched their pre-test hashes. All 394 Swift tests
passed, including the existing process-tree, timeout and cancellation
tests. This comparison does not measure frame time or process RSS.

PERF.08 remains open for incremental retention of complete redacted
logs, search and copy from file, and verification under sustained output.
Existing Support Bundles retain their bounded diagnostic sidecars.
