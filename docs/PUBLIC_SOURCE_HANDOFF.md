# Public Source Handoff

The development GitHub repository is the private preservation and development
record. Do not change its visibility to public: its reachable history contains
personal email addresses, machine-specific paths, historical Spanish documents,
and evidence that is useful privately but unsuitable for a clean public start.

A separate private source repository exists at
`interemi/scientific-workbench-source`. It contains an earlier baseline and
hosted validation history, including an older internal readiness document.
Keep it private. The repository intended for public visibility is
`interemi/scientific-workbench-public`. It was created privately with one
reviewed source snapshot and a new Git root commit on 2026-09-28. Preserve both
private histories. Later updates must descend normally from that new root.

## Before exporting

Before making a snapshot, the exact private source commit must have:

- a clean worktree;
- a selected project license and a recorded third-party distribution boundary;
- reviewed ownership of fixtures, icons, guides, and copied source; and
- hash-bound exclusions and replacements for historical private paths and
  Spanish documentation intended to remain only in the private record.

The private commit deliberately retains original historical evidence. The
exported copy, not the private source tree, must pass strict English,
portability, secret, snapshot, test, release, and quality checks before its
content is committed to the new source repository. Hosted clean-runner
evidence can only follow a private upload;
it must be reviewed before any public-visibility decision. Unresolved
third-party terms remain blockers for the relevant distribution scope.

Review `distribution/public-source-exclusions.txt`. Every exclusion must be an
exact file or directory prefix with a reason recorded here. Exclusion is only a
publication-scope decision; it must not delete or rewrite the private evidence.

## Reviewed documentation exclusions

| Private original excluded from export | Retained English edition | Reason |
| --- | --- | --- |
| `docs/M102_GUIDED_COVERAGE.md` | [M102_GUIDED_COVERAGE.en.md](M102_GUIDED_COVERAGE.en.md) | Preserve the Spanish milestone record privately; publish a traceable English edition with the original hash and dated scope |
| `docs/M103_PERSISTENCE_EVOLUTION.md` | [M103_PERSISTENCE_EVOLUTION.en.md](M103_PERSISTENCE_EVOLUTION.en.md) | Preserve the Spanish recovery/validation record privately; retain all counts, schemas, and dates in the English edition |
| `docs/PUBLIC_PREPARATION_2026-09-14.md` | [PUBLIC_PREPARATION_2026-09-14.en.md](PUBLIC_PREPARATION_2026-09-14.en.md) | Preserve the initial private preparation record; retain dated evidence and then-pending requirements in English |
| `docs/PUBLIC_FULL_VALIDATION_2026-09-15.md` | [PUBLIC_FULL_VALIDATION_2026-09-15.en.md](PUBLIC_FULL_VALIDATION_2026-09-15.en.md) | Preserve the original full-smoke failure and correction record; translate without relabeling historical failures |
| `docs/PUBLIC_FULL_LOCK_2026-09-15.md` | [PUBLIC_FULL_LOCK_2026-09-15.en.md](PUBLIC_FULL_LOCK_2026-09-15.en.md) | Preserve the original dependency-lock evidence; retain package counts, hashes, warnings, and platform limitations in English |
| `docs/PUBLIC_PRIVACY_REVIEW_2026-09-14.md` | [PUBLIC_PRIVACY_REVIEW_2026-09-14.en.md](PUBLIC_PRIVACY_REVIEW_2026-09-14.en.md) | Preserve the initial privacy/provenance report; translate findings without publishing personal identifier values |
| `docs/PUBLIC_SECURITY_REVIEW_2026-09-16.md` | [PUBLIC_SECURITY_REVIEW_2026-09-16.en.md](PUBLIC_SECURITY_REVIEW_2026-09-16.en.md) | Preserve the original security review; retain exact fixes, tested scope, and review limitations in English |
| `docs/PUBLIC_DEPENDENCY_REVIEW_2026-09-15.md` | [PUBLIC_DEPENDENCY_REVIEW_2026-09-15.en.md](PUBLIC_DEPENDENCY_REVIEW_2026-09-15.en.md) | Preserve the dependency notice and OCR-weight investigation; retain unresolved findings and hashes in English |
| `docs/ASSET_AND_FIXTURE_PROVENANCE.md` | [ASSET_AND_FIXTURE_PROVENANCE.en.md](ASSET_AND_FIXTURE_PROVENANCE.en.md) | Preserve the original asset review; retain the dated inventory and source hashes in English |
| `M101_CHECKPOINT_2026-09-13.md` | [M101_CHECKPOINT_2026-09-13.public.md](../M101_CHECKPOINT_2026-09-13.public.md) | Preserve original machine paths privately; publish an otherwise unchanged edition using explicit path aliases |
| `docs/PRIVATE_CHECKPOINT_2026-09-14.md` | None | Historical private-copy preparation and upload state; private evidence retained, subsequent public preparation records remain available |
| `docs/UPLOAD_PRIVATE.md` | This handoff | Completed owner-specific upload instructions for the original private repository; superseded for public export |
| `Guides/ScientificWorkbench_Guia.tex` and `Guides/ScientificWorkbench_Guia.pdf` | [Current user guide](../Guides/Scientific_Workbench_User_Guide.md) | Superseded Spanish app guide with author-machine paths; neither file is required by the app, bundle scripts, or tests |

Active links point to the English editions. These exclusions do not affect
the skill snapshot or runtime files. Validate the exported tree and links
before treating this reviewed scope as publication-ready.

## English editions at legacy skill paths

Some skill references and historical checks depend on existing guide paths.
`distribution/public-documentation-map.json` explicitly maps reviewed original
files to English editions under `docs/`. Both hashes and a review reason are
required. Current editions are listed in the [guide inventory](skill-guides/README.md).

The exporter reads mappings, editions, and repository-local exclusions from the
selected commit. It rejects changed hashes, missing/excluded editions, executable
files, symlink replacements, and attempts to replace runtime code as documentation.
An explicitly supplied external exclusion policy is recorded by hash.

Only the exported copy changes: legacy skill paths receive the reviewed English
bytes, existing symlinks retain their targets, and a derived skill manifest
records updated document sizes/hashes plus original-manifest and mapping hashes.
The private manifest and all private skill files remain unchanged. This is not
a skill release promotion or a migration of application persistence.

The private checkout also contains author-machine fallback paths in 32
historical Python regression scripts. The reviewed, hash-bound substitution
policy at `distribution/private-code-path-map.json` is excluded from the public
snapshot because it contains the original private path strings. During export,
only the listed regular Python files receive the exact reviewed substitutions.
App-root references resolve to the exported checkout, interpreter references
use the selected environment, and installed-root references use the current
user's skill directory. The source scripts remain unchanged privately. The
public skill manifest and `SOURCE_PROVENANCE.json` record the transformed hashes
and the policy hash. These historical scripts still require their relevant
optional backends and scientific fixtures when run; path portability alone is
not a fresh validation of their original scientific results.

Transformed exports use `SOURCE_PROVENANCE.json` schema 2, with per-file
`transformation` records and hashes of the actual exported bytes. Untransformed
exports retain schema 1. Verify the derived backend with
`script/check_distribution_snapshot.py` and run the applicable gates on that
export; do not reuse a private-tree PASS as proof of the transformed snapshot.

## Create the snapshot

Choose a new destination outside the private checkout. It must not already
exist:

```bash
python3 script/export_public_source.py \
  --source-ref HEAD \
  --output "$HOME/ScientificWorkbench-public-source"
```

The exporter:

- refuses a dirty private worktree;
- resolves the requested ref to an exact commit and tree;
- copies only tracked blobs from that commit;
- applies only the explicitly reviewed, hash-bound documentation replacements
  described above and records the derived manifest;
- preserves executable bits and safe relative symlinks;
- rejects symlinks that would escape the snapshot;
- never overwrites an existing destination; and
- writes `SOURCE_PROVENANCE.json` with the source commit, tree, exclusions,
  modes, sizes, and SHA-256 values.

It does not initialize Git, create a remote, push, publish, sign, notarize, or
package a release.

## Review the exported snapshot locally

After checking `SOURCE_PROVENANCE.json`, a separate Git index in the exported
folder may be needed for publication audits. This index is for local review;
it does not make the export a successor to the existing source repository.
Inspect the exported file list and manifest before staging its reviewed paths.
Use the identity that the owner wants to publish; do not copy a local machine
address automatically if a local audit commit is needed.

```bash
cd "$HOME/ScientificWorkbench-public-source"
git init
git branch -M main
git add --all  # only after checking the export inventory and exclusions
git status --short
git diff --cached --stat
git diff --cached --check
git diff --cached --name-status
```

Before integrating the snapshot, run the same publication checks from the
exported directory. The final documentation audit must use all strict options:

```bash
python3 script/audit_public_documentation.py \
  --require-english \
  --strict-links \
  --strict-portability
./script/check_git_publication_readiness.sh
./script/run_swift_tests.sh
./script/check_release_readiness.sh
./script/run_quality_gate.sh
```

Do not suppress a failure or copy a report from the private checkout. Evidence
must refer to the commit being published.

## GitHub handoff

The reviewed export must **not** be pushed to either existing private
repository. Their histories are preservation records. Do not force-push,
replace, or publish those histories.

Only after the final export inventory, staged scope, and all local gates have
been reviewed:

1. Initialize Git in a separate copy of the exact export. Review every staged
   path, file mode, and content hash; make one root commit with the owner's
   approved public identity. The source provenance manifest records the
   private source commit without importing its Git history.
2. For this project, the owner created an empty **private** repository named
   `interemi/scientific-workbench-public`, without GitHub-generated files. The
   initial root commit was uploaded normally; no private history was pushed.
3. Check the remote SHA, repository privacy, and uploaded tree after each normal
   non-force push. Never replace the private histories or rewrite the public one.
4. Run the two hosted Core jobs and the separate opt-in Full job on the exact
   candidate commit. Review and retain logs and artifacts; check any Actions
   minutes or billing implications before the Full job. The initial commit
   `b57c168` passed both runs on 2026-09-28, but later commits need their own
   runs.
5. Show the owner the exact public scope, remaining limits, and hosted results
   for the final candidate before changing visibility. Verify the newly public
   page and private vulnerability reporting route afterward.

The hosted jobs provide fresh-VM technical installation evidence. If no second
Mac is available, state prominently that independent interactive acceptance
remains unproven. Changing visibility to public is a separate explicit
decision. A source repository passing these checks is not a signed or
notarized macOS release.
