from pathlib import Path
import subprocess

desktop = Path.home() / "Desktop"
target = Path.cwd() / "run.bat"
lnk = desktop / "CodexUU.lnk"

script = f"""
$wsh = New-Object -ComObject WScript.Shell
$s = $wsh.CreateShortcut('{str(lnk)}')
$s.TargetPath = '{str(target)}'
$s.WorkingDirectory = '{str(Path.cwd())}'
$s.Save()
"""

subprocess.run(["powershell", "-Command", script], check=True)
print("Shortcut created at:", lnk)
