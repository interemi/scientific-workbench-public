# Public preparation — September 14, 2026

English publication edition of `docs/PUBLIC_PREPARATION_2026-09-14.md`
at private commit `4aae9a6`. Original SHA-256:
`a34b74adb03ac0666e122a35f7157a31e9b6f38601302cbeb626dda8efc5a1fe`.
The Spanish original remains unchanged privately. Results and pending decisions
below describe the source date; translation is not new execution evidence.
See [PUBLIC_READINESS.md](PUBLIC_READINESS.md) for current requirements.

This record continues the goal of preparing Scientific Workbench for a reviewed
public opening. The repository remains private. This batch does not complete
that goal, establish full support, or authorize a release or visibility change.

## Starting state

- The owner uploaded `main` to `interemi/scientific-workbench`.
- Verified remote HEAD: `4bb7a3397f96f3eae6a346679c63648a4648221d`.
- Local branch `codex/public-readiness-foundation` started from that commit
  with a clean tree.
- A fresh remote clone retained 1,919 snapshot entries and completed 23/23 core
  workflows. This first check used an existing Python environment and is not
  evidence of installation on a clean Mac.
- Git could read the repository; the GitHub plugin returned 404 for its metadata
  query. Plugin access would need investigation before relying on that route.

## Changes in this batch

- The publication gate distinguishes Git candidates from ignored Finder
  metadata. Strict local checks remain available; no files were deleted.
- The Swift runner uses SwiftPM when it discovers tests and retains the Command
  Line Tools fallback. It propagates failures and rejects zero-test runs.
- `run_portable_core.py` requires a new output directory outside the checkout,
  strict diagnostics, and core coverage. It retains evidence and verifies the
  snapshot before and after execution.
- A 32-package runtime lock for CPython 3.11/macOS arm64 includes wheel hashes
  and a technical inventory. The installer uses it with `--locked`, checks
  compatibility, runs `pip check`, and records its plan even if installation fails.
- CI was prepared for macOS 15 arm64 and Intel, with commit-pinned actions and
  read permissions. These changes had not run on hosted CI.
- Current cloning/installation instructions, a validation guide, an acceptance
  form for another Mac, and bug-report/review templates were added.

This batch did not change Swift application sources, persisted models, the five
skills, or their manifest. Historical checkpoints, benchmarks, and reports were
not rewritten.

## New evidence

Local platform: macOS 26.6.2 arm64, Swift 6.3.3, Python 3.11.15 from Conda,
used to create a new virtual environment with copies. The previous environment
was preserved.

| Check | Observed result | Scope |
| --- | --- | --- |
| Remote clone and snapshot before/after | PASS, 1,919 entries; clean Git tree | Remote commit `4bb7a33` |
| Swift build from fresh clone | PASS | Development Mac toolchain |
| Modified Swift runner | PASS, 281 tests / three suites | Local fallback; native route tested with a simulated toolchain |
| Distribution tests | PASS, 21/21 | Protected directories, propagated failures, hashes/platforms, Swift discovery |
| Smoke from remote clone | PASS, 23/23, no missing coverage | Core backend with an existing environment |
| Hashed core installation | PASS; no `pip check` conflicts; satisfactory core diagnostics | New environment on the development Mac |
| Installed versions | 32/32 match; only pip and setuptools extra | Runtime pinned; bootstrap recorded but not pinned |
| Smoke with the new environment | PASS, 23/23; snapshot intact before/after | Core arm64 backend |
| CI workflow | YAML and action references reviewed | GitHub execution pending |

Installed lock SHA-256:
`6daddc98d97e3afa89827580888ffac643a7b3e63ff8385ab7eb520d6d186e98`.

Complete evidence remains outside Git in run `public-readiness-20260914.jxR4qz`:
Swift and distribution-test logs, `remote-core-summary.json`,
`locked-core-install.log`, `locked-core-verification.json`, and
`locked-core-smoke/verification.json`. Wheels and environments are not uploaded.
Final branch-review results are new files there; they do not replace M101 or
private-distribution evidence.

Historical UI, packaging, dual-gate, and DOCUS results were not used to claim
portability for this batch. No application package or DOCUS benchmark was made.

## Requirements open at the source date

| Requirement | Evidence needed | Recorded state |
| --- | --- | --- |
| Real GitHub CI | URL, SHA, both jobs green; investigate failures | Branch upload and execution pending |
| Installation and use by another person | Completed CLEAN_INSTALL_ACCEPTANCE with logs | Pending; a local venv does not prove another Mac |
| Intel and full profile | Fresh installations, platform locks, verified workflows | Pending |
| Project license | Explicit owner decision and confirmed ownership | Pending |
| Third-party licenses/provenance | Original texts, permissions, notices, snapshot/full/model review | Core inventory started; review open |
| History privacy | All commit blobs, PDFs, authorship, personal identifiers | Open; personal email, machine identity, historical paths observed |
| Public security | Code/history review, resolved findings, documented limits | Basic gate passes; not a complete public audit |
| Skill-family compatibility | Five-skill gates and release-version decision | Pending before claiming 2.8 promotion |
| Product quality | Guided coverage, persistence/migrations, M102–M104 UX acceptance | Prioritization and verification pending |
| Downloadable distribution | Signing/notarization decision, traceable release, external installation | Authorization and separate work pending |
| Public opening | Final review and explicit owner decision | A green technical result does not authorize it |

Existing history is preserved. Resolving personal identifiers may require
deciding which history to distribute publicly; automation must not rewrite or
delete evidence on its own. A license must not be chosen without reviewing
ownership and included material.

## Recorded continuation

1. Review and consolidate the branch locally; the owner decides its upload.
2. Run CI, correct actual failures, and record demonstrated compatibility.
3. Complete provenance/privacy review and seek concrete owner decisions on
   licensing and personal identifiers.
4. Test full and accept installation/UI on another Mac; continue M102–M104 based
   on that use, with explicit migration for any persisted-model change.
