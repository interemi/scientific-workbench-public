# Security review for public preparation — September 16, 2026

English publication edition of `docs/PUBLIC_SECURITY_REVIEW_2026-09-16.md`
at private commit `7bb7d0f`. Original SHA-256:
`f2d83704a002c43fd92d5af38b85be4ae6ec19b86d470ed3c90d5ef5fd94e5e3`.
The Spanish original remains unchanged privately. Results and pending items
describe the source date; translation is not new verification evidence.

This review examines Scientific Workbench's trust boundaries before considering
public opening. The repository remains private. The result does not authorize a
release, replace an independent audit, or establish absence of vulnerabilities.

## Scope and threat model

The audit started at `c9f9440696e83e8ede705193956856dc268dd903` and reviewed the
Swift app, Python entrypoints used by the app, configuration import, process
execution, file access, AI providers, installation, locks, CI, and publication
checks.

The primary assets are original scientific inputs, credentials, the user's
execution authority, and reproducible evidence. Sensitive boundaries include:

- workflow arguments passed from Swift to Python processes;
- JSON configurations that could select local code or executables;
- prompts, attachments, and keys crossing into cloud providers;
- results/manifests that must remain separate from original inputs; and
- external scientific tools that retain user authority and are not contained
  by an app-provided kernel sandbox.

## Confirmed findings and resolution

Two medium-severity, high-confidence findings were confirmed. Both were fixed
in commit `24b9c2b856f84497f3f48e940a460d4d48b910cf`.

### Abbreviated options interpreted with greater authority

The Swift policy blocked exact SQL and notebook-mutation options, but some
Python parsers accepted unique prefixes. The correction:

- rejects exact forms and every prefix of each blocked option in Swift,
  including `--option=value` syntax;
- disables abbreviation in the three affected parsers;
- rejects unknown long assignments that `argparse` could absorb as supposed
  positional inputs; and
- retains legitimate exact options through regression coverage.

### Imported configuration could change local executables

Import applied and persisted skill roots, executables, and Codex sandbox
authority. A prepared file could change the code executed by the next refresh.
Ordinary import now preserves local paths, executables, output, and sandbox
settings. It only applies portable preferences such as provider, models,
Ollama endpoint, attachment context, and timeout. API keys remain outside the
portable file.

A test uses a synthetic executable that would create a marker if accepted,
runs the post-import refresh, and confirms the marker does not exist.

## Observed evidence

| Check | Result |
| --- | --- |
| Swift tests | PASS, 281/281 |
| Distribution tests | PASS, 52/52 |
| Five-skill snapshot | PASS, 1,919 entries |
| Core lock | PASS, 32 runtime packages |
| Full lock | PASS, 215 runtime packages and three build tools |
| Portable core validation | PASS, 23/23; 1,919 snapshot entries before/after |
| Portable full validation | PASS, 38/38; 1,919 snapshot entries before/after |
| Post-fix adversarial reproduction | PASS; six variants rejected with code 2, no markers, input hashes intact |
| Git candidate gate | PASS; zero potential secrets and zero oversized objects |
| Reachable Git history | PASS; zero potential secrets under the reviewed rules and synthetic exceptions |

Reproductions used only synthetic inputs and fresh directories under
`ScientificWorkbenchRuns`. They did not use DOCUS or modify original scientific
data. Local evidence remains in directories with suffixes
`security-fix-*-final-20260916.9a31df` and
`security-option-fix-final-20260916.9a31df`; it is not added to Git.

## Limits and work pending at the source date

- Scan coverage was partial: independent reviewers could not finish because of
  usage limits. A second sequential review examined bypasses, callers, and regressions.
- Trusted scientific processes retain the macOS account's authority. Explicit
  notebook-code confirmation is not operating-system isolation.
- Hosted CI, another Mac, Intel, signing, notarization, and a downloadable
  release had not been exercised.
- Public opening required `SECURITY.md` and a verified private reporting
  channel. Vulnerabilities, keys, and scientific data must not go into public issues.
- Project licensing, legal/technical review of sensitive dependencies and OCR
  weights, and the decision on historical personal identifiers remained pending.

## Repeating public gates

From the checkout root:

```bash
./script/run_swift_tests.sh
python3 -m unittest discover -s Tests/DistributionTests -v
python3 script/check_distribution_snapshot.py
python3 script/check_core_lock.py
python3 script/check_full_lock.py
./script/check_git_publication_readiness.sh
python3 script/audit_publication_history.py --history --check-secrets
```

Results must identify the exact commit. A later PASS on another tree does not
replace this evidence or justify hiding a relevant failure. Current requirements
are recorded in [PUBLIC_READINESS.md](PUBLIC_READINESS.md).
