# Navigation and capability catalog invalidations

This local comparison covers two measured view dependencies in PERF.03.
It also covers repeated filtering within a catalog update, one part of
PERF.10.

## Method

The reference was commit `09c4ef7`. The candidate changed the sidebar
and catalog to compare their displayed state before SwiftUI reevaluates
their bodies. The catalog reuses a single filtered collection for the
rows, count, and displayed detail in each body evaluation. The detail
panel still observes the store for execution state, input and argument
changes. Navigation and selection continue to write to the same store.

Two isolated debug builds on an Apple M1 Pro running macOS 27.0.1 used
the macOS 26.5 SDK, SwiftPM native, the same 25 synthetic jobs, and the
same 55-route registry. Test-only instrumentation counted calls to
`body` and to the catalog filter. With each listed section visible,
the probe changed a synthetic job's log five times, spaced by 140 ms.
A separate catalog scenario triggered one environment refresh with a
synthetic Python probe and no job change. Counts cover the marked
interaction windows after navigation settled.

## Results

| Scenario | Sidebar body | Catalog body | Catalog filter | Relevant detail or active view body |
| --- | ---: | ---: | ---: | --- |
| Job log while in Chat | 5 → 0 | — | — | Chat 5 → 5 |
| Job log while in Dashboard | 5 → 0 | — | — | Dashboard 5 → 5 |
| Job log while in Capabilities | 5 → 0 | 5 → 0 | 56 → 0 | Capability detail 5 → 5 |
| Environment refresh while in Capabilities | 2 → 0 | 2 → 0 | 23 → 0 | Capability detail 2 → 2 |
| Job log while in Jobs | 5 → 0 | — | — | Jobs 5 → 5 |

Jobs displayed the fifth log update. In the candidate app, searching
for `profile csv` selected the sole matching route and showed its
detail. A conflicting task filter showed the empty state, and Clear
Filters restored all 55 routes. Maintenance retained its own query and
selected route after switching sections. Opening the FITS task from
Dashboard cleared an incompatible catalog query and selected the
requested route. The 387 Swift tests passed. All 126 synthetic files,
the 22 ordinary app-state files, and ordinary preferences matched their
pre-test hashes.

The counts measure SwiftUI body evaluation and filter invocation.
They leave layout, frame latency, and painting unmeasured. The root,
title bar, Chat, and Dashboard still reevaluated in the observed
scenarios. SwiftUI Instruments was unavailable on the test Mac, and
the broader PERF.03 criterion remains open. PERF.10 still requires
measurement of search under representative load and review of stale
results where searches run asynchronously.
