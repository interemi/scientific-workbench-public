# Asset and fixture provenance

English publication edition of `docs/ASSET_AND_FIXTURE_PROVENANCE.md`
at private commit `7bb7d0f`. Original SHA-256:
`ec77b45dd1541fce94618f9cbd72ad9f11a932a06eda16695b533a21d71d538e`.
The Spanish original remains unchanged privately. This records the review dated
September 16, 2026, including decisions pending then; it is not a new asset audit.
Later owner decisions are tracked in [OWNERSHIP_CONFIRMATION.md](OWNERSHIP_CONFIRMATION.md).

This review records what can be demonstrated technically about assets included
in Scientific Workbench. It does not grant licenses or turn file metadata into
proof of ownership.

## Scope and method

Review ran against commit `83815300ccc1a2e6a88a9e5c66a25c3726d65bfa` on
September 16, 2026. Reachable binary Git objects were inspected with
`script/audit_distribution_assets.py` using the prepared core environment.
Git modes, current-tree SHA-256 values, LaTeX sources, and example documentation
were also checked.

The icon was regenerated with `script/generate_app_icon.swift` in a fresh
directory outside the checkout. The ten PNGs and ICNS matched the eleven
distributed files byte for byte. DOCUS was not accessed; no asset, fixture,
or original input was modified.

The tree contains 52 paths with PDF, FITS, PNG, or ICNS extensions. Twenty-four
are internal snapshot symlinks. The 28 regular paths represent 21 unique binary
contents: 11 PDFs, seven PNGs, two FITS files, and one ICNS.

## Results by class

| Class | Technical evidence | Provenance status at review |
| --- | --- | --- |
| App icon | AppKit generator loads no external images; its 11 outputs exactly reproduce `Resources/` files. Generator SHA-256: `1e56886718c3ef467ebcfb2b45b4fffa7edef098c5fd1c8225e55f1140eb80a2` | Reproducible. Code/design ownership confirmation required before public licensing |
| Scientific Workbench guide | PDF has versioned LaTeX source under `Guides/`; no attachments or secret candidates | Traceable source. Authorship/publication permission confirmation pending |
| Skill-family guides | Ten unique PDFs have versioned LaTeX sources; remaining paths are snapshot links. No attachments or secret candidates | Traceable source. `pdfauthor=Codex` describes the tool, not ownership; authorship/incorporated-material confirmation pending |
| Spectroscopy FITS | Two 5,760-byte contents, with 2×32 and 32-value arrays. Headers use `MINI_LEGACY`/`MINI_TEMPLATE`; README declares synthetic examples without real scientific data | Consistent with synthetic fixtures. Owner confirmation of generation and redistribution permission pending |
| Example CSV, Markdown, configuration | Small text files described as synthetic, used by deterministic tests | Reviewed by publication gates. Same authorship confirmation as FITS pending |

## Scientific and document content inventory

| Unique content | SHA-256 |
| --- | --- |
| `Guides/ScientificWorkbench_Guia.pdf` | `f6e09514e930d6c8046084f9f319b32f72b36d2d59a46e521d31e9b8bbc38b01` |
| v1.7 guide | `508ec0551dbb8f15835fa2a140fe411c8dd950d3321391bb36b6c73f20c2fc8c` |
| v1.8 guide | `96ddd9bf1a50d51aad3be74ab4811fa4dae6c4f2678a9ccd141836caa9407d01` |
| v1.9 guide | `fe31f687e62bb8bcb82cca09526dee4c0e44593c701871203d2a6deda6c26c1d` |
| v2.0 guide | `74dc5803dfe59825c6247f9d5e698cd6ec21301320354d4505b940a658bc2d5b` |
| v2.1 guide | `db0cb5e29540abbbfb87849106d19be80bc1a72f04435dae3e727ba0a91f633e` |
| v2.2 guide | `e59cd6d28101734048ed62b1db97464902b7af9a2712f089b57d0e4a35f7ca15` |
| v2.5 guide | `bce6edf03cec7c1c4acb3c61e0b3d6e2c5c8af02b3c82232c31a191968757849` |
| v2.6 guide | `9dee9cdc2cef0bd15fefddb8e7dc79ea5d2c5c1f0c2fbc50e0fb3bb54f35260e` |
| v2.7 guide | `7cf7ccb14301cb1a2c6f42b7c59aed5048d51c053b94b6a4182d47f6eeeafb73` |
| v2.8 guide | `3506fa3576b2f6f2b4eebd7ce4f4036d58fd420988ff12f3b493a25ab1b737bf` |
| `mini_multispec.fits` | `2a2bbfc0f5c6eb6120dfed9715a6579b6c042ca381f96ce89b7f80b66a1970e5` |
| `mini_template.fits` | `39e47f910c47a6af423d4fe1a7e32eab013f76c14d4dda584cea8fa96d058d1b` |

## Privacy and limits

Text/metadata extraction found zero secret candidates, zero read errors, and
zero PDF attachments. Four historical PDFs retain 17 local-path matches already
recorded by the privacy review. They are not credentials but may reveal
author-environment identifiers. Public opening requires explicit acceptance of
that disclosure or a reviewed public distribution preserving private evidence
without rewriting or deleting it.

ICNS is the only object whose internals the generic auditor does not interpret.
Exact reproduction covers technical provenance, not format vulnerabilities.
Inspection also does not establish legal originality, third-party rights, or
scientific validity of synthetic values.

Complete evidence remains outside Git in run `public-assets-20260916.G6QjgR`.
Changes to assets, sources, or links require a new inventory and new evidence.
