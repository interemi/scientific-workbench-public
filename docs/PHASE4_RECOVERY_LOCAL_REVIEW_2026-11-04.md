# Recovery actions: local technical review, 2026-11-04

The recovery matrix was exercised on source `88588df` using the test executable
built from `d271065`. Only documentation differs between those sources. Its
executable SHA-256 was
`12bd7a547af5acb3d9812011ae154ff533804312d90ec4d9a15da7905ec15452`.
The existing isolated, ad hoc signed app bundle was reused on the maintainer's
macOS 27.0.1 Apple Silicon Mac. No release bundle was distributed.

## What was simulated and what was observed

Nine terminal job records were created in a separate test history. Every job
was visibly labelled **RECOVERY FIXTURE** and **capability not executed**.
Their error messages were simulated; this review did not fill a disk, break
the network, uninstall packages, or induce a remote-service failure. The
original navigation-test history was preserved separately.

The interface's current-state probes, setup destinations, and support export
were real actions. Eight read-only rechecks and all nine recovery destinations
were observed. The additional timeout case provides a settings action rather
than a recheck of a historical process.

| Simulated failure | Observed current-state check | Recovery destination |
| --- | --- | --- |
| Generic capability network error | macOS reported an available network path. The UI explicitly said that no server request was sent and that endpoint, credentials, model, and service availability remained unverified. | The failed capability's setup and preflight, rather than an unrelated AI panel. |
| Ollama model unavailable | The current selected model was found at the configured local endpoint. The historical fixture remained failed. | Local AI Setup. |
| Python dependency error | The current Python diagnostic reported Core ready and Full incomplete, with detailed package findings available in Settings. | Environment Diagnosis. |
| File permission denied | A generated test file with mode `000` was reported as 0/1 readable; the output root appeared writable. The UI retained its warning that subprocess access and macOS privacy permissions can differ. | Paths. |
| Disk-space error | The current output volume's available capacity was measured. The UI did not infer that a new job would fit because its required space was not recorded. | Paths / output root. |
| Occupied output | Current root-overlap checks passed. The UI kept the exact historical occupied target unverified and required a new destination and Dry Run. The occupied test file was preserved. | The failed capability, for review before a new run. |
| Optional DuckDB backend unavailable | Named-dependency discovery reported `duckdb: not located` in the selected Core environment. It did not claim to test an import or execute DuckDB. | The DuckDB capability's setup and preflight. |
| Missing input | The recorded nonexistent test path was reported as 0/1 readable. | Prepare New Run at the relevant capability. |
| Timeout | No past process was rechecked. Guidance required reviewing logs and input size before changing the limit. | Behavior / capability timeout. |

The selected Core environment was existing Python 3.11.15; this was not a fresh
installation. Full and optional external backends remain separate requirements.
The file used to test denied access was a generated fixture, not an original
input. Its mode was restored to `0600` after the observations, and its content
hash still matched its initial bytes.

## Redacted support export

A deliberately fictitious credential was entered only into the isolated app's
in-memory connection field. **Save Connections** and cloud connection tests
were not used. The selected job contained that same synthetic string in its
retained stdout and stderr so that the actual export could be checked.

The job's **Support Bundle** action produced five local files: job state,
support Markdown, command, stdout, and stderr. None contained the synthetic
credential. Exported stdout, stderr, and job state contained `[REDACTED]`.
The original unredacted fixture history and sidecars remained byte-for-byte
unchanged. The temporary credential was cleared before the app was closed.
No credential was saved to Keychain and no diagnostic was uploaded or sent.

This demonstrates redaction of a **configured** credential. It does not
establish removal of arbitrary unknown secrets or personal paths. Review a
support bundle before sharing it, as described in
[troubleshooting](TROUBLESHOOTING.md#support-bundle-and-issue-report).

## Evidence and limits

After the checks, the nine-record history had the same SHA-256 as its initial
accepted fixture, all jobs retained their failed/timeout states, and no new
capability job existed. The earlier navigation-test history, generated input
bytes, and occupied output also retained their hashes. Raw app screenshots,
accessibility observations, launch records, the redaction check, and a verified
runtime archive remain outside Git.

The initial fixture preparation used an invalid raw timeout status. The app
preserved that seed in its recovery archive and retained the eight valid
records. A separate corrected nine-record history was then prepared with the
documented `timeout` value; both earlier records were preserved. No application
code change was needed for this preparation error.

The underlying code had already passed 380/380 Swift tests and release
readiness at `d271065`; no app or test source changed during this GUI review.
The [workflow-context review](PHASE4_WORKFLOW_CONTEXT_LOCAL_REVIEW_2026-11-04.md)
separately covers real capability execution and cancellation. These fixture
checks do not establish remote endpoint recovery, exhaustive error detection,
successful repair of every external backend, independent usability, or manual
use on another Mac.

This supplies the bounded local P1.13 action/recheck/export acceptance evidence.
Phase 4 remains open for P1.11 model-download acceptance, full quality and
production-bundle checks, coherent public integration, and hosted validation
of the exact candidate.
