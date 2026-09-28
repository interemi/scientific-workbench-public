$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$CondaBin = if ($env:CONDA_BIN) { $env:CONDA_BIN } else { "conda" }

Set-Location $Root
$EnvList = & $CondaBin env list
if ($EnvList -match '(^|\s)datanalysis(\s|$)') {
  & $CondaBin env update -f environment.yml --prune
} else {
  & $CondaBin env create -f environment.yml
}
& $CondaBin run -n datanalysis python scripts/env_doctor.py --summary-json (Join-Path $Root "deploy\env_doctor.conda.json")
Write-Host "Conda installation complete. Activate with: conda activate datanalysis"
