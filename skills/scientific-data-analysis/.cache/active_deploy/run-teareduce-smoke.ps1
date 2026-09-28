$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
if (-not $env:OUTPUT_DIR -or [string]::IsNullOrWhiteSpace($env:OUTPUT_DIR)) {
    $OutputDir = Join-Path $RootDir "deploy/teareduce-smoke-output"
} else {
    $OutputDir = $env:OUTPUT_DIR
}

$Args = @(
    "scripts/datanalysis_env.py",
    "run-script",
    "scripts/teareduce_smoke_test.py",
    "--output-dir", $OutputDir,
    "--summary-json", (Join-Path $OutputDir "summary.json"),
    "--manifest-json", (Join-Path $OutputDir "manifest.json")
)

if ($env:SEARCH_ROOT -and -not [string]::IsNullOrWhiteSpace($env:SEARCH_ROOT)) {
    $Args += @("--search-root", $env:SEARCH_ROOT)
}

Push-Location $RootDir
try {
    python scripts/datanalysis_env.py @($Args[1..($Args.Length - 1)])
    Write-Host "TEAREDUCE smoke test complete. See: $OutputDir"
}
finally {
    Pop-Location
}
