# Idle and active application activity

PERF.11 measured the debug executable from `687cf8d`, also used for the
[large history graphical check](PHASE5_HISTORY_GUI_2026-11-09.md), on an
Apple M1 Pro with macOS 27.0.1. The isolated app ran one synthetic job
for about 151 seconds. The fixture produced a stdout checkpoint every
two seconds and exited with code zero. Its 75 checkpoints and final
status record were retained.

The following are single 25-second intervals. CPU is the app process's
user and system time divided by elapsed time. Interrupt wakeups and
energy estimates come from macOS process resource counters. The
samples exclude the Python child and other processes.

| Application state | CPU | Interrupt wakeups | Process energy estimate |
| --- | ---: | ---: | ---: |
| Dashboard before a run | 0.0095% | 12 | 12.7 mJ |
| Jobs showing the running job | 0.0394% | 194 | 21.7 mJ |
| App hidden during the run | 0.0505% | 174 | 20.1 mJ |
| Dashboard during the run | 0.0196% | 151 | 8.7 mJ |
| Jobs shortly after completion | 0.2991% | 2,683 | 4,607.7 mJ |
| Jobs after settling | 0.0001% | 9 | 0.1 mJ |

Activity Monitor displayed an Energy Impact of 0.2 during the run and
0.0 after settling. The process counters and Energy Impact use different
scales. The elevated first post-completion interval had settled by the
next sample. These intervals establish observations for the tested
scenario. They leave the transient's cause and run-to-run variance open.

The running Jobs view advanced its elapsed clock and kept cancellation
available. Returning to it after hiding the app showed the elapsed time
for the same job. Once the job succeeded, the live clock was replaced
by completed status and a recorded duration. The external tool exposed
no structured live progress to the app.

The source audit found a one-second view timer conditional on a running
job. The process runner's 100 ms wait applies only while a process group
is active. Its checks enforce the output bound, timeout and cancellation.
Environment expiry is a one-shot task. The search delays start on
input. The settled observations support retaining the current cadence.
A change to active process supervision would need repeatable evidence
of a cost and verification of those limits.

The app used an isolated preferences session and a separate output
directory. Hashes of the 22 ordinary state files and the preferences
digest matched. The executable was the same one verified by 402 Swift
tests before the experiment.
