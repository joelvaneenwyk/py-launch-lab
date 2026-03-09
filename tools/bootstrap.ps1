# Bootstrap script for py-launch-lab on Windows.
# Requires: winget or scoop for uv, Rust toolchain for pyshim-win.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== py-launch-lab Bootstrap ===" -ForegroundColor Cyan

# --- uv ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    winget install --id astral-sh.uv -e --source winget
} else {
    Write-Host "uv already installed: $(uv --version)" -ForegroundColor Green
}

# --- Rust ---
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Rust toolchain..." -ForegroundColor Yellow
    winget install Rustlang.Rustup
} else {
    Write-Host "Rust already installed: $(cargo --version)" -ForegroundColor Green
}

# --- Python dev environment ---
Write-Host "Syncing Python dev environment..." -ForegroundColor Yellow
uv sync --extra dev

Write-Host "Bootstrap complete." -ForegroundColor Green
