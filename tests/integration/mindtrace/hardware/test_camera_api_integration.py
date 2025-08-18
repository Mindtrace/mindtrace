"""
Comprehensive integration tests for the Camera API service with real hardware.

This test suite validates the complete camera workflow through the REST API
using real camera backends and hardware devices when available.
"""

import asyncio
import os
import tempfile
from typing import List, Dict, Any
import pytest
import httpx


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_backend_discovery_and_health(api_client: httpx.AsyncClient, real_backends: List[str]):
    """Test backend discovery and health checking with real backends."""
    # Skip if no real backends available
    if not real_backends:
        pytest.skip("No real camera backends available")
    
    # Test backend listing
    response = await api_client.get("/backends")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) > 0
    
    # Verify at least one real backend is discovered
    assert any(backend in data["data"] for backend in real_backends)
    
    # Test backend health check
    response = await api_client.get("/backends/health")
    assert response.status_code == 200
    health_data = response.json()
    assert health_data["success"] is True
    assert health_data["data"]["total_backends"] > 0
    
    # Test specific backend info
    for backend in real_backends:
        if backend in data["data"]:
            response = await api_client.get(f"/backends/{backend}/info")
            assert response.status_code == 200
            backend_info = response.json()
            assert backend_info["success"] is True
            assert backend_info["data"]["name"] == backend


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_camera_discovery_and_connection(api_client: httpx.AsyncClient, real_cameras: List[str]):
    """Test camera discovery and connection testing with real hardware."""
    # Skip if no real cameras available
    if not real_cameras:
        pytest.skip("No real cameras discovered")
    
    # Test camera discovery
    response = await api_client.get("/cameras/discover")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) > 0
    
    # Verify real cameras are discovered
    discovered_cameras = data["data"]
    assert any(camera in discovered_cameras for camera in real_cameras)
    
    # Test connection to first real camera
    test_camera = real_cameras[0]
    
    # Initialize camera
    response = await api_client.post(f"/cameras/{test_camera}/initialize", json={
        "test_connection": True
    })
    assert response.status_code == 200
    init_data = response.json()
    assert init_data["success"] is True
    
    # Check connection
    response = await api_client.get(f"/cameras/{test_camera}/connection")
    assert response.status_code == 200
    conn_data = response.json()
    assert conn_data["success"] is True
    assert conn_data["data"]["connected"] is True
    
    # Clean up
    await api_client.delete(f"/cameras/{test_camera}")


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_complete_camera_workflow(
    api_client: httpx.AsyncClient, 
    initialized_camera: str, 
    temp_dir: str
):
    """Test complete camera workflow with real hardware through API."""
    camera = initialized_camera
    
    # 1. Get camera information
    response = await api_client.get(f"/cameras/{camera}/info")
    assert response.status_code == 200
    info_data = response.json()
    assert info_data["success"] is True
    camera_info = info_data["data"]
    assert "camera" in camera_info
    assert "backend" in camera_info
    assert "initialized" in camera_info
    
    # 2. Test configuration capabilities
    # Get exposure range
    response = await api_client.get(f"/cameras/{camera}/exposure/range")
    assert response.status_code == 200
    exposure_range_data = response.json()
    assert exposure_range_data["success"] is True
    exposure_range = exposure_range_data["data"]
    assert len(exposure_range) == 2
    assert exposure_range[0] < exposure_range[1]
    
    # Get gain range
    response = await api_client.get(f"/cameras/{camera}/gain/range")
    assert response.status_code == 200
    gain_range_data = response.json()
    assert gain_range_data["success"] is True
    gain_range = gain_range_data["data"]
    assert len(gain_range) == 2
    assert gain_range[0] < gain_range[1]
    
    # 3. Configure camera with realistic values
    # Set exposure to middle of range
    mid_exposure = int((exposure_range[0] + exposure_range[1]) / 2)
    response = await api_client.put(f"/cameras/{camera}/exposure", json={
        "exposure": mid_exposure
    })
    assert response.status_code == 200
    exp_data = response.json()
    assert exp_data["success"] is True
    
    # Verify exposure was set
    response = await api_client.get(f"/cameras/{camera}/exposure")
    assert response.status_code == 200
    current_exp = response.json()
    assert current_exp["success"] is True
    # Allow some tolerance for hardware rounding
    assert abs(current_exp["data"] - mid_exposure) <= 1000
    
    # Set gain to middle of range
    mid_gain = (gain_range[0] + gain_range[1]) / 2
    response = await api_client.put(f"/cameras/{camera}/gain", json={
        "gain": mid_gain
    })
    assert response.status_code == 200
    gain_data = response.json()
    assert gain_data["success"] is True
    
    # 4. Test single image capture
    capture_path = os.path.join(temp_dir, "test_capture.jpg")
    response = await api_client.post(f"/cameras/{camera}/capture", json={
        "return_image": True,
        "save_path": capture_path
    })
    assert response.status_code == 200
    capture_data = response.json()
    assert capture_data["success"] is True
    assert capture_data["image_data"] is not None
    assert len(capture_data["image_data"]) > 1000  # Should be substantial base64 data
    assert os.path.exists(capture_path)
    assert os.path.getsize(capture_path) > 1000  # Should be substantial file
    
    # 5. Test HDR capture
    response = await api_client.post(f"/cameras/{camera}/capture/hdr", json={
        "exposure_levels": 3,
        "exposure_multiplier": 2.0,
        "return_images": True
    })
    assert response.status_code == 200
    hdr_data = response.json()
    assert hdr_data["success"] is True
    assert hdr_data["images"] is not None
    assert len(hdr_data["images"]) == 3
    assert hdr_data["successful_captures"] == 3
    
    # 6. Test configuration export/import
    config_path = os.path.join(temp_dir, f"{camera.replace(':', '_')}_config.json")
    
    # Export configuration
    response = await api_client.post(f"/cameras/{camera}/config/export", json={
        "config_path": config_path
    })
    assert response.status_code == 200
    export_data = response.json()
    assert export_data["success"] is True
    assert os.path.exists(config_path)
    
    # Modify settings
    response = await api_client.put(f"/cameras/{camera}/exposure", json={
        "exposure": exposure_range[0]
    })
    assert response.status_code == 200
    
    # Import configuration (should restore previous settings)
    response = await api_client.post(f"/cameras/{camera}/config/import", json={
        "config_path": config_path
    })
    assert response.status_code == 200
    import_data = response.json()
    assert import_data["success"] is True
    
    # Verify settings were restored (with tolerance)
    response = await api_client.get(f"/cameras/{camera}/exposure")
    assert response.status_code == 200
    restored_exp = response.json()
    assert abs(restored_exp["data"] - mid_exposure) <= 1000


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_network_bandwidth_management(
    api_client: httpx.AsyncClient, 
    real_cameras: List[str],
    cleanup_cameras
):
    """Test network bandwidth management with real cameras."""
    if len(real_cameras) < 1:
        pytest.skip("Need at least 1 real camera for bandwidth testing")
    
    # Initialize a camera for testing
    test_camera = real_cameras[0]
    response = await api_client.post(f"/cameras/{test_camera}/initialize")
    assert response.status_code == 200
    
    try:
        # Test bandwidth info
        response = await api_client.get("/network/bandwidth")
        assert response.status_code == 200
        bandwidth_data = response.json()
        assert bandwidth_data["success"] is True
        assert "max_concurrent_captures" in bandwidth_data["data"]
        assert "active_cameras_by_type" in bandwidth_data["data"]
        
        # Test concurrent limit management
        response = await api_client.get("/network/concurrent-limit")
        assert response.status_code == 200
        limit_data = response.json()
        original_limit = limit_data["data"]
        
        # Set new limit
        new_limit = 3
        response = await api_client.put("/network/concurrent-limit", json={
            "limit": new_limit
        })
        assert response.status_code == 200
        
        # Verify limit was set
        response = await api_client.get("/network/concurrent-limit")
        assert response.status_code == 200
        current_limit = response.json()["data"]
        assert current_limit == new_limit
        
        # Test network health
        response = await api_client.get("/network/health")
        assert response.status_code == 200
        health_data = response.json()
        assert health_data["success"] is True
        assert "status" in health_data["data"]
        assert "usage_percentage" in health_data["data"]
        
        # Restore original limit
        await api_client.put("/network/concurrent-limit", json={
            "limit": original_limit
        })
        
    finally:
        # Cleanup
        await api_client.delete(f"/cameras/{test_camera}")


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_batch_operations(
    api_client: httpx.AsyncClient, 
    real_cameras: List[str],
    cleanup_cameras
):
    """Test batch operations with real cameras."""
    if len(real_cameras) < 1:
        pytest.skip("Need at least 1 real camera for batch testing")
    
    # Use first camera for batch testing
    test_cameras = real_cameras[:1]  # Use single camera to avoid overwhelming
    
    # Batch initialize
    response = await api_client.post("/cameras/batch/initialize", json={
        "cameras": test_cameras,
        "test_connections": True
    })
    assert response.status_code == 200
    batch_init_data = response.json()
    assert batch_init_data["success"] is True
    assert batch_init_data["successful_count"] >= 1
    
    try:
        # Batch capture (without returning images to save bandwidth)
        response = await api_client.post("/cameras/batch/capture", json={
            "cameras": test_cameras,
            "return_images": False
        })
        assert response.status_code == 200
        batch_capture_data = response.json()
        assert batch_capture_data["success"] is True
        assert batch_capture_data["successful_count"] >= 1
        
        # Batch HDR capture
        response = await api_client.post("/cameras/batch/capture/hdr", json={
            "cameras": test_cameras,
            "exposure_levels": 2,
            "return_images": False
        })
        assert response.status_code == 200
        batch_hdr_data = response.json()
        assert batch_hdr_data["success"] is True
        
    finally:
        # Cleanup - close all cameras
        await api_client.delete("/cameras")


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_video_streaming(
    api_client: httpx.AsyncClient, 
    initialized_camera: str
):
    """Test video streaming functionality with real camera."""
    camera = initialized_camera
    
    # Test video stream endpoint
    async with api_client.stream("GET", f"/cameras/{camera}/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers.get("content-type", "")
        
        # Read a few frames to verify stream is working
        frame_count = 0
        async for chunk in response.aiter_bytes(chunk_size=1024):
            if b"--frame" in chunk:
                frame_count += 1
                if frame_count >= 3:  # Read 3 frames then stop
                    break
        
        assert frame_count >= 2  # Should have received at least 2 frames


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_error_handling_and_edge_cases(
    api_client: httpx.AsyncClient, 
    real_cameras: List[str]
):
    """Test error handling and edge cases with real hardware."""
    if not real_cameras:
        pytest.skip("No real cameras available for error testing")
    
    # Test invalid camera operations
    fake_camera = "NonExistent:Camera"
    
    # Try to initialize non-existent camera
    response = await api_client.post(f"/cameras/{fake_camera}/initialize")
    assert response.status_code in [404, 422, 500]  # Should fail appropriately
    
    # Try to capture from non-initialized camera
    real_camera = real_cameras[0]
    response = await api_client.post(f"/cameras/{real_camera}/capture")
    assert response.status_code in [404, 409]  # Should fail - camera not initialized
    
    # Test invalid configuration values
    # Initialize camera first
    response = await api_client.post(f"/cameras/{real_camera}/initialize")
    assert response.status_code == 200
    
    try:
        # Try invalid exposure value
        response = await api_client.put(f"/cameras/{real_camera}/exposure", json={
            "exposure": -1000  # Invalid negative exposure
        })
        assert response.status_code in [400, 422]  # Should fail with validation error
        
        # Try invalid gain value
        response = await api_client.put(f"/cameras/{real_camera}/gain", json={
            "gain": -10.0  # Invalid negative gain
        })
        assert response.status_code in [400, 422]  # Should fail with validation error
        
    finally:
        # Cleanup
        await api_client.delete(f"/cameras/{real_camera}")


@pytest.mark.hardware
@pytest.mark.slow
@pytest.mark.asyncio
async def test_camera_state_management(
    api_client: httpx.AsyncClient, 
    real_cameras: List[str],
    cleanup_cameras
):
    """Test camera state management and lifecycle."""
    if not real_cameras:
        pytest.skip("No real cameras available for state testing")
    
    camera = real_cameras[0]
    
    # Check initial state - should be no active cameras
    response = await api_client.get("/cameras/active")
    assert response.status_code == 200
    initial_active = response.json()["data"]
    
    # Initialize camera
    response = await api_client.post(f"/cameras/{camera}/initialize")
    assert response.status_code == 200
    
    # Check camera is now active
    response = await api_client.get("/cameras/active")
    assert response.status_code == 200
    active_cameras = response.json()["data"]
    assert camera in active_cameras
    assert len(active_cameras) == len(initial_active) + 1
    
    # Double initialization should be idempotent
    response = await api_client.post(f"/cameras/{camera}/initialize")
    assert response.status_code == 200
    assert "already initialized" in response.json()["message"].lower()
    
    # Close camera
    response = await api_client.delete(f"/cameras/{camera}")
    assert response.status_code == 200
    
    # Check camera is no longer active
    response = await api_client.get("/cameras/active")
    assert response.status_code == 200
    final_active = response.json()["data"]
    assert camera not in final_active
    assert len(final_active) == len(initial_active)
    
    # Double close should be idempotent
    response = await api_client.delete(f"/cameras/{camera}")
    assert response.status_code == 200
    assert "already closed" in response.json()["message"].lower()