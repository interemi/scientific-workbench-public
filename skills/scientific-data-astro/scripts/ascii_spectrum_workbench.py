#!/usr/bin/env python3
# Thin entrypoint; executable body lives in fixtures.
import sys

from _internal.astro_cli_output_safety import preflight_astro_cli
from _internal.fixture_script_dispatch import load_fixture_module, main as dispatch_main

if __name__ == "__main__":
    safety_returncode = preflight_astro_cli(__file__, sys.argv[1:])
    if safety_returncode is not None:
        raise SystemExit(safety_returncode)
    raise SystemExit(dispatch_main(__file__))

module = load_fixture_module(__file__)
if module:
    globals().update(
        {name: value for name, value in vars(module).items() if not name.startswith("__")}
    )
