@echo off
chcp 65001 >nul
rem === Sozlamalar oynasini ochish (tahrirlash) ===
cd /d "%~dp0"
python main.py --setup
