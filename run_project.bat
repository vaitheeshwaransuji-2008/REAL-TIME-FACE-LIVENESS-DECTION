@echo off
cls
title Yudhistra Biometric Launcher
:menu
echo ===================================================
echo        YUDHISTRA BIOMETRIC CONSOLE LAUNCHER
echo ===================================================
echo.
echo  1. Install / Update Dependencies (pip)
echo  2. Launch Web App (FastAPI + Browser Dashboard)
echo  3. Launch Desktop Console (OpenCV Interface)
echo  4. Exit
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="1" goto install
if "%choice%"=="2" goto webapp
if "%choice%"=="3" goto desktop
if "%choice%"=="4" goto exit
echo Invalid choice, try again.
pause
cls
goto menu

:install
echo.
echo Installing Python dependencies...
pip install -r requirements.txt
echo.
echo Dependency check complete.
pause
cls
goto menu

:webapp
echo.
echo Starting FastAPI Web Server...
echo Please wait for the console to say "[System] Models loaded successfully."
echo.
echo Loading server...
timeout /t 2 >nul
start "" http://127.0.0.1:8000
python web_app.py
pause
cls
goto menu

:desktop
echo.
echo Starting OpenCV Desktop Console...
python liveness_detection_themed.py
pause
cls
goto menu

:exit
exit
