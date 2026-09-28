# Privacy and provenance before opening the repository

English publication edition of `docs/PUBLIC_PRIVACY_REVIEW_2026-09-14.md`
at private commit `4aae9a6`. Original SHA-256:
`0f054120a1467b99a2160b4a5d76f4f7a985987f993e5c2481539eead6ec4709`.
The Spanish original remains unchanged privately. Results and pending decisions
describe the source date; translation is not new execution evidence.

Review started at `e0863066ef82ce52770435c3fcb6a86a3fa8ab41`, with four locally
reachable commits. Previous documents remain preserved. This record does not
authorize publication of the history or establish ownership of materials.

## Implemented checks

- `audit_publication_history.py` inspects Git candidates or every blob in
  reachable commit trees, plus commit metadata/messages. It rejects historical
  review from a shallow clone. It does not print secret values: findings record
  rule, path, object, line, and line fingerprint.
- Tests, scripts, and fixtures are included. Whole-file/directory exceptions
  were removed from the publication gate. The 17 reviewed exceptions are bound
  to path/rule/line hash in `distribution/publication-secret-fixtures.json`.
  Changing a synthetic key invalidates its exception and requires renewed review.
- The gate also rejects Git-visible `.env`, keys, and signing material, even
  when force-added despite `.gitignore`.
- CI prepares a complete-history clone and runs the historical check.
- `audit_distribution_assets.py`, run with the core environment, inspects
  historical PDF, FITS, and PNG content without changing blobs or current files.

These are pattern detection and metadata extraction checks. They do not replace
a complete security audit, legal review, or visual interpretation of assets.
Uninterpreted formats and attachments are identified explicitly.

## Observed results

| Scope | Result | Interpretation |
| --- | --- | --- |
| History through `e086306` | 1,340 text/metadata objects; 21 unique binary blobs; none over 5 MiB | Four commits and their trees traversed |
| Possible secrets in that history | 24 matches for 17 unique reviewed synthetic lines; zero pending under these rules | Does not prove absence of secrets in every format |
| Privacy pattern findings | 196 matches: 170 user paths and 26 emails | Includes examples, historical repetition, and metadata; not 196 distinct personal details |
| Commit identity | Personal and local Mac email addresses present | Owner decision required before publishing that history |
| Historical assets | 11 PDFs, seven unique PNGs, two unique FITS files, one ICNS | Identical copies deduplicated by blob |
| Asset extraction | No read errors or secret candidates; 17 path matches in PDFs | No OCR or embedded-attachment inspection |
| Icon | 10/10 PNGs and the ICNS reproduced byte for byte by the included Swift generator | Reproducible technical provenance without external images; generator ownership confirmation still pending then |
| Distribution tests | PASS, 29/29 | New secrets in tests, secrets removed from tree but retained in history, commit messages, unquoted assignments, changed exceptions, forced Git configuration |

The icon was generated from `script/generate_app_icon.swift` in a new working
directory outside the checkout. The original script regenerates/replaces its
destinations under `Resources/`; it was not run from the project root.
Distributed resources were unchanged. Its source uses AppKit drawing without
loading external images. The generic asset auditor did not interpret ICNS;
exact reproduction verified it separately.

The FITS files contain two small fixtures (2×32 and 32 arrays, identified as
MINI_LEGACY/MINI_TEMPLATE) repeated across skills. CSVs contain minimal example
tables. Size, names, and test use establish their technical role, not legal
proof of origin. DOCUS was not consulted for this review.

## Documents retaining local paths

- `Guides/ScientificWorkbench_Guia.pdf`: two matches.
- v2.0 guide under `skills/scientific-data-maintainer/.cache/active_references/guides/`: four.
- v2.1 guide in the same directory: eight.
- v2.2 guide in the same directory: three.

These historical guides were not rewritten or deleted. Before opening the
repository, decide whether to disclose those identifiers or prepare a reviewed
public distribution while preserving private evidence separately. No history
rewrite, branch/worktree deletion, or visibility change follows without an
explicit decision.

## Provenance and decisions pending at the source date

| Material | Available evidence | Pending |
| --- | --- | --- |
| App and five skills | Sources/local history, manifest, tests | Ownership and incorporated third-party material |
| Icon | Included generator and exact reproduction | Generator ownership |
| Guides and fixtures | Technical inspection and backend references | Authors, permissions, origins, complete-text review |
| Python core | Hashed wheels and license metadata | All included texts and bundled components |
| Full, models, external tools | Declared dependencies | Version/license inventory and distribution conditions |
| Project-code license | None selected | Owner decision after clarifying ownership |
| Historical personal identifiers | Located without republishing values here | Public-history scope and future commit attribution |

Legacy headers were reviewed in the three wheels without License-Expression or
classifiers: charset-normalizer declares MIT, fonttools MIT, and lxml BSD-3-Clause.
fonttools/lxml also include external-component texts; a header alone cannot
complete that review.

## Evidence and recorded next step

Complete reports remain outside Git in run `public-readiness-20260914.jxR4qz`:

- `history-triage-initial.json` and `history-triage-reviewed.json`.
- `candidate-triage-initial.json`.
- `history-assets-reviewed.json` and `asset-provenance-triage.json`.
- `icon-reproduction-verification.json` and the new reproduction directory.
- `publication-audit-tests-final.log` and `publication-audit-tests-29.log` (final suite).

Results apply only to the stated scope; new commits require rerunning auditors.
The recorded provenance next step was owner confirmation of any course,
collaborator, or other external material and resolution of license/public-history
scope. CI, installation, and product work can continue without changing visibility.
