# Scientific Workbench

A macOS app for planning, reviewing, and running scientific workflows with
Python, a family of local skills, and a SwiftUI interface. It integrates Ollama
for local AI and optional cloud providers with explicit consent.

**Status: research software under development.** The source includes M101
trust-boundary hardening, M102 guided workflows, M103 persistence migrations,
and M104 connection/navigation improvements. It has been exercised on the
maintainer's Apple Silicon Mac. **It has not been manually tested on another
Mac**, and no independent user has evaluated its interface. The clean-root
source commit `b57c168` passed hosted macOS 15 Core checks on arm64 and Intel
and a separate focused Full installation check on arm64 on 2026-09-28.
Those results apply to that commit; check Actions for the commit you use.
There is no signed or notarized downloadable release.

## Get started

1. Follow [INSTALL.md](INSTALL.md) to create a new Python environment, configure
   the bundled skills, and build the app.
2. Read the [user guide](Guides/Scientific_Workbench_User_Guide.md).
3. Read [what the skills and capabilities do](docs/SKILLS_AND_CAPABILITIES.md),
   choose one route in the [55-capability setup matrix](docs/CAPABILITY_SETUP_MATRIX.md),
   then check [optional backends](docs/OPTIONAL_BACKENDS.md),
   [workflow requirements](docs/WORKFLOW_REQUIREMENTS.md), and
   [troubleshooting](docs/TROUBLESHOOTING.md).
4. Start with synthetic data. A direct **Run Capability** action starts immediately,
   so review its inputs and output folder first. For a Chat-generated plan, use
   **Dry Run** to inspect its commands before **Run Enabled**.

The app requires macOS 14 or later and Swift 6 to build. The reference scientific
environment uses Python 3.11. The [public repository's portable validation](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml)
must be checked on the exact commit being used. Its Intel job uses an unlocked
compatibility resolution; a validated Intel lock and manual use on another Mac
remain unverified.

## Repository contents

| Path | Contents |
| --- | --- |
| `Sources/`, `Resources/`, `Package.swift` | macOS app source and resources |
| `skills/` | All five scientific skills, including scripts, implementations, registries, and examples |
| `distribution/skill-manifest.json` | File, hash, and symlink inventory of the bundled backend |
| `script/` | Build, validation, and environment setup tools |
| `Tests/` | App and distribution-safety tests |
| `Guides/`, `DECISIONS/` | User documentation and technical decisions |
| `docs/WORKFLOW_REQUIREMENTS.md` | Dependencies and workflow-family coverage |
| `docs/CAPABILITY_SETUP_MATRIX.md` | One-row setup and evidence limits for each of the 55 user-facing capabilities |
| `docs/SKILLS_AND_CAPABILITIES.md` | Plain-language purpose of the five skills and all 55 user-facing capabilities |
| `docs/CAPABILITY_VALIDATION_EVIDENCE.md` | Dated smoke or diagnostic scope for each user-facing capability |
| `docs/TROUBLESHOOTING.md` | Reproducible diagnosis and safe recovery |
| `docs/PUBLIC_READINESS.md` | Dated source validation and use limits |
| `docs/PUBLIC_SOURCE_HANDOFF.md` | Reviewed source export and publication handoff |

Names without spaces are retained only for technical identifiers. The skills
are siblings under `skills/`; the app runs each capability from its owning
root. The local backend does not require Codex or copying anything into
`~/.codex/skills`. The Codex bridge is optional.

## Dependencies and scope

The `core` profile installs 13 direct libraries for tables, statistics, FITS,
and documents. The `full` profile adds advanced astronomy, notebooks, SQL, and
OCR. Ollama models, LaTeX, LibreOffice, IRAF/APT/STILTS, and cloud integrations
are configured separately for workflows that need them. Missing components
must produce a diagnosis or a controlled block, never an invented result.

Core has a lock for 32 runtime packages with wheel hashes on native Python 3.11
for Apple Silicon. Use `--locked` as described in INSTALL.md. Full has a lock for
Python 3.11 arm64/macOS 15+: 200 runtime packages and three pinned installation
and build tools. It verifies 199 wheels and the PIMS 0.7 source archive; PIMS is
built with pinned tools inside the new environment.

Intel currently resolves unpinned versions. The locks do not pin Python, Apple
tools, or external backends. Every installation records its resolution and
diagnostics. Full pins pip, setuptools, and wheel; core retains the interpreter's
bootstrap tools. The [dated full-lock evidence](docs/PUBLIC_FULL_LOCK_2026-09-15.en.md)
describes the earlier 215-package lock. The current lock uses pypdfium2 for PDF
work, retains `olefile` for legacy Office metadata, and excludes automatic
TEAREDUCE and oletools installation. See [optional backends](docs/OPTIONAL_BACKENDS.md)
for the separate, unverified TEAREDUCE notebook route. The revised Full lock
installed in a fresh hosted macOS 15 arm64 environment on 2026-09-28; that
focused job did not run the 38-case Full smoke or external tools.

The [source distribution boundary](docs/SOURCE_DISTRIBUTION_BOUNDARY.md)
distinguishes material in Git from dependencies and models downloaded into each
user's environment. A self-contained application bundle needs separate review.

The [local full-profile validation](docs/PUBLIC_FULL_VALIDATION_2026-09-15.en.md)
covers 38 synthetic cases, including two expected rejections that check input
protection. It exercised notebook execution, copied run data, and LaTeX
compilation. It does not establish a clean installation on another Mac or
exhaustive coverage of optional backends.

## Data and security

Original inputs are treated as read-only. Results, logs, and manifests are
written into separate run directories. Review destinations and permissions
before running external tools: app controls do not provide an operating-system
sandbox. Credentials are configured locally and kept out of Git. DOCUS,
Python environments, models, transient caches, builds, and credentials are
outside this distribution.

Some skill-internal `.cache` directories contain required deferred code and
documentation. They are part of the backend manifest and must be retained.
Transient runtime outputs are excluded separately.

## Verification

```bash
python3 script/check_distribution_snapshot.py
python3 script/check_core_lock.py
python3 script/check_full_lock.py
python3 -m unittest discover -s Tests/DistributionTests -v
./script/check_git_publication_readiness.sh
./script/run_swift_tests.sh
```

[Portable validation](docs/PORTABLE_VALIDATION.md) explains the tests and locks.
On commit `b57c168`, the [Core run](https://github.com/interemi/scientific-workbench-public/actions/runs/36435979426)
passed both macOS 15 jobs: 306/306 Swift tests and 23/23 synthetic Core cases
per job, with the 1,926-entry snapshot intact. The separate
[manual Full run](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
installed the revised lock in a fresh hosted arm64 environment, passed 23/23
Core synthetic cases there and 39/39 document tests. It did not run the 38-case
Full smoke, which also needs an external LaTeX engine. Check the
[portable validation runs](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml)
for the exact commit you use; a green run on `b57c168` does not validate a
later commit.
See [portable validation](docs/PORTABLE_VALIDATION.md) for the exact scope. The
[public preparation record](docs/PUBLIC_PREPARATION_2026-09-14.en.md) preserves
dated results and open limitations.

The [M101 checkpoint](M101_CHECKPOINT_2026-09-13.public.md) records 281 tests, the
quality gate, dual gate, and DOCUS benchmark in the original environment.
It does not establish clean installation of this distribution. Historical
benchmarks must not be overwritten or repeated on original data.

The [security review](docs/PUBLIC_SECURITY_REVIEW_2026-09-16.en.md) records the
audit scope, two corrected findings, and its limits. It is not a guarantee
that the app has no vulnerabilities. The [asset provenance record](docs/ASSET_AND_FIXTURE_PROVENANCE.en.md)
preserves technical evidence; the subsequent [owner confirmation](docs/OWNERSHIP_CONFIRMATION.md)
records the project-material licensing decision.

The [M102 coverage record](docs/M102_GUIDED_COVERAGE.en.md) covers all 55 visible
capabilities and the specialized forms' format limits. The
[M103 persistence contract](docs/M103_PERSISTENCE_EVOLUTION.en.md) describes
migrations, conservative recovery, and exact backups. The
[M104 architecture and UX review](docs/M104_ARCHITECTURE_AND_UX.md) documents
ephemeral connection state, accessible controls, and pending external usability
acceptance.

## Development and license

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing code, scientific
contracts, skills, or persistence.

Project-authored code, documentation, the app icon, and synthetic fixtures use
[PolyForm Noncommercial License 1.0.0](LICENSE), with attribution to **interemi**
in [NOTICE](NOTICE). This permits use, modification, and distribution for the
license's permitted purposes, including noncommercial use; it does not grant
general commercial-use permission. Its educational and other institutional
permissions are explained in the [license decision](docs/LICENSE_DECISION.md).

The project is source-available, not OSI open source. Third-party dependencies
and materials retain their own copyright and license terms. Scientific
Workbench does not claim ownership of TEAREDUCE or any other external package,
tool, model, or user-supplied data. The [ownership and attribution map](docs/DEPENDENCIES_AND_LICENSES.md#ownership-and-attribution-map)
identifies what the project license covers, links to the exact Python package
inventories, and points to the [optional tools and their upstream projects](docs/OPTIONAL_BACKENDS.md).
Acknowledging an upstream author does not replace that component's license or
make every combination of licenses compatible.

The [public-readiness record](docs/PUBLIC_READINESS.md) identifies remaining
validation and distribution limits. Repository visibility is an owner decision,
not a measure of installation support or scientific validity.

## Use limitations and no warranty

Scientific Workbench is research software under development. It may contain
errors; successful execution does not establish scientific validity or fitness
for a particular purpose. Independently review methods, units, uncertainties,
and outputs before relying on or publishing results.

Keep independent backups and use copies of important inputs. External tools
run with your account's permissions; cloud services may transmit selected data
and incur charges. Start with synthetic fixtures and review each run's scope.

The software is provided as is. The warranty and liability limitations in
[LICENSE](LICENSE), under **No Liability**, apply only as far as applicable law
allows. Nothing in this documentation excludes rights or liabilities that
cannot lawfully be excluded. These notices do not guarantee immunity from
claims or replace the project's obligation to describe known limitations honestly.
