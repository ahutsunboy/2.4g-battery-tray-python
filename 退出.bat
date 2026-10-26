@echo off
rem  Stop the tray app using the pid file it writes on start.
setlocal enabledelayedexpansion
set "PIDFILE=%TEMP%\2.4g_battery_tray.pid"
if not exist "%PIDFILE%" (
    echo [INFO] Not running ^(pid file not found^).
    ping -n 4 127.0.0.1 >nul
    exit /b 1
)
set /p PID=<"%PIDFILE%"
echo Stopping PID !PID! ...
taskkill /PID !PID! /F >nul 2>&1
del "%PIDFILE%" >nul 2>&1
echo Done.
ping -n 3 127.0.0.1 >nul
exit /b 0
