#!/usr/bin/env python3
# Thin entrypoint; executable body lives in fixtures.
from _internal.fixture_script_dispatch import main as _dispatch_main, load_fixture_module as L

if __name__ == "__main__":
    raise SystemExit(_dispatch_main(__file__))

m = L(__file__)
if m:
    globals().update({key: value for key, value in vars(m).items() if not key.startswith("__")})
