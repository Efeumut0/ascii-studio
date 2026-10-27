@echo off
chcp 65001 >nul
title Retro ASCII Video Studio
cd /d "%~dp0"

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

set "PYW_CMD=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=.venv\Scripts\pythonw.exe"

where "%PYW_CMD%" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "" "%PYW_CMD%" ascii_gui.py %*
) else (
    start "" /b "%PY_CMD%" ascii_gui.py %*
)
exit /b 0
