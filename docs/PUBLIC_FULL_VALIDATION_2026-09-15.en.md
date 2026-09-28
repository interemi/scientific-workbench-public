# Local full-profile validation — September 15, 2026

English publication edition of `docs/PUBLIC_FULL_VALIDATION_2026-09-15.md`
at private commit `4aae9a6`. Original SHA-256:
`57dcbee60ca7b4f74f27fb8e26408f5a66eb5d503323b46b7dd354afc73f3343`.
The Spanish original remains unchanged privately. This is dated evidence, not
a new execution. The later [full-lock record](PUBLIC_FULL_LOCK_2026-09-15.en.md)
addresses the dependency-lock blocker recorded here.

Scientific Workbench remains private. This batch verifies and corrects the
included backend's current smoke suite; it does not complete public preparation.

## State and scope

Base: `0da80f3fe3579528bdf7e1c05a9d9046c562ac80`, branch
`codex/public-readiness-foundation`. Changes affect the installer, portable
runner, tests, documentation, and one current maintainer-skill smoke
implementation. Swift sources, persisted models, compatibility wrappers,
historical reports, and skills installed outside the checkout are unchanged.
No DOCUS data was used; no package, push, or visibility change was made.

Observed platform: macOS 26.6.2 arm64; Conda Python 3.11.15 used to create a new
venv with copies. Existing Python/environments were preserved. External tools
were already installed on this Mac, so this is not a clean-Mac test.

## Initial failures preserved

Full installation succeeded with 217 packages including pip and setuptools.
`pip check` found no conflicts. The doctor confirmed core/full, teareduce, SQL,
time series, astronomy, notebooks, OCR, and containers. Availability diagnostics
alone do not prove execution of every capability or presence of all external tools.

The first full smoke failed: 32/35 cases succeeded and coverage was missing for
`latex_workbench.compile`. Two flows attempted to run a notebook using an
absolute data path outside the run workspace; another used
`--run-from-source-dir`. Existing protections rejected those operations. The
suite also omitted LaTeX compilation required by the current registry. This
failed run and its files remain in `smoke-initial/`.

## Correction and checks

- The original generated template remains a negative case. The positive run
  uses a new notebook copy with relative paths and `--stage-extra`.
- The former `--run-from-source-dir` case now verifies explicit rejection. A
  separate case runs the notebook with its relative data copied into the run.
- Expected rejections retain `observed_returncode=2`. They count as successful
  assertions only when contract, reason, and original-input protection match.
  Tests ensure that unexpected success, a different error, invalid summary, or
  modified input cannot become PASS.
- LaTeX compilation must produce a PDF and manifest and preserve the source hash.
- Full installation and the runner explicitly require `core_ready`, `full_ready`,
  and `teareduce_ready` to be true. Core availability/validation alone is insufficient.

The complete installation preceded the installer's new final check. The corrected
runner exercised the same validation function against the environment's real
doctor result. This is not claimed as a second fresh installation with the
modified installer.

| Check | Observed result |
| --- | --- |
| Corrected full smoke | PASS, 38/38: 36 operations and two expected rejections; no missing core/full tier coverage |
| Snapshot before/after full | PASS, 1,919 entries in both checks |
| Positive notebook | Six code cells executed; the last produces `42` |
| Relative-data notebook | Cell executed; produces `portable smoke relative data` |
| New-case input integrity | Notebook, data, and LaTeX source hashes preserved |
| LaTeX PDF | Readable two-page file; text extracted to check content |
| Core regression with its locked environment | PASS, 23/23; snapshot intact before/after |
| Current v2.8 structural gate | PASS, 12 checks, 61 registry/routing entries, zero errors |
| Distribution tests | PASS, 37/37 |

These checks are not exhaustive scientific coverage, UI acceptance, promotion of
the entire installed family, or historical release gates. Swift tests were not
repeated for Python/documentation-only changes; the previous batch records 281/281.

The manifest retains snapshot provenance and records an explicit local patch to
`scientific-data-maintainer/fixtures/portable_smoke_test.py`:

- Previous SHA-256: `9e8cc5599a89838565cfbd0e7da0c935dfb515767a7a2835ac9b208c112da3b5`.
- New SHA-256: `787e7856a2131dc064d6f59a48067d4c77d29a1a5a9561ad11df6539a5dfa55c`.

## Full lock: pending with a demonstrated cause

The observed installation resolves 215 runtime packages. PIMS 0.7, required by
`dask-image` through `pims>=0.4.1`, was built from source. A later wheels-only
download attempt for all resolved versions failed on PIMS 0.7. PIMS was not
downgraded and the resolution was not substituted to conceal the failure.

A locally built wheel hash is insufficient for a reproducible lock: verified
source, build tools, and build policy are still needed. The next step is to
resolve that build chain or explicitly review a compatible alternative and test
it in another fresh environment. Core retains its wheel lock; at this source
date, `--locked --profile full` remained rejected.

LaTeX works on this Mac, but the Python installer does not install it. The doctor
reported STILTS, TOPCAT, and APT batch as absent; a green full smoke does not
validate those optional programs.

## Preserved evidence

Complete artifacts remain outside Git under
`ScientificWorkbenchRuns/public-full-20260915.rZF6Wr/`:

- `install-full.log`, `install-full.exit`, and
  `environment/datanalysis/scientific-workbench-setup/`: plan, diagnostics, freeze.
- `smoke-initial/`: unchanged original failure.
- `smoke-corrected/`: commands, logs, summary, manifest, outputs, verification.
- `core-regression/`: independent core regression.
- `family-integrity.json`: current structural gate.
- `distribution-tests-37.log`: this batch's distribution tests.
- `download-full-wheels.log`, `download-full-wheels.exit`, and
  `full-runtime-pins.txt`: failed binary-only attempt and observed versions,
  not an approved lock.

Installation freeze SHA-256:
`dadc377cb12b3b890af9188d88c1aeb354798cc9712dd29dcd89317ea65b3708`.
Generated environments, wheels, PDFs, and notebooks are not included in the commit.

## Work open at the source date

Run prepared GitHub CI, validate Intel and another Mac, resolve the full lock,
confirm ownership/license and disclosure of historical personal identifiers,
complete security review, and continue M102–M104 product quality. Current order
and completion criteria are in [PUBLIC_READINESS.md](PUBLIC_READINESS.md).
