from pathlib import Path


def test_compact_router_surface_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "SKILL.md").exists()
    assert (root / "scripts" / "scientific_workflow_router.py").exists()
    assert (root / "references" / "v2-5-budget-deferral-hardening.md").exists()
