@echo off
chcp 65001 >nul
title Retro ASCII Video Player - Standalone EXE Builder

:: Anchor working directory to script folder
cd /d "%~dp0"

echo ====================================================================
echo      RETRO ASCII VIDEO PLAYER - STANDALONE EXE BUILDER
echo ====================================================================
echo [INFO] PyInstaller ile tek dosya .exe derlemesi baslatiliyor...
echo.

:: 1. Check for Python/PyInstaller in venv
if exist ".venv\Scripts\pyinstaller.exe" set "PYI_EXE=.venv\Scripts\pyinstaller.exe" & goto BUILD
if exist "..\.venv\Scripts\pyinstaller.exe" set "PYI_EXE=..\.venv\Scripts\pyinstaller.exe" & goto BUILD

:: 2. Check for pyinstaller in PATH
where pyinstaller >nul 2>&1
if %ERRORLEVEL% equ 0 set "PYI_EXE=pyinstaller" & goto BUILD

:: 3. Try python -m PyInstaller
where py >nul 2>&1
if %ERRORLEVEL% equ 0 set "PYI_EXE=py -m PyInstaller" & goto BUILD
where python >nul 2>&1
if %ERRORLEVEL% equ 0 set "PYI_EXE=python -m PyInstaller" & goto BUILD

echo [HATA / ERROR] PyInstaller bulunamadi!
echo Lutfen 'pip install pyinstaller' calistirin.
echo.
pause
exit /b 1

:BUILD
echo [INFO] Derleyici: %PYI_EXE%
echo [INFO] standalone_player.spec derleniyor...
%PYI_EXE% standalone_player.spec --distpath . --workpath build_temp --clean -y
set "EXIT_CODE=%ERRORLEVEL%"

if exist "build_temp" rd /s /q "build_temp" >nul 2>&1

if %EXIT_CODE% equ 0 goto SUCCESS

echo.
echo ====================================================================
echo [HATA / ERROR] EXE olusturulamadi - Cikis Kodu: %EXIT_CODE%
echo ====================================================================
echo.
pause
exit /b %EXIT_CODE%

:SUCCESS
echo.
echo ====================================================================
echo [BASARILI] Tek dosya .exe basariyla olusturuldu: ASCII_Player.exe
echo Programinizi dogrudan calistirabilirsiniz!
echo ====================================================================
echo.
pause
exit /b 0
