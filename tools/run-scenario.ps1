# Run a single scenario by ID.
# Usage: .\tools\run-scenario.ps1 -ScenarioId python-script-py

param(
    [Parameter(Mandatory)]
    [string] $ScenarioId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Running scenario: $ScenarioId" -ForegroundColor Cyan
uv run py-launch-lab scenario run $ScenarioId
