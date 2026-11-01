# CodeWarden 1-Click Startup Script for PowerShell
$ErrorActionPreference = "Continue"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      🛡️ CodeWarden Security Guard - 1-Click Startup     " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

# 1. Docker Check
Write-Host "[1/3] Checking Docker status..." -ForegroundColor Yellow
$dockerReady = (docker info 2>&1) -match "Server:"
if (-not $dockerReady) {
    Write-Host "Docker Desktop not active. Launching Docker Desktop..." -ForegroundColor Magenta
    if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") {
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        Write-Host "Waiting 10s for Docker engine..." -ForegroundColor Gray
        Start-Sleep -Seconds 10
    } else {
        Write-Host "[WARNING] Docker Desktop not found at default location." -ForegroundColor Red
    }
} else {
    Write-Host "[OK] Docker is running." -ForegroundColor Green
}

# 2. Docker Sandbox Image Check
Write-Host ""
Write-Host "[2/3] Checking Docker Sandbox Image..." -ForegroundColor Yellow
$imageInspect = (docker image inspect codewarden-sandbox 2>&1) -match "RepoTags"
if (-not $imageInspect) {
    Write-Host "Building codewarden-sandbox image..." -ForegroundColor Magenta
    docker build -t codewarden-sandbox -f backend\Dockerfile.sandbox backend\
} else {
    Write-Host "[OK] Sandbox image (codewarden-sandbox) is ready." -ForegroundColor Green
}

# 3. Start Backend
Write-Host ""
Write-Host "[3/3] Launching CodeWarden Backend..." -ForegroundColor Yellow
Set-Location "$rootDir\backend"

if (-not (Test-Path ".\.venv\Scripts\uvicorn.exe")) {
    Write-Host "Setting up Python virtual environment..." -ForegroundColor Magenta
    python -m venv .venv
    & ".\.venv\Scripts\pip.exe" install -r requirements.txt
}

Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Green
Write-Host "  Backend running on : http://127.0.0.1:8765" -ForegroundColor White
Write-Host "  API Docs (Swagger) : http://127.0.0.1:8765/docs" -ForegroundColor White
Write-Host "  Health Endpoint    : http://127.0.0.1:8765/health" -ForegroundColor White
Write-Host "--------------------------------------------------------" -ForegroundColor Green
Write-Host "Press Ctrl+C to terminate the server anytime." -ForegroundColor Gray
Write-Host ""

& ".\.venv\Scripts\uvicorn.exe" main:app --host 127.0.0.1 --port 8765 --reload
