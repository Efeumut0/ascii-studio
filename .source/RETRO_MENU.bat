@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Retro ASCII Video Studio - Ana Kontrol Menusu

cd /d "%~dp0"

if not "%~1"=="" (
    set "SELECTED_VID=%~nx1"
    set "FULL_VID_PATH=%~f1"
    goto ACTION_MENU
)

:MAIN_MENU
set "FULL_VID_PATH="
set "SELECTED_VID="
cls
echo ====================================================================
echo                 RETRO ASCII VIDEO STUDIO
echo ====================================================================
echo.
echo   [Klasorde Bulunan Video Dosyalari]
echo   ------------------------------------------------------------------

set "COUNT=0"
for %%F in (*.mp4 *.avi *.mkv *.mov *.webm *.flv) do (
    call :ADD_VIDEO "%%~nxF" "%%~zF"
)

if %COUNT% equ 0 echo     [!] Klasor icinde video dosyasi bulunamadi.
if %COUNT% equ 0 echo         Lutfen bir video dosyasini bu klasore kopyalayin.

echo   ------------------------------------------------------------------
echo     [G] Grafik Arayuzunu Ac
echo     [Q] Cikis
echo ====================================================================
echo.

set "CHOICE="
set /p "CHOICE=Seciminiz (1-%COUNT% / G / Q): "
if not defined CHOICE goto MAIN_MENU
if /i "%CHOICE%"=="Q" goto EXIT_APP
if /i "%CHOICE%"=="G" goto LAUNCH_GUI

set "SELECTED_VID="
for /L %%i in (1,1,%COUNT%) do (
    if "%CHOICE%"=="%%i" set "SELECTED_VID=!VID_%%i!"
)

if not defined SELECTED_VID (
    echo.
    echo [UYARI] Gecersiz secim yaptiniz!
    timeout /t 2 >nul
    goto MAIN_MENU
)

:ACTION_MENU
cls
echo ====================================================================
echo   Secilen Video: %SELECTED_VID%
echo ====================================================================
echo.
echo   Hangi islemi yapmak istiyorsunuz?
echo     [1] Canli Oynat (Live ASCII Player)
echo     [2] EXE Projesi Olustur
echo     [3] ASCII Video Render Al (Export MP4)
echo     [G] Geri Don
echo ====================================================================
echo.
set "ACT_CHOICE="
set /p "ACT_CHOICE=Islem (1/2/3/G): "

if /i "%ACT_CHOICE%"=="G" goto MAIN_MENU
if "%ACT_CHOICE%"=="1" set "MODE=PLAY" & goto QUALITY_MENU
if "%ACT_CHOICE%"=="2" set "MODE=EXPORT" & goto QUALITY_MENU
if "%ACT_CHOICE%"=="3" set "MODE=RENDER" & goto QUALITY_MENU

echo [UYARI] Gecersiz islem secimi!
timeout /t 1 >nul
goto ACTION_MENU

:QUALITY_MENU
cls
echo ====================================================================
echo   Kalite ve Detay Seviyesi Secimi (%SELECTED_VID%)
echo ====================================================================
echo.
echo     [1]  LOW         - 50 sutun,  10 karakter
echo     [2]  RETRO       - 65 sutun,  10 karakter
echo     [3]  BALANCED    - 80 sutun,  15 karakter
echo     [4]  CLASSIC     - 95 sutun,  15 karakter
echo     [5]  HIGH        - 110 sutun, 68 karakter
echo     [6]  SUPER       - 125 sutun, 68 karakter
echo     [7]  ULTRA       - 140 sutun, 68 karakter
echo     [8]  MASTER      - 160 sutun, 68 karakter
echo     [9]  CINEMA      - 180 sutun, 68 karakter
echo     [10] TITAN       - 200 sutun, 68 karakter
echo     [11] OVERKILL    - 230 sutun, 68 karakter
echo     [12] GODLIKE     - 260 sutun, 94 karakter
echo     [13] MONOLITH    - 300 sutun, 94 karakter
echo     [14] SINGULARITY - 340 sutun, 94 karakter
echo     [15] INFINITE    - 380 sutun, 94 karakter
echo     [G]  Geri Don
echo ====================================================================
echo.
set "QUAL_CHOICE="
set /p "QUAL_CHOICE=Kalite (1-15/G) [Varsayilan: 3]: "

if /i "%QUAL_CHOICE%"=="G" goto ACTION_MENU
if "%QUAL_CHOICE%"=="1" set "QUAL=low" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="2" set "QUAL=retro" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="3" set "QUAL=balanced" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="4" set "QUAL=classic" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="5" set "QUAL=high" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="6" set "QUAL=super" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="7" set "QUAL=ultra" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="8" set "QUAL=master" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="9" set "QUAL=cinema" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="10" set "QUAL=titan" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="11" set "QUAL=overkill" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="12" set "QUAL=godlike" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="13" set "QUAL=monolith" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="14" set "QUAL=singularity" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="15" set "QUAL=infinite" & goto COLOR_MENU
if "%QUAL_CHOICE%"=="" set "QUAL=balanced" & goto COLOR_MENU

echo [UYARI] Gecersiz kalite secimi!
timeout /t 1 >nul
goto QUALITY_MENU

:COLOR_MENU
cls
echo ====================================================================
echo   Renk Paleti / Temasi Secimi
echo ====================================================================
echo.
echo     [1] Truecolor RGB  - Orijinal 24-bit canli renkler
echo     [2] Siyah-Beyaz    - Monokrom klasik gri tonlama
echo     [3] Matrix Yesili  - Retro CRT fosforlu yesil terminal
echo     [4] Amber          - Vintage amber / kehribar terminal
echo     [5] Cyberpunk Neon - Sentetik pembe ve camgobegi palet
echo     [G] Geri Don
echo ====================================================================
echo.
set "COLOR_CHOICE="
set /p "COLOR_CHOICE=Renk Temasi (1-5/G) [Varsayilan: 1]: "

if /i "%COLOR_CHOICE%"=="G" goto QUALITY_MENU
if "%COLOR_CHOICE%"=="1" set "COLOR_ARG=truecolor" & goto CHECK_RES
if "%COLOR_CHOICE%"=="2" set "COLOR_ARG=grayscale" & goto CHECK_RES
if "%COLOR_CHOICE%"=="3" set "COLOR_ARG=green" & goto CHECK_RES
if "%COLOR_CHOICE%"=="4" set "COLOR_ARG=amber" & goto CHECK_RES
if "%COLOR_CHOICE%"=="5" set "COLOR_ARG=cyberpunk" & goto CHECK_RES
if "%COLOR_CHOICE%"=="" set "COLOR_ARG=truecolor" & goto CHECK_RES

echo [UYARI] Gecersiz renk temasi secimi!
timeout /t 1 >nul
goto COLOR_MENU

:CHECK_RES
if "%MODE%"=="RENDER" goto RESOLUTION_MENU
set "RES_ARG=auto"
goto EXECUTE

:RESOLUTION_MENU
cls
echo ====================================================================
echo   Render Cozunurlugu Secimi (%SELECTED_VID%)
echo ====================================================================
echo.
echo     [1] Otomatik (Auto 1080p / 2K - Video uzunluguna gore) [VARSAYILAN]
echo     [2] 1080p Full HD (1920x1080)
echo     [3] 2K Quad HD (2560x1440)
echo     [4] 4K Ultra HD (3840x2160)
echo     [5] 720p HD (1280x720)
echo     [6] Orijinal (1:1 Izgara Boyutu)
echo ====================================================================
echo.
set "RES_CHOICE="
set /p "RES_CHOICE=Cozunurluk (1-6) [Varsayilan: 1]: "
set "RES_ARG=auto"
if "%RES_CHOICE%"=="2" set "RES_ARG=1080p"
if "%RES_CHOICE%"=="3" set "RES_ARG=2k"
if "%RES_CHOICE%"=="4" set "RES_ARG=4k"
if "%RES_CHOICE%"=="5" set "RES_ARG=720p"
if "%RES_CHOICE%"=="6" set "RES_ARG=original"
goto EXECUTE

:EXECUTE
cls
set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

set "VID_INPUT=%SELECTED_VID%"
if defined FULL_VID_PATH set "VID_INPUT=%FULL_VID_PATH%"

set "VID_STEM="
for /f "tokens=* delims=" %%A in ('%PY_CMD% -c "import ascii_exporter, sys; print(ascii_exporter.sanitize_video_folder_name(sys.argv[1]))" "!VID_INPUT!" 2^>nul') do set "VID_STEM=%%A"
if "!VID_STEM!"=="" (
    for %%A in ("!VID_INPUT!") do set "VID_STEM=%%~nA"
)
set "TARGET_DIR=output\!VID_STEM!"
if not exist "!TARGET_DIR!" mkdir "!TARGET_DIR!"

if "%MODE%"=="PLAY" (
    echo ====================================================================
    echo   Canli ASCII Oynatici Baslatiliyor...
    echo   Video : !VID_INPUT!
    echo   Kalite: %QUAL%
    echo   Renk  : %COLOR_ARG%
    echo ====================================================================
    echo.
    %PY_CMD% ascii_player.py -i "!VID_INPUT!" --quality %QUAL% --color-mode %COLOR_ARG%
    goto END_RUN
)

if "%MODE%"=="EXPORT" (
    echo ====================================================================
    echo   EXE projesi olusturuluyor...
    echo   Video : !VID_INPUT!
    echo   Kalite: %QUAL%
    echo   Renk  : %COLOR_ARG%
    echo   Hedef : !TARGET_DIR!\
    echo ====================================================================
    echo.
    %PY_CMD% ascii_exporter.py -i "!VID_INPUT!" -o "!TARGET_DIR!" --quality %QUAL% --color-mode %COLOR_ARG% --overwrite --build-exe
    if exist "!TARGET_DIR!" start "" "!TARGET_DIR!"
    goto END_RUN
)

if "%MODE%"=="RENDER" (
    echo ====================================================================
    echo   ASCII Video (MP4) Render Aliniyor...
    echo   Video      : !VID_INPUT!
    echo   Kalite     : %QUAL%
    echo   Renk       : %COLOR_ARG%
    echo   Cozunurluk : %RES_ARG%
    echo   Hedef      : !TARGET_DIR!\!VID_STEM!_ascii.mp4
    echo ====================================================================
    echo.
    %PY_CMD% ascii_video_renderer.py -i "!VID_INPUT!" -o "!TARGET_DIR!\!VID_STEM!_ascii.mp4" --quality %QUAL% --color-mode %COLOR_ARG% --resolution %RES_ARG% --overwrite
    if exist "!TARGET_DIR!" start "" "!TARGET_DIR!"
    goto END_RUN
)

:LAUNCH_GUI
cls
echo [INFO] Retro ASCII Studio Grafik Arayuzu baslatiliyor...
set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"
set "PYW_CMD=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYW_CMD=.venv\Scripts\pythonw.exe"
where "%PYW_CMD%" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "" "%PYW_CMD%" ascii_gui.py
) else (
    start "" /b "%PY_CMD%" ascii_gui.py
)
goto MAIN_MENU

:END_RUN
echo.
echo ====================================================================
echo   Islem tamamlandi. Ana menuye donmek icin bir tusa basin...
echo ====================================================================
pause >nul
goto MAIN_MENU

:ADD_VIDEO
set /a COUNT+=1
set "VID_NAME=%~1"
set "VID_%COUNT%=%VID_NAME%"
set "V_SIZE=%~2"
set /a "V_MB=%V_SIZE% / 1048576"
if %V_MB% gtr 0 (
    echo     [%COUNT%] %VID_NAME%  -  %V_MB% MB
) else (
    set /a "V_KB=%V_SIZE% / 1024"
    echo     [%COUNT%] %VID_NAME%  -  !V_KB! KB
)
exit /b 0

:EXIT_APP
exit /b 0
