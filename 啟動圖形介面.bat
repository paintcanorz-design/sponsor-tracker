@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
    python run_gui.py
) else (
    py -3.11 run_gui.py
)
pause

