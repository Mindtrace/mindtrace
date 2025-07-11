import reflex as rx
import httpx
from typing import List, Dict, Optional, Any

class CameraState(rx.State):
    """
    State management for Camera Configurator page.
    Handles camera discovery, config, capture, import/export, diagnostics, and (future) streaming.
    """
    # Camera data
    cameras: List[str] = []  # List of camera names ("Backend:device_name")
    selected_camera: Optional[str] = None
    camera_info: Dict[str, Any] = {}
    camera_config: Dict[str, Any] = {}
    camera_status: Dict[str, Any] = {}
    diagnostics: Dict[str, Any] = {}

    # Camera status tracking
    camera_statuses: Dict[str, str] = {}  # "not_initialized", "initialized", "unavailable", "closed"
    
    # Computed properties for UI
    @rx.var
    def camera_status_badges(self) -> Dict[str, str]:
        """Get status badges for all cameras."""
        badges = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "initialized":
                badges[camera] = "Available"
            elif status == "unavailable":
                badges[camera] = "Unavailable"
            elif status == "closed":
                badges[camera] = "Closed"
            else:
                badges[camera] = "Not Initialized"
        return badges
    
    @rx.var
    def camera_status_colors(self) -> Dict[str, str]:
        """Get status colors for all cameras."""
        colors = {}
        for camera in self.cameras:
            status = self.camera_statuses.get(camera, "not_initialized")
            if status == "initialized":
                colors[camera] = "#059669"  # Green
            elif status == "unavailable":
                colors[camera] = "#DC2626"  # Red
            elif status == "closed":
                colors[camera] = "#F59E0B"  # Orange
            else:
                colors[camera] = "#6B7280"  # Gray
        return colors
    camera_ranges: Dict[str, Dict[str, List[float]]] = {}  # Store exposure/gain ranges per camera

    # UI/operation state
    is_loading: bool = False
    error: str = ""
    success: str = ""

    # Capture result
    capture_image_data: Optional[str] = None  # base64 or URL
    capture_loading: bool = False

    # Import/export
    import_status: str = ""
    export_status: str = ""
    import_loading: bool = False
    export_loading: bool = False

    # (Future) Stream state
    stream_url: Optional[str] = None
    stream_active: bool = False

    # Popup state
    open_config_popup: bool = False

    API_BASE = "http://localhost:8001/api/v1"

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
                        # Check status of each discovered camera
                        for camera in self.cameras:
                            try:
                                status_response = await client.get(f"{self.API_BASE}/cameras/status?camera={camera}")
                                if status_response.status_code == 200:
                                    status_data = status_response.json()
                                    if status_data.get("success") and status_data.get("data", {}).get("initialized"):
                                        self.camera_statuses[camera] = "initialized"
                                    else:
                                        self.camera_statuses[camera] = "not_initialized"
                                else:
                                    self.camera_statuses[camera] = "not_initialized"
                            except:
                                self.camera_statuses[camera] = "not_initialized"
                        
                        print(f"DEBUG: Discovered cameras: {self.cameras}")
                        print(f"DEBUG: Camera statuses after status check: {self.camera_statuses}")
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
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/initialize",
                    json={"camera": camera}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_statuses[camera] = "initialized"
                        self.success = f"Camera {camera} initialized successfully"
                        print(f"DEBUG: Camera {camera} initialized, status: {self.camera_statuses[camera]}")
                        print(f"DEBUG: All camera statuses: {self.camera_statuses}")
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.error = data.get("message", f"Failed to initialize {camera}")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.error = f"Failed to initialize {camera}: {response.status_code}"
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.error = f"Error initializing {camera}: {str(e)}"

    async def fetch_camera_ranges(self, camera: str):
        """Fetch exposure and gain ranges for a camera."""
        try:
            async with httpx.AsyncClient() as client:
                # Fetch exposure range
                exposure_response = await client.get(f"{self.API_BASE}/cameras/config/async/exposure/range?camera={camera}")
                if exposure_response.status_code == 200:
                    exposure_data = exposure_response.json()
                    if exposure_data.get("success"):
                        exposure_range = exposure_data.get("data", [0, 100000])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["exposure"] = exposure_range
                        print(f"DEBUG: Fetched exposure range for {camera}: {exposure_range}")
                
                # Fetch gain range
                gain_response = await client.get(f"{self.API_BASE}/cameras/config/sync/gain/range?camera={camera}")
                if gain_response.status_code == 200:
                    gain_data = gain_response.json()
                    if gain_data.get("success"):
                        gain_range = gain_data.get("data", [0, 100])
                        if camera not in self.camera_ranges:
                            self.camera_ranges[camera] = {}
                        self.camera_ranges[camera]["gain"] = gain_range
                        print(f"DEBUG: Fetched gain range for {camera}: {gain_range}")
                        
        except Exception as e:
            print(f"DEBUG: Error fetching ranges for {camera}: {e}")
            # If ranges fail, use default ranges
            if camera not in self.camera_ranges:
                self.camera_ranges[camera] = {}
            self.camera_ranges[camera]["exposure"] = [1000, 100000]
            self.camera_ranges[camera]["gain"] = [0, 100]

    async def fetch_camera_info(self, camera: str):
        """Fetch camera information and update status if it fails."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/info?camera={camera}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.camera_info = data.get("data", {})
                        # Update status to initialized if we can get info
                        self.camera_statuses[camera] = "initialized"
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.error = data.get("message", f"Failed to get info for {camera}")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.error = f"Failed to get info for {camera}: {response.status_code}"
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.error = f"Error getting info for {camera}: {str(e)}"

    async def update_camera_config(self, camera: str, config: Dict[str, Any]):
        """Update camera configuration and update status if it fails."""
        self.is_loading = True
        self.clear_messages()
        try:
            async with httpx.AsyncClient() as client:
                # Split config into different parameter types
                async_config = {}
                sync_config = {}
                trigger_config = {}
                
                for key, value in config.items():
                    if key in ["exposure"]:
                        async_config[key] = value
                    elif key in ["gain"]:
                        sync_config[key] = value
                    elif key in ["mode"]:  # Trigger mode
                        trigger_config[key] = value
                
                # Update async parameters (exposure)
                if async_config:
                    async_payload = {"configurations": {camera: async_config}}
                    async_response = await client.post(
                        f"{self.API_BASE}/cameras/config/async/batch",
                        json=async_payload
                    )
                    if async_response.status_code != 200:
                        self.error = f"Failed to update async config for {camera}: {async_response.status_code}"
                        return
                
                # Update sync parameters (gain)
                if sync_config:
                    sync_payload = {"configurations": {camera: sync_config}}
                    sync_response = await client.post(
                        f"{self.API_BASE}/cameras/config/sync/batch",
                        json=sync_payload
                    )
                    if sync_response.status_code != 200:
                        self.error = f"Failed to update sync config for {camera}: {sync_response.status_code}"
                        return
                
                # Update trigger mode
                if trigger_config:
                    trigger_response = await client.post(
                        f"{self.API_BASE}/cameras/config/trigger",
                        json={"camera": camera, "mode": trigger_config["mode"]}
                    )
                    if trigger_response.status_code != 200:
                        self.error = f"Failed to update trigger mode for {camera}: {trigger_response.status_code}"
                        return
                
                self.success = f"Configuration updated for {camera}"
                # Refresh camera info to get updated values
                await self.fetch_camera_info(camera)
                
        except Exception as e:
            self.error = f"Error updating config for {camera}: {str(e)}"
        finally:
            self.is_loading = False

    async def import_camera_config(self, camera: str, file_path: str):
        """Import camera configuration from file via API (not implemented)."""
        self.import_loading = True
        self.import_status = "Import not implemented."
        self.import_loading = False

    async def export_camera_config(self, camera: str, file_path: str):
        """Export camera configuration to file via API (not implemented)."""
        self.export_loading = True
        self.export_status = "Export not implemented."
        self.export_loading = False

    async def capture_image(self, camera: str):
        """Capture image from camera and update status if it fails."""
        self.capture_loading = True
        self.clear_messages()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.API_BASE}/cameras/capture/",
                    json={"camera": camera}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        image_data = data.get("image_data", "")
                        self.capture_image_data = image_data
                        self.selected_camera = camera  # Ensure selected camera is set for image display
                        self.success = f"Image captured from {camera}"
                        print(f"DEBUG: Captured image data length: {len(image_data) if image_data else 0}")
                        print(f"DEBUG: Image data preview: {image_data[:50] if image_data else 'None'}...")
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.error = data.get("message", f"Failed to capture from {camera}")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.error = f"Failed to capture from {camera}: {response.status_code}"
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.error = f"Error capturing from {camera}: {str(e)}"
        finally:
            self.capture_loading = False

    async def fetch_camera_diagnostics(self, camera: str):
        """Fetch camera diagnostics and update status if it fails."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.API_BASE}/cameras/status?camera={camera}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.diagnostics = data.get("data", {})
                        # Update status based on connection
                        if self.diagnostics.get("connected"):
                            self.camera_statuses[camera] = "initialized"
                        else:
                            self.camera_statuses[camera] = "unavailable"
                    else:
                        self.camera_statuses[camera] = "unavailable"
                        self.error = data.get("message", f"Failed to get diagnostics for {camera}")
                else:
                    self.camera_statuses[camera] = "unavailable"
                    self.error = f"Failed to get diagnostics for {camera}: {response.status_code}"
        except Exception as e:
            self.camera_statuses[camera] = "unavailable"
            self.error = f"Error getting diagnostics for {camera}: {str(e)}"

    def update_config_value(self, key: str, value: Any):
        """Update a configuration value."""
        self.camera_config[key] = value

    # (Future) Stream actions
    def start_stream(self, camera: str):
        """Start real-time stream (placeholder)."""
        self.stream_active = True
        self.stream_url = f"/api/v1/cameras/stream?camera={camera}"

    def stop_stream(self):
        """Stop real-time stream (placeholder)."""
        self.stream_active = False
        self.stream_url = None

    def clear_messages(self):
        """Clear error and success messages."""
        self.error = ""
        self.success = ""

    async def select_camera(self, camera: str):
        """Select a camera and fetch its information."""
        self.selected_camera = camera
        await self.fetch_camera_info(camera)
        await self.fetch_camera_diagnostics(camera)
        # Open the popup dialog automatically
        self.open_config_popup = True

    def open_camera_popup(self, camera: str):
        """Open the camera configuration popup."""
        self.selected_camera = camera
        self.open_config_popup = True

    def fetch_camera_data(self, camera: str):
        """Fetch camera data when popup opens."""
        self.selected_camera = camera
        # This will be called when the popup opens
        # The actual data fetching will happen in the popup

    async def open_camera_config(self, camera: str):
        """Open camera configuration popup and fetch camera data."""
        self.selected_camera = camera
        try:
            # Fetch current camera info and diagnostics
            await self.fetch_camera_info(camera)
            await self.fetch_camera_diagnostics(camera)
            # Fetch ranges for sliders
            await self.fetch_camera_ranges(camera)
            
            # Now sync config from the fetched info
            info = self.camera_info
            
            # Get valid ranges
            exposure_range = self.camera_ranges.get(camera, {}).get("exposure", [1000, 100000])
            gain_range = self.camera_ranges.get(camera, {}).get("gain", [0, 100])
            
            # Use current values or clamp to valid range
            current_exposure = info.get("current_exposure", exposure_range[0])
            current_gain = info.get("current_gain", gain_range[0])
            
            # Ensure values are within valid ranges
            if current_exposure < exposure_range[0]:
                current_exposure = exposure_range[0]
            elif current_exposure > exposure_range[1]:
                current_exposure = exposure_range[1]
                
            if current_gain < gain_range[0]:
                current_gain = gain_range[0]
            elif current_gain > gain_range[1]:
                current_gain = gain_range[1]
            
            self.camera_config = {
                "exposure": current_exposure,
                "gain": current_gain,
                "width": info.get("width", ""),
                "height": info.get("height", ""),
                "pixel_format": info.get("pixel_format", "BGR8"),
                "mode": info.get("mode", "continuous"),
                "image_enhancement": info.get("image_enhancement", False),
            }
            
        except Exception as e:
            self.error = f"Error opening camera config: {str(e)}"

    def clear_selection(self):
        """Clear the selected camera."""
        self.selected_camera = ""
        self.camera_info = {}
        self.camera_config = {}
        self.diagnostics = {}
        self.capture_image_data = None
        self.open_config_popup = False
        self.clear_messages()

    @property
    def diagnostics_items(self):
        return list(self.diagnostics.items()) if self.diagnostics else [] 