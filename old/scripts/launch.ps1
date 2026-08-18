$shell = New-Object -ComObject Shell.Application
$py = (Get-Command pythonw.exe).Source
$main = (Resolve-Path "$PSScriptRoot\..\runner.py").Path
$cwd = (Resolve-Path "$PSScriptRoot\..").Path
$shell.ShellExecute($py, "`"$main`"", $cwd, "open", 1)
Start-Sleep -Seconds 2
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*main.py*" })
foreach ($p in $procs) {
    Write-Output "Running PID: $($p.ProcessId) Name: $($p.Name)"
}
