# Export artifacts to a timestamped zip file.
# Usage: .\tools\export-artifacts.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = "artifacts-$timestamp.zip"

Compress-Archive -Path artifacts/ -DestinationPath $dest -Force
Write-Host "Exported artifacts to $dest" -ForegroundColor Green
