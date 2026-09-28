# Ownership Confirmation

Public licensing requires an owner statement in addition to technical
provenance. Hashes, reproducible generators, and synthetic-looking data do not
prove that the project has authority to license a work.

On 2026-09-22, the owner confirmed that project-authored material was created
with AI assistance and approved `interemi` as the public attribution name.
The owner then clarified that third parties must not commercially exploit
that work. PolyForm Noncommercial 1.0.0 implements that licensing requirement,
with the permitted-purpose provisions recorded in [LICENSE_DECISION.md](LICENSE_DECISION.md).
This is an owner statement, not an independent determination of the copyright
status of every file.

## Project-authored material

| Scope | Technical evidence | Recorded owner statement |
| --- | --- | --- |
| Swift app, tests, resources, and scripts | Git history and current source tree | Owner confirms the project-authored original and AI-assisted code under the selected license. |
| Five-skill Python family | Complete snapshot and file manifest | Owner confirms project-authored material; incorporated third-party material retains its own terms. |
| Current README, installation, architecture, guides, and decisions | Versioned text and TeX sources | Owner confirms the current documentation and its English editions. |
| App icon and generator | The AppKit generator reproduces the ten PNG files and ICNS byte for byte | Owner confirms the generator and visual design. |
| Synthetic FITS fixtures | Two 5,760-byte fixtures with tiny arrays and synthetic identifiers | Owner confirms these fixtures may be distributed with the project. |
| Other synthetic text/table fixtures | Small deterministic inputs used by tests | Owner confirms project-created fixtures; any third-party input needs separate clearance. |

No copyright or SPDX headers were found in the project source during the
current text scan. That reduces conflicting-header evidence but does not prove
original authorship.

## Historical material

Historical checkpoints, audits, release guides, generated PDFs, and regression
evidence remain part of the private preservation record. They must not be
silently rewritten to make the public tree look cleaner.

For every historical item proposed for public use, choose one reviewed action:

- publish an English translation as a new, clearly identified derivative while
  retaining the private original;
- publish the original only after explicit privacy, language, and ownership
  approval; or
- exclude it from the clean public snapshot and record why.

The public repository starts from a reviewed source snapshot without inheriting
private Git history merely to retain historical evidence.
[PUBLIC_SOURCE_HANDOFF.md](PUBLIC_SOURCE_HANDOFF.md) defines that route.

## Third-party material

The project license must not be applied to:

- Python packages, model weights, or optional backends downloaded by users;
- Apple system frameworks and applications;
- third-party code, fonts, icons, or examples whose terms have not been
  preserved; or
- DOCUS and any other original scientific input outside this repository.

See [SOURCE_DISTRIBUTION_BOUNDARY.md](SOURCE_DISTRIBUTION_BOUNDARY.md) and
[DEPENDENCIES_AND_LICENSES.md](DEPENDENCIES_AND_LICENSES.md) for the current
technical inventory.

## Recorded owner statement

- Public attribution name: **interemi**.
- Selected project license: **PolyForm Noncommercial 1.0.0**, in [LICENSE](../LICENSE).
- Code and documentation: owner confirmation received for material created
  with AI assistance.
- App icon/generator: included in the owner's confirmation.
- FITS and other synthetic fixtures: included in the owner's confirmation.
- Contributions must be offered under the same terms, as described in
  [CONTRIBUTING.md](../CONTRIBUTING.md); contributors retain their rights.
- Decision date and evidence: **2026-09-22**, the owner's license/ownership
  response and separate attribution-name approval in the project conversation.

The exported source scope and exclusions are recorded in the export's
`SOURCE_PROVENANCE.json`. Third-party packages and
uncertain incorporated material retain separate provenance requirements; this
owner statement does not grant rights in those components.
