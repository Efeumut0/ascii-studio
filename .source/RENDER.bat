@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Retro ASCII Video Studio - MP4 Video Render

cd /d "%~dp0"

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

set "INPUT_VID=%~1"

if "%INPUT_VID%"=="" (
    cls
    echo ====================================================================
    echo        RETRO ASCII VIDEO STUDIO - MP4 VIDEO RENDER ALICI
    echo ====================================================================
    echo.
    echo   [!] Bir video dosyasi surukleyip bu bat dosyasinin uzerine birakabilir
    echo       veya asagidan bir video secip render alabilirsiniz.
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
    set /p "CHOICE=Render almak istediginiz video (1-!COUNT!): "
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
echo   Video : %INPUT_VID%
echo   Islem : MP4 Video Render (H.264 + AAC Audio)
echo ====================================================================
echo.
echo   [Render Cozunurlugu / Kalite Secimi]
echo   ------------------------------------------------------------------
echo     [1] Otomatik (Auto 1080p / 2K - Video uzunluguna gore) [VARSAYILAN]
echo     [2] 1080p Full HD (1920x1080)
echo     [3] 2K Quad HD (2560x1440)
echo     [4] 4K Ultra HD (3840x2160)
echo     [5] 720p HD (1280x720)
echo     [6] Orijinal (1:1 Izgara Boyutu)
echo   ------------------------------------------------------------------
echo.
set "RES_CHOICE="
set /p "RES_CHOICE=Cozunurluk secimi (1-6, Enter=Auto): "
set "RES_ARG=auto"
if "%RES_CHOICE%"=="2" set "RES_ARG=1080p"
if "%RES_CHOICE%"=="3" set "RES_ARG=2k"
if "%RES_CHOICE%"=="4" set "RES_ARG=4k"
if "%RES_CHOICE%"=="5" set "RES_ARG=720p"
if "%RES_CHOICE%"=="6" set "RES_ARG=original"

cls
echo ====================================================================
echo   Video      : %INPUT_VID%
echo   Cozunurluk : %RES_ARG%
echo   Islem      : MP4 Video Render (H.264 + AAC Audio)
echo ====================================================================
echo.

%PY_CMD% ascii_video_renderer.py -i "%INPUT_VID%" --resolution %RES_ARG% --overwrite

set "VID_STEM="
for /f "tokens=* delims=" %%A in ('%PY_CMD% -c "import ascii_exporter, sys; print(ascii_exporter.sanitize_video_folder_name(sys.argv[1]))" "%INPUT_VID%" 2^>nul') do set "VID_STEM=%%A"
if "!VID_STEM!"=="" (
    for %%A in ("%INPUT_VID%") do set "VID_STEM=%%~nA"
)
set "TARGET_DIR=output\!VID_STEM!"

echo.
echo ====================================================================
if exist "!TARGET_DIR!" (
    echo   [BASARILI] Render tamamlandi! Klasor aciliyor: !TARGET_DIR!
    start "" "!TARGET_DIR!"
)
echo ====================================================================
echo.
pause
