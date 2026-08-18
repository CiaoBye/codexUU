$workspace = "C:\Users\Ayuan\Documents\Vibe\CodexUU"
$mainPath = Join-Path $workspace "main.py"
$escapedMainPath = [regex]::Escape($mainPath)

$existing = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "pythonw.exe" -or $_.Name -eq "python.exe") -and $_.CommandLine -match $escapedMainPath
}
foreach ($p in $existing) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

$pythonw = (Get-Command pythonw.exe).Source
$taskName = "CodexUU_Interactive_Start"
$taskRun = "`"$pythonw`" `"$mainPath`""

# Register interactive one-shot task and run it
schtasks.exe /Create /TN $taskName /TR $taskRun /SC ONCE /ST 23:59 /F /IT | Out-Null
schtasks.exe /Run /TN $taskName | Out-Null
Start-Sleep -Seconds 2
schtasks.exe /Delete /TN $taskName /F | Out-Null

# Verify running process
$running = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "pythonw.exe" -or $_.Name -eq "python.exe") -and $_.CommandLine -match $escapedMainPath
}
if ($running) {
    Write-Host "CodexUU successfully launched on interactive desktop! PID: $($running.ProcessId)"
} else {
    Write-Host "Process not found after launch."
}
