@echo off
echo 🔍 Running camera debug inside Windows container...
echo ================================================

REM Check if container is running
docker ps | findstr hardware-camera-service >nul
if errorlevel 1 (
    echo ❌ Camera service container is not running!
    echo    Please run: start.bat
    exit /b 1
)

REM Copy debug script into container and run it
docker cp debug-cameras.py hardware-camera-service-1:/app/mindtrace/hardware/
docker exec hardware-camera-service-1 bash -c "cd mindtrace/hardware && uv run python debug-cameras.py"

echo ================================================
echo Debug complete! Check the output above for issues.