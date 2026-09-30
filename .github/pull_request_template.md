## Change and reason

Describe the concrete problem and resulting behavior.

## Verification

List commands run, results, and pending manual checks. For scientific workflows,
identify fixtures, units, tolerances, and original-input protection.

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

For a scientific result, name the exact commit and environment. A green CI run
proves only the checks it executed on that commit; it is not a scientific or
independent-Mac acceptance result.
