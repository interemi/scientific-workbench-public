# Source-installation rehearsal and validation scope — 2026-10-02

This is a maintainer-run technical check of the existing public source
repository. The checked public `main` commit was
`9c8514120ee390c27519977d595b28db7d91cb15`. A new HTTPS clone of that
commit was used for the app build, current guide preview, Core smoke, GUI
exercise, local gates, and documentation audit. The earlier Core installation
was made from reviewed source commit `5c89a1546028d8a593fa8d0fba8002890667fcec`.
The bundled skills, locks, installer, and portable runner have no file changes
between that commit and the checked `main` commit. The separate Full CI head
`c248d99fcf6b3d17ae267622cd775738f00c5f08` and the merge commit have
identical Git trees.

This record supports the internal technical criteria for P0.09 and P0.05. It
does not measure whether a newcomer can follow the guide without help, test an
interactive session on another Mac, or establish scientific correctness for
real observations.

## Machine, source, and dependencies

| Item | Observed state |
| --- | --- |
| Local machine | MacBookPro18,3; macOS 27.0.1 (26A434); arm64 |
| Build tools | Apple Command Line Tools; Swift 6.4; SDK 26.5 workaround for this toolchain |
| Bootstrap Python | Existing Conda Python 3.11.15, arm64; `python3.11` was not on `PATH` |
| Core environment | New isolated `datanalysis` venv, separate from the existing Conda environment; `pip check` passed |
| Core lock SHA-256 | `6daddc98d97e3afa89827580888ffac643a7b3e63ff8385ab7eb520d6d186e98` |
| Full runtime/build lock SHA-256 | `65cf8885dbbf847f3c413abc19dc8c46d970eab23f1f3127f54f0ad02040a55f` / `019579e45416357c53ac3cce8b8f092c58c0bda356cc6def7f7b07cb8ff2b541` |
| Distribution snapshot | 1,926 entries verified before and after both local smokes; 480 relative symlinks retained in the public clone |

The source clone was clean and tracked `origin/main`. The installed Core
environment's plan and package inventory were retained outside Git. A second
Core plan was previewed from the exact public `main` clone; it reported the
reviewed hashes and created no destination or packages. The installer returned
success for the new Core environment. Its `env-doctor.json` reported a warning:
the named `datanalysis` discovery found the Mac's pre-existing Conda environment
instead of treating the new venv as that named environment. This warning is
retained. `pip check`, direct Core smoke, and the app's environment refresh
passed with the new venv's interpreter explicitly selected; those checks do
not erase the diagnostic ambiguity.

The first plain `swift build` on macOS 27.0.1 failed before source compilation
with `Unknown error parsing property list`. With the SDK 26.5 already present
on this Mac and `SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM=native`, the development
bundle built from the public clone. This is a scoped local workaround, not a
requirement for other installations or evidence that a signed installer works.

## Current guide walkthrough

| `INSTALL.md` step | Result on the available Mac |
| --- | --- |
| 1. Requirements | Swift 6.4, Command Line Tools, and native Python 3.11.15 found. The Python executable required an absolute path because `python3.11` was absent from `PATH`. No tools were installed for this step. |
| 2. Clone and verify | New HTTPS clone of the public `main`; clean checkout, 480 symlinks, and 1,926-entry backend snapshot passed. No individual skill folder was downloaded. |
| 3. Plan and install Core | Read-only plan first; new locked Core venv installed in a previously absent external destination. Installer inventory retained; `pip check` passed. No existing environment was updated. The exact-main plan was also previewed without installation. |
| 4. Build | Plain SwiftPM failed with the property-list error above; the documented SDK/native-build workaround built the development app bundle. No release was packaged, signed for distribution, or notarized. |
| 5. Configure | Launched the public-main bundle in an isolated app session. Set this checkout's mother skill root, the new Core Python, and a new external output root. Used **Save Settings**, **Reload Registry**, and **Refresh Environment**. Setup showed the scientific environment, 55 capabilities, and output folder ready. |
| 6. Synthetic first run | Direct Core smoke passed **23/23** cases on the public-main clone. In the GUI, **Dashboard → Prepare Small table → Run Capability → Jobs → Results** ran `profile_table` successfully: three rows, four columns, `app_status: PASS`, `original_modified: false`, with readable summary and manifest. **Reset Example (New Copy)** created another synthetic copy while preserving the earlier copy and job. |

The accepted GUI job folder was
`20261002_131357_profile_table_678adfe0-7020-4b10-be3c-bb4f5f3de432`.
The manifest's input SHA-256 and a read-only post-run hash both equal
`a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72`.
The two generated example copies retain this same hash. Results displayed
`summary.json` and `manifest.json` in the isolated output root. Closing and
reopening the app window left the job visible, but the process may have
remained running; this is not a full process-restart test.

The local Core smoke's `verification.json` reports `PASS`, profile `core`,
23 passed features, and 1,926 snapshot entries before and after. Its retained
SHA-256 is `c4d0c128d60913613683e2ede6718d15ff5a546b6cbf5b72259940b1734c7a23`.
The input files were synthetic. No original scientific data or DOCUS input was
used.

The acceptance form includes additional recovery and lifecycle checks beyond
the guide's first direct capability run. Their status in this rehearsal is:

| Form step | Result |
| --- | --- |
| Prepare a synthetic table | PASS: expected values and selected input were shown; a direct capability run has no Chat-plan Dry Run step. |
| Cancel a synthetic workflow | `INCOMPLETE`; cancellation belongs to the later P0.04 walkthrough. |
| Close and reopen the full app process | `INCOMPLETE`; only the window was closed and reopened, with the job still visible. |
| Try a missing optional backend | `INCOMPLETE`; no optional backend was invoked. |
| Check original-input protection | PASS for the table: manifest and post-run SHA-256 match; this does not test arbitrary user files. |

## Validation at the checked source tree

| Check | Exact scope and outcome |
| --- | --- |
| Swift tests on public `main` | **312/312 passed** with the scoped SDK/native-build settings. |
| Release readiness | Passed. This checks static release contracts; it does not create a release. |
| Quality gate | Passed, including process, planner, capability, privacy, first-run, packaged real-run, and packaged UI smokes. DOCUS benchmark was **skipped**. |
| Strict public documentation audit | 877 text documents and 10 unique PDF documents inspected; zero likely Spanish documents/PDF groups, broken-link documents, portable-path documents, or unsafe active guidance. |
| Local Full smoke | **38/38 synthetic cases passed** with an **existing** Conda scientific environment on this Mac; 1,926 snapshot entries before and after. It was not a fresh local Full-lock installation. Retained `verification.json` SHA-256: `b347b4c5061d277da7e4c9ded1efb4ace50c49a6e74ba674e803d69f99e28377`. |
| [Hosted Core on public `main`](https://github.com/interemi/scientific-workbench-public/actions/runs/36998229330) | Both macOS 15 jobs passed: arm64 locked and Intel unlocked-compatibility. The Full job was skipped in this Core run. |
| [Hosted Full on identical PR tree](https://github.com/interemi/scientific-workbench-public/actions/runs/36997759557) | Fresh locked Full installation on macOS 15 arm64 passed, followed by 23 Core synthetic cases and 39 document tests. The 38-case Full smoke was not run there because it requires an external TeX engine. |

After drafting this documentation follow-up, its local strict audit covered
878 text documents and 10 unique PDFs with zero language, link, portability,
or active-guidance findings. The publication scan found zero possible secrets
and zero oversized objects. Its 105 privacy-pattern hits were unchanged from
the public-main baseline; they are scanner findings, not a privacy clearance.
Release readiness passed on the edited documentation. The follow-up's hosted
CI must be inspected at its own commit before treating that update as complete.

The local gate logs and smoke directories are retained in maintainer-only
scratch space outside Git. The logs' SHA-256 values are
`887d39c2024871167295a2afdca2a9cc443e20d6000bf8d9b204c79e61bf96d0`
(Swift tests), `f7932caf32362f8418d5cbee545a46e11bf39acb033ab82070305e60fa070b44`
(release readiness), and
`4378b0c24ef1496bdaf60e8dc1c8d147d3bb09bdf35286ae7b77e6915b96eb91`
(quality gate). These hashes identify local evidence; they do not make the
private scratch files publicly downloadable.

## Unperformed and limited checks

- No fresh **local** Full installation was performed. The hosted fresh Full
  check used a GitHub runner and did not run the 38-case Full smoke.
- No manual interactive session on a second Mac, uncoached newcomer trial,
  signed or notarized installer, Gatekeeper acceptance, or update test was
  performed.
- Cancellation, missing optional backend recovery, cloud-provider consent,
  and a complete process restart were not part of this installation exercise.
  Their own roadmap criteria remain separate.
- The Intel hosted Core run resolved dependencies without a lock. macOS 14,
  other Swift/SDK combinations, and Full on Intel remain unverified here.
- A successful process, artifact contract, or synthetic smoke does not validate
  every method, uncertainty, or scientific interpretation. Inspect the source
  data, units, assumptions, QA, and outputs for each real research task.
