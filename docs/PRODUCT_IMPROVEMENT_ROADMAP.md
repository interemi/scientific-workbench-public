# Scientific Workbench product improvement roadmap

This is the working plan for improving the **existing** public source repository
and the local macOS app. It is a plan, not a list of shipped features or a
promise of scientific validity. The original development pathway remains in
[`ROADMAP.md`](../ROADMAP.md); dated source-validation limits remain in
[`PUBLIC_READINESS.md`](PUBLIC_READINESS.md). GitHub Issues track the active
work, pull requests carry reviewed changes, and Actions records validation for
each commit.

## Starting point and decision rules

The repository already publishes the SwiftUI app source, five bundled skills,
installation instructions, and automated macOS checks. The
[capability setup matrix](CAPABILITY_SETUP_MATRIX.md) currently classifies 55
user-facing routes as 17 `app_ready`, 19 `app_ready_partial`, 7
`blocked_optional`, 10 `cli_only`, and 2 `not_applicable_to_app`. These are
different access and readiness levels, not 55 complete graphical workflows.
There is no signed or notarized app release. Manual use on another Mac has not
been verified; hosted CI does not replace that check.

The product direction is a small set of complete, inspectable local workflows:
one for tables, one for astronomy/FITS, and one for a mixed folder that ends in
a report. The [user-needs desk research](USER_NEEDS_DESK_RESEARCH.md) frames
the specific tasks and audience as hypotheses; no interview-based validation
has occurred. Use synthetic or explicitly licensed
data, keep original inputs unchanged, and tie conclusions to recorded artifacts.
A technical PASS never means that a scientific interpretation is correct.

We work through the phases below in order. A measured bottleneck may justify
bringing forward one performance fix. Binary distribution and large platform
extensions are conditional decisions. Validate on the available Mac and with
the existing GitHub Actions checks; record the exact commit, environment,
fixtures, and unverified systems. No second Mac is required to keep improving
the source.

Prefer syncing the public default branch when a phase is complete. If a phase
is long, use an interim pull request for a coherent batch of at least four
related improvements, with its own reviewed snapshot and passing checks.
Keep unfinished phase criteria open in GitHub Issues; a green interim PR does
not close the whole phase.

## Phase 1 — Maintain a trustworthy public repository

These items are **partly addressed** in the current source, but none should be
called closed solely because the repository is public. Each needs an issue
with evidence against its own completion criterion.
The [2026-09-29 Phase 1 checkpoint](PHASE1_CHECKPOINT_2026-09-29.md) records
local verification and the limits still awaiting exact-commit CI and review.

| ID | Work and completion evidence |
| --- | --- |
| P0.10 | Keep private vulnerability reporting reachable; provide safe bug/feature templates and a supported-version policy. Verify the private route without posting a vulnerability publicly. |
| P0.02 | Reconcile all 55 route states across source, app, README, and documentation in a repeatable check; never present partial, optional, or CLI routes as ready graphical actions. |
| P0.12 | Keep the current plan, historical milestones, and dated readiness record consistent; link each completion claim to evidence. |
| P0.07 | Before each public update, record the reviewed paths, included/excluded material, hashes, provenance, and privacy checks for the exact snapshot. |
| P0.08 | Review origin, license, notices, and redistribution conditions for every new dependency, skill, fixture, and asset. |
| P0.09 | Keep retained public material in English, validate links and portable commands, and verify an installation tutorial without coaching when a participant is available. |
| P0.05 | Re-run relevant Core/Full installation and gates on the available Mac; record hardware, macOS, Python, lock, commit, and scope. |
| P0.06 | Limit compatibility claims to observed systems and checks; mark other interactive Mac use as unverified. |

Exit: the current source, documentation, and GitHub checks agree on what is
available, how to report a problem, and what has actually been tested.

## Phase 2 — Choose a focused first audience and tasks

| ID | Work |
| --- | --- |
| P0.01 | Replace the proposed 5–8 interviews with [documentary research](USER_NEEDS_DESK_RESEARCH.md) into what such a round would investigate; publish sources, population limits, open questions, and a provisional audience decision. Do not invent participants. |
| P2.01 | Choose two or three astronomy tasks with a named user, example data, method, outputs, dependencies, and scientific limits. |
| P0.03 | Specify the table, astronomy, and mixed-document workflows with a complete GUI path, expected result, and known limits. |

Exit: a source-backed provisional user brief and three concrete workflow
specifications. Independent-user evidence remains pending wherever a later
acceptance criterion requires it.

## Phase 3 — Build repeatable examples and a local baseline

| ID | Work |
| --- | --- |
| P1.02 | Provide small one-click synthetic examples with known expected outputs and no optional account or backend. |
| P2.05 | Add reviewed scientific fixtures with units, tolerances, rejection cases, and unchanged-input checks. |
| P2.06 | Separate process success, artifact-contract checks, automatic QA, and human scientific review. |
| PERF.01 | Measure startup and main interactions with controlled local traces and record the tested machine. |
| PERF.16 | Measure Core/Full installation and first-use costs on the available machine and network. |
| P0.04 | Run the M104 usability protocol with synthetic fixtures on the available Mac; label independent acceptance pending if necessary. |
| P1.10 | Review keyboard, VoiceOver, contrast, dark mode, and window sizes on that Mac. |

Exit: reproducible examples, reviewed expected values, and a dated performance
and usability baseline.

## Phase 4 — Complete the first interface journey

| ID | Work |
| --- | --- |
| P1.01 | Make Home a launcher for the chosen tasks and a way to resume a run. |
| P1.03 | Explain Core versus Full and what external tools still require separate setup. |
| P1.04 | Show prioritized environment diagnosis and safe repair into a new environment. |
| P1.05 | Organize capabilities by user task, format, profile, readiness, and skill. |
| P1.06 | Show input, output, backend, network, consent, and dependency scope before execution. |
| P1.07 | Connect progress, cancellation, job evidence, retry, and results. |
| P1.08 | Let users inspect artifacts safely without running code or changing inputs. |
| P1.09 | Add useful search and explicit empty, blocked, running, and failed states. |
| P1.13 | Turn common errors into a diagnosis and safe recovery action. |
| P1.15 | Preserve the same run context from selection through plan, execution, and result. |
| P1.11 | Improve local Ollama setup while preserving a model-free deterministic route. |
| P1.12 | Publish short, version-matched guides for the selected workflows. |
| P1.14 | Publish real screenshots and a tour tied to an identified build. |

Exit: a new user can choose, prepare, run or cancel, and inspect a workflow
without losing the connection between its plan, job, and artifacts.

## Phase 5 — Optimize measured bottlenecks

| ID | Work |
| --- | --- |
| PERF.02 | Move disk, network, and scientific computation off the UI thread. |
| PERF.03 | Reduce broad SwiftUI invalidations when traces show unrelated redraws. |
| PERF.04 | Display the first screen before optional startup probes finish. |
| PERF.05 | Cache environment checks with explicit invalidation. |
| PERF.06 | Bound FITS/image preview memory and keep display processing separate from measurement. |
| PERF.07 | Sample or page large tables without hiding full-result counts. |
| PERF.08 | Bound in-memory log rendering and preserve appropriately redacted evidence. |
| PERF.09 | Page history and artifacts when measured scale requires it. |
| PERF.10 | Cancel stale searches and avoid repeated filtering per render. |
| PERF.11 | Reduce unnecessary polling and redraws, especially while idle. |
| PERF.12 | Limit concurrent work and propagate cancellation to child processes. |
| PERF.13 | Deduplicate repeated submissions and refreshes. |
| PERF.14 | Improve persistence only against measured size, latency, and recovery cases. |
| PERF.15 | Explain derived-data quotas and clean only reviewed, regenerable material. |
| PERF.17 | Set fluency budgets against the recorded local baseline and representative fixtures. |

Exit: each optimization shows a measured gain without losing results, evidence,
responsiveness, or cancellation on the tested machine.

## Phase 6 — Strengthen scientific rigor and reproducibility

| ID | Work |
| --- | --- |
| P2.02 | Inspect FITS HDUs, headers, WCS, scale, masks, and display limits. |
| P2.03 | Require explicit units, time scales, coordinate frames, and epochs where needed. |
| P2.04 | Present method, uncertainty, residuals, flags, and QA alongside derived values. |
| P2.12 | Version skill input/output manifests as a public contract shared by docs, UI, and CLI. |
| P2.08 | Record input/output hashes, versions, environment, backend, and consent without leaking secrets. |
| P2.07 | Ground generated summaries in selected, validated run artifacts. |
| P2.09 | Verify and replay eligible runs into new directories, reporting differences and missing prerequisites. |
| P2.10 | Export a reviewed portable run package with hashes and selected, permitted contents. |
| P2.11 | Produce reproducible reports that distinguish generated text from measured evidence. |
| P2.13 | Rebuild and document scientific examples with clear synthetic/reference/observed labels. |

Exit: every scientific conclusion points to its artifacts, method, QA, and
limits, with replay status stated rather than assumed.

## Phase 7 — Conditional downloadable-app decision

| ID | Work |
| --- | --- |
| P0.11 | If a binary is requested, separately review signing, notarization, installation, updates, and recovery on available equipment; keep other Macs unverified. |

The public source repository does not itself imply a downloadable app release.

## Phase 8 — Demand-driven extensions

| ID | Work |
| --- | --- |
| P3.06 | Keep contribution review within existing scientific, license, privacy, and CI gates. |
| P3.02 | Define a stable CLI only if users need automation of the selected workflows. |
| P3.01 | Consider reviewed, versioned skill packs before any marketplace. |
| P3.05 | Test safe project export/import in another directory on the same Mac if needed. |
| P3.03 | Consider a narrow read-first MCP/API with explicit permissions and a public threat model. |
| P3.04 | Add another compatible local-model endpoint only after demand and protocol tests. |
| P3.09 | Consider model-based report review only after deterministic artifact validation. |
| P3.07 | Defer remote/HPC execution until a real test cluster is available. |
| P3.08 | Defer Windows/Linux claims until those platforms can be tested. |

Exit: each extension has a documented user need, permission boundary, contract,
and validation scope. Deferred items are not presented as supported features.

## How to track changes on GitHub

Create issues for the **active phase**, each with its ID, completion evidence,
and dependencies. Put those issues in a phase milestone. Link implementation
pull requests to their issues; review the diff, licenses, inputs, and CI before
merging. Treat Actions as technical evidence for the exact commit. A green run
cannot close a task that requires a user study, domain review, or a private
reporting check. Add later-phase issues when their prerequisites and scope are
clear, rather than publishing 66 vague tickets at once.
