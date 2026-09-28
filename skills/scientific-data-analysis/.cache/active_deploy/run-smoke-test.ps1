$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutputDir = if ($env:OUTPUT_DIR) { $env:OUTPUT_DIR } else { Join-Path $Root "deploy\smoke-test-output" }
$Profile = if ($env:PROFILE) { $env:PROFILE } else { "core" }

if ($env:PYTHON_BIN) {
  $PythonBin = $env:PYTHON_BIN
} elseif (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) {
  $PythonBin = Join-Path $Root ".venv\Scripts\python.exe"
} else {
  $PythonBin = "python"
}

Set-Location $Root
& $PythonBin scripts/portable_smoke_test.py `
  --output-dir $OutputDir `
  --examples-dir (Join-Path $Root "examples") `
  --profile $Profile `
  --summary-json (Join-Path $OutputDir "summary.json") `
  --manifest-json (Join-Path $OutputDir "manifest.json")
Write-Host "Smoke test complete. See: $OutputDir"
