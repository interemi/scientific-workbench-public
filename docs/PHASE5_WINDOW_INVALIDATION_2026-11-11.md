# Window updates during job log changes

The title bar, workflow journey bar and inspector now compare the
values they display before SwiftUI reevaluates their bodies. The
title and journey bars still route actions through the shared store.
The inspector reads the environment, counts and selected section or
capability from its display values.

## Local comparison

The reference was `1450600`. Two instrumented SwiftPM debug builds
ran on the same Apple M1 Pro with 16 GiB of RAM, macOS 27.0.1, Swift 6.4
and SDK 26.5. The builds used the same trace driver, 25 synthetic jobs
and 55 catalog routes. Each ran in a separate preference session.
The test window was wide enough to show the inspector.

After navigation settled, the driver changed only a synthetic job's
stdout five times per section, 140 ms apart. It then marked the job
running, restored its status and switched from Jobs to Chat. No
scientific process was started.

| Scenario | Title bar bodies | Journey bar bodies | Inspector bodies |
| --- | ---: | ---: | ---: |
| Five log updates in Chat | 5 → 0 | 5 → 0 | 5 → 0 |
| Five log updates in Dashboard | 5 → 0 | 5 → 0 | 5 → 0 |
| Five log updates in Capabilities | 5 → 0 | 5 → 0 | 5 → 0 |
| Five log updates in Jobs | 5 → 0 | 5 → 0 | 5 → 0 |
| Job starts and returns to its previous status | 2 → 2 | 2 → 0 | 2 → 0 |
| Navigate from Jobs to Chat | 1 → 1 | 1 → 1 | 1 → 1 |

The root still reevaluated once per measured log change, as did
the active Chat, Dashboard or Jobs content when applicable. Jobs
continued to reevaluate on log changes. The journey bar's display
values still check summary-file availability when a summary path
exists. This trace measures body evaluations. Layout, drawing and
frame presentation remain outside its scope.

## Verification

- The instrumented candidate hid and restored the inspector and its
  environment and job count. Its journey bar opened Jobs and Results.
- Both sessions preserved all 126 synthetic file hashes. The 22
  ordinary app-state files and ordinary preferences also matched.
- All 411 Swift tests passed on the non-instrumented candidate.
