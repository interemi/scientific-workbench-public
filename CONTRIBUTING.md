# Contributing to Scientific Workbench

Scientific Workbench is research software under development. Current priorities
are verifiable scientific workflows, non-destructive data handling, and clear
installation limits. It has not been interactively tested on another Mac.

The [product improvement roadmap](docs/PRODUCT_IMPROVEMENT_ROADMAP.md) orders
post-publication work. Use a GitHub Issue with its task ID and evidence criteria
for the active phase, then link the implementation pull request. Later phases
remain proposals until their prerequisites and scope are clear.

## Change workflow

1. Check the branch, HEAD, and `git status --short` before editing.
2. Make small changes that preserve original inputs and existing local work.
3. For skill changes, update the snapshot and manifest together after reviewing
   provenance, symlinks, contracts, and the diff. Do not copy installed environments.
4. Run tests relevant to the change and document actual failures or limits.
5. Review staging explicitly. Never add models, credentials, or scientific run data.

The manifest identifies the backend in this distribution. Do not regenerate it
during installation or merely to turn a failure into PASS.

## Routine checks

```bash
python3 script/check_distribution_snapshot.py
python3 script/check_core_lock.py
python3 script/check_full_lock.py
python3 -m unittest discover -s Tests/DistributionTests -v
./script/check_git_publication_readiness.sh
./script/run_swift_tests.sh
```

Full gates that open apps or execute scientific workflows need a configured
environment and new output directories. Historical audit scripts may contain
paths from the original environment; they are not portable CI instructions.

The [portable workflow](docs/PORTABLE_VALIDATION.md) checks Swift sources,
distribution safeguards, core installation, and synthetic workflows. Preserve
every failing job and identify the platform actually tested. Use the
[acceptance form](docs/CLEAN_INSTALL_ACCEPTANCE.md) to verify installation and
use by another person.

Changes to persisted models require explicit migrations. Scientific-command
changes require review of units, parameters, statuses, and original-input
protection. Missing optional features must have a visible explanation without
blocking unrelated core functionality.

## Reporting problems

Include the version/commit, macOS and architecture, reproduction steps, expected
and actual results, environment status, and a minimal synthetic example.
Inspect logs and screenshots before sharing: do not attach original scientific
data, credentials, unnecessary personal paths, or unreviewed support bundles.

Do not report suspected vulnerabilities or credentials in public issues.
Follow [SECURITY.md](SECURITY.md) for the private reporting route and what to do
if GitHub does not show its reporting button.

## License and publication

Project-authored code, documentation, the app icon, and synthetic fixtures use
[PolyForm Noncommercial License 1.0.0](LICENSE). Preserve its required notices
in [NOTICE](NOTICE) and applicable third-party notices.

Offer project-authored contributions under the same license and submit only
material you have authority to contribute. Identify third-party code, data,
and applicable terms before inclusion. Contributors retain their rights;
acceptance does not transfer copyright or grant the maintainer automatic
permission to relicense contributions commercially. No separate contributor
license agreement is currently required.

The project is source-available, not OSI open source. Review the
[license decision](docs/LICENSE_DECISION.md) for permitted purposes, including
the license's institutional-use provisions.

Repository visibility, signing, notarization, and releases require explicit
owner decisions. Passing a technical gate does not authorize those actions.
