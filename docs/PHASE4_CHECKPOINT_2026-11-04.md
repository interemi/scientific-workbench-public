# Phase 4 local integration checkpoint

- Date: 2026-11-04
- Tested source: `08497a77596beb20562ddce4c8b47572bb371d55`
- Public base: `aa722f282292e7ab926b5c9445d6592a7b27f996`
- Status: local checks passed; exact-candidate hosted CI and public integration pending

This groups the first-interface-journey work in the
[product roadmap](PRODUCT_IMPROVEMENT_ROADMAP.md). The observations are
maintainer-run checks on one development Mac. They do not establish independent
usability, accessibility certification, or scientific validity.

## Reviewed scope

| Criteria | Change and evidence |
| --- | --- |
| P1.01 | Dashboard task launchers, synthetic examples, and return to an existing job; [local review](PHASE4_DASHBOARD_LOCAL_REVIEW_2026-10-04.md). |
| P1.03–P1.04 | Core/Full guidance and lock counts, prioritized diagnosis, and repair into a new destination; [profile review](PHASE4_PROFILE_GUIDANCE_LOCAL_REVIEW_2026-10-04.md) and [diagnosis review](PHASE4_ENVIRONMENT_DIAGNOSIS_LOCAL_REVIEW_2026-10-04.md). |
| P1.05 | Task/format/profile/readiness/skill discovery, filters, and explicit CLI/Expert context; [discovery review](PHASE4_CAPABILITY_DISCOVERY_LOCAL_REVIEW_2026-10-05.md). |
| P1.06–P1.09 | Per-step execution scope, linked job progress and cancellation evidence, bounded read-only artifact inspection/comparison, job search, and explicit empty/blocked states; [user guide](../Guides/Scientific_Workbench_User_Guide.md) and the automated checks below. |
| P1.11 | Reviewed model downloads at the selected endpoint, active cancellation, retained partial data, and deterministic execution with that endpoint offline; [real model-download acceptance](PHASE4_LOCAL_MODEL_ACCEPTANCE_2026-11-04.md). |
| P1.12, P1.14 | Three short task guides, three GIF tours, six real app screenshots, and source/capture provenance; [workflow tours](WORKFLOW_TOURS.md). |
| P1.13 | Nine simulated historical failures, eight actual current-state rechecks, relevant setup destinations, and a real redacted support export; [recovery acceptance](PHASE4_RECOVERY_LOCAL_REVIEW_2026-11-04.md). |
| P1.15 | Captured workflow inputs/output, exact step/job associations, preserved drafts, and four completed attempts plus an actual cancellation; [workflow-context acceptance](PHASE4_WORKFLOW_CONTEXT_LOCAL_REVIEW_2026-11-04.md). |

The final app sources are unchanged from `d271065`; subsequent changes add
documentation, media, gate corrections, and test isolation. Earlier GUI/media
records retain their own source and executable hashes.

## Current verification

The available machine was arm64, macOS 27.0.1 (26A434), with Apple Swift 6.4
(`swiftlang-6.4.0.34.1`). Local builds used the already-installed macOS 26.5 SDK
and SwiftPM's deprecated native build system. The previously observed default
build/toolchain problem remains a compatibility limitation.

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM=native \
RUN_DOCUS_BENCHMARK=0 ./script/run_quality_gate.sh
```

The gate closes named app processes and rebuilds the local `dist` bundle.
Preserve active sessions, the previous bundle, and application state before
running it. This invocation kept diagnostic outputs outside Git and used
generated fixtures; the original DOCUS directory was not accessed.

| Check | Observed result |
| --- | --- |
| Complete quality gate | Exit 0; all 16 required steps passed. DOCUS benchmark was explicitly not run. |
| Swift unit/integration tests | 380/380 tests in three suites; 9.371 seconds for the final test run. |
| Process groups | Cancellation and timeout terminated the tested process trees while preserving an unrelated process. |
| Planner and transcript gates | Six planning cases and five golden transcript cases passed. |
| Capability E2E | Six execution cases and the controlled missing-STILTS case passed; later planned steps did not execute after the block. |
| M102 guided smoke | Native crossmatch and isolated legacy-report checks passed with unchanged generated inputs. |
| Mixed research benchmark | Three jobs, 24 indexed artifacts; input fingerprints unchanged. |
| Secret redaction and Settings | Both gates passed. Redaction coverage concerns configured test credentials. |
| Release readiness and first run | Static checks and isolated packaged first-run planning passed. |
| Packaged app | Bundle verification, Finder/Dock smoke, real execution, and seven-section UI navigation passed. The real-run case retained three jobs and 20 artifacts. |
| Bundle resources/signature | All four bundled guides match source; strict ad hoc signature verification passed. This is a development bundle. |
| Normal application state | During the final complete gate, all 22 pre-existing state files remained byte-identical and preference values remained unchanged. |
| Distribution tests | 67/67 Python tests passed before the gate corrections, using Python 3.14.0. |
| Documentation/publication audit | The preceding snapshot had 896 text documents, 44 PDFs / ten unique PDFs, zero detected Spanish documents, broken local links, private documentation paths, unreadable PDF groups, or unsafe active guidance. Git candidates had zero pending potential secrets, 18 reviewed fixture matches, 110 informational privacy findings, and zero oversized objects. Those counts precede this new checkpoint. |

The packaged executable SHA-256 was
`4dc4d0edf2e30f132d68ffbe97c22c2379cdad604737e7423a6c7b62104cdb38`.
Its bundle identity/signature differs from the isolated GUI test bundle.
Raw logs, captures, model files, application-state snapshots, and test runtimes
remain outside the repository.

## Failures found and retained

The first gate stopped at an obsolete `Not run` summary expectation. Actual
STILTS execution was correctly blocked with exit 2, later jobs were absent,
and the generated input was unchanged. `16d8264` updates the expected unlinked
wording and verifies each Step ID/Job ID against the transcript. A replay accepts
the valid record and rejects wrong step IDs, wrong job IDs, fabricated links,
and an executed post-block step.

The second gate stopped at obsolete Ollama setup copy. `739252f` checks the
current optional-model explanation and review, confirmation, progress, and
cancellation controls. No application behavior was changed to satisfy either
outdated expectation.

A later preservation check found that a cloud-planning test wrote its
synthetic `Safe plan` draft into the normal output directory despite using
separate preferences. `08497a7` gives that test its own temporary output root
and verifies persistence there. The complete suite then passed while normal
state files stayed unchanged; the subsequent full gate confirmed the same.
Both observed draft versions were retained. The earlier backup already held
the synthetic test plan, so this checkpoint cannot establish preservation of
a draft predating that backup. Observed job history and preferences were
unchanged. An intermediate compile error in the new assertion was corrected
before the successful reruns; its log was retained.

## Remaining integration and limits

Publish the reviewed phase branch, inspect its pull request, and require
passing exact-candidate hosted Core CI before merging. Record the resulting
public commit and its CI separately. No tag or GitHub Release is created by
this checkpoint; the [release plan](GITHUB_RELEASE_PLAN.md) remains a separate
decision.

Phase 3's P1.10 spoken VoiceOver and measured-contrast review remains open.
Manual testing on another Mac and independent-user acceptance remain
unverified. Later performance, scientific-contract, replay/export, and
conditional-extension work stays in its existing roadmap phases.
