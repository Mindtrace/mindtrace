@echo off
echo 🪟 Windows Docker Desktop detected
echo    Trying host networking for GigE camera access...
set NETWORK_MODE=host
echo Starting camera service with NETWORK_MODE=%NETWORK_MODE%
docker-compose up %*