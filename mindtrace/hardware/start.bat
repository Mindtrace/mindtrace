@echo off
echo 🪟 Windows Docker Desktop detected
echo    Reverting to bridge networking for Windows compatibility
echo    Use start-windows-hybrid.bat to test both networking modes
echo.
set NETWORK_MODE=bridge
echo Starting camera service with NETWORK_MODE=%NETWORK_MODE%
docker-compose up %*