#!/bin/bash
# Platform-aware Docker Compose starter for camera service

# Detect platform and set network mode
if [[ "$OS" == "Windows_NT" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ -n "$WSL_DISTRO_NAME" ]]; then
    echo "🪟 Detected Windows environment - using bridge networking"
    echo "   Note: GigE cameras may have limited network access"
    export NETWORK_MODE="bridge"
else
    echo "🐧 Detected Linux environment - using host networking for full GigE camera access"
    export NETWORK_MODE="host"
fi

# Start docker-compose with the appropriate configuration
echo "Starting camera service with NETWORK_MODE=$NETWORK_MODE"
docker-compose up "$@"