@echo off
chcp 65001 >nul
title Karyer - Holat tekshiruvi
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Holat.ps1"
echo.
echo   Yopish uchun istalgan tugmani bosing...
pause >nul
