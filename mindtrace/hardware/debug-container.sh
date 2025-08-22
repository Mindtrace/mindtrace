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

# Run the debug script inside container
docker exec -it hardware-camera-service-1 bash -c "
    cd mindtrace/hardware && 
    uv run python debug-cameras.py
"

echo "================================================"
echo "Debug complete! Check the output above for issues."