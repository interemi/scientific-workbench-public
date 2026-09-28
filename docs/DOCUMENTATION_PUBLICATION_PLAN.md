# Documentation Publication Plan

All documentation retained in the future public GitHub repository must be in
English. This is the final editorial phase before the complete publication
recheck, after code, scope, licensing, security, ownership, and external-test
decisions are stable.

## Measured private scope

At commit `8bec11f`, the reproducible inventory reported:

- 812 text documentation files;
- 35 PDF paths representing 11 unique PDF contents;
- 59 text files likely to contain Spanish;
- all 11 unique PDFs likely to contain Spanish;
- 29 documents containing author-machine absolute paths;
- zero broken local Markdown links;
- zero active user documents containing the removed unsafe sandbox guidance;
  and
- zero unique PDF contents without a traceable TeX source group.

Run the audit again before using these counts. Later commits can change them.
The inventory also includes plain-text README, release, installation, and
similar named documents, including extensionless files. Numeric `.txt` datasets,
dependency lists, and original third-party license texts are not prose guides.
The language detector is a review aid; manually inspect retained material too.

## Editorial classes

### Active public documentation

Translate active material in place once its facts are frozen:

- `README.md`, `INSTALL.md`, and `CONTRIBUTING.md`;
- GitHub issue and pull-request templates;
- the current Markdown user guide;
- living architecture, release, installation, requirements, troubleshooting,
  contribution, security, and public-readiness documents; and
- the current v2.8 skill guide, with its dated claims preserved and an explicit
  distinction between translation and installed-family compatibility promotion.

Translation must preserve commands, identifiers, units, counts, hashes,
statuses, limitations, and links. A translated claim does not become newer
evidence.

### Historical evidence

Do not overwrite dated checkpoints, audits, benchmark reports, old release
guides, or generated historical PDFs. The private repository keeps those bytes
and their history.

If historical evidence is useful publicly, add a separate English translation
with a reference to the private source commit and mark it as a translation of
dated evidence. The clean public export must include the English derivative and
exclude the Spanish private original. If tests require the historical path, the
export mapping and skill manifest must be updated coherently and revalidated;
do not remove a guide in isolation.

### Private or obsolete instructions

Private-upload instructions, private checkpoints, author-machine commands, and
superseded internal handoffs should normally remain private. Record each exact
path in `distribution/public-source-exclusions.txt` with a reason in
`PUBLIC_SOURCE_HANDOFF.md`. An exclusion is not complete until the exported
snapshot passes its own tests and link audit.

## Duplicate guide handling

The 35 PDF paths collapse to 11 byte-identical content groups. The Spanish TeX
guide paths similarly contain repeated byte-identical copies. Translate each
canonical source once, then use a reviewed synchronization step so every
retained duplicate is derived from the same English source. Verify hashes after
synchronization.

Generated PDFs must be rebuilt from the English TeX source in a new temporary
directory. Inspect rendered pages and extracted text before replacing a public
derivative. Never compile over the private historical PDF.

## Final sequence

1. Record the private source commit and existing local changes.
2. Save the pre-translation documentation inventory outside the checkout.
3. Translate active documents and add English derivatives for retained
   historical evidence.
4. Populate the exact public exclusion/mapping scope without deleting private
   originals.
5. Rebuild retained PDFs from English sources in isolated output directories.
6. Review and commit the exact editorial/exclusion scope locally, then confirm
   the private worktree is clean. Keep its complete inventory as evidence;
   preserved Spanish originals mean that the private tree need not pass the
   public English gate.
7. Export a clean public snapshot from that exact commit. Initialize a temporary
   Git repository in the snapshot so the auditor can enumerate its files.
8. Run the strict documentation audit **inside the exported snapshot**:

   ```bash
   python3 script/audit_public_documentation.py \
     --require-english \
     --strict-links \
     --strict-portability
   ```

   Then run history/secret checks, snapshot verification, Swift tests, release
   readiness, and the full quality gate on the same export. The exported
   publication scope, not the private preservation tree, is authoritative for
   the final English/link/portability result.
9. Review the staged public tree and provenance manifest before any remote or
   visibility action.

The goal is not met by reducing the detector score, adding broad language
exceptions, or hiding a document that will still be present in the public
repository.
