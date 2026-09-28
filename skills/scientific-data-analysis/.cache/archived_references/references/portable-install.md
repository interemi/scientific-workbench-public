# Portable Install Guide

Compact v2.5 portability note. Use this when moving or validating `scientific-data-analysis` on another machine.

## Core Rule

Copying the skill folder is not enough: validate Python, optional backends, and platform-specific tools. Core routes must degrade cleanly when extras are missing.

## Target Path

```text
~/.codex/skills/scientific-data-analysis
```

## Recommended Setup

Conda/datanalysis for the full stack:

```bash
conda env create -f environment.yml
conda activate datanalysis
python scripts/env_doctor.py --summary-json env_doctor.json
python scripts/datanalysis_healthcheck.py --summary-json datanalysis_health.json
```

Light core route:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-core.txt
python scripts/env_doctor.py --summary-json env_doctor.json
```

## Optional Tools

- Keynote and Quick Look: macOS-only, optional, must block cleanly when absent.
- LibreOffice: useful for office/presentation PDF export.
- LaTeX distribution: only needed for local compile, not for source review.
- STILTS/TOPCAT/APT/TEAREDUCE: optional astronomy backends, never core dependencies.

## Portable Smoke

```bash
python scripts/portable_smoke_test.py --profile core --output-dir smoke-out --examples-dir examples --summary-json smoke-out/summary.json
python scripts/sync_public_surface_docs.py --check
```

Archive note: the long historical portability guide was moved to `tmp/v2_5_efficiency_goal/archived_mother_references/portable-install.md`.
