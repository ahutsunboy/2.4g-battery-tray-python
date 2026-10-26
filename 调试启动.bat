@echo off
rem  Run in a console window so Python errors stay visible (for debugging).
cd /d "%~dp0tray"
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python.exe not found in PATH.
    pause
    exit /b 1
)
python tray_app.py
echo.
echo Program exited. Press any key to close.
pause >nul
