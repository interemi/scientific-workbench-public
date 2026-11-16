# Run cancellation and application quit

PERF.12 uses one active scientific job at a time within a Workbench
instance. Enabled steps in a reviewed workflow run in order. An
overlapping direct request returns before creating another job or
starting a process. A retry can start after the first job reaches a
terminal state and records its source job.

Cancel Run signals the owned process group and preserves partial
evidence. A cancellation while the launch check is suspended also
prevents that command from starting. A later request can still run.
During normal macOS Quit, the app stops admitting jobs, shuts down the
scientific and support process runners, and waits for the job and
workflow to save their final state before allowing the app to exit.
Support subprocesses include diagnostics, the skill router, and the
local clients for Ollama and Codex. Closing an individual window can
leave the app running. Force Quit can interrupt evidence retention.

## Local verification

The isolated GUI comparison used debug builds on an Apple M1 Pro with
macOS 27.0.1. The fixture allocated 16 MiB in each of three Python
processes and wrote a distinct stdout marker from each process. The
three processes had a combined RSS of 81,120 KiB in one candidate
sample. The sum includes shared pages. This sample does not establish
a memory budget for scientific backends.

| Scenario | Observed result |
| --- | --- |
| Quit during a run at the reference revision `fa43c8d` | The persisted job was still marked running and its stdout file was missing. The three recorded PIDs were absent at the later check. |
| Start a second job while the first is running | The GUI disabled Run Capability. A separate Swift test submitted an overlapping request directly and verified that the store kept one job. |
| Cancel Run | The parent, child and grandchild PIDs were gone. The cancelled job and all three stdout markers were available in its run folder. |
| Retry and Quit | The retry used a distinct process group and run folder. AppKit deferred termination and approved it after cleanup. All three PIDs were gone after exit. The two saved jobs were cancelled, with their partial captures and recovery notes retained. |

All 404 Swift tests passed, including cancellation during launch
preparation, store shutdown, and the existing timeout and process
isolation tests. The process-group smoke passed its cancellation and
timeout scenarios, including survival of an unrelated fixture process.
All six headless planner smoke scenarios passed. The ordinary state file and preferences hashes
matched before and after. The tests used local fixture processes and
an isolated preferences session. Backend-specific memory and I/O
limits remain open.
