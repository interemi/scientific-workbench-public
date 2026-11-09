# Phase 5 capability catalog search

PERF.10 compares the catalog at `8340beb` with the indexed implementation on
the same Apple Silicon Mac running macOS 27.0.1. Both measurements used
SwiftPM debug builds and the same bundled registry of 55 user-facing routes.

When the registry changes, the app prepares searchable text and group order
for each catalog. The view reuses the matching groups until the query,
facets, or registry changes. Typing waits for a 75 ms quiet period. A
superseded task is cancelled, and the view checks the registry and current
query before applying results. While an update is pending, it holds the
previous rows in place, disables their interaction, and shows a status in the
space occupied by the result count. Maintenance keeps its own phrase search.

## Component comparison

The probe repeated seven search strings 500 times per pass. It compared the
previous filtering and grouping algorithm with the index in five alternating
paired passes. Both returned the same ordered route IDs for each query and
51,000 row matches per pass.

| Measurement | Previous algorithm | Indexed |
| --- | ---: | ---: |
| Median for 3,500 queries and grouping | 1,383.657 ms | 659.104 ms |
| Time per query from the median pass | 0.395 ms | 0.188 ms |

Index construction took 4.876 ms in the paired probe. The measured matching
and grouping cost fell by 52.4%. The 75 ms typing delay, SwiftUI updates and
time to present a frame are outside the component timing.

## Verification

All 402 Swift tests passed. The new tests compared the index with the previous
matcher across empty, partial and complete queries, checked facet and group
ordering, and confirmed a cancelled query could not return a result.

In an isolated graphical instance, typing `fits` returned 11 routes.
Replacing the query with `profile CSV` returned one row and selected its
matching detail. An unmatched query returned zero rows, and clearing the
query and facets restored 55 routes. The Analyze data facet returned 12
routes, and combining it with `inspect FITS` returned zero. The Dashboard
shortcut reopened the FITS task despite that conflicting filter. Maintenance
found `portable_smoke_test` without changing the user catalog query. These
observations verify the settled views. Frame-by-frame stability and
keystroke-to-frame latency remain unmeasured.

The 22 ordinary application state files and the preferences digest matched
before and after verification. The Swift tests and graphical checks used
isolated output directories. Hosted CI remains part of the Phase 5 batch.
