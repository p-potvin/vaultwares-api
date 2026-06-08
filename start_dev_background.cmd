@echo off
setlocal

:: Get the directory of this script
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: Log file for startup errors
set "LOG_FILE=%ROOT_DIR%logs\startup.log"
if not exist "%ROOT_DIR%logs" mkdir "%ROOT_DIR%logs"
echo [%date% %time%] Starting background services... > "%LOG_FILE%"

:: 1. Start Redis if not running
tasklist /NH /FI "IMAGENAME eq redis-server.exe" | find /I "redis-server.exe" >nul
if ERRORLEVEL 1 (
    echo [%date% %time%] Starting Redis... >> "%LOG_FILE%"
    start "VaultWares Redis" /b redis-server.exe
)

:: Wait for Redis to be ready
timeout /t 2 >nul

:: 2. Start the API Server (uses Uvicorn with reload=True internally in api_server.py)
echo [%date% %time%] Starting API Server... >> "%LOG_FILE%"
start "VaultWares API" /MIN cmd /c ".venv\Scripts\python.exe api_server.py"

:: 3. Start the SPA Task Assigner 
echo [%date% %time%] Starting SPA Task Assigner... >> "%LOG_FILE%"
set "PYTHONPATH=%ROOT_DIR%;%ROOT_DIR%vaultwares-agentciation"
start "VaultWares Task Assigner" /MIN cmd /c ".venv\Scripts\python.exe assign_spa_tasks.py"

:: 4. Start the Frontend (Vite uses HMR for automatic reloading)
if exist "%ROOT_DIR%frontend\package.json" (
    echo [%date% %time%] Starting Frontend Vite Server... >> "%LOG_FILE%"
    cd "%ROOT_DIR%frontend"
    start "VaultWares Frontend" /MIN cmd /c "npm run dev"
)

echo [%date% %time%] All background services dispatched. >> "%LOG_FILE%"
exit /b 0