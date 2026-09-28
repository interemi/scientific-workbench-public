"""Run maintainer regression bodies stored outside the active script surface."""

from __future__ import annotations

from pathlib import Path


def main(wrapper_file: str) -> int:
    wrapper_path = Path(wrapper_file).resolve()
    root = wrapper_path.parents[1]
    target = root / "fixtures" / Path(wrapper_file).name
    if not target.exists():
        raise SystemExit(f"Archived regression target is missing: {target}")

    namespace = {
        "__builtins__": __builtins__,
        "__cached__": None,
        "__doc__": None,
        "__file__": str(wrapper_path),
        "__loader__": None,
        "__name__": "__main__",
        "__package__": None,
        "__spec__": None,
    }
    exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)
    return 0
