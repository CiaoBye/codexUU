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
Start-Sleep -Seconds 2

$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "pythonw.exe" -and $_.CommandLine -match $escapedMainPath
})
if ($running.Count -ne 1) {
    throw "CodexUU restart failed: expected 1 process, found $($running.Count)."
}

if (-not ("CodexUU.NativeWindowProbe" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace CodexUU {
    public static class NativeWindowProbe {
        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
        public static bool HasVisibleMainWindow(uint targetProcessId) {
            bool found = false;
            EnumWindows((hWnd, lParam) => {
                uint processId;
                GetWindowThreadProcessId(hWnd, out processId);
                if (processId != targetProcessId || !IsWindowVisible(hWnd)) return true;
                var title = new StringBuilder(256);
                GetWindowText(hWnd, title, title.Capacity);
                if (title.ToString() == "CodexUU") { found = true; return false; }
                return true;
            }, IntPtr.Zero);
            return found;
        }
    }
}
"@
}

$windowReady = $false
for ($attempt = 0; $attempt -lt 16; $attempt++) {
    if ([CodexUU.NativeWindowProbe]::HasVisibleMainWindow([uint32]$started.Id)) {
        $windowReady = $true
        break
    }
    Start-Sleep -Milliseconds 500
}
if (-not $windowReady) {
    Stop-Process -Id $started.Id -Force -ErrorAction SilentlyContinue
    throw "CodexUU restart failed: process started but no visible main window appeared."
}

Write-Output "CodexUU restarted: PID $($started.Id)"
