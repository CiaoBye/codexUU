Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class PidWinFinder {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    public static void Inspect(uint targetPid) {
        EnumWindows((hWnd, lParam) => {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (targetPid == 0 || pid == targetPid) {
                var title = new StringBuilder(256);
                GetWindowText(hWnd, title, 256);
                var cls = new StringBuilder(256);
                GetClassName(hWnd, cls, 256);
                RECT r;
                GetWindowRect(hWnd, out r);
                bool vis = IsWindowVisible(hWnd);
                Console.WriteLine("HWND=" + hWnd + " PID=" + pid + " Vis=" + vis + " Title='" + title + "' Class='" + cls + "' Rect=" + r.Left + "," + r.Top + " " + (r.Right-r.Left) + "x" + (r.Bottom-r.Top));
            }
            return true;
        }, IntPtr.Zero);
    }
}
"@
$proc = Get-Process codexuu -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc) {
    Write-Host "Checking PID: $($proc.Id) ($($proc.ProcessName))"
    [PidWinFinder]::Inspect([uint32]$proc.Id)
} else {
    Write-Host "No codexuu process found."
}
