@echo off
title CodeWarden - All-In-One Launcher
cd /d "%~dp0"

echo ========================================================
echo       CodeWarden Security Guard - 1-Click Startup
echo ========================================================
echo.

:: 1. Check Docker Desktop
echo [1/3] Checking Docker Desktop...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker is not running. Starting Docker Desktop...
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        echo Waiting for Docker to initialize...
        timeout /t 10 /nobreak >nul
    ) else (
        echo [WARNING] Docker Desktop not found in default path.
    )
) else (
    echo [OK] Docker is running.
)

:: 2. Check Sandbox Container Image
echo.
echo [2/3] Checking Docker Sandbox Image...
docker image inspect codewarden-sandbox >nul 2>&1
if %errorlevel% neq 0 (
    echo Building codewarden-sandbox Docker image...
    docker build -t codewarden-sandbox -f backend\Dockerfile.sandbox backend\
) else (
    echo [OK] codewarden-sandbox image ready.
)

:: 3. Start FastAPI Backend Server
echo.
echo [3/3] Starting CodeWarden Backend (port 8765)...

:: Free port 8765 if previously in use
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :8765 ^| findstr LISTENING') do (
    echo Port 8765 is in use by PID %%p. Stopping old instance...
    taskkill /F /PID %%p >nul 2>&1
    timeout /t 1 /nobreak >nul
)

cd backend
if not exist ".venv\Scripts\uvicorn.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    .\.venv\Scripts\pip.exe install -r requirements.txt
)

echo.
echo --------------------------------------------------------
echo  Backend URL : http://127.0.0.1:8765
echo  Swagger API : http://127.0.0.1:8765/docs
echo  Health Check: http://127.0.0.1:8765/health
echo --------------------------------------------------------
echo Press CTRL+C to stop the server anytime.
echo.

.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8765 --reload
pause
