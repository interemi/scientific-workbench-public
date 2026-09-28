"""Synthetic scientific regressions for the astro child skill.

All fixtures are created under temporary directories; no source data are read or
modified.  The MULTISPEC expectations follow IRAF 2.18 specwcs:
https://iraf.readthedocs.io/en/doc-autoupdate/tasks/sptable/xonedspec/specwcs.html
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from astropy.io import fits

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "fixtures"
for entry in (str(SCRIPTS), str(FIXTURES)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def load_fixture(relative_path: str):
    path = FIXTURES / relative_path
    name = "astro_regression_" + relative_path.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load fixture module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=180,
    )


LEGACY = load_fixture("_internal/legacy_spectroscopy_common.py")
LI = load_fixture("li6708_equivalent_width_workbench.py")
ASTROMETRY = load_fixture("astrometry_net_workbench.py")
SPECTRAL = load_fixture("spectral_workbench.py")
EXOPLANET = load_fixture("exoplanet_timeseries_workbench.py")
RGB = load_fixture("fits_rgb_batch.py")
CCD = load_fixture("reduce_ccd_batch.py")
PHOTOMETRIC = load_fixture("photometric_solution.py")
RV = load_fixture("radial_velocity_workbench.py")
SB2 = load_fixture("sb2_double_gaussian_workbench.py")
APERTURE = load_fixture("aperture_photometry.py")
ASCII = load_fixture("ascii_spectrum_workbench.py")
