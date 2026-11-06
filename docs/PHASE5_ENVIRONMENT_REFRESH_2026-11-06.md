# Environment check reuse and invalidation

This change addresses PERF.05 and the overlapping environment refresh
part of PERF.13. It was verified locally against base `6e0d421` using
the existing SwiftPM test suite and an isolated macOS app.

## Session behavior

- An automatic and a manual check for the same configuration share
  one in-flight Python discovery and package diagnosis. A check for
  new paths waits for the canceled process group to stop before starting.
- An automatic check may reuse a completed result for ten minutes in
  the same app session. A one-shot timer marks the result expired.
  Visiting a section or reaching expiry does not launch a probe.
- Changing the configured Python or skill root, or reloading the
  registry, invalidates the previous result. A result from a superseded
  check cannot replace the diagnosis for the new configuration.
- Recheck Environment starts a fresh check whenever one is not already
  in progress. Use it after external package installs or updates.
  Changes performed outside the app at the same paths are picked up by
  a new check. The session result is kept in memory.
- Settings shows checking, current, expired and configuration-change
  states. Expired reports remain available as evidence, while the
  checklist asks for a fresh check. Workflow-specific preflight remains
  separate from this session result.

The macOS unified log records the check lifecycle under
`EnvironmentChecks`. Its messages cover start, completion, joining,
reuse, expiry and invalidation. They contain no configured paths,
Python output or package details.

## Verification

A synthetic interpreter counted invocations during overlapping
startup and explicit refresh. The previous source produced
`status, status, doctor`. The new source produced `status, doctor`
with both callers receiving the completed check. The test holds
the first probe open so the overlap is reproducible. The comparison
measures subprocess count.

The expiry regression reused a current result, forced a new explicit
check, observed expiry without an extra process, then started a fresh
automatic check. Another regression changed Python and the skill root
while the old status process was running. The old process produced no
doctor result. The new configuration completed, and registry reload
invalidated that result. The full Swift suite passed 387 tests.

An isolated app with a 15-second test lifetime used the same production
logic and the bundled registry. A manual toolbar refresh joined the
held startup check. Dashboard, Capabilities, Jobs and Settings kept
the count at one `status` and one `doctor`. Settings showed the
expired state and then a current diagnosis after Recheck Environment.
Changing the synthetic interpreter path cleared that diagnosis.
Restoring it and rechecking verified the new result. The UI run recorded
three completed check pairs in total, one join, one expiry and one
invalidation. The test runner log also recorded reuse.

These are synthetic probe results. The 22 ordinary app-state files
and ordinary preferences matched their pre-test hashes. No packages
were installed or changed.
