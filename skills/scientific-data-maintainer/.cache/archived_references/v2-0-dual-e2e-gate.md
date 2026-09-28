# v2.0 dual end-to-end gate

Phase 8 validates the editable `scientific-data-analysis` skill and
ScientificWorkbench together before any release or installed-skill
synchronization. Fixtures are synthetic, anonymized, and copied into temporary
directories. Original inputs remain read-only and are fingerprinted where the
underlying regression supports it.

## Required families

| Family | Expected lane | Accepted result |
|---|---|---|
| tabla profesional | general app workflow | `PASS` |
| documento administrativo | document intake | `PASS` or honest `WARNING` |
| notebook heredado | copied notebook preflight | `PASS`, `WARNING`, or `BLOCKED_CONTROLADO` for interactive or unsafe execution |
| contenedor corrupto | safe inventory/recovery | honest `WARNING` or `BLOCKED_CONTROLADO` |
| serie temporal | app-ready analysis preflight | `PASS` or honest `WARNING` |
| sensor/medicion | physical QA | `PASS` or honest `WARNING` |
| FITS/RGB | expert science workflow | `PASS`, with incomplete WCS reported as `WARNING` |
| backend opcional ausente | optional panel/preflight | `BLOCKED_CONTROLADO`, never false success |
| DOCX roundtrip en copia | inventory, preview, confirmation, edited copy | `PASS`; the source DOCX must remain unchanged |
| Keynote/GUI preflight o bloqueo | confirmed macOS GUI export | `PASS` when ready, otherwise `BLOCKED_CONTROLADO` |

## Dual checks

The skill-side family regression runs the v1.9 app-like matrix plus the v2.0
FITS/RGB, DOCX, Keynote, parser/artifact, and jobs/previews regressions. The
top-level gate then runs the ScientificWorkbench quality gate, which includes
Swift unit/integration tests, deterministic headless capability execution,
secret-redaction checks, packaged app verification, Finder/Dock smoke, and a
packaged real-run smoke.

The optional DOCUS benchmark is not a release prerequisite. The Accessibility
driven UI smoke may be skipped in the deterministic pass with
`SKIP_UI_SMOKE=1`; the packaged headless and Finder/Dock paths remain required.

## Release decision

`WARNING` is accepted only for ambiguous or incomplete input that still
produces traceable, useful output. `BLOCKED_CONTROLADO` is accepted only for a
known interactive safety boundary or missing optional backend. Any `FAIL`,
`ROTO`, raw traceback, modified original, misleading artifact, parser failure,
secret leak, Swift test failure, or packaged smoke failure blocks Phase 9.

ScientificWorkbench and the installed skill are not synchronized by this gate.

## Executed result

The final editable-tree run on 2026-06-15 completed with `PASS` and decision
`LISTO_PARA_FASE_9`.

| Family | Result | Evidence |
|---|---|---|
| tabla profesional | `PASS` | Parseable profile run bundle with seven artifacts. |
| documento administrativo | `WARNING` | Useful intake bundle; copied pseudo-documents retain a deeper-format-review warning. |
| notebook heredado | `BLOCKED_CONTROLADO` | Interactive input and a potential side effect were detected before copied execution. |
| contenedor corrupto | `WARNING` | Surviving structure was inventoried without presenting the damaged archive as healthy. |
| serie temporal | `WARNING` | Ambiguous dates were surfaced explicitly. |
| sensor/medicion | `WARNING` | Suspicious physical ranges remained visible in QA. |
| FITS/RGB | `WARNING` | Happy RGB passed; incomplete WCS produced an honest warning and typed previews/manifests. |
| backend opcional ausente | `BLOCKED_CONTROLADO` | Missing backend returned actionable blocking output. |
| DOCX roundtrip en copia | `PASS` | Five style matches were inventoried and two confirmed replacements were written to a separate edited document. |
| Keynote/GUI preflight o bloqueo | `PASS` | Real Keynote preflight and confirmed copied-deck export produced PDF, log, summary, and manifest. |

The ScientificWorkbench quality gate also passed: 151 Swift tests, process-tree
cancellation, planner smoke, golden transcripts, capability E2E, mixed research
benchmark, secret redaction, first-run packaged smoke, app bundle verification,
Finder/Dock smoke, and packaged real-run smoke. The packaged real run completed
three jobs and discovered 20 artifacts.

The DOCUS benchmark remained optional and was not executed. The Accessibility
driven UI smoke was skipped in favor of the deterministic headless and packaged
paths. No installed skill synchronization was performed.
