$workspace = Split-Path -Parent $PSScriptRoot
$exePath = Join-Path $workspace "src-tauri\target\release\codexuu.exe"

# Stop any running codexuu instance
Get-Process codexuu -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

$taskName = "CodexUU_Tauri_Release_Launch"
$taskRun = "`"$exePath`""

# Launch on interactive desktop Session 1
schtasks.exe /Create /TN $taskName /TR $taskRun /SC ONCE /ST 23:59 /F /IT | Out-Null
schtasks.exe /Run /TN $taskName | Out-Null
Start-Sleep -Seconds 2
schtasks.exe /Delete /TN $taskName /F | Out-Null

$running = Get-Process codexuu -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "CodexUU 1.0 (Standalone Release App) successfully launched on interactive desktop! PID: $($running.Id)"
} else {
    Write-Host "CodexUU process not found after launch."
}
