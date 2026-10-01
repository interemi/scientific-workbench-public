# Clean-install acceptance

Status: this is a technical installation evidence form, not a requirement to
recruit a tester. The owner has no second Mac and does not plan a separate
local-user/environment trial. Follow the
[research-led acceptance decision](RESEARCH_LED_ACCEPTANCE.md) on the available
Mac and exact-commit GitHub-hosted runners; mark every unperformed step
`INCOMPLETE`. This blank form is not evidence that installation passed.

The hosted workflow runs on newly provisioned macOS runner images and checks
the source checkout, new core environment, Swift/distribution tests, and
synthetic backend workflows. It does not exercise the app's interactive setup
or represent an untouched consumer Mac. Mark untested interactive rows
`INCOMPLETE`. A signed or downloadable app still needs its own installation
and Gatekeeper acceptance.

Copy the form into a new evidence directory outside the checkout. Use only
synthetic data and retain every failure. Do not edit earlier reports.

## Identification

- Date and operator:
- Evidence mode: hosted clean runner / available Mac with an existing environment / available Mac with a new isolated environment:
- Run URL and runner image, or local evidence directory:
- Commit (`git rev-parse HEAD`):
- macOS and architecture (`sw_vers`, `uname -m`):
- Swift and selected toolchain (`swift --version`, `xcode-select -p`):
- Selected Python, version, and source:
- Core/full profile; lock path and SHA-256:
- Existing Codex, Conda, skills, or other app installations:
- External tools installed specifically for this test:

## User journey

| Step | Evidence to retain | Result and observations |
| --- | --- | --- |
| Clone GitHub following INSTALL.md | Commit and verified 1,926-entry backend snapshot | Pending |
| Review the setup plan | Command and new destination | Pending |
| Install core | Plan, package inventory, pip check, and env-doctor | Pending |
| Run `run_portable_core.py` | verification.json, logs, and manifest | Pending |
| Build and open the app | Build log and screenshot without personal data | Pending |
| Configure root, Python, and output | Available catalog and Setup Checklist | Pending |
| Prepare a synthetic table or FITS | Readable plan and successful Dry Run | Pending |
| Run from the interface | Final job, command, manifest, and accessible artifacts | Pending |
| Inspect results | Expected values/units checked against the fixture | Pending |
| Cancel a synthetic workflow | Cancelled job with no remaining owned child process | Pending |
| Close and reopen the app | Recoverable history and artifacts | Pending |
| Try a missing optional backend | Actionable message without false success | Pending |
| Check original-input protection | Identical before/after hashes | Pending |

## Outcome

- Steps completed by following the written guide exactly:
- Steps requiring explanation missing from the guide:
- Failures, exact commands, and inspected logs without keys or personal data:
- Result: PASS / FAIL / INCOMPLETE.
- What this test establishes and what remains untested:
- Whether interactive use on another Mac was tested (normally no):

Passing automated checks does not complete any unperformed UI rows or establish
scientific correctness across all workflows. An operator-run GUI walkthrough
does not measure unfamiliar-user comprehension. Original scientific data is
unnecessary for this acceptance test and must not be attached to issues.
