# Remove build artifacts and cached files.
# Usage: .\tools\clean.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$targets = @(
    'dist',
    'build',
    '.mypy_cache',
    '.ruff_cache',
    '.pytest_cache',
    'src\launch_lab.egg-info',
    'artifacts\json',
    'artifacts\markdown',
    'artifacts\logs',
    'artifacts\screenshots',
)

foreach ($t in $targets) {
    if (Test-Path $t) {
        Remove-Item -Recurse -Force $t
        Write-Host "Removed $t" -ForegroundColor Yellow
    }
}

Write-Host "Clean complete." -ForegroundColor Green
