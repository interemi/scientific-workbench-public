## Change and reason

Link the issue or roadmap task. Describe the concrete problem and resulting
behavior.

## Verification

List commands run, results, and pending checks. Link CI for the reviewed
revision and record each tested macOS version, architecture, profile, and
dependency mode. Record the build and scope of any manual app checks.

For scientific workflows, identify synthetic fixtures, the reference method,
expected and actual values, units, tolerances, and before/after input hashes.
Record scientific-review limits alongside the technical result.

## Scope and risks

Describe changes to contracts, dependencies, or persistence, including the
migration where needed. Identify limitations that the tests do not cover.

## Public snapshot and provenance

- Base and head commits:
- Included new/changed paths and any generated files:
- Explicitly excluded local inputs, run data, environments, models, secrets,
  build output, and other non-source material:
- Origin, license, and required notices for new code, skills, fixtures,
  dependencies, documents, and assets:
- Publication checks and reviewed diff (`git diff --check`,
  `./script/check_git_publication_readiness.sh`, and relevant language/link
  audit). Record any failure or unverified check rather than calling it PASS.

For a scientific result, name the exact commit and environment. Describe CI,
local app verification, independent acceptance, and scientific review using the
evidence available for each.
