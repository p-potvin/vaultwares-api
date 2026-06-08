@echo off
setlocal enabledelayedexpansion

:: Path Configuration
set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"

echo [System] Checking for Redis...
set "REDIS_RUNNING=0"

:: Use a safer check for the process
tasklist /NH /FI "IMAGENAME eq redis-server.exe" | find /I "redis-server.exe" >nul
if !ERRORLEVEL! EQU 0 (
    set "REDIS_RUNNING=1"
    echo [System] Redis is already running.
)

if "%REDIS_RUNNING%"=="0" (
    echo [Warning] redis-server.exe not found in tasklist.
    echo [Action] Attempting to start local redis-server...
    start /min "Redis" redis-server.exe
    timeout /t 2 > nul
)

echo.
echo --- ?? VaultWares Pipeline Stream: SPA Deployment Team ---
echo.

set "PYTHONPATH=%PROJECT_ROOT%;%PROJECT_ROOT%vaultwares-adk;%PROJECT_ROOT%..\vaultwares-adk"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" assign_spa_tasks.py
) else (
    echo [Error] Virtual environment not found at .venv\Scripts\python.exe
)

pause
