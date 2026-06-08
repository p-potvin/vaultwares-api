@echo off
echo Stopping VaultWares Background Services...

:: Kill API Server
taskkill /F /FI "WINDOWTITLE eq VaultWares API*" /T 2>nul

:: Kill Task Assigner
taskkill /F /FI "WINDOWTITLE eq VaultWares Task Assigner*" /T 2>nul

:: Kill Vite Frontend Node Process
taskkill /F /FI "WINDOWTITLE eq VaultWares Frontend*" /T 2>nul

:: Note: usually you leave Redis running, but uncomment below if you want to kill it too
:: taskkill /F /IM redis-server.exe /T 2>nul

echo All services stopped successfully.
pause