$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
Push-Location $workspace
try {
    Write-Output "Starting CodexUU test version with Tauri dev mode (no installer will be generated)."
    pnpm tauri dev --config src-tauri/tauri.dev.conf.json
}
finally {
    Pop-Location
}
