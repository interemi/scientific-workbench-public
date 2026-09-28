#!/usr/bin/env python3
"""Regression checks for the first audit-fix pass.

This script uses only synthetic fixtures in a temporary directory. It is meant
for maintenance after the April 2026 audit, not as a public user entrypoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_cmd(args: list[str], *, tmp: Path, expect_ok: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(tmp / "mplconfig")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if expect_ok and completed.returncode != 0:
        raise AssertionError(
            f"Command failed unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    if not expect_ok and completed.returncode == 0:
        raise AssertionError(f"Command succeeded unexpectedly: {' '.join(args)}\nSTDOUT:\n{completed.stdout}")
    return completed


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_latex(path: Path, documentclass: str) -> None:
    path.write_text(
        "\n".join(
            [
                documentclass,
                "\\begin{document}",
                "\\section{Intro}",
                "Texto minimo para una revision estructural.",
                "\\end{document}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def check_latex(tmp: Path) -> None:
    tex_plain = tmp / "plain.tex"
    tex_options = tmp / "options.tex"
    plain_json = tmp / "plain_latex.json"
    options_json = tmp / "options_latex.json"
    write_latex(tex_plain, "\\documentclass{article}")
    write_latex(tex_options, "\\documentclass[12pt]{article}")
    run_cmd([sys.executable, str(SCRIPTS / "latex_workbench.py"), "review", str(tex_plain), "--summary-json", str(plain_json)], tmp=tmp)
    run_cmd([sys.executable, str(SCRIPTS / "latex_workbench.py"), "review", str(tex_options), "--summary-json", str(options_json)], tmp=tmp)
    assert read_json(plain_json)["results"]["inspection"]["documentclass_options"] == []
    assert read_json(options_json)["results"]["inspection"]["documentclass_options"] == ["12pt"]


def check_profile_parquet_datetime(tmp: Path) -> None:
    import pandas as pd

    path = tmp / "datetime.parquet"
    summary = tmp / "profile_datetime.json"
    pd.DataFrame(
        {
            "obs_time": pd.to_datetime(["2026-04-24T20:00:00", "2026-04-24T20:01:00"]),
            "flux": [1.0, 1.1],
        }
    ).to_parquet(path, index=False)
    run_cmd([sys.executable, str(SCRIPTS / "profile_table.py"), str(path), "--summary-json", str(summary)], tmp=tmp)
    payload = read_json(summary)
    preview_value = payload["results"]["preview"][0]["obs_time"]
    if not isinstance(preview_value, str) or "2026-04-24" not in preview_value:
        raise AssertionError(f"Parquet datetime preview was not JSON-safe: {preview_value!r}")


def check_li_ascii(tmp: Path) -> None:
    import numpy as np

    spectrum = tmp / "li_ascii.dat"
    output = tmp / "li_out"
    summary = tmp / "li_summary.json"
    wavelength = np.linspace(6704.5, 6710.0, 300)
    flux = 1.0 - 0.12 * np.exp(-0.5 * ((wavelength - 6707.8) / 0.12) ** 2)
    spectrum.write_text(
        "# wavelength flux\n" + "\n".join(f"{w:.6f} {f:.8f}" for w, f in zip(wavelength, flux)) + "\n",
        encoding="utf-8",
    )
    run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "li6708_equivalent_width_workbench.py"),
            "measure",
            str(spectrum),
            "--output-dir",
            str(output),
            "--summary-json",
            str(summary),
            "--continuum-window",
            "6704.8",
            "6705.8",
            "--continuum-window",
            "6708.6",
            "6709.6",
            "--integration-window",
            "6707.2",
            "6708.2",
            "--skip-systematic-grid",
        ],
        tmp=tmp,
    )
    payload = read_json(summary)
    assert payload["results"]["input_format"] == "ascii"
    assert payload["results"]["ew_milliangstrom"] > 0


def check_exoplanet_blocks_missing_comparison(tmp: Path) -> None:
    import numpy as np
    from astropy.io import fits

    seq = tmp / "exoplanet_one_star"
    out = tmp / "exoplanet_out"
    seq.mkdir()
    yy, xx = np.indices((128, 128))
    for idx in range(3):
        data = 100.0 + 6000.0 * np.exp(-0.5 * (((xx - 64.0) / 2.0) ** 2 + ((yy - 64.0) / 2.0) ** 2))
        header = fits.Header()
        header["OBJECT"] = "SyntheticTransit"
        header["IMAGETYP"] = "LIGHT"
        header["EXPTIME"] = 30.0
        header["DATE-OBS"] = f"2026-04-24T20:0{idx}:00"
        header["AIRMASS"] = 1.2
        fits.PrimaryHDU(data.astype("float32"), header=header).writeto(seq / f"science_{idx}.fits")
    completed = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "exoplanet_timeseries_workbench.py"),
            str(seq),
            "--output-dir",
            str(out),
            "--max-sources",
            "1",
            "--skip-reduced-fits",
        ],
        tmp=tmp,
        expect_ok=False,
    )
    combined = completed.stdout + completed.stderr
    if "estrella de comparacion" not in combined and "comparacion valida" not in combined:
        raise AssertionError(f"Unexpected exoplanet failure message:\n{combined}")


def check_photometric_missing_columns(tmp: Path) -> None:
    table = tmp / "photometry_bad.csv"
    table.write_text("instrumental,standard,secz\n1.0,11.0,1.1\n1.2,11.1,1.3\n1.4,11.2,1.5\n", encoding="utf-8")
    completed = run_cmd([sys.executable, str(SCRIPTS / "photometric_solution.py"), str(table)], tmp=tmp, expect_ok=False)
    combined = completed.stdout + completed.stderr
    if "Missing required columns" not in combined or "TypeError" in combined:
        raise AssertionError(f"Unexpected photometric_solution error:\n{combined}")


def check_legacy_rv_input_validation(tmp: Path) -> None:
    fits_root = tmp / "fits_p1"
    fits_root.mkdir()
    csv_path = tmp / "fxcor_missing_aperture.csv"
    csv_path.write_text(
        "case_id,mode,image_name,template_image,vrel_kms,verr_kms,tdr\n"
        "case1,single_rv,obj.fits,tpl.fits,1.0,0.5,8.0\n",
        encoding="utf-8",
    )
    completed = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "legacy_rv_coursework_workbench.py"),
            "analyze",
            str(csv_path),
            "--fits-root",
            str(fits_root),
            "--output-dir",
            str(tmp / "legacy_out"),
        ],
        tmp=tmp,
        expect_ok=False,
    )
    combined = completed.stdout + completed.stderr
    if "faltan columnas requeridas" not in combined or "aperture" not in combined:
        raise AssertionError(f"Unexpected legacy_rv validation error:\n{combined}")


def check_physical_qa_table_flags(tmp: Path) -> None:
    table = tmp / "physical_bad.csv"
    table.write_text("flux,airmass\n-2.0,0.5\n1.0,1.2\n", encoding="utf-8")
    completed = run_cmd([sys.executable, str(SCRIPTS / "physical_qa.py"), str(table)], tmp=tmp)
    payload = json.loads(completed.stdout)
    messages = "\n".join(item["message"] for item in payload["issues"])
    if "negative flux" not in messages or "airmass" not in messages:
        raise AssertionError(f"physical_qa did not flag synthetic bad table:\n{completed.stdout}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sda_step1_regression_") as raw_tmp:
        tmp = Path(raw_tmp)
        checks = [
            check_latex,
            check_profile_parquet_datetime,
            check_li_ascii,
            check_exoplanet_blocks_missing_comparison,
            check_photometric_missing_columns,
            check_legacy_rv_input_validation,
            check_physical_qa_table_flags,
        ]
        for check in checks:
            check(tmp)
            print(f"PASS {check.__name__}")
    print("All audit step 1 regressions passed.")


if __name__ == "__main__":
    main()
