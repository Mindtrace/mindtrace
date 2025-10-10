"""Camera state management for the standalone camera configurator."""

import logging
import math
from typing import Any, Dict, List, Optional

import reflex as rx

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
    uploaded_files: list[str] = []
    selected_file: str = ""
    config_export_loading: bool = False
    config_import_loading: bool = False

    # Computed vars for compatibility with camera_card component
    @rx.var
    def streaming_camera_name(self) -> str:
        """Alias for current_streaming_camera for component compatibility."""
        return self.current_streaming_camera

    @rx.var
    def streaming_url(self) -> str:
        """Alias for current_stream_url for component compatibility."""
        return self.current_stream_url

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
                        config_response = await _camera_api.get_camera_configuration(camera)
                        camera_configs[camera] = (
                            config_response.get("data", {}) if config_response.get("success") else {}
                        )
                    elif camera in discovered_cameras:
                        # Camera is discoverable but not initialized
                        camera_statuses[camera] = "available"
                        camera_configs[camera] = {}
                    else:
                        # Camera was previously discovered but is now not discoverable
                        # Keep it as available so user can try to reinitialize it
                        camera_statuses[camera] = "available"
                        camera_configs[camera] = {}

                except Exception:
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

            self.set_message(
                f"Tracking {len(self.cameras)} cameras ({len(active_cameras)} active, {len(discovered_cameras)} discoverable)",
                "success",
            )

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
                await self.stop_stream()

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
        self.selected_file = ""  # Clear selected file when closing modal

    async def apply_camera_config(self):
        """Apply configuration to the selected camera."""
        if not self.selected_camera:
            return

        # Convert exposure value based on camera backend
        exposure_value = self.config_exposure
        if self.selected_camera.startswith("OpenCV:"):
            # Convert microseconds back to logarithmic value for OpenCV
            # Formula: log2(microseconds / 1000000)
            if exposure_value > 0:
                exposure_value = math.log2(exposure_value / 1000000)

        config = {"exposure_time": exposure_value, "gain": self.config_gain, "trigger_mode": self.config_trigger_mode}

        try:
            result = await _camera_api.configure_camera(self.selected_camera, config)
            if result.get("success", False):
                # Refresh camera configuration from API to get actual values
                actual_config_response = await _camera_api.get_camera_configuration(self.selected_camera)
                self.camera_configs[self.selected_camera] = (
                    actual_config_response.get("data", {}) if actual_config_response.get("success") else {}
                )
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
        """Start MJPEG video stream for the given camera."""

        # Stop any existing stream first
        if self.current_streaming_camera:
            await self.stop_stream()

        try:
            # Start the stream on the backend
            result = await _camera_api.start_camera_stream(camera_name)

            if result.get("success", False):
                # Use the stream URL from the API response
                stream_data = result.get("data", {})
                stream_url = stream_data.get("stream_url")

                if stream_url:
                    self.current_stream_url = stream_url
                    self.current_streaming_camera = camera_name
                    self.set_message(f"Stream started for {camera_name}", "success")
                else:
                    self.set_message("Failed to get stream URL", "error")
            else:
                error = result.get("error", "Failed to start stream")
                self.set_message(f"Failed to start stream: {error}", "error")

        except Exception as e:
            self.set_message(f"Error starting stream: {str(e)}", "error")

    async def stop_stream(self):
        """Stop the MJPEG video stream."""

        if self.current_streaming_camera:
            try:
                # Stop the stream on the backend
                result = await _camera_api.stop_camera_stream(self.current_streaming_camera)

                if result.get("success", False):
                    self.set_message(f"Stream stopped for {self.current_streaming_camera}", "success")
                else:
                    error = result.get("error", "Unknown error")
                    self.set_message(f"Failed to stop stream: {error}", "error")

            except Exception as e:
                self.set_message(f"Error stopping stream: {str(e)}", "error")

        # Always clear the state
        self.current_streaming_camera = ""
        self.current_stream_url = ""
        self.set_message("Stream stopped", "success")

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

        initialized_cameras = [name for name, status in self.camera_statuses.items() if status == "initialized"]

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
    def set_config_exposure(self, value):
        """Set exposure configuration value."""
        try:
            if isinstance(value, (int, float)):
                self.config_exposure = int(value)
            else:
                self.config_exposure = int(value)
        except (ValueError, TypeError):
            pass  # Keep existing value if conversion fails

    def set_config_gain(self, value):
        """Set gain configuration value."""
        try:
            if isinstance(value, (int, float)):
                self.config_gain = int(value)
            else:
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

    def set_selected_file(self, value: str):
        """Set selected file for import."""
        self.selected_file = value

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle uploaded configuration files."""
        logger.info(f"🔍 UPLOAD DEBUG: handle_upload called with {len(files)} files")

        if not files:
            logger.warning("⚠️ UPLOAD DEBUG: No files received in handle_upload")
            self.set_message("No files received", "warning")
            return

        for i, file in enumerate(files):
            try:
                logger.info(f"📁 UPLOAD DEBUG: Processing file {i + 1}/{len(files)}")
                logger.info(f"📄 UPLOAD DEBUG: File object type: {type(file)}")
                logger.info(f"🔍 UPLOAD DEBUG: File object attributes: {dir(file)}")

                # Extract filename from the file object
                filename = None
                if hasattr(file, "name") and file.name:
                    filename = file.name
                    logger.info(f"✅ UPLOAD DEBUG: Got filename from .name: {filename}")
                elif hasattr(file, "filename") and file.filename:
                    filename = file.filename
                    logger.info(f"✅ UPLOAD DEBUG: Got filename from .filename: {filename}")
                else:
                    filename = f"config_{len(self.uploaded_files) + 1}.json"
                    logger.info(f"🔄 UPLOAD DEBUG: Using fallback filename: {filename}")

                if not filename.endswith(".json"):
                    logger.error(f"❌ UPLOAD DEBUG: File {filename} is not a JSON file")
                    self.set_message("Please upload only JSON files", "error")
                    continue

                logger.info(f"📂 UPLOAD DEBUG: Processing JSON file: {filename}")
                upload_path = rx.get_upload_dir() / filename
                logger.info(f"💾 UPLOAD DEBUG: Upload path: {upload_path}")

                # Handle different file content types
                content = None
                if hasattr(file, "read") and callable(file.read):
                    logger.info("📖 UPLOAD DEBUG: Reading file with .read() method")
                    content = await file.read()
                    logger.info(f"📊 UPLOAD DEBUG: Read {len(content)} bytes")
                elif isinstance(file, bytes):
                    logger.info("📦 UPLOAD DEBUG: File is already bytes")
                    content = file
                else:
                    logger.info("🔄 UPLOAD DEBUG: Converting file to bytes")
                    content = str(file).encode("utf-8")

                if content is None or len(content) == 0:
                    logger.error("❌ UPLOAD DEBUG: No content extracted from file")
                    self.set_message(f"File '{filename}' appears to be empty", "error")
                    continue

                # Write the file content
                logger.info(f"💾 UPLOAD DEBUG: Saving to {upload_path}")
                with upload_path.open("wb") as file_obj:
                    file_obj.write(content)

                # Avoid duplicates
                if filename not in self.uploaded_files:
                    self.uploaded_files.append(filename)
                    logger.info(f"📝 UPLOAD DEBUG: Added {filename} to uploaded_files list")

                # Set the selected file for import
                self.selected_file = filename

                self.set_message(f"File '{filename}' uploaded successfully", "success")
                logger.info(f"✅ UPLOAD DEBUG: Successfully processed file: {filename}")

            except Exception as e:
                logger.error(f"❌ UPLOAD DEBUG: Error uploading file: {e}")
                import traceback

                logger.error(f"🔍 UPLOAD DEBUG: Full traceback:\n{traceback.format_exc()}")
                self.set_message(f"Error uploading file: {str(e)}", "error")

    async def export_camera_config(self, camera_name: str):
        """Export camera configuration and trigger download."""
        self.config_export_loading = True
        self.clear_message()

        try:
            # Get current camera configuration
            config = await _camera_api.get_camera_configuration(camera_name)
            if config.get("success", False):
                import json

                config_data = json.dumps(config.get("data", {}), indent=2)
                filename = f"{camera_name.replace(':', '_')}_config.json"
                self.set_message(f"Configuration exported for {camera_name}", "success")
                return rx.download(data=config_data, filename=filename)
            else:
                error = config.get("error", "Unknown error")
                self.set_message(f"Failed to export config: {error}", "error")
        except Exception as e:
            self.set_message(f"Error exporting config: {str(e)}", "error")
        finally:
            self.config_export_loading = False

    async def import_camera_config(self, camera_name: str):
        """Import camera configuration from selected uploaded file."""
        self.config_import_loading = True
        self.clear_message()

        if not self.selected_file:
            self.set_message("Please select a file to import", "error")
            self.config_import_loading = False
            return

        try:
            # Read the uploaded file
            upload_path = rx.get_upload_dir() / self.selected_file
            if not upload_path.exists():
                self.set_message(f"File '{self.selected_file}' not found. Please upload it first.", "error")
                return

            import json

            with upload_path.open("r") as f:
                config_data = json.load(f)

            logger.info(f"Loaded config data from {self.selected_file}: {config_data}")

            # Filter configuration to only include API-supported fields
            filtered_config = {}
            if "exposure_time" in config_data:
                filtered_config["exposure_time"] = config_data["exposure_time"]
            if "gain" in config_data:
                filtered_config["gain"] = config_data["gain"]
            if "trigger_mode" in config_data:
                filtered_config["trigger_mode"] = config_data["trigger_mode"]

            # Apply configuration via API
            if camera_name in self.cameras:
                logger.info(f"Loaded config data from {self.selected_file}: {config_data}")
                logger.info(f"Filtered config for API: {filtered_config}")
                logger.info(f"Configuring camera {camera_name} with filtered data: {filtered_config}")
                # Configure camera with the filtered settings
                success = await _camera_api.configure_camera(camera_name, filtered_config)
                logger.info(f"Configure camera result: {success}")
                if success.get("success", False):
                    self.set_message(f"Configuration imported from {self.selected_file}", "success")
                    # Refresh camera configuration after import
                    await self.refresh_cameras()
                else:
                    error = success.get("error", "Unknown error")
                    self.set_message(f"Failed to apply config: {error}", "error")
            else:
                self.set_message(f"Camera '{camera_name}' not found", "error")
        except json.JSONDecodeError:
            self.set_message(f"Invalid JSON file: {self.selected_file}", "error")
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

    # Computed properties
    @rx.var
    def camera_count(self) -> int:
        """Total number of cameras."""
        return len(self.cameras)

    @rx.var
    def initialized_camera_count(self) -> int:
        """Number of initialized cameras."""
        return len([status for status in self.camera_statuses.values() if status == "initialized"])

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

    @rx.var
    def available_trigger_modes(self) -> List[str]:
        """Get available trigger modes for selected camera as strings."""
        if not self.selected_camera:
            return ["continuous", "trigger"]

        ranges = self.camera_ranges.get(self.selected_camera, {})
        trigger_modes = ranges.get("trigger_modes", [])

        # Ensure all modes are strings
        if trigger_modes:
            return [str(mode) for mode in trigger_modes]
        else:
            # Default modes if none specified
            return ["continuous", "trigger"]

    @rx.var
    def exposure_supported(self) -> bool:
        """Check if the selected camera supports exposure control."""
        if not self.selected_camera:
            return False

        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure")

        # Return True only if exposure_range exists (not None/null)
        # OpenCV cameras will have exposure_range: null
        # Basler cameras will have exposure_range: [min, max]
        return exposure_range is not None

    @rx.var
    def exposure_min_microseconds(self) -> int:
        """Get minimum exposure in microseconds, handling different backends."""
        if not self.selected_camera:
            return 100

        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [])

        if len(exposure_range) >= 2:
            min_val = exposure_range[0]
            # Check if this looks like OpenCV log values (negative numbers)
            if min_val < 0:
                # Convert from log values: 2^(log_value) * 1000000
                return int(2**min_val * 1000000)
            else:
                # Already in microseconds (Basler, etc.)
                return int(min_val)
        return 100

    @rx.var
    def exposure_max_microseconds(self) -> int:
        """Get maximum exposure in microseconds, handling different backends."""
        if not self.selected_camera:
            return 10000

        ranges = self.camera_ranges.get(self.selected_camera, {})
        exposure_range = ranges.get("exposure", [])

        if len(exposure_range) >= 2:
            max_val = exposure_range[1]
            # Check if this looks like OpenCV log values (negative numbers)
            if max_val < 0:
                # Convert from log values: 2^(log_value) * 1000000
                return int(2**max_val * 1000000)
            else:
                # Already in microseconds (Basler, etc.)
                return int(max_val)
        return 10000
