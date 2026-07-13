$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$mainPath = Join-Path $workspace "main.py"
$escapedMainPath = [regex]::Escape($mainPath)

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "pythonw.exe" -and $_.CommandLine -match $escapedMainPath
}
foreach ($process in $existing) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

$pythonw = (Get-Command pythonw.exe).Source
$started = Start-Process -FilePath $pythonw -ArgumentList ('"' + $mainPath + '"') -WorkingDirectory $workspace -PassThru
Start-Sleep -Seconds 3

$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "pythonw.exe" -and $_.CommandLine -match $escapedMainPath
})
if ($running.Count -ne 1) {
    throw "CodexUU restart failed: expected 1 process, found $($running.Count)."
}

Write-Output "CodexUU restarted: PID $($started.Id)"
