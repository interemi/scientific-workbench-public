"""Run maintainer regression bodies stored outside the active script surface."""

from __future__ import annotations

from pathlib import Path
import sys


def _candidate_targets(root: Path, wrapper_name: str) -> list[Path]:
    """Return regression body locations in preferred modular order."""
    return [
        root.parent / "scientific-data-maintainer" / "fixtures" / wrapper_name,
        root / "fixtures" / wrapper_name,
    ]


def main(wrapper_file: str) -> int:
    wrapper_path = Path(wrapper_file).resolve()
    root = wrapper_path.parents[1]
    wrapper_name = Path(wrapper_file).name
    candidates = _candidate_targets(root, wrapper_name)
    target = next((path for path in candidates if path.exists()), None)
    if target is None:
        locations = ", ".join(str(path) for path in candidates)
        raise SystemExit(f"Archived regression target is missing. Checked: {locations}")

    target_root = target.parents[1]
    for path in [target.parent, target_root, target_root / "scripts"]:
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

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
