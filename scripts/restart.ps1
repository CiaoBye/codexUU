$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$releaseExe = Join-Path $workspace "src-tauri\target\release\codexuu.exe"
$debugExe = Join-Path $workspace "src-tauri\target\debug\codexuu.exe"

$targetExe = if (Test-Path $releaseExe) { $releaseExe } else { $debugExe }

if (-not (Test-Path $targetExe)) {
    throw "CodexUU binary not found. Please run 'cargo build --release' in src-tauri first."
}

# Stop any running instances
Get-Process codexuu -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*$workspace*" -or $_.CommandLine -like "*$workspace*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Milliseconds 500

$taskName = "CodexUU_Restart"
$taskRun = "`"$targetExe`""

# Launch on interactive desktop Session 1
schtasks.exe /Create /TN $taskName /TR $taskRun /SC ONCE /ST 23:59 /F /IT | Out-Null
schtasks.exe /Run /TN $taskName | Out-Null
Start-Sleep -Seconds 2
schtasks.exe /Delete /TN $taskName /F | Out-Null

$running = Get-Process codexuu -ErrorAction SilentlyContinue
if (-not $running) {
    throw "CodexUU restart failed: codexuu process not found."
}
Write-Output "CodexUU restarted (Native Tauri 2 Release): PID $($running[0].Id)"
