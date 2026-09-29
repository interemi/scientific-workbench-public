# Security Policy

## Reporting a vulnerability

Scientific Workbench is development software with no published
security-response SLA. Do not put vulnerability details, credentials, original
scientific inputs, or unreviewed support bundles in public issues, pull
requests, or discussions.

If this repository's **Security and quality > Advisories** page shows **Report a
vulnerability**, use that GitHub form to send details privately to the owner.
GitHub shows that button when private vulnerability reporting is enabled.
If the button is absent, do not post the details publicly. Existing
collaborators can use their established private contact with the owner; this
repository does not publish a general security contact address.

The owner should keep the reporting route enabled and follow
[GitHub's repository instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository):
enable **Private vulnerability reporting** in the repository security settings,
then confirm that **Report a vulnerability** appears in the repository's
**Security and quality > Advisories** page. The owner should also enable GitHub
notifications for security alerts. Verify the button after any visibility or
security-settings change.

A useful report includes the affected commit, macOS version and architecture,
entry point, expected and observed behavior, impact, and a minimal synthetic
reproduction. Inspect and redact logs before sharing them. Preserve the original
inputs and the failed run's evidence.

## Supported versions

Security reports are assessed against the current `main` source branch. Older
commits may receive a fix only if the owner explicitly decides to maintain
them. There is no supported signed binary release or long-term-support branch.
Include the affected commit in a report so the owner can reproduce it.

## System and scope

This policy covers the macOS Swift/SwiftUI app, bundled five-skill Python family,
configuration and persistence, process execution, provider integrations, setup
scripts, and build/publication workflows in this repository.

The important assets are scientific inputs, credentials, local execution
authority, private prompts and document content, and the integrity of plans,
results, manifests, and recovery evidence.

The app operates under the macOS user's account. It is not a multi-tenant
service and does not provide a dedicated operating-system sandbox for Python,
notebooks, external astronomy tools, or other explicitly selected local code.

## Trust boundaries

Treat attached documents, tables, notebooks, model responses, imported
configuration, registry metadata, and generated manifests as untrusted at the
boundary where they are consumed. A provider response or imported file cannot
grant itself permission to execute code, select new executables, access
credentials, or overwrite scientific inputs.

The owner selects local skill roots, Python, and external tools. Those selections
are an execution trust decision. Imported portable settings must not replace
machine-local executable paths, output authority, or sandbox configuration.

Cloud requests cross a separate boundary from local Ollama requests. Selected
provider, request content, attachment mode, and consent must remain consistent
until dispatch; changing them requires the applicable consent review again.

## Required security properties

- Preserve original scientific inputs and historical evidence. Use separate
  run directories and copied inputs where mutation is required.
- Validate canonical paths and symlinks at filesystem boundaries. Do not let
  catalog entries, manifests, or output paths escape their permitted scope.
- Validate scientific command arguments before execution. Python option
  abbreviation must not bypass the app's argument restrictions.
- Keep provider credentials out of portable configuration and child-process
  environments that do not need them. Redact credentials from errors, logs,
  transcripts, and support exports.
- Apply cloud consent and attachment privacy settings at the payload boundary.
  Ollama endpoints must satisfy the loopback policy, and HTTP redirects must
  not silently cross the selected provider boundary.
- Refuse unsupported persisted schemas without replacing them. Preserve
  recovery copies and distinguish partial recovery from complete success.
- Install dependencies only into a new, explicit environment. For locked
  installs, require the reviewed versions and hashes and preserve failures.
- Tie validation evidence to the actual source revision and environment.
  Failed, skipped, or undiscovered tests must not become a claimed PASS.

## Findings and severity

Report a reachable failure of these properties, including unauthorized
execution, input/evidence modification, credential or private-context
disclosure, path-boundary bypass, and misleading success that conceals a
security-relevant failure.

Assess severity from the actual entry point, attacker-controlled input,
required user action, scope of authority, and realistic impact. A synthetic
fixture can demonstrate a failure; it does not justify a claim of remote
exploitation without a reachable remote path.

No repository-wide finding class is automatically excluded by this policy.
Local execution, optional backends, or existing limitations do not by themselves
make a bypass unreportable. Reproducible dependency findings require assessment
of the affected version, invocation, and impact.

## Known limits

Process-group cancellation does not contain a child that creates a new process
group/session. Explicit notebook execution permission is not OS-level code
isolation. Cloud consent authorizes the selected data transfer; it does not
establish that the remote provider is suitable for every dataset.

Pattern-based secret checks and PDF/FITS metadata inspection are limited triage,
not proof of the absence of secrets in every format. Historical recovery files
may contain personal paths or older logs and require review before sharing.

Automated regression tests do not establish exhaustive security or scientific
correctness. Hosted CI, clean-Mac acceptance, and a verified reporting channel
are separate checks.
