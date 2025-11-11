"""
Hardware configuration management for Mindtrace project.

Provides unified configuration for all hardware components including cameras,
sensors, actuators, and other devices with support for environment variables,
JSON file loading/saving, and default values.

Features:
    - Unified configuration for all hardware components
    - Dataclass-based configuration structure
    - Environment variable integration with MINDTRACE_HW_ prefix
    - JSON file configuration loading and saving
    - Default values for all hardware settings
    - Component-specific configuration sections
    - Thread-safe global configuration instance

Configuration Sources:
    1. Default values defined in dataclasses
    2. Environment variables (MINDTRACE_HW_*)
    3. JSON configuration file (hardware_config.json)

Environment Variables:
    - MINDTRACE_HW_CONFIG: Path to configuration file
    - MINDTRACE_HW_CAMERA_IMAGE_QUALITY: Enable camera image quality enhancement
    - MINDTRACE_HW_CAMERA_RETRY_COUNT: Number of camera capture retry attempts
    - MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE: Default camera exposure time
    - MINDTRACE_HW_CAMERA_WHITE_BALANCE: Default camera white balance mode
    - MINDTRACE_HW_CAMERA_TIMEOUT: Camera capture timeout in seconds
    - MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES: Maximum concurrent captures for network bandwidth management
    - MINDTRACE_HW_CAMERA_OPENCV_WIDTH: OpenCV default frame width
    - MINDTRACE_HW_CAMERA_OPENCV_HEIGHT: OpenCV default frame height
    - MINDTRACE_HW_CAMERA_OPENCV_FPS: OpenCV default frame rate
    - MINDTRACE_HW_CAMERA_PIXEL_FORMAT: Default pixel format (BGR8, RGB8, etc.)
    - MINDTRACE_HW_CAMERA_BUFFER_COUNT: Number of frame buffers for cameras
    - MINDTRACE_HW_CAMERA_BASLER_MULTICAST_ENABLED: Enable Basler multicast streaming
    - MINDTRACE_HW_CAMERA_BASLER_MULTICAST_GROUP: Basler multicast group IP address
    - MINDTRACE_HW_CAMERA_BASLER_MULTICAST_PORT: Basler multicast port number
    - MINDTRACE_HW_CAMERA_BASLER_TARGET_IPS: Comma-separated list of target IP addresses for Basler discovery
    - MINDTRACE_HW_CAMERA_BASLER_ENABLED: Enable Basler backend
    - MINDTRACE_HW_CAMERA_OPENCV_ENABLED: Enable OpenCV backend
    - MINDTRACE_HW_CAMERA_GENICAM_ENABLED: Enable GenICam backend
    - MINDTRACE_HW_PATHS_LIB_DIR: Directory for library installations
    - MINDTRACE_HW_PATHS_BIN_DIR: Directory for binary installations
    - MINDTRACE_HW_PATHS_INCLUDE_DIR: Directory for header files
    - MINDTRACE_HW_PATHS_SHARE_DIR: Directory for shared data files
    - MINDTRACE_HW_PATHS_CACHE_DIR: Directory for temporary files and cache
    - MINDTRACE_HW_PATHS_LOG_DIR: Directory for log files
    - MINDTRACE_HW_PATHS_CONFIG_DIR: Directory for configuration files
    - MINDTRACE_HW_NETWORK_CAMERA_IP_RANGE: IP range for camera network communication
    - MINDTRACE_HW_NETWORK_FIREWALL_RULE_NAME: Name for firewall rules
    - MINDTRACE_HW_NETWORK_INTERFACE: Network interface to use for camera communication
    - MINDTRACE_HW_NETWORK_JUMBO_FRAMES_ENABLED: Enable jumbo frames for GigE camera optimization
    - MINDTRACE_HW_NETWORK_MULTICAST_ENABLED: Enable multicast for camera discovery

Usage:
    from mindtrace.hardware.core.config import get_hardware_config

    config = get_hardware_config()
    camera_settings = config.get_config().cameras
    backend_settings = config.get_config().backends
"""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from mindtrace.core import Mindtrace


@dataclass
class CameraSettings:
    """
    Configuration for camera settings.

    This configuration is divided into three categories based on when parameters can be changed:

    1. RUNTIME-CONFIGURABLE PARAMETERS:
       These parameters can be changed dynamically while the camera is running through the
       configure_camera API endpoint without requiring camera reinitialization.
       Example: POST /cameras/configure with {"camera": "...", "properties": {"exposure_time": 2000}}

    2. STARTUP-ONLY PARAMETERS:
       These parameters require camera reinitialization to change due to hardware limitations
       (e.g., memory reallocation, network reconnection). They can only be set when the camera
       is first initialized or after a full restart.

    3. SYSTEM CONFIGURATION:
       General system settings that affect camera manager behavior but are not camera-specific
       per-device settings.

    Configuration hierarchy: config.py → initial defaults → runtime changes via API
    """

    # ═══════════════════════════════════════════════════════════════════════════════
    # RUNTIME-CONFIGURABLE PARAMETERS (changeable via configure_camera API)
    # ═══════════════════════════════════════════════════════════════════════════════

    # Capture timeout (NEW: made runtime-configurable for dynamic adjustment)
    timeout_ms: int = 5000  # Capture timeout in milliseconds

    # Image quality parameters (all backends)
    exposure_time: float = 1000.0  # Exposure time in microseconds
    gain: float = 1.0  # Camera gain value
    trigger_mode: str = "continuous"  # Trigger mode: "continuous" or "trigger"
    white_balance: str = "auto"  # White balance: "auto", "off", "once"
    image_quality_enhancement: bool = False  # Enable CLAHE image enhancement
    pixel_format: str = "BGR8"  # Pixel format: BGR8, RGB8, Mono8, etc.

    # OpenCV resolution and framerate (runtime-configurable for OpenCV backend)
    opencv_default_width: int = 1280  # Frame width in pixels
    opencv_default_height: int = 720  # Frame height in pixels
    opencv_default_fps: int = 30  # Frames per second
    opencv_default_exposure: float = -1.0  # OpenCV exposure (-1 = auto)

    # ═══════════════════════════════════════════════════════════════════════════════
    # STARTUP-ONLY PARAMETERS (require camera reinitialization to change)
    # ═══════════════════════════════════════════════════════════════════════════════

    # Frame buffer allocation (requires memory reallocation)
    buffer_count: int = 25  # Number of frame buffers (memory allocation)

    # Basler multicast streaming (requires network reconnection)
    basler_multicast_enabled: bool = False  # Enable multicast streaming mode
    basler_multicast_group: str = "239.192.1.1"  # Multicast group IP address
    basler_multicast_port: int = 3956  # Multicast port number
    basler_target_ips: List[str] = field(default_factory=list)  # Target IPs for discovery

    # ═══════════════════════════════════════════════════════════════════════════════
    # SYSTEM CONFIGURATION (manager-level settings, not per-camera)
    # ═══════════════════════════════════════════════════════════════════════════════

    # Capture and retry settings
    retrieve_retry_count: int = 3  # Number of retry attempts for failed captures
    max_concurrent_captures: int = 2  # Max concurrent captures (bandwidth management)

    # Discovery settings
    max_camera_index: int = 1  # Maximum camera index for OpenCV discovery

    # Mock/testing settings
    mock_camera_count: int = 10  # Number of mock cameras to simulate

    # Image enhancement algorithm settings
    enhancement_gamma: float = 2.2  # Gamma correction value
    enhancement_contrast: float = 1.2  # Contrast enhancement factor

    # OpenCV capability ranges (defines hardware limits)
    opencv_exposure_range_min: float = -13.0
    opencv_exposure_range_max: float = -1.0
    opencv_width_range_min: int = 160
    opencv_width_range_max: int = 1920
    opencv_height_range_min: int = 120
    opencv_height_range_max: int = 1080


@dataclass
class CameraBackends:
    """
    Configuration for camera backends.

    Attributes:
        basler_enabled: Enable Basler camera backend
        opencv_enabled: Enable OpenCV camera backend
        genicam_enabled: Enable GenICam camera backend
        mock_enabled: Enable mock camera backend for testing
        discovery_timeout: Camera discovery timeout in seconds
    """

    basler_enabled: bool = True
    opencv_enabled: bool = True
    genicam_enabled: bool = True
    mock_enabled: bool = False
    discovery_timeout: float = 10.0


@dataclass
class PathSettings:
    """
    Configuration for installation and library paths.

    Attributes:
        lib_dir: Directory for library installations (default: ~/.local/lib)
        bin_dir: Directory for binary installations (default: ~/.local/bin)
        include_dir: Directory for header files (default: ~/.local/include)
        share_dir: Directory for shared data files (default: ~/.local/share)
        cache_dir: Directory for temporary files and cache (default: ~/.cache/mindtrace)
        log_dir: Directory for log files (default: ~/.cache/mindtrace/logs)
        config_dir: Directory for configuration files (default: ~/.config/mindtrace)
    """

    lib_dir: str = "~/.local/lib"
    bin_dir: str = "~/.local/bin"
    include_dir: str = "~/.local/include"
    share_dir: str = "~/.local/share"
    cache_dir: str = "~/.cache/mindtrace"
    log_dir: str = "~/.cache/mindtrace/logs"
    config_dir: str = "~/.config/mindtrace"


@dataclass
class NetworkSettings:
    """
    Network infrastructure configuration for GigE camera communication.

    Attributes:
        camera_ip_range: IP range for camera network communication (default: 192.168.50.0/24)
        firewall_rule_name: Name for firewall rules (default: "Allow Camera Network")
        network_interface: Network interface to use for camera communication
        jumbo_frames_enabled: Enable jumbo frames for GigE camera optimization
        multicast_enabled: Enable multicast for camera discovery
    """

    camera_ip_range: str = "192.168.50.0/24"
    firewall_rule_name: str = "Allow Camera Network"
    network_interface: str = "auto"  # "auto" for automatic detection
    jumbo_frames_enabled: bool = True
    multicast_enabled: bool = True


@dataclass
class SensorSettings:
    """
    Configuration for sensor components.

    Attributes:
        auto_discovery: Automatically discover connected sensors
        polling_interval: Sensor polling interval in seconds
        timeout: Sensor operation timeout in seconds
        retry_count: Number of retry attempts for sensor operations
    """

    auto_discovery: bool = True
    polling_interval: float = 1.0
    timeout: float = 5.0
    retry_count: int = 3


@dataclass
class ActuatorSettings:
    """
    Configuration for actuator components.

    Attributes:
        auto_discovery: Automatically discover connected actuators
        default_speed: Default actuator movement speed
        timeout: Actuator operation timeout in seconds
        retry_count: Number of retry attempts for actuator operations
    """

    auto_discovery: bool = True
    default_speed: float = 1.0
    timeout: float = 10.0
    retry_count: int = 3


@dataclass
class PLCSettings:
    """
    Configuration for PLC components.

    Attributes:
        auto_discovery: Automatically discover connected PLCs
        connection_timeout: PLC connection timeout in seconds
        read_timeout: Tag read operation timeout in seconds
        write_timeout: Tag write operation timeout in seconds
        retry_count: Number of retry attempts for PLC operations
        retry_delay: Delay between retry attempts in seconds
        max_concurrent_connections: Maximum number of concurrent PLC connections
        keep_alive_interval: Keep-alive ping interval in seconds
        reconnect_attempts: Number of reconnection attempts
        default_scan_rate: Default tag scanning rate in milliseconds
    """

    auto_discovery: bool = True
    connection_timeout: float = 10.0
    read_timeout: float = 5.0
    write_timeout: float = 5.0
    retry_count: int = 3
    retry_delay: float = 1.0
    max_concurrent_connections: int = 10
    keep_alive_interval: float = 30.0
    reconnect_attempts: int = 3
    default_scan_rate: int = 1000


@dataclass
class PLCBackends:
    """
    Configuration for PLC backends.

    Attributes:
        allen_bradley_enabled: Enable Allen Bradley PLC backend (pycomm3)
        siemens_enabled: Enable Siemens PLC backend (python-snap7)
        modbus_enabled: Enable Modbus PLC backend (pymodbus)
        mock_enabled: Enable mock PLC backend for testing
        discovery_timeout: PLC discovery timeout in seconds
    """

    allen_bradley_enabled: bool = True
    siemens_enabled: bool = True
    modbus_enabled: bool = True
    mock_enabled: bool = False
    discovery_timeout: float = 15.0


@dataclass
class GCSSettings:
    """
    Configuration for Google Cloud Storage integration.

    Attributes:
        enabled: Enable GCS integration
        bucket_name: GCS bucket name
        credentials_path: Path to service account JSON
        auto_upload: Auto-upload captured images
    """

    enabled: bool = False
    bucket_name: str = "mindtrace-camera-data"
    credentials_path: str = ""
    auto_upload: bool = False


@dataclass
class HardwareConfig:
    """
    Main hardware configuration container.

    Attributes:
        cameras: Camera-specific settings and parameters
        backends: Camera backend availability and configuration
        paths: Installation and library paths
        network: Network settings and firewall configuration
        sensors: Sensor component configuration
        actuators: Actuator component configuration
        plcs: PLC component configuration
        plc_backends: PLC backend availability and configuration
        gcs: Google Cloud Storage settings
    """

    cameras: CameraSettings = field(default_factory=CameraSettings)
    backends: CameraBackends = field(default_factory=CameraBackends)
    paths: PathSettings = field(default_factory=PathSettings)
    network: NetworkSettings = field(default_factory=NetworkSettings)
    sensors: SensorSettings = field(default_factory=SensorSettings)
    actuators: ActuatorSettings = field(default_factory=ActuatorSettings)
    plcs: PLCSettings = field(default_factory=PLCSettings)
    plc_backends: PLCBackends = field(default_factory=PLCBackends)
    gcs: GCSSettings = field(default_factory=GCSSettings)


class HardwareConfigManager(Mindtrace):
    """
    Hardware configuration manager for Mindtrace project.

    Manages hardware configuration from multiple sources including environment
    variables, JSON files, and default values. Provides a unified interface
    for accessing hardware settings across the application.

    Attributes:
        config_file: Path to the configuration file
        _config: Internal configuration data structure
    """

    def __init__(self, config_file: Optional[str] = None, **kwargs):
        """
        Initialize hardware configuration manager.

        Args:
            config_file: Path to configuration file (uses environment variable or default if None)
        """
        super().__init__(**kwargs)
        self.config_file = config_file or os.getenv("MINDTRACE_HW_CONFIG", "hardware_config.json")
        self._config = HardwareConfig()
        self.logger.info(f"hardware_config_manager_initialized file={self.config_file}")
        self._load_config()

    def _load_config(self):
        """Load configuration from environment variables and config file."""
        self.logger.debug(f"hardware_config_load_start file={self.config_file}")
        self._load_from_env()

        if os.path.exists(Path(self.config_file).expanduser()):
            try:
                self._load_from_file(str(Path(self.config_file).expanduser()))
                self.logger.debug(f"hardware_config_loaded source=file file={self.config_file}")
            except Exception as e:
                self.logger.warning(f"hardware_config_load_failed source=file file={self.config_file} error={e}")
        else:
            self.logger.info(f"hardware_config_file_not_found file={self.config_file} Using default configuration.")

    def _load_from_env(self):
        """Load configuration from environment variables with MINDTRACE_HW_ prefix."""
        # Camera settings
        if env_val := os.getenv("MINDTRACE_HW_CAMERA_IMAGE_QUALITY"):
            self._config.cameras.image_quality_enhancement = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_RETRY_COUNT"):
            try:
                self._config.cameras.retrieve_retry_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE"):
            try:
                self._config.cameras.exposure_time = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_WHITE_BALANCE"):
            self._config.cameras.white_balance = env_val

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_TIMEOUT"):
            try:
                self._config.cameras.timeout_ms = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_OPENCV_WIDTH"):
            try:
                self._config.cameras.opencv_default_width = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_OPENCV_HEIGHT"):
            try:
                self._config.cameras.opencv_default_height = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_OPENCV_FPS"):
            try:
                self._config.cameras.opencv_default_fps = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_OPENCV_EXPOSURE"):
            try:
                self._config.cameras.opencv_default_exposure = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_TIMEOUT_MS"):
            try:
                self._config.cameras.timeout_ms = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_MAX_INDEX"):
            try:
                self._config.cameras.max_camera_index = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_MOCK_COUNT"):
            try:
                self._config.cameras.mock_camera_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_ENHANCEMENT_GAMMA"):
            try:
                self._config.cameras.enhancement_gamma = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_ENHANCEMENT_CONTRAST"):
            try:
                self._config.cameras.enhancement_contrast = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # Basler-specific settings
        if env_val := os.getenv("MINDTRACE_HW_CAMERA_PIXEL_FORMAT"):
            self._config.cameras.pixel_format = str(env_val)

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BUFFER_COUNT"):
            try:
                self._config.cameras.buffer_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # Basler multicast settings
        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BASLER_MULTICAST_ENABLED"):
            self._config.cameras.basler_multicast_enabled = env_val.lower() == "false"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BASLER_MULTICAST_GROUP"):
            self._config.cameras.basler_multicast_group = env_val

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BASLER_MULTICAST_PORT"):
            try:
                self._config.cameras.basler_multicast_port = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BASLER_TARGET_IPS"):
            # Parse comma-separated list of IPs
            self._config.cameras.basler_target_ips = [ip.strip() for ip in env_val.split(",") if ip.strip()]

        # Network bandwidth management
        if env_val := os.getenv("MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES"):
            try:
                self._config.cameras.max_concurrent_captures = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # Camera backends
        if env_val := os.getenv("MINDTRACE_HW_CAMERA_BASLER_ENABLED"):
            self._config.backends.basler_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_OPENCV_ENABLED"):
            self._config.backends.opencv_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_GENICAM_ENABLED"):
            self._config.backends.genicam_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_MOCK_ENABLED"):
            self._config.backends.mock_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_CAMERA_DISCOVERY_TIMEOUT"):
            try:
                self._config.backends.discovery_timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # Path settings
        if env_val := os.getenv("MINDTRACE_HW_PATHS_LIB_DIR"):
            self._config.paths.lib_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_BIN_DIR"):
            self._config.paths.bin_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_INCLUDE_DIR"):
            self._config.paths.include_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_SHARE_DIR"):
            self._config.paths.share_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_CACHE_DIR"):
            self._config.paths.cache_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_LOG_DIR"):
            self._config.paths.log_dir = env_val

        if env_val := os.getenv("MINDTRACE_HW_PATHS_CONFIG_DIR"):
            self._config.paths.config_dir = env_val

        # Network settings
        if env_val := os.getenv("MINDTRACE_HW_NETWORK_CAMERA_IP_RANGE"):
            self._config.network.camera_ip_range = env_val

        if env_val := os.getenv("MINDTRACE_HW_NETWORK_FIREWALL_RULE_NAME"):
            self._config.network.firewall_rule_name = env_val

        if env_val := os.getenv("MINDTRACE_HW_NETWORK_INTERFACE"):
            self._config.network.network_interface = env_val

        if env_val := os.getenv("MINDTRACE_HW_NETWORK_JUMBO_FRAMES_ENABLED"):
            self._config.network.jumbo_frames_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_NETWORK_MULTICAST_ENABLED"):
            self._config.network.multicast_enabled = env_val.lower() == "true"

        # Sensor settings
        if env_val := os.getenv("MINDTRACE_HW_SENSOR_AUTO_DISCOVERY"):
            self._config.sensors.auto_discovery = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_SENSOR_POLLING_INTERVAL"):
            try:
                self._config.sensors.polling_interval = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_SENSOR_TIMEOUT"):
            try:
                self._config.sensors.timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_SENSOR_RETRY_COUNT"):
            try:
                self._config.sensors.retry_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # Actuator settings
        if env_val := os.getenv("MINDTRACE_HW_ACTUATOR_AUTO_DISCOVERY"):
            self._config.actuators.auto_discovery = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_ACTUATOR_DEFAULT_SPEED"):
            try:
                self._config.actuators.default_speed = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_ACTUATOR_TIMEOUT"):
            try:
                self._config.actuators.timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_ACTUATOR_RETRY_COUNT"):
            try:
                self._config.actuators.retry_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # PLC settings
        if env_val := os.getenv("MINDTRACE_HW_PLC_AUTO_DISCOVERY"):
            self._config.plcs.auto_discovery = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_PLC_CONNECTION_TIMEOUT"):
            try:
                self._config.plcs.connection_timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_READ_TIMEOUT"):
            try:
                self._config.plcs.read_timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_WRITE_TIMEOUT"):
            try:
                self._config.plcs.write_timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_RETRY_COUNT"):
            try:
                self._config.plcs.retry_count = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # PLC backends
        if env_val := os.getenv("MINDTRACE_HW_PLC_ALLEN_BRADLEY_ENABLED"):
            self._config.plc_backends.allen_bradley_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_PLC_SIEMENS_ENABLED"):
            self._config.plc_backends.siemens_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_PLC_MODBUS_ENABLED"):
            self._config.plc_backends.modbus_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_PLC_MOCK_ENABLED"):
            self._config.plc_backends.mock_enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_PLC_DISCOVERY_TIMEOUT"):
            try:
                self._config.plc_backends.discovery_timeout = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_RETRY_DELAY"):
            try:
                self._config.plcs.retry_delay = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_MAX_CONCURRENT_CONNECTIONS"):
            try:
                self._config.plc_backends.max_concurrent_connections = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_KEEP_ALIVE_INTERVAL"):
            try:
                self._config.plc_backends.keep_alive_interval = float(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_RECONNECT_ATTEMPTS"):
            try:
                self._config.plc_backends.reconnect_attempts = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        if env_val := os.getenv("MINDTRACE_HW_PLC_DEFAULT_SCAN_RATE"):
            try:
                self._config.plc_backends.default_scan_rate = int(env_val)
            except ValueError:
                pass  # Keep default value on invalid input

        # GCS settings
        if env_val := os.getenv("MINDTRACE_HW_GCS_ENABLED"):
            self._config.gcs.enabled = env_val.lower() == "true"

        if env_val := os.getenv("MINDTRACE_HW_GCS_BUCKET_NAME"):
            self._config.gcs.bucket_name = env_val

        if env_val := os.getenv("MINDTRACE_HW_GCS_CREDENTIALS_PATH"):
            self._config.gcs.credentials_path = env_val

        if env_val := os.getenv("MINDTRACE_HW_GCS_AUTO_UPLOAD"):
            self._config.gcs.auto_upload = env_val.lower() == "true"

    def _load_from_file(self, config_file: str):
        """
        Load configuration from JSON file.

        Args:
            config_file: Path to JSON configuration file
        """
        self.logger.debug(f"hardware_config_file_load_start file={config_file}")
        with open(config_file, "r") as f:
            config_data = json.load(f)
        self.logger.debug(f"hardware_config_file_parsed file={config_file}")

        sections = (
            ("cameras", self._config.cameras),
            ("backends", self._config.backends),
            ("paths", self._config.paths),
            ("network", self._config.network),
            ("sensors", self._config.sensors),
            ("actuators", self._config.actuators),
            ("plcs", self._config.plcs),
            ("plc_backends", self._config.plc_backends),
            ("gcs", self._config.gcs),
        )

        for section_name, target in sections:
            section_data = config_data.get(section_name)
            if isinstance(section_data, dict):
                self.logger.debug(
                    f"hardware_config_section_merge section={section_name} keys={list(section_data.keys())}"
                )
                for key, value in section_data.items():
                    if hasattr(target, key):
                        setattr(target, key, value)
        self.logger.debug(f"hardware_config_file_load_complete file={config_file}")

    def save_to_file(self, config_file: Optional[str] = None):
        """
        Save current configuration to JSON file.

        Args:
            config_file: Path to save configuration file (uses default if None)
        """
        file_path = config_file or self.config_file
        config_dict = asdict(self._config)

        Path(file_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

        with open(Path(file_path).expanduser(), "w") as f:
            json.dump(config_dict, f, indent=2)

        self.logger.debug(f"hardware_config_saved file={file_path}")

    def get_config(self) -> HardwareConfig:
        """
        Get current hardware configuration.

        Returns:
            Current hardware configuration object
        """
        return self._config

    def __getitem__(self, key):
        """
        Allow dictionary-style access to configuration.

        Args:
            key: Configuration section key ("cameras", "backends", "sensors", "actuators", "plcs", "plc_backends")

        Returns:
            Configuration section as dictionary
        """
        if key == "cameras":
            return asdict(self._config.cameras)
        elif key == "backends":
            return asdict(self._config.backends)
        elif key == "paths":
            return asdict(self._config.paths)
        elif key == "network":
            return asdict(self._config.network)
        elif key == "sensors":
            return asdict(self._config.sensors)
        elif key == "actuators":
            return asdict(self._config.actuators)
        elif key == "plcs":
            return asdict(self._config.plcs)
        elif key == "plc_backends":
            return asdict(self._config.plc_backends)
        elif key == "gcs":
            return asdict(self._config.gcs)
        else:
            return getattr(self._config, key, None)


_hardware_config_instance: Optional[HardwareConfigManager] = None


def get_hardware_config() -> HardwareConfigManager:
    """
    Get the global hardware configuration instance.

    Returns:
        Global hardware configuration manager instance
    """
    global _hardware_config_instance
    if _hardware_config_instance is None:
        _hardware_config_instance = HardwareConfigManager()
    return _hardware_config_instance


# Backward compatibility aliases for camera-specific access
def get_camera_config() -> HardwareConfigManager:
    """
    Get camera configuration (backward compatibility alias).

    Returns:
        Hardware configuration manager instance
    """
    return get_hardware_config()
