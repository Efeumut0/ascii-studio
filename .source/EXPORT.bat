@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Retro ASCII Video Studio - EXE Derleyici

cd /d "%~dp0"

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

set "INPUT_VID=%~1"

if "%INPUT_VID%"=="" (
    cls
    echo ====================================================================
    echo        RETRO ASCII VIDEO STUDIO - EXE DERLEYICI (STANDALONE)
    echo ====================================================================
    echo.
    echo   [!] Bir video dosyasi surukleyip bu bat dosyasinin uzerine birakabilir
    echo       veya asagidan bir video secip derleyebilirsiniz.
    echo.
    set "COUNT=0"
    for %%F in (*.mp4 *.avi *.mkv *.mov *.webm *.flv) do (
        set /a COUNT+=1
        set "VID_!COUNT!=%%~nxF"
        echo     [!COUNT!] %%~nxF
    )
    if !COUNT! equ 0 (
        echo     Klasorde video dosyasi bulunamadi.
        pause
        exit /b 1
    )
    echo.
    set "CHOICE="
    set /p "CHOICE=Derlemek istediginiz video (1-!COUNT!): "
    for /L %%i in (1,1,!COUNT!) do (
        if "!CHOICE!"=="%%i" set "INPUT_VID=!VID_%%i!"
    )
)

if "%INPUT_VID%"=="" (
    echo [UYARI] Gecersiz secim!
    pause
    exit /b 1
)

cls
echo ====================================================================
echo   Video      : %INPUT_VID%
echo   Islem      : EXE projesi Olusturma (PyInstaller)
echo ====================================================================
echo.

%PY_CMD% ascii_exporter.py -i "%INPUT_VID%" --build-exe --overwrite

set "VID_STEM="
for /f "tokens=* delims=" %%A in ('%PY_CMD% -c "import ascii_exporter, sys; print(ascii_exporter.sanitize_video_folder_name(sys.argv[1]))" "%INPUT_VID%" 2^>nul') do set "VID_STEM=%%A"
if "!VID_STEM!"=="" (
    for %%A in ("%INPUT_VID%") do set "VID_STEM=%%~nA"
)
set "TARGET_DIR=output\!VID_STEM!"

echo.
echo ====================================================================
if exist "!TARGET_DIR!\ASCII_Player.exe" (
    echo   [BASARILI] EXE dosyasi hazir: !TARGET_DIR!\ASCII_Player.exe
    start "" "!TARGET_DIR!"
) else if exist "!TARGET_DIR!" (
    echo   [BASARILI] Proje klasoru hazir: !TARGET_DIR!
    start "" "!TARGET_DIR!"
)
echo ====================================================================
echo.
pause
