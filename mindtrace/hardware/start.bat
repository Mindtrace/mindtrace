@echo off
echo 🪟 Detected Windows environment - using bridge networking
echo    Note: GigE cameras may have limited network access
set NETWORK_MODE=bridge
echo Starting camera service with NETWORK_MODE=%NETWORK_MODE%
docker-compose up %*