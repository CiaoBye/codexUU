$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$env:CARGO_TARGET_DIR = Join-Path $workspace "src-tauri\target"

function Stop-CodexUUInstances {
    Get-Process -Name "codexuu" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match 'codexuu' -or
            ($_.CommandLine -and $_.CommandLine -match 'CodexUU\\src-tauri|tauri\.js" "dev"')
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

Push-Location $workspace
try {
    Write-Output "Closing previous CodexUU windows (including tray)..."
    Stop-CodexUUInstances
    $version = (Get-Content (Join-Path $workspace "VERSION") -Raw).Trim()
    Write-Output "Starting CodexUU $version development window (hot reload, no installer)."
    Write-Output "Leave this console open. Close it to stop the app."
    pnpm tauri dev --config src-tauri/tauri.dev.conf.json
}
finally {
    Pop-Location
}
