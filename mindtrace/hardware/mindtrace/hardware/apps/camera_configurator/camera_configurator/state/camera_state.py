"""Camera state management for the standalone camera configurator."""

import reflex as rx
from typing import List, Dict, Any, Optional
import asyncio
import logging
from ..services.camera_api import CameraAPI

logger = logging.getLogger(__name__)

# Global camera API instance
_camera_api = CameraAPI()

class CameraState(rx.State):
    """State management for camera operations."""
    
    # Camera data
    cameras: List[str] = []
    camera_statuses: Dict[str, str] = {}
    camera_configs: Dict[str, Dict[str, Any]] = {}
    camera_ranges: Dict[str, Dict[str, List[float]]] = {}
    
    # Selected camera for operations
    selected_camera: str = ""
    
    # Configuration modal state
    config_modal_open: bool = False
    config_exposure: int = 1000
    config_gain: int = 0
    config_trigger_mode: str = "continuous"
    
    # UI state
    is_loading: bool = False
    capture_loading: bool = False
    captured_image: Optional[str] = None
    
    # Simplified streaming state (like poseidon)
    # Instead of complex dictionaries, use simple reactive state
    current_streaming_camera: str = ""  # Which camera is currently streaming
    current_stream_url: str = ""  # Current stream URL
    
    # Messages
    message: str = ""
    message_type: str = "info"  # info, success, error, warning
    
    # API connectivity
    api_connected: bool = False
    
    # File-based configuration management
    config_file_path: str = ""
    config_export_loading: bool = False
    config_import_loading: bool = False
    
    def set_message(self, message: str, message_type: str = "info"):
        """Set a status message."""
        self.message = message
        self.message_type = message_type
    
    def clear_message(self):
        """Clear the current message."""
        self.message = ""
        self.message_type = "info"
    
    async def check_api_connection(self):
        """Check if camera API is reachable."""
        try:
            self.api_connected = await _camera_api.health_check()
            if not self.api_connected:
                self.set_message("Camera API is not responding", "error")
        except Exception as e:
            self.api_connected = False
            self.set_message(f"Cannot connect to camera API: {str(e)}", "error")
    
    async def refresh_cameras(self):
        """Refresh the list of available cameras."""
        self.is_loading = True
        self.clear_message()
        
        try:
            await self.check_api_connection()
            if not self.api_connected:
                return
            
            # Discover cameras from all backends
            discovered_cameras = await _camera_api.discover_cameras()
            
            # Check if this is initial load (no cameras currently tracked)
            is_initial_load = len(self.cameras) == 0
            
            # Merge with existing cameras to preserve ones that are no longer discoverable
            # This keeps cameras visible even after they're closed/deinitialized
            all_cameras = list(set(self.cameras + discovered_cameras))
            self.cameras = sorted(all_cameras)  # Sort for consistent display order
            
            # Get active cameras (already opened)
            active_cameras = await _camera_api.get_active_cameras()
            
            # Get status for each camera (including previously discovered ones)
            camera_statuses = {}
            camera_configs = {}
            
            for camera in self.cameras:
                try:
                    if camera in active_cameras:
                        # Camera is active, get detailed info
                        status_info = await _camera_api.get_camera_status(camera)
                        if status_info.get("connected"):
                            camera_statuses[camera] = "initialized"
                        else:
                            camera_statuses[camera] = "available"
                        
                        # Get current configuration
                        config = await _camera_api.get_camera_configuration(camera)
                        camera_configs[camera] = config
                    elif camera in discovered_cameras:
                        # Camera is discoverable but not initialized
                        camera_statuses[camera] = "available"
                        camera_configs[camera] = {}
                    else:
                        # Camera was previously discovered but is now not discoverable
                        # Keep it as available so user can try to reinitialize it
                        camera_statuses[camera] = "available"
                        camera_configs[camera] = {}
                    
                except Exception as e:
                    camera_statuses[camera] = "error"
                    camera_configs[camera] = {}
            
            self.camera_statuses = camera_statuses
            self.camera_configs = camera_configs
            
            # Only reset streaming state on initial load
            # This preserves active streams during normal refresh operations
            if is_initial_load:  # Initial load - reset streaming state
                # Debug log removed
                self.current_streaming_camera = ""
                self.current_stream_url = ""
                # Debug log removed
            else:
                # Debug log removed
                pass
            
            self.set_message(f"Tracking {len(self.cameras)} cameras ({len(active_cameras)} active, {len(discovered_cameras)} discoverable)", "success")
            
        except Exception as e:
            self.set_message(f"Error refreshing cameras: {str(e)}", "error")
        finally:
            self.is_loading = False
    
    async def initialize_camera(self, camera_name: str):
        """Initialize a camera."""
        # Debug log removed
        self.clear_message()
        
        try:
            result = await _camera_api.initialize_camera(camera_name)
            # Debug log removed
            if result.get("success", False):
                self.camera_statuses[camera_name] = "initialized"
                self.set_message(f"Camera {camera_name} initialized successfully", "success")
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to initialize {camera_name}: {error}", "error")
        except Exception as e:
            self.set_message(f"Error initializing {camera_name}: {str(e)}", "error")
        
        # Debug log removed
        # Refresh camera status
        await self.refresh_cameras()
        # Debug log removed
    
    async def close_camera(self, camera_name: str):
        """Close/deinitialize a camera."""
        self.clear_message()
        
        try:
            # Stop streaming if active for this camera
            if self.is_camera_streaming(camera_name):
                await self.stop_stream(camera_name)
            
            result = await _camera_api.close_camera(camera_name)
            if result.get("success", False):
                self.camera_statuses[camera_name] = "available"
                self.set_message(f"Camera {camera_name} closed successfully", "success")
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to close {camera_name}: {error}", "error")
        except Exception as e:
            self.set_message(f"Error closing {camera_name}: {str(e)}", "error")
        
        # Refresh camera status
        await self.refresh_cameras()
    
    async def open_config_modal(self, camera_name: str):
        """Open configuration modal for a camera."""
        self.selected_camera = camera_name
        
        # Load current config if available
        current_config = self.camera_configs.get(camera_name, {})
        self.config_exposure = int(current_config.get("exposure_time", 1000))
        self.config_gain = int(current_config.get("gain", 0))
        self.config_trigger_mode = current_config.get("trigger_mode", "continuous")
        
        # Fetch camera capabilities for parameter ranges
        try:
            capabilities = await _camera_api.get_camera_capabilities(camera_name)
            if capabilities:
                ranges = {}
                
                # Extract exposure range
                if "exposure_range" in capabilities and capabilities["exposure_range"]:
                    ranges["exposure"] = capabilities["exposure_range"]
                
                # Extract gain range  
                if "gain_range" in capabilities and capabilities["gain_range"]:
                    ranges["gain"] = capabilities["gain_range"]
                
                # Extract trigger modes
                if "trigger_modes" in capabilities and capabilities["trigger_modes"]:
                    ranges["trigger_modes"] = capabilities["trigger_modes"]
                
                # Store the ranges for this camera
                self.camera_ranges[camera_name] = ranges
        except Exception as e:
            logger.error(f"Error fetching capabilities for {camera_name}: {e}")
            # Continue with empty ranges if capabilities fetch fails
        
        self.config_modal_open = True
    
    def close_config_modal(self):
        """Close configuration modal."""
        self.config_modal_open = False
        self.selected_camera = ""
    
    async def apply_camera_config(self):
        """Apply configuration to the selected camera."""
        if not self.selected_camera:
            return
        
        config = {
            "exposure_time": self.config_exposure,
            "gain": self.config_gain,
            "trigger_mode": self.config_trigger_mode
        }
        
        try:
            result = await _camera_api.configure_camera(self.selected_camera, config)
            if result.get("success", False):
                # Refresh camera configuration from API to get actual values
                actual_config = await _camera_api.get_camera_configuration(self.selected_camera)
                self.camera_configs[self.selected_camera] = actual_config
                self.set_message(f"Configuration applied to {self.selected_camera}", "success")
                self.close_config_modal()
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to configure {self.selected_camera}: {error}", "error")
        except Exception as e:
            self.set_message(f"Error configuring {self.selected_camera}: {str(e)}", "error")
    
    async def capture_image(self, camera_name: str):
        """Capture an image from a camera."""
        self.capture_loading = True
        self.clear_message()
        
        try:
            result = await _camera_api.capture_image(camera_name)
            if result.get("success", False):
                self.captured_image = result.get("image_data")
                self.set_message(f"Image captured from {camera_name}", "success")
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to capture from {camera_name}: {error}", "error")
        except Exception as e:
            self.set_message(f"Error capturing from {camera_name}: {str(e)}", "error")
        finally:
            self.capture_loading = False
    
    async def start_stream(self, camera_name: str):
        """Start video stream from a camera. Only one camera can stream at a time."""
        # Debug log removed
        try:
            # Stop any existing stream first (only one stream at a time)
            if self.current_streaming_camera:
                await self.stop_stream(self.current_streaming_camera)
            
            # Start the stream on the API side
            result = await _camera_api.start_camera_stream(camera_name)
            # Debug log removed
            if result.get("success"):
                stream_url = result.get("data", {}).get("stream_url")
                if stream_url:
                    self.current_streaming_camera = camera_name
                    self.current_stream_url = stream_url
                    # Debug log removed
                    self.set_message(f"Stream started for {camera_name}", "success")
                else:
                    # Debug log removed
                    self.set_message(f"Failed to get stream URL for {camera_name}", "error")
            else:
                # Debug log removed
                self.set_message(f"Failed to start stream for {camera_name}", "error")
        except Exception as e:
            # Debug log removed
            self.set_message(f"Error starting stream for {camera_name}: {str(e)}", "error")

    async def stop_stream(self, camera_name: str):
        """Stop video stream for a specific camera."""
        # Debug log removed
        try:
            # Only stop if this camera is actually streaming
            if self.current_streaming_camera != camera_name:
                # Debug log removed
                return
            
            # Stop the stream on the API side
            result = await _camera_api.stop_camera_stream(camera_name)
            # Debug log removed
            if result.get("success"):
                # Clear streaming state
                self.current_streaming_camera = ""
                self.current_stream_url = ""
                # Debug log removed
                self.set_message(f"Stream stopped for {camera_name}", "success")
            else:
                # Debug log removed
                self.set_message(f"Failed to stop stream for {camera_name}", "error")
        except Exception as e:
            # Debug log removed
            self.set_message(f"Error stopping stream for {camera_name}: {str(e)}", "error")
    
    def is_camera_streaming(self, camera_name: str) -> bool:
        """Check if a specific camera is streaming."""
        result = self.current_streaming_camera == camera_name
        # Debug log removed: current_streaming_camera={self.current_streaming_camera}, result={result}")
        return result
    
    def get_camera_stream_url(self, camera_name: str) -> str:
        """Get stream URL for a specific camera."""
        if self.current_streaming_camera == camera_name:
            result = self.current_stream_url
        else:
            result = ""
        # Debug log removed: current_streaming_camera={self.current_streaming_camera}, result={result}")
        return result
    
    async def close_all_cameras(self):
        """Close all initialized cameras."""
        self.clear_message()
        
        initialized_cameras = [
            name for name, status in self.camera_statuses.items() 
            if status == "initialized"
        ]
        
        if not initialized_cameras:
            self.set_message("No cameras to close", "info")
            return
        
        self.is_loading = True
        
        try:
            # Use the close_all endpoint if available
            result = await _camera_api.close_all_cameras()
            if result.get("success", False):
                # Update all statuses
                for camera in initialized_cameras:
                    self.camera_statuses[camera] = "available"
                self.set_message(f"Closed {len(initialized_cameras)} cameras", "success")
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to close all cameras: {error}", "error")
        except Exception as e:
            self.set_message(f"Error closing cameras: {str(e)}", "error")
        finally:
            self.is_loading = False
        
        # Refresh status
        await self.refresh_cameras()
    
    # State setters for UI controls
    def set_config_exposure(self, value: str):
        """Set exposure configuration value."""
        try:
            self.config_exposure = int(value)
        except (ValueError, TypeError):
            pass  # Keep existing value if conversion fails
    
    def set_config_gain(self, value: str):
        """Set gain configuration value."""
        try:
            self.config_gain = int(value)
        except (ValueError, TypeError):
            pass  # Keep existing value if conversion fails
    
    def set_config_trigger_mode(self, value: str):
        """Set trigger mode configuration value."""
        self.config_trigger_mode = value
    
    def set_selected_camera(self, value: str):
        """Set selected camera."""
        self.selected_camera = value
    
    def set_captured_image(self, value: Optional[str]):
        """Set captured image data."""
        self.captured_image = value
    
    def set_config_file_path(self, value: str):
        """Set configuration file path."""
        self.config_file_path = value
    
    async def export_camera_config(self, camera_name: str, file_path: str):
        """Export camera configuration to file."""
        self.config_export_loading = True
        self.clear_message()
        
        try:
            result = await _camera_api.export_camera_config(camera_name, file_path)
            if result.get("success", False):
                self.set_message(f"Configuration exported to {file_path}", "success")
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to export config: {error}", "error")
        except Exception as e:
            self.set_message(f"Error exporting config: {str(e)}", "error")
        finally:
            self.config_export_loading = False
    
    async def import_camera_config(self, camera_name: str, file_path: str):
        """Import camera configuration from file."""
        self.config_import_loading = True
        self.clear_message()
        
        try:
            result = await _camera_api.import_camera_config(camera_name, file_path)
            if result.get("success", False):
                self.set_message(f"Configuration imported from {file_path}", "success")
                # Refresh camera configuration after import
                await self.refresh_cameras()
            else:
                error = result.get("error", "Unknown error")
                self.set_message(f"Failed to import config: {error}", "error")
        except Exception as e:
            self.set_message(f"Error importing config: {str(e)}", "error")
        finally:
            self.config_import_loading = False

    # Computed properties for streaming state
    def get_streaming_component_for_camera(self, camera_name: str) -> rx.Component:
        """Get streaming component for a specific camera - returns None if not streaming."""
        if self.is_camera_streaming(camera_name):
            return rx.box(
                rx.image(
                    src=self.get_camera_stream_url(camera_name),
                    alt=f"Live stream from {camera_name}",
                    width="100%",
                    height="200px",
                    object_fit="cover",
                ),
                width="100%",
                margin_bottom="16px",
            )
        return rx.box(height="0px", width="100%")  # Empty box when not streaming
    
    # Computed properties for reactive streaming state
    @rx.var
    def has_active_stream(self) -> bool:
        """Whether any camera is currently streaming."""
        return self.current_streaming_camera != ""
    
    @rx.var
    def streaming_camera_name(self) -> str:
        """Name of the currently streaming camera."""
        return self.current_streaming_camera
    
    @rx.var
    def streaming_url(self) -> str:
        """Current stream URL."""
        return self.current_stream_url
    
    # Computed properties
    @rx.var
    def camera_count(self) -> int:
        """Total number of cameras."""
        return len(self.cameras)
    
    @rx.var
    def initialized_camera_count(self) -> int:
        """Number of initialized cameras."""
        return len([
            status for status in self.camera_statuses.values() 
            if status == "initialized"
        ])
    
    @rx.var
    def has_cameras(self) -> bool:
        """Whether any cameras are available."""
        return len(self.cameras) > 0
    
    @rx.var
    def config_ranges_for_selected(self) -> Dict[str, List[float]]:
        """Get parameter ranges for selected camera."""
        if not self.selected_camera:
            return {}
        return self.camera_ranges.get(self.selected_camera, {})