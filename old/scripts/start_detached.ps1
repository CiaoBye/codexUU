$workspace = "C:\Users\Ayuan\Documents\Vibe\CodexUU"
$mainPath = Join-Path $workspace "main.py"
$escapedMainPath = [regex]::Escape($mainPath)

# Stop any old python/pythonw running this workspace main.py
$existing = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "pythonw.exe" -or $_.Name -eq "python.exe") -and $_.CommandLine -match $escapedMainPath
}
foreach ($p in $existing) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 300

$pythonw = (Get-Command pythonw.exe).Source
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonw
$psi.Arguments = "`"$mainPath`""
$psi.WorkingDirectory = $workspace
$psi.UseShellExecute = $true

$proc = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 1
Write-Host "Started detached CodexUU process PID: $($proc.Id)"
