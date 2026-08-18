param(
    [string]$Version = (Get-Content (Join-Path $PSScriptRoot "..\VERSION") -Raw).Trim(),
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

Write-Output "Building CodexUU $Version for Windows..."

# 1. Build frontend assets
pnpm build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed."
}

# 2. Build and bundle the complete Tauri application. The CLI is pinned in
# package.json and installed through pnpm, so a missing global/npx CLI cannot
# produce a misleading partial Rust-only build.
Set-Location $workspace
pnpm tauri build
if ($LASTEXITCODE -ne 0) {
    throw "Tauri release build failed."
}

$outputExe = Join-Path $workspace "src-tauri\target\release\codexuu.exe"

if (-not (Test-Path $outputExe)) {
    throw "Build output not found at $outputExe"
}

Write-Output "Windows build completed successfully: $outputExe"
