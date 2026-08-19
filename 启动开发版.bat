@echo off
chcp 65001 >nul
cd /d "%~dp0"
title CodexUU 开发版
echo.
echo  会先关闭所有 CodexUU（含托盘里的旧窗口），再启动当前源码的开发版。
echo  请保持本窗口不要关；改前端会热更新，改 Rust 会自动重编。
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1"
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装 Node / pnpm，并在本目录执行过 pnpm install。
  pause
)
