# GitHub release plan

Status: planned. No tag or GitHub Release is authorized or created by this document.

Scientific Workbench is currently distributed as source in
[`interemi/scientific-workbench-public`](https://github.com/interemi/scientific-workbench-public).
A GitHub Release will identify one reviewed source commit and give users a stable
version, release notes, and a download page. It will not turn the Swift package
into an installed, signed, or notarized macOS app. The first release should be
marked **pre-release** and contain no application binary or installer.

## Version and scope

Use a product-version tag such as `v1.0.0-alpha.1` only after checking that it
matches the app-version decision. The current release tooling defaults to app
version `1.0.0`; the integrated app/skill compatibility line `2.0` and declared
skill axis `2.8` are separate, as recorded in
[ADR 0003](../DECISIONS/0003-versioning-and-release-evidence.md). A tag must not
imply that every installed skill has been promoted to `2.8` or that a signed app
exists. Decide the exact first tag at the release checkpoint; never reuse or move
a published tag to replace evidence.

The release notes should state the supported macOS/Python combinations, what
Core and Full validation actually covered, required optional tools, known
limitations, the exact Git commit, and links to [installation](../INSTALL.md),
[portable validation](PORTABLE_VALIDATION.md), and [license terms](../LICENSE).
They must say that the app has not been manually tested on another Mac and that
scientific results require independent review. Historical test results apply
only to their recorded commits.

## First source pre-release checkpoint

1. Finish a coherent roadmap phase and merge its reviewed changes normally into
   `main`. Do not release an unmerged branch or a dirty working tree. Choose the
   exact `main` commit and record its full SHA and tree hash.
2. On that exact source tree, pass the strict English/links/portability audit,
   distribution snapshot and lock checks, Git publication readiness, Swift
   tests, release readiness, and the applicable quality gate. Retain output and
   report any failed or skipped check. Run the separate Full-profile and optional
   backend checks before claiming their coverage.
3. Confirm the public GitHub Actions Core jobs for that same commit pass on
   macOS arm64 (locked) and Intel (unlocked compatibility). The workflow does
   not currently trigger on tags; a successful earlier or later commit is not
   equivalent. Its manual Full job has narrower coverage and must be described
   accurately if used.
4. Test a fresh source checkout at the selected commit with
   [INSTALL.md](../INSTALL.md), the bundled-backend snapshot check, a new
   isolated Python environment, and a synthetic app run. Protect existing
   installations and input data. Before recommending GitHub's automatic ZIP or
   tarball as an installation route, extract one and verify its required
   relative symlinks and snapshot; until then, recommend `git clone` and checking
   out the release tag.
5. Review the changed-file inventory, license/third-party boundary, secrets,
   documentation, and release notes. Do not attach local logs, datasets,
   environments, models, credentials, or historical evidence directories as
   Release assets. The first source pre-release needs no custom asset.
6. Prepare a **draft** GitHub Release against the reviewed tag. Check its title,
   notes, target commit, pre-release flag, and automatically generated source
   archives. Publish only after the owner approves that concrete result.

The release notes should contain: what changed; how to install this exact tag;
which tests passed on its exact commit; Core/Full and architecture limits;
known issues and scientific-use warnings; and how to report vulnerabilities via
[SECURITY.md](../SECURITY.md). Write them manually for the first release so
automatically generated notes cannot overstate coverage.

## Later binary distribution

An optional app-bundle Release is a separate milestone. It requires the
[bundle release checklist](../RELEASE_CHECKLIST.md), reviewed skill-version
evidence, explicit packaging authorization, Developer ID signing and Apple
notarization for normal public Gatekeeper acceptance, archive/manifest checks,
and a tested installation path. An ad hoc signed development bundle is not a
public installer. GitHub Releases do not provide app auto-update behavior by
themselves; that would need its own design and verification.

## Current state

As inspected on 2026-10-08, the public remote has no tags or Releases. The
portable workflow runs for branch pushes, pull requests, and manual dispatch,
not tag pushes. Phase 4 work remains in progress locally; no first-release tag
or publication date has been selected.
