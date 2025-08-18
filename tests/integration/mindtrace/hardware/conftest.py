"""
Configuration and fixtures for hardware integration tests.

This module provides fixtures for testing the hardware camera API service
with real camera backends and hardware devices.
"""

import asyncio
import os
import tempfile
from typing import AsyncGenerator, List
import pytest
import httpx
import uvicorn
from contextlib import asynccontextmanager
from mindtrace.hardware.api.app import camera_api_service


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def api_server():
    """Start the camera API service for integration testing."""
    import subprocess
    import socket
    import time
    import requests
    import sys
    
    # Find an available port
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    
    # Start server in subprocess
    server_cmd = [
        "uv", "run", "uvicorn", 
        "mindtrace.hardware.api.app:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "error"
    ]
    
    server_process = subprocess.Popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/home/yasser/mindtrace"
    )
    
    # Wait for server to be ready
    for attempt in range(30):  # Try for up to 30 seconds
        try:
            response = requests.get(f"{base_url}/backends", timeout=2.0)
            if response.status_code == 200:
                break
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(1)
        
        # Check if process is still running
        if server_process.poll() is not None:
            stdout, stderr = server_process.communicate()
            raise RuntimeError(f"Server process died: {stderr.decode()}")
    else:
        # Kill the process if it didn't start properly
        server_process.terminate()
        server_process.wait()
        raise RuntimeError("Failed to start API server for testing")
    
    yield base_url
    
    # Shutdown server
    server_process.terminate()
    server_process.wait()


@pytest.fixture
async def api_client(api_server) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an HTTP client for API testing."""
    async with httpx.AsyncClient(
        base_url=api_server,
        timeout=30.0,  # Generous timeout for hardware operations
        follow_redirects=True
    ) as client:
        yield client


@pytest.fixture
async def cleanup_cameras(api_client):
    """Ensure cameras are cleaned up before and after tests."""
    # Pre-test cleanup
    try:
        response = await api_client.delete("/cameras")
        if response.status_code == 200:
            await asyncio.sleep(1)  # Give time for cleanup
    except Exception:
        pass  # Ignore cleanup errors
    
    yield
    
    # Post-test cleanup
    try:
        response = await api_client.delete("/cameras")
        if response.status_code == 200:
            await asyncio.sleep(1)  # Give time for cleanup
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
async def real_cameras(api_client) -> List[str]:
    """Discover and return list of real cameras (non-mock)."""
    response = await api_client.get("/cameras/discover")
    assert response.status_code == 200
    
    data = response.json()
    all_cameras = data.get("data", [])
    
    # Filter out mock cameras
    real_cameras = [
        camera for camera in all_cameras 
        if not any(mock_term in camera for mock_term in ["Mock", "mock"])
    ]
    
    return real_cameras


@pytest.fixture
async def real_backends(api_client) -> List[str]:
    """Discover and return list of real backends (non-mock)."""
    response = await api_client.get("/backends")
    assert response.status_code == 200
    
    data = response.json()
    all_backends = data.get("data", [])
    
    # Filter out mock backends
    real_backends = [
        backend for backend in all_backends 
        if not backend.startswith("Mock")
    ]
    
    return real_backends


@pytest.fixture
async def initialized_camera(api_client, real_cameras, cleanup_cameras):
    """Initialize a real camera for testing and ensure cleanup."""
    if not real_cameras:
        pytest.skip("No real cameras available for testing")
    
    test_camera = real_cameras[0]
    
    # Initialize the camera
    response = await api_client.post(f"/cameras/{test_camera}/initialize", json={
        "test_connection": True
    })
    
    if response.status_code != 200:
        pytest.skip(f"Failed to initialize camera {test_camera}: {response.text}")
    
    yield test_camera
    
    # Cleanup will be handled by cleanup_cameras fixture


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring real hardware"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add hardware marker to all integration tests
        if "integration" in str(item.fspath) and "hardware" in str(item.fspath):
            item.add_marker(pytest.mark.hardware)
            item.add_marker(pytest.mark.slow)