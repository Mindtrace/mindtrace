import reflex as rx
import httpx
from typing import List, Dict, Optional, Any
import math

class CameraState(rx.State):
    """
    Clean camera state management for the camera page.
    Handles: camera discovery, initialization, configuration (exposure/gain), image capture, and deinitialization.
    """
    
    # Camera discovery and status
    cameras: List[str] = []  # List of discovered camera names ("Backend:device_name")
    camera_statuses: Dict[str, str] = {}  # "not_initialized", "available", "unavailable"
    
    # Selected camera for configuration
    selected_camera: Optional[str] = None
    
    # Camera configuration (exposure and gain only)
    camera_config: Dict[str, Any] = {
        "exposure": 1000,  # Default exposure in microseconds
        "gain": 0,         # Default gain
    }
    
    # Camera ranges for sliders
    camera_ranges: Dict[str, Dict[str, List[float]]] = {}
    
    # Image capture
    capture_image_data: Optional[str] = None  # base64 image data
    capture_loading: bool = False
    
    # UI state
    is_loading: bool = False
    error: str = ""
    success: str = ""
    config_modal_open: bool = False
    
    API_BASE = "http://localhost:8001/api/v1"
    
    # Computed properties for UI
    @rx.var
    def camera_status_badges(self) -> Dict[str, str]:
        """Get status badges for all cameras."""
        badges = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "available":
                badges[camera] = "Available"
            elif status == "unavailable":
                badges[camera] = "Unavailable"
            else:
                badges[camera] = "Not Initialized"
        return badges
    
    @rx.var
    def camera_status_colors(self) -> Dict[str, str]:
        """Get status colors for all cameras."""
        colors = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "available":
                colors[camera] = "#059669"  # Green
            elif status == "unavailable":
                colors[camera] = "#DC2626"  # Red
            else:
                colors[camera] = "#6B7280"  # Gray
        return colors
    
    @rx.var
    def current_camera_ranges(self) -> Dict[str, List[float]]:
        """Get ranges for the currently selected camera."""
        if not self.selected_camera:
            return {"exposure": [31, 1000000], "gain": [0, 24]}
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        return {
            "exposure": ranges.get("exposure", [31, 1000000]),
            "gain": ranges.get("gain", [0, 24])
        }
    
    @rx.var
    def exposure_slider_value(self) -> int:
        """Get current exposure slider value (0-100) for log scale."""
        if not self.selected_camera:
            return 50  # Default middle position
        
        current_exp = self.camera_config.get("exposure", 1000)
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        
        min_exp = float(exposure_range[0])
        max_exp = float(exposure_range[1])
        
        if current_exp <= min_exp:
            return 0
        if current_exp >= max_exp:
            return 100
        
        min_log = math.log10(min_exp)
        max_log = math.log10(max_exp)
        current_log = math.log10(current_exp)
        
        slider_value = int(100 * (current_log - min_log) / (max_log - min_log))
        return max(0, min(100, slider_value))
    
    @rx.var
    def exposure_display_value(self) -> int:
        """Get current exposure value for display."""
        return int(self.camera_config.get("exposure", 1000))
    
    @rx.var
    def exposure_min_value(self) -> int:
        """Get minimum exposure value for display."""
        if not self.selected_camera:
            return 31
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        return int(exposure_range[0])
    
    @rx.var
    def exposure_max_value(self) -> int:
        """Get maximum exposure value for display."""
        if not self.selected_camera:
            return 1000000
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        return int(exposure_range[1])
    
    async def fetch_camera_list(self):
        """Fetch the list of available cameras."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/discover")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.cameras = data.get("data", [])
                        # Initialize all cameras as not_initialized
                        for camera in self.cameras:
                            self.camera_statuses[camera] = "not_initialized"
                        self.success = f"Found {len(self.cameras)} cameras"
                    else:
                        self.error = data.get("message", "Failed to fetch cameras")
                else:
                    self.error = f"Failed to fetch cameras: {response.status_code}"
        except Exception as e:
            self.error = f"Error fetching cameras: {str(e)}"
        finally:
            self.is_loading = False
    
    async def initialize_camera(self, camera: str):
        """Initialize a camera and update its status."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/initialize",
                    json={"camera": camera}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_statuses[camera] = "available"
                        self.success = f"Camera {camera} initialized successfully"
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.error = data.get("message", f"Failed to initialize {camera}")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.error = f"Failed to initialize {camera}: {response.status_code}"
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.error = f"Error initializing {camera}: {str(e)}"
        finally:
            self.is_loading = False
    
    async def close_camera(self, camera: str):
        """Close a specific camera and update its status."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.API_BASE}/cameras/?camera={camera}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_statuses[camera] = "not_initialized"
                        self.success = f"Camera {camera} closed successfully"
                        
                        # If the closed camera was selected, clear the selection
                        if self.selected_camera == camera:
                            self.selected_camera = None
                            self.config_modal_open = False
                            self.camera_config = {"exposure": 1000, "gain": 0}
                            self.capture_image_data = None
                    else:
                        self.error = data.get("message", f"Failed to close {camera}")
                else:
                    self.error = f"Failed to close {camera}: {response.status_code}"
        except Exception as e:
            self.error = f"Error closing {camera}: {str(e)}"
        finally:
            self.is_loading = False
    
    async def close_all_cameras(self):
        """Close all active cameras and update their statuses."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.API_BASE}/cameras/all")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # Update all camera statuses to not_initialized
                        for camera in self.cameras:
                            self.camera_statuses[camera] = "not_initialized"
                        
                        # Clear selection and modal if any camera was selected
                        if self.selected_camera:
                            self.selected_camera = None
                            self.config_modal_open = False
                            self.camera_config = {"exposure": 1000, "gain": 0}
                            self.capture_image_data = None
                        
                        self.success = data.get("message", "All cameras closed successfully")
                    else:
                        self.error = data.get("message", "Failed to close all cameras")
                else:
                    self.error = f"Failed to close all cameras: {response.status_code}"
        except Exception as e:
            self.error = f"Error closing all cameras: {str(e)}"
        finally:
            self.is_loading = False
    
    async def refresh_camera_statuses(self):
        """Refresh the status of all cameras by checking which ones are active."""
        self.is_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                # Get list of active cameras
                response = await client.get(f"{self.API_BASE}/cameras/active")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        active_cameras = data.get("data", [])
                        
                        # Update status for all cameras
                        for camera in self.cameras:
                            if camera in active_cameras:
                                self.camera_statuses[camera] = "available"
                            else:
                                self.camera_statuses[camera] = "not_initialized"
                        
                        self.success = f"Refreshed camera statuses. {len(active_cameras)} cameras active."
                    else:
                        self.error = data.get("message", "Failed to refresh camera statuses")
                else:
                    self.error = f"Failed to refresh camera statuses: {response.status_code}"
        except Exception as e:
            self.error = f"Error refreshing camera statuses: {str(e)}"
        finally:
            self.is_loading = False

    async def set_exposure_from_slider(self, slider_value: int):
        """Convert slider value (0-100) to real exposure value and update."""
        if not self.selected_camera:
            return
        
        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [31, 1000000])
        
        min_exp = float(exposure_range[0])
        max_exp = float(exposure_range[1])
        
        min_log = math.log10(min_exp)
        max_log = math.log10(max_exp)
        
        # Convert slider value (0-100) to log value
        log_value = min_log + (max_log - min_log) * (slider_value / 100)
        real_value = int(10 ** log_value)
        
        # Update exposure value
        self.camera_config["exposure"] = real_value
        
        # Call backend API
        await self.update_config_value("exposure", real_value)

    async def fetch_camera_ranges(self, camera: str):
        """Fetch exposure and gain ranges for a camera."""
        try:
            async with httpx.AsyncClient() as client:
                # Fetch exposure range
                exposure_response = await client.get(f"{self.API_BASE}/cameras/config/async/exposure/range?camera={camera}")
                if exposure_response.status_code == 200:
                    exposure_data = exposure_response.json()
                    if exposure_data.get("success"):
                        exposure_range = exposure_data.get("data", [31, 1000000])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["exposure"] = exposure_range
                        print(f"DEBUG: Fetched exposure range for {camera}: {exposure_range}")
                    else:
                        print(f"DEBUG: Failed to get exposure range for {camera}: {exposure_data.get('message')}")
                else:
                    print(f"DEBUG: Exposure range request failed for {camera}: {exposure_response.status_code}")
                
                # Fetch gain range
                gain_response = await client.get(f"{self.API_BASE}/cameras/config/sync/gain/range?camera={camera}")
                if gain_response.status_code == 200:
                    gain_data = gain_response.json()
                    if gain_data.get("success"):
                        gain_range = gain_data.get("data", [0, 24])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["gain"] = gain_range
                        print(f"DEBUG: Fetched gain range for {camera}: {gain_range}")
                    else:
                        print(f"DEBUG: Failed to get gain range for {camera}: {gain_data.get('message')}")
                else:
                    print(f"DEBUG: Gain range request failed for {camera}: {gain_response.status_code}")
                        
        except Exception as e:
            print(f"DEBUG: Error fetching ranges for {camera}: {e}")
            # Use default ranges if fetching fails
            if camera not in self.camera_ranges:
                self.camera_ranges[camera] = {}
            self.camera_ranges[camera]["exposure"] = [31, 1000000]
            self.camera_ranges[camera]["gain"] = [0, 24]
            print(f"DEBUG: Using default ranges for {camera}: exposure={self.camera_ranges[camera]['exposure']}, gain={self.camera_ranges[camera]['gain']}")
    


    async def open_camera_config(self, camera: str):
        """Open camera configuration modal and fetch camera data."""
        self.selected_camera = camera
        self.config_modal_open = True
        try:
            # Fetch camera ranges for sliders
            await self.fetch_camera_ranges(camera)
            # Get current camera values
            async with httpx.AsyncClient() as client:
                # Get current exposure
                exposure_response = await client.get(f"{self.API_BASE}/cameras/config/async/exposure?camera={camera}")
                if exposure_response.status_code == 200:
                    exposure_data = exposure_response.json()
                    if exposure_data.get("success"):
                        self.camera_config["exposure"] = exposure_data.get("data", 1000)
                # Get current gain
                gain_response = await client.get(f"{self.API_BASE}/cameras/config/sync/gain?camera={camera}")
                if gain_response.status_code == 200:
                    gain_data = gain_response.json()
                    if gain_data.get("success"):
                        self.camera_config["gain"] = gain_data.get("data", 0)
        except Exception as e:
            self.error = f"Error opening camera config: {str(e)}"
    
    async def update_config_value(self, key: str, value: Any):
        """Update a configuration value and apply it to the camera."""
        self.camera_config[key] = value
        if not self.selected_camera:
            return
        try:
            async with httpx.AsyncClient() as client:
                if key == "exposure":
                    print(f"DEBUG: Setting exposure to {value} for {self.selected_camera}")
                    response = await client.put(
                        f"{self.API_BASE}/cameras/config/async/exposure",
                        json={"camera": self.selected_camera, "exposure": value}
                    )
                elif key == "gain":
                    print(f"DEBUG: Setting gain to {value} for {self.selected_camera}")
                    response = await client.put(
                        f"{self.API_BASE}/cameras/config/sync/gain",
                        json={"camera": self.selected_camera, "gain": value}
                    )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        print(f"DEBUG: Successfully updated {key} to {value}")
                        self.success = f"{key.title()} updated to {value}"
                    else:
                        print(f"DEBUG: Failed to update {key}: {data.get('message')}")
                        self.error = data.get("message", f"Failed to update {key}")
                else:
                    print(f"DEBUG: Failed to update {key}: {response.status_code}")
                    self.error = f"Failed to update {key}: {response.status_code}"
        except Exception as e:
            print(f"DEBUG: Error updating {key}: {str(e)}")
            self.error = f"Error updating {key}: {str(e)}"
    
    async def capture_image(self):
        """Capture image from the selected camera."""
        if not self.selected_camera:
            self.error = "No camera selected"
            return
        
        self.capture_loading = True
        self.clear_messages()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/capture/",
                    json={"camera": self.selected_camera}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.capture_image_data = data.get("image_data", "")
                        self.success = f"Image captured from {self.selected_camera}"
                    else:
                        self.error = data.get("message", f"Failed to capture from {self.selected_camera}")
                else:
                    self.error = f"Failed to capture from {self.selected_camera}: {response.status_code}"
        except Exception as e:
            self.error = f"Error capturing from {self.selected_camera}: {str(e)}"
        finally:
            self.capture_loading = False
    
    def close_config_modal(self):
        """Close the configuration modal."""
        self.config_modal_open = False
        self.selected_camera = None
        self.camera_config = {"exposure": 1000, "gain": 0}
        self.capture_image_data = None
        self.clear_messages()
    
    def clear_messages(self):
        """Clear error and success messages."""
        self.error = ""
        self.success = ""
    
    def set_config_modal_open(self, open: bool):
        """Set the config modal open state."""
        self.config_modal_open = open
        if not open:
            self.close_config_modal() 