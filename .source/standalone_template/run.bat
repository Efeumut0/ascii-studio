@echo off
chcp 65001 >nul
title Retro ASCII Video Player - Standalone Launcher

:: Anchor working directory to script folder
cd /d "%~dp0"

:: 1. Check for virtual environments
if exist ".venv\Scripts\python.exe" set "PY_EXE=.venv\Scripts\python.exe" & goto RUN
if exist "..\.venv\Scripts\python.exe" set "PY_EXE=..\.venv\Scripts\python.exe" & goto RUN

:: 2. Check for Windows Python Launcher (py)
where py >nul 2>&1
if %ERRORLEVEL% equ 0 set "PY_EXE=py" & goto RUN

:: 3. Check for python in system PATH
where python >nul 2>&1
if %ERRORLEVEL% equ 0 set "PY_EXE=python" & goto RUN

:: 4. Fallback: Python not found
echo.
echo ====================================================================
echo [HATA / ERROR] Python calistiricisi bulunamadi!
echo Python executable was not found on your system!
echo.
echo Lutfen Python 3.10 veya daha yenisini yukleyin ve PATH'e ekleyin.
echo Please install Python 3.10+ and add it to your system PATH:
echo https://www.python.org/downloads/
echo ====================================================================
echo.
pause
exit /b 1

:RUN
echo [INFO] ASCII Oynatici baslatiliyor / Starting ASCII Player (%PY_EXE%)...
"%PY_EXE%" run.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% equ 0 goto SUCCESS

echo.
echo ====================================================================
echo [HATA / ERROR] Oynatici bir hata ile kapandi - Cikis Kodu: %EXIT_CODE%
echo Player terminated with an error code: %EXIT_CODE%
echo ====================================================================
echo.
pause
exit /b %EXIT_CODE%

:SUCCESS
exit /b 0
