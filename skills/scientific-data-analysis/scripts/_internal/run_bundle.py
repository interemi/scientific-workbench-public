"""Thin internal shim; implementation lives in fixtures/_internal."""

from __future__ import annotations

from _internal.deferred_internal import load_deferred_internal as _load_deferred_internal

_deferred_module = _load_deferred_internal(__file__, globals())
