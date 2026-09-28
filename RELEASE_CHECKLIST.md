# Scientific Workbench Release Checklist

This checklist covers application bundles. Publishing a source repository does
not require signing or notarization; follow
[PUBLIC_SOURCE_HANDOFF.md](docs/PUBLIC_SOURCE_HANDOFF.md) for that process.
An app bundle intended for normal public Gatekeeper acceptance needs Apple
Developer ID signing and notarization. Packaging remains a separate decision.

## 1. Local Release Package

Start in the application checkout. The historical `run_v2_0_dual_gate.sh` is a
separate workspace integration tool, not a file included in this repository.
Set `DUAL_GATE_SCRIPT` to its reviewed absolute path before using these commands.
It must refer to the same application checkout and the deliberately reviewed
skill family. Preserve earlier reports and run destructive-output checks on
safe copies, as described in the [M101 record](M101_CHECKPOINT_2026-09-13.public.md).

After authorization to package, run:

```bash
APP_ROOT="$PWD" "${DUAL_GATE_SCRIPT:?Set the reviewed external dual-gate script path}"
git status --short --branch
./script/package_release.sh --local --version 1.0.0 --build 1 --run-quality
```

Packaging requires a clean Git worktree. Commit the exact validated source
before running this command; generated and local-only paths remain ignored.

Expected output:

- `dist/Scientific Workbench.app`
- `dist/release/<version>/Scientific_Workbench_<version>_<build>_macOS.zip`
- `dist/release/<version>/Scientific_Workbench_<version>_<build>_manifest.json`

The package script verifies both the manifest and extracted archive
automatically. It refuses to overwrite an existing build identifier. To
re-check a package later:

```bash
./script/verify_release_manifest.sh \
  dist/release/<version>/Scientific_Workbench_<version>_<build>_manifest.json
./script/verify_release_archive.sh \
  dist/release/<version>/Scientific_Workbench_<version>_<build>_manifest.json
```

Schema-2 manifests record the full Git revision, branch, build environment,
app/integration/declared-skill version axes, gate execution, and the complete
installed registry-resolution chain. Packaging proves a clean unchanged `HEAD`
around validation and rejects registry drift during the build. Only the exact
allowlisted immutable historical schema-1 manifest is accepted unchanged.

The default declared skill axis is `2.8`; this is not proof that the installed
roots have been promoted to `2.8`. Before packaging with that declaration,
review or synchronize the installed family deliberately, run its installed
checks, and run the dual gate against the same mother root:

```bash
APP_ROOT="$PWD" SKILL_ROOT="$HOME/.codex/skills/scientific-data-analysis" \
  "${DUAL_GATE_SCRIPT:?Set the reviewed external dual-gate script path}"
```

At M101 closure this broad installed-family promotion was intentionally not
performed, so creating an M101 package remains blocked pending that review and
explicit packaging authorization.

This package is for your Mac or controlled local testing. It is not a public
Gatekeeper-ready distribution artifact.

## 2. Signed Developer ID Package

Prerequisites:

- Apple Developer Program membership.
- A `Developer ID Application` certificate installed in Keychain.
- Xcode command line tools available.

Run:

```bash
./script/package_release.sh \
  --sign \
  --identity "Developer ID Application: Your Name (TEAMID)" \
  --version 1.0.0 \
  --build 1 \
  --run-quality
```

The script signs with hardened runtime, verifies the signature, verifies the
app bundle, and creates a zip archive.

## 3. Notarized Public Package

Store notary credentials once:

```bash
xcrun notarytool store-credentials "scientific-workbench-notary" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "app-specific-password"
```

Then run:

```bash
./script/package_release.sh \
  --notarize \
  --identity "Developer ID Application: Your Name (TEAMID)" \
  --notary-profile "scientific-workbench-notary" \
  --version 1.0.0 \
  --build 1 \
  --run-quality
```

The script submits the upload zip with `notarytool`, staples the ticket to the
app bundle, validates the staple, runs Gatekeeper assessment, and creates the
final zip.

## 4. Manual Verification

After packaging:

```bash
codesign --verify --deep --strict --verbose=2 "dist/Scientific Workbench.app"
spctl --assess --type execute --verbose "dist/Scientific Workbench.app"
xcrun stapler validate "dist/Scientific Workbench.app"
```

For local unsigned builds, `spctl` and `stapler` are not expected to pass.

## 5. Release Criteria

- v2.0 dual skill + app gate passes using the explicitly reviewed external
  `DUAL_GATE_SCRIPT`, with `APP_ROOT` pointing to this checkout and `SKILL_ROOT`
  pointing to the exact reviewed family. Its absence is an unmet bundle-release
  prerequisite, not a passing or skipped gate.
- Skill docs and public surface checks pass:
  `cd ~/.codex/skills/scientific-data-analysis && python3 scripts/sync_public_surface_docs.py --check`
- Installed skill public-surface and senior integration gates pass:
  `cd ~/.codex/skills/scientific-data-analysis && python3 scripts/audit_v2_7_senior_integration_regression.py`
- Installed ten-family Phase 8 E2E gate passes:
  `cd ~/.codex/skills/scientific-data-analysis && python3 scripts/audit_v2_0_phase8_dual_e2e_regression.py`
- Git publication readiness passes before any GitHub push or release upload:
  `./script/check_git_publication_readiness.sh`
- `./script/run_quality_gate.sh` passes.
- `./script/run_first_run_smoke.sh` passes against the packaged app with
  isolated preferences.
- `./script/verify_release_manifest.sh dist/release/<version>/Scientific_Workbench_<version>_<build>_manifest.json`
  passes for the package being tested.
- `./script/verify_release_archive.sh dist/release/<version>/Scientific_Workbench_<version>_<build>_manifest.json`
  passes for the extracted package being tested.
- Optional full DOCUS benchmark passes when validating a major milestone:
  `RUN_DOCUS_BENCHMARK=1 DOCUS_BENCHMARK_MODE=full ./script/run_quality_gate.sh`
- `./script/run_docus_safety_contract_smoke.sh` proves early-failure guarding,
  safe-copy symlink isolation, metadata-change detection, and overlap rejection.
- `final-100` is preserved as a historical build identifier and is never reused.
  A future package needs a new unique build identifier and explicit approval.
- Packaged app launches from Finder.
- Dock icon appears correctly.
- `./script/run_finder_dock_smoke.sh` passes for the packaged app.
- `./script/check_settings_surface.sh` passes.
- `./script/run_packaged_real_run_smoke.sh` passes.
- Settings can open the user guide.
- Export Configuration works and does not include API keys.
- Export Support Bundle works and redacts configured secrets.
- A fresh mixed non-DOCUS benchmark still passes.
- Integrated release `2.0` is a dual-gate compatibility claim, not an installed
  skill-version label. Registry-chain evidence binds the observed skill content.
- The declared skill release matches the deliberately reviewed installed family;
  mixed historical labels are documented and never treated as proof by themselves.

## Apple References

- [Distributing software on macOS](https://developer.apple.com/macos/distribution/)
- [Signing Mac Software with Developer ID](https://developer.apple.com/developer-id/)
- [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Packaging Mac software for distribution](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution)
