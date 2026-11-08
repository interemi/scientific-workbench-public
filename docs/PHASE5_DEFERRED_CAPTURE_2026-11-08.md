# Load run capture when opening a job

This checkpoint follows the [history scale measurement](PHASE5_HISTORY_SCALE_2026-11-08.md).
For a graphical restore or reload above 250 jobs, the history still
indexes artifacts, tool summaries, status, tags and next steps. It
loads the command and log captures from disk when Jobs or the Results
summary displays that job. Old runs with an envelope only in stdout
still contribute that metadata to search.

The detail view reads bounded capture off the main actor, cancels a
superseded request and only displays data for the current job and
history revision. It overlays that job's command and log text without
replacing the search record or rewriting the index. If a capture file
is missing, the detail uses the saved excerpt. The configured secret
redaction applies before the detail is displayed. Small histories
retain the eager behavior. Schema 2 and existing sidecars are unchanged.

## Local evidence

A debug component probe compared eager and deferred hydration on the
same Apple M1 Pro, macOS 27.0.1 and SDK 26.5. It alternated the order
over three paired passes. Timings exclude JSON decode and view layout.

| Fixture | Eager median | Deferred median | Capture bytes loaded into restored records |
| --- | ---: | ---: | ---: |
| 1,000 jobs with separate summaries and captures | 429.0 ms | 333.8 ms | 32,814,000 → 0 |
| 10,000 jobs with light sidecars | 2,075.9 ms | 1,847.0 ms | 0 → 0 |

Both paths returned identical tool names, short summaries and relative
artifact paths for every job in each fixture. The deferred path
then recovered the exact command and final stdout and stderr lines
for a selected job. The 400 Swift tests passed. The large-history
regression verifies selection, the legacy stdout-envelope fallback,
redaction, the saved excerpt fallback and unchanged index bytes.
Synthetic files and ordinary app-state hashes matched before and after.

PERF.09 still needs its outstanding graphical checks for Results page
selection and reload with 10,000 jobs. The earlier screen lock
interrupted those checks. The next run should also verify opening a
deferred detail and switching quickly between jobs. The timings
measure the component and do not establish frame latency.
