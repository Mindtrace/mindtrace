#!/bin/bash
# Run camera debug script inside the running container

echo "🔍 Running camera debug inside container..."
echo "================================================"

# Check if container is running
if ! docker ps | grep -q hardware-camera-service; then
    echo "❌ Camera service container is not running!"
    echo "   Please run: ./start.sh -d"
    exit 1
fi

# Copy debug script into container and run it
docker cp debug-cameras.py hardware-camera-service-1:/app/mindtrace/hardware/
docker exec hardware-camera-service-1 bash -c "
    cd mindtrace/hardware && 
    uv run python debug-cameras.py
"

echo "================================================"
echo "Debug complete! Check the output above for issues."