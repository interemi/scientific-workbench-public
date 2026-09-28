# Scientific Workbench source validation and limits

This page records evidence available on 2026-09-28. It is a dated snapshot,
not a live certification. Check the current commit and its GitHub Actions runs
before treating a later checkout as validated.

Scientific Workbench is distributed as source under PolyForm Noncommercial
1.0.0 for project-authored material, attributed to interemi. It is
source-available, not OSI open source. Third-party components retain their own
licenses; see the [license decision](LICENSE_DECISION.md),
[dependency inventory](DEPENDENCIES_AND_LICENSES.md), and root
[LICENSE](../LICENSE).

## What the source includes

The checkout contains a SwiftUI macOS app, five bundled scientific skills,
their recorded file manifest, tests, and source-installation scripts. The
[installation guide](../INSTALL.md) covers Core and Full Python profiles and a
first synthetic exercise. The [skill and capability guide](SKILLS_AND_CAPABILITIES.md)
explains all five skills and 55 user-facing capabilities. The
[setup matrix](CAPABILITY_SETUP_MATRIX.md) identifies prerequisites and safe
first inputs; the [evidence table](CAPABILITY_VALIDATION_EVIDENCE.md) separates
smoke tests from narrower diagnostics. Optional external tools and services
are described in the [backend guide](OPTIONAL_BACKENDS.md).

## Dated validation

- An earlier private-source commit passed both hosted macOS 15 Core jobs on
  2026-09-24: arm64 with locked dependencies and Intel with an unlocked
  compatibility resolution. That private run is dated evidence for the older
  baseline only and cannot validate this new public history.
- The clean-root public-source commit `b57c168` passed the
  [Core run](https://github.com/interemi/scientific-workbench-public/actions/runs/36435979426)
  on 2026-09-28: arm64 locked and Intel unlocked, 306/306 Swift tests and 23/23
  synthetic Core cases in each job, with the 1,926-entry snapshot intact. Its
  separate [manual Full run](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
  installed the 200-package Full lock plus three pinned tools in a fresh hosted
  arm64 environment, passed 23/23 Core cases and 39/39 document tests. The
  results apply to that SHA only.
- The same `b57c168` source candidate was checked locally on the development Mac:
  306/306 Swift tests, a 16/16 quality gate without the DOCUS benchmark, and
  a 1,926-entry bundled-skill snapshot passed. A synthetic Full smoke passed
  38/38 cases in an existing Python 3.11 environment. That smoke does not
  establish a fresh installation of the current Full lock.
- On 2026-09-27 the app GUI completed a synthetic `profile_table` exercise
  on the development Mac using the bundled skill root. The example input
  remained unchanged. No manual interactive test has been performed on a
  second Mac.

Hosted checks for the exact public commit must be read from that commit's
[Portable validation runs](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml).
Older green runs do not validate newer commits.

## Limits to understand before use

- This is a source distribution. There is no signed or notarized downloadable
  app release, independent-Mac UI acceptance, or validated Intel dependency
  lock. The fresh hosted Full installation checked Core cases and document
  tests; the separate 38-case Full smoke ran locally in an existing environment.
  Neither covers every optional backend or interactive app use on another Mac.
- Documentation covers 55 capabilities, but not every optional backend,
  account, model, or scientific route has been exercised end to end. Some
  require separate software, permissions, or paid services. TEAREDUCE is an
  optional external notebook backend and is not bundled or installed by Full.
  Legacy `.xls` macro assessment is unavailable in this source candidate.
- Successful execution does not establish scientific correctness. Check
  methods, units, uncertainties, outputs, and original-input hashes for each
  research use. See the [use limitations](../README.md#use-limitations-and-no-warranty).
- Third-party attribution and remaining notice questions are recorded in the
  [dependency inventory](DEPENDENCIES_AND_LICENSES.md). A license statement
  for project-authored material does not replace third-party obligations.

For a security concern, follow [SECURITY.md](../SECURITY.md). The private
reporting button must be verified on the public GitHub repository before it
is advertised as available. This page does not assert that it is active.
