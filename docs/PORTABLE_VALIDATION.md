# Portable validation

These checks use the five bundled skills and synthetic examples. They do not
require Codex, Ollama, cloud credentials, DOCUS, or a packaged app. They do not
replace UI acceptance, release gates, or methodological validation of a real
scientific analysis.

## Local checks

From the checkout root:

```bash
python3 script/check_distribution_snapshot.py
python3 script/check_core_lock.py
python3 script/check_full_lock.py
python3 -m unittest discover -s Tests/DistributionTests -v
./script/check_git_publication_readiness.sh
swift build
./script/run_swift_tests.sh
```

The publication gate checks Git candidates. An ignored `.DS_Store` is not
uploaded and does not fail this check; a tracked one does. The local hygiene
gate without `--git-visible` retains its stricter worktree checks. Neither
script deletes reported files.

Potential-secret scanning includes tests. Reviewed exceptions are restricted
to a path, rule, and synthetic-line SHA-256 in
`distribution/publication-secret-fixtures.json`; whole files are not excluded.
To inspect historical blobs and commit metadata as well:

```bash
python3 script/audit_publication_history.py --history --check-secrets \
  --output "$HOME/ScientificWorkbenchRuns/history-review-01.json"
```

The report must be new and outside the checkout. It records paths, objects,
rules, and hashes without printing matched values. The history audit requires
a full clone; CI checks out full history for this purpose. Passing secret checks
does not resolve privacy findings. PDFs, images, and FITS also need the asset
auditor, using the core environment's Python:

```bash
"$HOME/Library/Application Support/Scientific Workbench/environments/core/datanalysis/bin/python" \
  script/audit_distribution_assets.py \
  --output "$HOME/ScientificWorkbenchRuns/assets-review-01.json"
```

This auditor extracts PDF text/metadata, FITS headers, and PNG metadata. It does
not interpret images, perform OCR, or inspect embedded attachments; ICNS is
flagged for manual review. These checks do not certify that history is free of
personal data or secrets in every format. See the
[privacy review](PUBLIC_PRIVACY_REVIEW_2026-09-14.en.md).

The Swift runner tries SwiftPM first and checks discovered test counts. If
SwiftPM succeeds without discovering tests, it tries the existing Command Line
Tools runner. A compilation or test failure is never replaced by a second,
successful-looking attempt. Zero tests is not successful validation.

## Reproducible core within a defined scope

`distribution/locks/core-macos-arm64-py311.txt` pins 32 runtime packages and a
SHA-256 hash for each reviewed wheel, including 13 direct core dependencies
and the reference installation's transitive dependencies. Wheels stay outside
Git. Setup downloads them with `--require-hashes` and prevents source builds
through `--only-binary=:all:`.

`distribution/core-wheel-inventory.json` records versions, wheel names, hashes,
and license metadata. It is a technical inventory, not a license or security
certification. The lock verifier detects inventory mismatches and unpinned
core requirements. `pip check` and the smoke exercise compatibility and
execution in a new environment.

The lock requires CPython 3.11, macOS 14+, and native arm64. Current local
execution evidence is from macOS 26.6.2. It does not pin the Python binary,
bootstrap pip/setuptools, Apple SDK, Ollama/models, or external applications.
PyPI must continue serving the wheels; there is no distribution mirror or
offline-installation guarantee.

To update the lock, resolve core in a new environment, retain its inventory,
download the wheels, review hashes and provenance, update the lock and inventory
together, then reinstall with `--locked` into another empty environment. Do not
regenerate the lock during installation or change hashes to conceal a failure.
See pip's guidance on [repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
and [hash checking](https://pip.pypa.io/en/stable/topics/secure-installs/).

## Full profile: verified local execution

The runner retains the name `run_portable_core.py` for compatibility and accepts
`--profile full`. Use Python 3.11 from the full environment and a new output
directory outside the checkout; [INSTALL.md](../INSTALL.md) contains the command.
Without `--profile`, the runner continues to use core.

Before the smoke, diagnostics must report `core_ready` and `full_ready`.
`teareduce_ready` is separate optional-backend discovery for the current Python
interpreter, not a Full-profile gate or a check of a selected notebook kernel.
Afterwards, validation requires the full profile, core/full
tier coverage, no failed cases, and intact snapshots before and after. A core
summary cannot satisfy full validation. Setup applies the same readiness check.

The 2026-09-15 run passed 38/38 cases: 36 successful operations and two expected
rejections of unsafe notebooks. These two cases retain their observed exit code
(2). They pass only when the summary satisfies the contract, explains the
expected block, and confirms intact originals. Synthetic-input hashes are
compared as well. Unexpected failures remain failures.

Positive notebook cases use copied data through `--stage-extra`. LaTeX
compilation preserves its source and requires a PDF and manifest. It needs an
external LaTeX engine in addition to Python dependencies; the smoke installs
no applications. This does not establish support for every optional backend,
OS-level isolation, or methodological correctness of all analyses.

The [first full validation](PUBLIC_FULL_VALIDATION_2026-09-15.en.md) used unpinned
versions and found that PIMS 0.7 had no published wheel. The subsequent run added
`--profile full --locked`, retaining that version while pinning its source and
build tools. See the [full-lock record](PUBLIC_FULL_LOCK_2026-09-15.en.md).

`distribution/locks/full-macos-arm64-py311.txt` pins 200 packages: 199 wheels
and the PIMS 0.7 source archive. `full-build-py311.txt` pins pip 26.2.1,
setuptools 79.0.1, and wheel 0.45.1. Setup verifies both locks against
`full-package-inventory.json`, installs the three tools with hashes, then
installs runtime packages with hashes. Only PIMS may use a source build;
implicit build-dependency downloads and built-wheel cache reuse are disabled.
Everything runs inside the new environment, and any failed step stops setup.
The current lock excludes PyMuPDF, TEAREDUCE, and the oletools/pcodedmp chain.
It retains `olefile` for legacy Office metadata without claiming `.xls` macro
detection. Static lock and archive checks passed; the current source worktree
also passed 38/38 synthetic Full cases on 27 September 2026 in an existing
Python 3.11 environment, with the 1,926-entry snapshot intact before and after.
The [hosted Full job](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
installed this lock from scratch on arm64 for commit `b57c168`, then passed
23 Core synthetic cases and 39 document tests. It did not run the 38-case Full
smoke; the local run below remains dated evidence for its own tree.

On 25 September 2026, local preparation commit `3c979e6` passed the Full
portable wrapper with 38/38 synthetic cases, Core and Full tier coverage with
no missing ID, and the 1,922-entry skill snapshot unchanged before and after.
The two unsafe-notebook cases were expected controlled rejections with observed
exit code 2 and verified original hashes. This was macOS 26.6.2 arm64 with
Python 3.11.15 and a real `latexmk`, using an **existing** scientific
environment. Its pypdfium2 5.6.0 and teareduce 0.7.6 differ from the revised
lock's 5.13.0 and 0.7.9. The run proves those synthetic workflows on that
checkout and environment, not fresh locked installation, hosted Full support,
or results on the final exported commit. The run logs, manifest, and generated
fixtures are retained outside Git by the maintainer.

Full requires arm64 Python 3.11 and macOS 15+ because of the selected debugpy
wheel. Core retains macOS 14 as its minimum. The inventory records exact
distribution metadata without certifying security or redistribution terms.
PIMS build inputs are pinned without claiming byte-identical output wheels.
Python, the SDK, and external applications remain outside the lock. The initial
`venv` pip installs only the pinned tools; runtime installation uses pip 26.2.1.

## GitHub Actions

`.github/workflows/portable-validation.yml` defines macOS 15 arm64 and Intel
jobs. They build app sources, run Swift/distribution tests, check both locks and
release readiness, install core in a new environment, and exercise its synthetic
workflows. arm64 uses the lock; Intel probes compatibility with unpinned
resolution. A matrix entry does not establish platform support before a
successful hosted execution.

On 28 September 2026, clean-root commit `b57c168` passed the
[public Core run](https://github.com/interemi/scientific-workbench-public/actions/runs/36435979426):
macOS 15 arm64 with the Core lock and macOS 15 Intel with unlocked compatibility
resolution. Each job reported 306 Swift tests, a fresh Core installation,
23 synthetic workflows, and a 1,926-entry unchanged skill snapshot. The
[manual Full run](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
also passed on the same SHA: fresh Full locked installation on arm64, 23 Core
cases, and 39 document tests. This is evidence for that commit only. Review the
[public repository's workflow runs](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml)
on the exact commit being used. No manual app session on another Mac has been
completed.

The [2026-10-02 installation rehearsal](INSTALLATION_REHEARSAL_2026-10-02.md)
records a later, exact public-main clone at `9c85141`: 312/312 local Swift
tests, release readiness, the quality gate without DOCUS, strict public
documentation audit, a new local locked Core environment, 23/23 Core cases,
and an isolated GUI table run. Its [main Core run](https://github.com/interemi/scientific-workbench-public/actions/runs/36998229330)
passed on macOS 15 arm64 locked and Intel unlocked-compatibility. A separate
[Full run on the identical PR tree](https://github.com/interemi/scientific-workbench-public/actions/runs/36997759557)
passed fresh Full installation, 23 Core cases, and 39 document tests on hosted
macOS 15 arm64. Local Full 38/38 used an existing environment; no fresh local
Full installation or interactive second-Mac test is inferred.

The workflow also defines a manual `workflow_dispatch` choice. `core` runs the
two established Core jobs; `full` selects a separate macOS 15 arm64 job that
installs the current 200-package Full lock into a new environment, runs the
23-case Core synthetic smoke with that interpreter, and runs the document unit
tests. It checks the source snapshot and lock first, records the exact commit
and environment, and retains focused diagnostics for 14 days. The 2026-09-28
run established fresh Full-lock installation and these focused checks on one
hosted runner, not Full scientific-workflow coverage. The 38-case Full smoke compiles
LaTeX and therefore still needs an external TeX engine; this manual job does
not install one or run those 38 cases. Nor does it exercise a manual app session
or all optional backends.

Swift integration tests use the app's default installed-skill paths. On each
fresh runner, the workflow links the five verified skill roots from this
checkout into the runner's temporary home directory before running those
tests. It refuses to replace an existing skill at that location; no external
skill download is involved. Swift workflow and retry tests use an isolated
process fixture for successful environment status, so their result does not
depend on the developer's installed Python environment. After the locked or
compatibility core install, CI separately runs the bundled
`datanalysis_env.py status` against that new interpreter and retains its JSON
and log before the synthetic workflow check.

Actions are pinned to full commits and use `contents: read`. Checkout does not
persist Git credentials. The workflow uses GitHub-hosted runners without project
secrets, self-hosted runners, or `pull_request_target`. See GitHub's
[Actions security guidance](https://docs.github.com/en/actions/reference/security/secure-use)
and [runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

The Core jobs run when the prepared `codex/...` branch is pushed, on main
changes, and on pull requests. Manual dispatch requires the workflow on the
default branch and chooses either Core or the focused Full-lock job. The two
manual choices have separate concurrency groups so a Full check does not
cancel a Core run on the same ref. It does not package, sign, notarize, or
publish an app.
GitHub-hosted macOS jobs run on fresh virtual machines, making them useful
technical clean-environment evidence; their preinstalled image and automated
core smoke do not prove a consumer install or interactive usability.
GitHub Actions usage and billing depend on the account and repository settings;
manually selecting Full adds another macOS job. Check the current Actions
billing settings before dispatching the workflow.

After uploading, open Actions. Record the run URL, commit, architecture,
versions, and each job's result in new evidence. On failure, inspect the failed
step and logs. Do not add `continue-on-error` or remove a platform merely to
claim an overall PASS.

The workflow checks actual architecture and records the tested commit/tree,
runner image, toolchain, and dependency mode. Its summary labels Intel as
`unlocked-compatibility`. Selected reports and logs are retained for 14 days in
an Actions artifact per platform, run, and attempt, including after failures.
They include build/test logs, diagnostics, documentation inventory, redacted
history findings, smoke summary/manifest, and installed-package inventory.
The [capability evidence table](CAPABILITY_VALIDATION_EVIDENCE.md) separates
registered smoke coverage from narrower diagnostic probes for all 55 user IDs.

The retention list excludes the Python environment, models, app bundles, and
complete scientific-output directories. Download evidence before expiry if a
durable record is needed. Artifact-upload failure remains visible in the job
result.

The documentation script can also inventory the private preservation checkout.
When `SOURCE_PROVENANCE.json` identifies a public export, CI requires English
text and PDF content, valid local links, and portable paths. This condition
lets the private branch retain its historical records while a public source
checkout fails on documentation regressions.
`--check-secrets` does not resolve all privacy findings. Check the hosted run
for the exact exported commit before claiming a portable validation PASS.
