@echo off
rem ============================================================
rem  2.4G Battery Tray  -  launcher
rem  Finds a pythonw.exe and starts tray_app.py silently.
rem  Usage: start.bat            start the tray
rem         start.bat --print    only print the pythonw it would use
rem ============================================================
setlocal
cd /d "%~dp0tray"

set "PYW="
if exist "%~dp0runtime\pythonw.exe" set "PYW=%~dp0runtime\pythonw.exe"
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW if exist "D:\software\codingApp\miniconda\pythonw.exe" set "PYW=D:\software\codingApp\miniconda\pythonw.exe"

if /i "%~1"=="--print" (
    if defined PYW (echo %PYW%) else (echo NOT_FOUND)
    exit /b 0
)

if not defined PYW (
    echo [ERROR] pythonw.exe not found.
    echo Install Python 3.9+ ^(and add it to PATH^), or drop a portable
    echo runtime here:  %~dp0runtime\pythonw.exe
    pause
    exit /b 1
)

start "" "%PYW%" "%~dp0tray\tray_app.py"
exit /b 0
