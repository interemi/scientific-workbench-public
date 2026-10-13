# Troubleshooting Scientific Workbench

Use this guide to diagnose a failed or blocked run without modifying original
inputs or erasing evidence. Start with the smallest reversible check that can
distinguish the likely causes.

## Preserve evidence first

Before retrying:

1. Leave the original input where it is.
2. Keep the failed run directory, job record, stdout, stderr, summary, manifest,
   and `next_steps.md`.
3. Record the app commit, macOS version, architecture, selected Python path,
   skill root, capability ID, and exact visible status.
4. Export a redacted support bundle if the failure is difficult to reproduce.
5. Use a new run directory for the next attempt.

Do not edit historical reports, regenerate a manifest merely to hide a mismatch,
or paste API keys, private paths, scientific data, or unredacted logs into a
public issue.

## Status glossary

| Status | Meaning | Normal next step |
| --- | --- | --- |
| `PASS` / `SUCCEEDED` | The process and structured contract completed successfully. | Review scientific outputs and assumptions; technical success is not scientific validation. |
| `WARNING` | The run completed but reported a limitation or condition requiring review. | Read warnings and `next_actions`; do not silently promote it to an unconditional pass. |
| `BLOCKED_CONTROLADO` / `BLOCKED` | A known prerequisite, confirmation, dependency, or safe boundary prevented execution. | Follow the recovery advice or use the documented alternative. |
| `FAIL`, legacy `ERROR`, or `ROTO` | The capability or contract failed. A zero process exit code does not override this structured failure. | Inspect the structured error, stdout/stderr, and manifest before retrying. |
| `QUEUED` / `RUNNING` | The job has not reached a terminal state. | Open **Jobs** for its current app-level stage and last recorded change. External tools may not report finer progress; request cancellation if needed. |
| `CANCELLED` | The user or relaunch recovery stopped the job. | Inspect retained partial files and captured logs, verify no child process remains, then decide whether to retry or run remaining steps. |
| `TIMED_OUT` | The configured process deadline expired and the owned process group was terminated. | Reduce inputs, split the workflow, or increase the reviewed timeout within the allowed range. |
| Provider `UNKNOWN` | No connection probe applies to the current session/configuration. | Test the current credential/model/endpoint if a provider is needed. |
| Provider `TESTING` | A probe is in flight. | Wait. Changing the credential, model, or endpoint invalidates its result. |

## Triage order

For any failed workflow, inspect these in order:

1. The recovery card in **Chat**.
2. The selected job's status, exit code, parsed status, structured errors,
   warnings, next actions, and command.
3. `stderr`, then `stdout`.
4. `summary.json`, `manifest.json`, and typed artifacts in **Results**.
5. The workflow summary and run folder.
6. The environment/preflight report for the exact capability.

This order keeps the app-owned structured evidence ahead of guesses from an AI
provider or a manually edited command.

For a recognized job failure, **Jobs** also shows a likely-cause card. It uses
the structured error kind when available, with a limited fallback to the job
message and stderr. Its action opens the relevant setup screen or capability;
it does not retry, install a dependency, delete an occupied output, or change
the failed run. **Recheck Current Files**, **Recheck Python**, **Recheck
Backends**, and **Recheck Local AI** report the current state for applicable
jobs; a successful recheck does not retroactively turn the historical job
into a pass. The file check cannot reconstruct an exact occupied target or
required disk space when the job did not record them. STILTS and APT failures
open their dedicated astronomy setup. Other optional-backend failures and
network/model errors without identifiable AI-provider evidence open the
capability for its setup and preflight, rather than an unrelated settings
section. For cloud-AI evidence, the connection test in Settings checks
the provider you choose **now**; the job record does not separately retain its
historical provider. Inspect the original error before testing or retrying.
Use **Support Bundle** to export redacted diagnostic logs, and review that
bundle before sharing it.

## Common problems

### The capability catalog does not load

- Confirm that **Mother skill root** points to
  `skills/scientific-data-analysis` in the complete checkout.
- Confirm that the four sibling skill roots are still beside it.
- Run `python3 script/check_distribution_snapshot.py` from the repository root.
- Do not regenerate the snapshot if files are missing; restore a complete clone
  or compare it with the reviewed commit.

### The wrong Python interpreter is used

- Read the exact discovered Python path and Core/Full findings in **Settings →
  Environment Diagnosis**. The editable Python preference can differ from the
  interpreter that `datanalysis_env.py` discovers.
- Run `<selected-python> scripts/datanalysis_env.py status` from the owning skill
  root when diagnosing the backend directly.
- System Python may lack packages even when the dedicated `datanalysis`
  environment is healthy.
- Create a new environment instead of updating an evidence-bearing one in
  place.

### Core packages are missing or Full is incomplete

- Treat missing Core packages as a block. Missing Full groups are optional for
  Core routes, but block any selected route that requires them.
- In **Environment Diagnosis**, prepare a new Core or Full destination. Run its
  preview command from the source checkout before considering `--install`.
- If installation stops, keep the new directory and inspect
  `scientific-workbench-setup/installation.log` and `installation-plan.json`
  there. Choose another new destination for a retry; do not run the installer
  against the failed directory or an existing Conda environment.
- After success, select the new `datanalysis/bin/python` in Settings, refresh,
  and confirm that the displayed interpreter and requested profile match.

### The output folder is rejected

- Choose a dedicated results folder outside the checkout, original input trees,
  Desktop/Documents roots that are too broad, and protected credential folders.
- Do not pass raw output arguments that escape the job run directory.
- If the app asks for higher-risk output approval, review the exact input/output
  relationship; approval is session- and context-specific.

### Ollama is unavailable

- Open Ollama and confirm the configured loopback endpoint and model.
- Pull the selected model in **Local AI Setup**.
- Scientific Workbench rejects remote and non-HTTP(S) Ollama endpoints by
  design; use `localhost`, `127.0.0.0/8`, or `::1`.
- A missing local model should not trigger a cloud request automatically.

### A cloud provider fails

- Re-enter the API key in **Settings**, select the intended model, and use
  **Test Connection**.
- Read whether the failure is invalid credentials, quota/rate limit, missing
  model, network/timeout, or another provider response.
- Connection evidence is session-only and resets after a credential, model, or
  endpoint change.
- Gemini currently uses an API key. OAuth is not implemented.
- Switch deliberately to Ollama or deterministic local planning when cloud use
  is unnecessary.

### STILTS, APT, IRAF, iSTARMOD, Keynote, LaTeX, or another optional backend is missing

- Run the dedicated preflight and retain its output.
- Consult [Workflow Requirements](WORKFLOW_REQUIREMENTS.md) for the exact
  dependency and safe fallback.
- Install only the required backend after reviewing its license and source.
- Treat a documented controlled block as honest evidence, not as an app-wide
  failure.

### A notebook asks for input or attempts unsafe mutation

- Execute only the staged notebook copy.
- Declare values for interactive cells or remove the unresolved interaction in
  the copy.
- Do not enable arbitrary inline code to bypass the guided boundary.
- Review the executed notebook, logs, and copied data paths before accepting the
  result.

### A persisted-state recovery notice appears

- Read the recovery notice in **Jobs**.
- Use **Reveal preserved original** to inspect the byte-for-byte archived state
  under `.scientificworkbench/recovery/`.
- A recovered queued/running job becomes cancelled; it does not resume itself.
- Keep the preserved original with the new schema-2 state until the recovery is
  understood.

### Cancellation or timeout appears ineffective

- Wait for the terminal job state; cancellation first requests graceful
  termination and then escalates for the owned process group.
- Open the selected job's **Run → Job → Result** card. The last recorded change
  is an app state transition, not a heartbeat from the external tool. After the
  job stops, inspect its run folder, captured stdout/stderr, partial files, and
  recovery advice before retrying. A retry creates a new run folder.
- Check Activity Monitor only after the app reports the outcome.
- Record any surviving child PID and command in a support bundle; do not kill
  unrelated processes.
- A descendant that deliberately creates a new process group is outside the
  current process-group guarantee and should be reported with a synthetic
  reproducer.

### Results or previews are missing

- Refresh the run bundle from **Jobs**.
- Inspect `manifest.json`, `summary.json`, typed artifacts, and the run's
  `artifacts/` directory.
- Preview support is intentionally bounded; unsupported or large files may need
  **Open** or **Reveal**.
- A generated PDF proves that a file was produced, not that the scientific
  method or interpretation is correct.

### Swift tests do not run with Command Line Tools

Use the repository wrapper:

```bash
./script/run_swift_tests.sh
```

It verifies test discovery and uses the project fallback runner when SwiftPM
does not discover Swift Testing through the installed Command Line Tools.

### Swift build fails before compiling app sources on macOS 27

The maintainer observed this with macOS 27.0.1 and Command Line Tools Swift
6.4. See the [scoped SDK workaround](../INSTALL.md#4-build-the-app), which
worked with an older SDK already present on that Mac. Check the SDK path
before retrying. Preserve the failing build log and toolchain versions if the
workaround does not apply; it does not establish support for every macOS 27
installation.

## Support bundle and issue report

A useful report contains:

- expected and observed behavior;
- commit hash and whether the worktree is clean;
- macOS version and architecture;
- installation profile and selected Python path;
- capability ID, job ID, terminal status, and timestamps;
- the redacted support bundle; and
- the smallest synthetic fixture that reproduces the problem.

Review the bundle before sharing it. Heavy or personal artifacts remain in the
run folder and are listed rather than copied. Follow the repository's
[security policy](../SECURITY.md) for a suspected vulnerability or secret.
Use GitHub's private-reporting form only if **Report a vulnerability** is
visible; otherwise preserve the evidence without posting it in a public issue.

After a fix, rerun the narrow reproducer first, then the applicable release and
quality gates. Keep the failed run unchanged as historical evidence.
