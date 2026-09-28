#!/usr/bin/env python3
"""Shared runtime and export helpers for scientific-data-analysis scripts."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path


TMP_ROOT = Path("/tmp/scientific-data-analysis-runtime")
KNOWN_EXECUTABLE_PATHS = {
    "conda": [
        str(Path.home() / "opt" / "anaconda3" / "bin" / "conda"),
        "/opt/anaconda3/bin/conda",
        "C:/ProgramData/Anaconda3/Scripts/conda.exe",
        "C:/Users/Public/Anaconda3/Scripts/conda.exe",
    ],
    "soffice": [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "C:/Program Files/LibreOffice/program/soffice.exe",
        "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
    ],
    "libreoffice": [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "C:/Program Files/LibreOffice/program/soffice.exe",
        "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
    ],
    "pdflatex": [
        "/Library/TeX/texbin/pdflatex",
        "C:/Program Files/MiKTeX/miktex/bin/x64/pdflatex.exe",
        "C:/texlive/2025/bin/win32/pdflatex.exe",
    ],
    "latexmk": [
        "/Library/TeX/texbin/latexmk",
        "C:/Program Files/MiKTeX/miktex/bin/x64/latexmk.exe",
        "C:/texlive/2025/bin/win32/latexmk.exe",
    ],
    "qlmanage": ["/usr/bin/qlmanage"],
    "osascript": ["/usr/bin/osascript"],
}

KNOWN_STDERR_SUBSTRINGS = [
    "WARNING: Logging before InitGoogleLogging() is written to STDERR",
    "cpu_info.cc:239] IOError: sysctlbyname failed",
    "/arrow/cpp/src/arrow/util/cpu_info.cc:239: IOError: sysctlbyname failed",
    "Dask dataframe query planning is disabled because dask-expr is not installed.",
    "You can install it with `pip install dask[dataframe]` or `conda install dask`.",
    "This will raise in a future version.",
    "/site-packages/dask/dataframe/__init__.py:42: FutureWarning:",
    "warnings.warn(msg, FutureWarning)",
    "AstropyUserWarning: XDG_CONFIG_HOME is set to",
    "return set_temp_config._get_dir_path(rootname)",
    "Pandas requires version '2.8.4' or newer of 'numexpr'",
    "Pandas requires version '1.3.6' or newer of 'bottleneck'",
    "from pandas.core.computation.check import NUMEXPR_INSTALLED",
    "from pandas.core import (",
    "Matplotlib is building the font cache; this may take a moment.",
    "Fontconfig warning:",
    "Fontconfig error: No writable cache directories",
    "No writable cache directories",
]


def suppress_known_runtime_warnings() -> None:
    """Hide noisy optional-backend warnings that do not affect correctness."""
    warning_patterns = [
        r"Pandas requires version '.*' or newer of 'numexpr'.*",
        r"Pandas requires version '.*' or newer of 'bottleneck'.*",
        r"Pandas requires version '.*' or newer of 'xlsxwriter'.*",
        r"XDG_CONFIG_HOME is set to '.*', but the default location, .* already exists, and takes precedence.*",
        r"Matplotlib is building the font cache; this may take a moment\..*",
        r"Fontconfig warning:.*",
    ]
    for pattern in warning_patterns:
        warnings.filterwarnings("ignore", message=pattern, category=Warning)


def configure_runtime(app_name: str) -> Path:
    """Route caches and temp state to writable directories."""
    root = TMP_ROOT / app_name
    mpl_dir = root / "mplconfig"
    xdg_cache = root / "xdgcache"
    xdg_data = root / "xdgdata"
    xdg_config = root / "xdgconfig"
    xdg_astropy_cache = xdg_cache / "astropy"
    xdg_astropy_config = xdg_config / "astropy"
    font_cache = root / "fontconfig"
    texmf_var = root / "texmf-var"
    pycache = root / "pycache"
    numba_cache = root / "numba-cache"
    astropy_config = root / "astropy-config"
    astropy_cache = root / "astropy-cache"
    ipython_dir = root / "ipython"
    jupyter_config = root / "jupyter-config"
    jupyter_data = root / "jupyter-data"
    for path in (
        root,
        mpl_dir,
        xdg_cache,
        xdg_data,
        xdg_config,
        xdg_astropy_cache,
        xdg_astropy_config,
        font_cache,
        texmf_var,
        pycache,
        numba_cache,
        astropy_config,
        astropy_cache,
        ipython_dir,
        jupyter_config,
        jupyter_data,
    ):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))
    os.environ.setdefault("XDG_DATA_HOME", str(xdg_data))
    os.environ.setdefault("XDG_CONFIG_HOME", str(xdg_config))
    os.environ.setdefault("ASTROPY_CONFIG_DIR", str(astropy_config))
    os.environ.setdefault("ASTROPY_CACHE_DIR", str(astropy_cache))
    os.environ.setdefault("IPYTHONDIR", str(ipython_dir))
    os.environ.setdefault("JUPYTER_CONFIG_DIR", str(jupyter_config))
    os.environ.setdefault("JUPYTER_DATA_DIR", str(jupyter_data))
    os.environ.setdefault("FC_CACHEDIR", str(font_cache))
    os.environ.setdefault("TEXMFVAR", str(texmf_var))
    os.environ.setdefault("PYTHONPYCACHEPREFIX", str(pycache))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(numba_cache))
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("ARROW_USER_SIMD_LEVEL", "NONE")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    suppress_known_runtime_warnings()
    return root


def clean_known_stderr(text: str) -> str:
    """Strip repeated low-signal runtime noise that is harmless in this environment."""
    if not text:
        return text
    kept = []
    for line in text.splitlines():
        if any(pattern in line for pattern in KNOWN_STDERR_SUBSTRINGS):
            continue
        kept.append(line)
    cleaned = "\n".join(line for line in kept if line.strip()).strip()
    return cleaned


@contextlib.contextmanager
def suppress_fd_output(enabled: bool = True):
    """Temporarily silence C/C++-level stdout and stderr for noisy imports."""
    if not enabled:
        yield
        return
    sys.stdout.flush()
    sys.stderr.flush()
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull_fd)


def find_executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return str(candidate_path)
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        for known in KNOWN_EXECUTABLE_PATHS.get(candidate, []):
            known_path = Path(known)
            if known_path.exists():
                return str(known_path)
    return None


def run_command(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def compile_latex_project(main_tex: Path, passes: int = 2, latexmk_path: str | None = None) -> dict:
    """Compile a LaTeX project with latexmk when available, then pdflatex as fallback."""
    configure_runtime("latex_workbench")
    main_tex = Path(main_tex)
    pdf_path = main_tex.with_suffix(".pdf")
    result = {
        "attempted": False,
        "success": False,
        "pdf_path": str(pdf_path),
        "engine": None,
        "passes": [],
        "stderr": "",
    }
    latexmk_bin = latexmk_path or find_executable(["latexmk"])
    if latexmk_bin:
        cmd = [latexmk_bin, "-pdf", "-interaction=nonstopmode", "-halt-on-error", main_tex.name]
        completed = run_command(cmd, cwd=main_tex.parent)
        result.update(
            {
                "attempted": True,
                "engine": "latexmk",
                "passes": [{"command": cmd, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}],
                "success": completed.returncode == 0 and pdf_path.exists(),
                "stderr": completed.stderr or "",
            }
        )
        if result["success"]:
            return result
    pdflatex_bin = find_executable(["pdflatex", "/Library/TeX/texbin/pdflatex"])
    if pdflatex_bin is None:
        if not result["attempted"]:
            result["stderr"] = "No LaTeX compiler found."
        return result
    result["attempted"] = True
    result["engine"] = "pdflatex"
    result["passes"] = []
    for _ in range(max(1, passes)):
        cmd = [pdflatex_bin, "-interaction=nonstopmode", "-halt-on-error", main_tex.name]
        completed = run_command(cmd, cwd=main_tex.parent)
        result["passes"].append(
            {"command": cmd, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        )
        if completed.returncode != 0:
            result["success"] = False
            result["stderr"] = completed.stderr or completed.stdout
            return result
    result["success"] = pdf_path.exists()
    return result


def detect_presentation_export_backends() -> dict:
    soffice = find_executable(["soffice", "libreoffice"])
    keynote = Path("/Applications/Keynote.app").exists()
    return {
        "soffice": soffice,
        "keynote_available": keynote,
        "notes": (
            "Keynote export is available as a GUI fallback on macOS when AppleScript automation is permitted."
            if keynote
            else "No GUI fallback detected."
        ),
    }
