# v2.0 P1-10 STILTS/TOPCAT Optional Panel

STILTS and TOPCAT remain optional astronomy backends. ScientificWorkbench
exposes them in an optional settings panel, never as a core readiness
requirement.

## Closed Scope

- The panel reports Java, STILTS, and TOPCAT readiness.
- Users may provide explicit STILTS command/JAR and TOPCAT command/JAR paths.
- The check runs `external_astro_tools_preflight.py --require-stilts --probe`.
- Missing or invalid STILTS configuration returns `BLOCKED_CONTROLADO` with
  `errors.kind=missing_optional_backend`.
- The panel offers `catalog_workbench.py crossmatch-sky` as the native
  alternative for compact or medium sky crossmatches.
- `stilts_workbench.py` supports a no-input guided preflight from the capability
  catalog.

## Exposure

| Target | App exposure | Core dependency |
|---|---|---|
| `stilts_workbench.py` | `optional_panel` | no |
| TOPCAT GUI | manual inspection only | no |
| `catalog_workbench.py crossmatch-sky` | native alternative | datanalysis route |

## App-Facing Messages

When STILTS is absent:

- summary: STILTS/TOPCAT is unavailable, while core workflows remain ready;
- state: `BLOCKED_CONTROLADO`;
- error kind: `missing_optional_backend`;
- next route: native catalog crossmatch when scientifically equivalent.

When STILTS is ready:

- summary: Java and STILTS are ready;
- TOPCAT may remain unavailable without blocking reproducible STILTS work;
- STILTS remains the preferred reproducible command backend.

## Safety

- No input catalog is modified by preflight.
- No STILTS/TOPCAT installation is performed automatically.
- Explicit commands are checked, not trusted silently.
- TOPCAT GUI automation is outside this workflow.

## Regression

`scripts/audit_v2_0_p1_10_stilts_panel_regression.py` validates:

- real-machine readiness is represented honestly;
- a fake launchable STILTS command is detected without becoming a core
  dependency;
- missing and invalid commands block cleanly;
- the native alternative is present;
- the app panel, service, command builder, and tests remain wired.
