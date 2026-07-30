param(
    [string]$Version = (Get-Content (Join-Path $PSScriptRoot "..\VERSION") -Raw).Trim(),
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

$dirty = @(
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard -- app main.py resources VERSION requirements.txt CodexUU.spec installer scripts
) | Where-Object { $_ }
if ($LASTEXITCODE -ne 0) {
    throw "Unable to verify the source tree before building."
}
if ($dirty) {
    throw "Refusing to build from an uncommitted worktree. Commit or remove local changes first."
}

if (-not (Get-Command pyinstaller.exe -ErrorAction SilentlyContinue)) {
    throw "PyInstaller was not found. Run: python -m pip install pyinstaller"
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
pyinstaller --noconfirm --clean --windowed --name CodexUU `
    --add-data "resources;resources" `
    --add-data "VERSION;." `
    --collect-data tzdata `
    main.py

if ($Installer) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        throw "Inno Setup was not found. Install Inno Setup and retry."
    }
    & $iscc.Source "installer\CodexUU.iss" "/DMyAppVersion=$Version"
}

Write-Output "Windows build completed: dist\CodexUU"
