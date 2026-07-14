param(
    [string]$Version = (Get-Content (Join-Path $PSScriptRoot "..\VERSION") -Raw).Trim(),
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location $workspace

if (-not (Get-Command pyinstaller.exe -ErrorAction SilentlyContinue)) {
    throw "未找到 PyInstaller。请先运行：python -m pip install pyinstaller"
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
        throw "未找到 Inno Setup。请安装 Inno Setup 后重新运行。"
    }
    & $iscc.Source "installer\CodexUU.iss" "/DMyAppVersion=$Version"
}

Write-Output "Windows 构建完成：dist\CodexUU"
