@echo off
echo 🪟 Windows Docker Desktop - Hybrid networking solution
echo    ✅ localhost:8000 will be accessible (bridge networking)
echo    🔄 Attempting to enable camera network access...
echo.

REM Stop any existing containers
docker-compose down 2>nul

REM Use Windows-specific compose configuration
set COMPOSE_FILE=docker-compose.yml;docker-compose.windows.yml

echo Starting with Windows hybrid networking...
docker-compose up -d

echo.
echo Waiting for service to start...
timeout /t 15 /nobreak >nul

echo Testing service accessibility...
curl -s http://localhost:8000/cameras/discover >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Service accessible at http://localhost:8000
    echo.
    echo Testing camera discovery...
    curl -s http://localhost:8000/cameras/discover
    echo.
) else (
    echo ❌ Service not accessible at localhost:8000
    echo Check if container is running:
    docker ps | findstr hardware-camera-service
)

echo.
echo 💡 If cameras are not found:
echo    1. Camera networks may still be isolated in Windows Docker
echo    2. Try running debug-container.bat to diagnose
echo    3. Consider using Docker Desktop's "Use the WSL 2 based engine" option