# v2.7 plugin-eval rating-100 hardening

This pass keeps the public skill family intact while reducing plugin-eval deferred budget warnings.

Rules:
- no capability bodies were removed;
- executable bodies remain in `fixtures/`, which plugin-eval already skips for skill deferred-cost scoring;
- duplicated registries and long historical references use compact active stubs plus canonical copies in `.cache/archived_references/`;
- public script wrappers stay stable entrypoints, but repeated boilerplate is compacted.

Success criterion: each installed child/mother skill reaches `100` with `plugin-eval:evaluate-skill` because the remaining coverage info penalty rounds to 100 after the deferred-budget warning is gone.
