# Regression Test Wrappers

The skill historically uses executable `scripts/audit_*_regression.py` files as
its release-gate regression suite. This directory provides pytest-style wrappers
around representative audit scripts so external evaluators can recognize the
existing coverage convention without replacing the project-specific gates.

The wrappers intentionally stay small and deterministic. Heavy, optional,
backend-specific, GUI, and long-running regressions remain in the `scripts/`
audit family and release-candidate gates.
