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

# 2. Build Tauri release binary
Set-Location (Join-Path $workspace "src-tauri")
cargo build --release
if ($LASTEXITCODE -ne 0) {
    throw "Cargo release build failed."
}

Set-Location $workspace
$outputExe = Join-Path $workspace "src-tauri\target\release\codexuu.exe"

if (-not (Test-Path $outputExe)) {
    throw "Build output not found at $outputExe"
}

Write-Output "Windows build completed successfully: $outputExe"
