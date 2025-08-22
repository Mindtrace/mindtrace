@echo off
echo 🪟 Windows Docker Desktop - Testing connectivity approaches...

echo.
echo Testing host networking...
set NETWORK_MODE=host
docker-compose up -d

echo Waiting 10 seconds for service to start...
timeout /t 10 /nobreak >nul

echo Testing localhost:8000 accessibility...
curl -s http://localhost:8000/cameras/discover >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Host networking works! Service accessible at localhost:8000
    echo Cameras should be discoverable if network routes are available.
    goto :end
)

echo ❌ Host networking failed, trying bridge networking...
docker-compose down

echo.
echo Switching to bridge networking...
set NETWORK_MODE=bridge
docker-compose up -d

echo Waiting 10 seconds for service to start...
timeout /t 10 /nobreak >nul

echo Testing localhost:8000 accessibility...
curl -s http://localhost:8000/cameras/discover >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Bridge networking works! Service accessible at localhost:8000
    echo Note: GigE cameras may not be accessible due to network isolation.
    goto :end
)

echo ❌ Both networking modes failed. Please check:
echo   1. Docker Desktop is running
echo   2. No firewall blocking port 8000
echo   3. No other service using port 8000

:end
echo.
echo Docker container status:
docker ps | findstr hardware-camera-service