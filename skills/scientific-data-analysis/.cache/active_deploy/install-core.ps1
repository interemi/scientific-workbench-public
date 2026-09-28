$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py -3.11" }
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $Root ".venv" }

Set-Location $Root
Invoke-Expression "$PythonBin -m venv `"$VenvDir`""
& (Join-Path $VenvDir "Scripts\python.exe") -m pip install --upgrade pip setuptools wheel
& (Join-Path $VenvDir "Scripts\python.exe") -m pip install -r requirements-core.txt
& (Join-Path $VenvDir "Scripts\python.exe") scripts/env_doctor.py --summary-json (Join-Path $Root "deploy\env_doctor.core.json")
Write-Host "Core installation complete. Activate with: $VenvDir\Scripts\Activate.ps1"
