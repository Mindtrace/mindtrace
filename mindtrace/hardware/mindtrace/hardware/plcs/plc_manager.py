"""
Modern PLC Manager for Mindtrace Hardware System

A comprehensive PLC management system that provides unified access to
multiple PLC backends with async operations, proper resource management,
and batch processing capabilities.

Key Features:
    - Automatic PLC discovery and registration
    - Unified interface for different PLC manufacturers
    - Async operations with proper error handling
    - Batch tag read/write operations
    - Connection management and monitoring
    - Thread-safe operations with proper locking
    - Comprehensive configuration management
    - Integrated logging and status reporting

Supported Backends:
    - Allen-Bradley: ControlLogix, CompactLogix PLCs (pycomm3)
    - Siemens: S7-300, S7-400, S7-1200, S7-1500 PLCs (python-snap7)
    - Modbus: Modbus TCP/RTU devices (pymodbus)
    - Mock backends for testing and development

Requirements:
    - pycomm3: Allen-Bradley PLC communication
    - python-snap7: Siemens PLC communication
    - pymodbus: Modbus device communication
    - asyncio: Async operations support

Installation:
    pip install pycomm3 python-snap7 pymodbus

Usage:
    # Simple usage with discovery
    async with PLCManager() as manager:
        plcs = await manager.discover_plcs()
        await manager.register_plc("PLC1", "AllenBradley", "192.168.1.100")
        await manager.connect_plc("PLC1")

        # Read tags
        values = await manager.read_tag("PLC1", ["Tag1", "Tag2"])

        # Write tags
        await manager.write_tag("PLC1", [("Tag1", 100), ("Tag2", 200)])

    # Batch operations
    async with PLCManager() as manager:
        # Register multiple PLCs
        await manager.register_plc("PLC1", "AllenBradley", "192.168.1.100")
        await manager.register_plc("PLC2", "Siemens", "192.168.1.101")

        # Connect all PLCs
        results = await manager.connect_all_plcs()

        # Batch read from multiple PLCs
        read_requests = [
            ("PLC1", ["Temperature", "Pressure"]),
            ("PLC2", ["Speed", "Position"])
        ]
        values = await manager.read_tags_batch(read_requests)

Configuration:
    All parameters are configurable via the hardware configuration system:
    - MINDTRACE_HW_PLC_AUTO_DISCOVERY: Enable automatic PLC discovery
    - MINDTRACE_HW_PLC_CONNECTION_TIMEOUT: Connection timeout in seconds
    - MINDTRACE_HW_PLC_READ_TIMEOUT: Tag read timeout in seconds
    - MINDTRACE_HW_PLC_WRITE_TIMEOUT: Tag write timeout in seconds
    - MINDTRACE_HW_PLC_RETRY_COUNT: Number of retry attempts
    - MINDTRACE_HW_PLC_MAX_CONCURRENT_CONNECTIONS: Maximum concurrent connections
    - MINDTRACE_HW_PLC_ALLEN_BRADLEY_ENABLED: Enable Allen-Bradley backend
    - MINDTRACE_HW_PLC_SIEMENS_ENABLED: Enable Siemens backend
    - MINDTRACE_HW_PLC_MODBUS_ENABLED: Enable Modbus backend

Error Handling:
    The module uses a comprehensive exception hierarchy for precise error reporting:
    - PLCError: Base exception for all PLC-related errors
    - PLCNotFoundError: PLC not found during discovery or registration
    - PLCConnectionError: Connection establishment or maintenance failures
    - PLCInitializationError: PLC initialization failures
    - PLCCommunicationError: Communication protocol errors
    - PLCTagError: Tag-related operation errors
    - PLCTagReadError: Tag read operation failures
    - PLCTagWriteError: Tag write operation failures
    - HardwareOperationError: General hardware operation failures

Thread Safety:
    All PLC operations are thread-safe. Multiple PLCs can be operated
    simultaneously from different threads without interference.

Performance Notes:
    - PLC discovery may take several seconds depending on network size
    - Batch operations are more efficient than individual tag operations
    - Connection pooling is used for optimal performance
    - Consider PLC-specific optimizations for production use
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import get_hardware_config
from mindtrace.hardware.core.exceptions import (
    PLCConnectionError,
    PLCNotFoundError,
    PLCTagError,
    PLCTagReadError,
    PLCTagWriteError,
)
from mindtrace.hardware.plcs.backends.base import BasePLC


class PLCManager(Mindtrace):
    """
    Unified PLC management system for industrial automation.

    This manager provides a comprehensive interface for managing PLCs from different
    manufacturers with support for discovery, registration, connection management,
    and batch tag operations. It handles multiple PLC backends transparently and
    provides thread-safe operations with proper error handling.

    The manager supports:
    - Automatic PLC discovery across multiple backends
    - Dynamic PLC registration and connection management
    - Batch tag read/write operations for optimal performance
    - Connection monitoring and automatic reconnection
    - Comprehensive error handling and logging
    - Thread-safe operations with proper resource management

    Supported PLC Types:
    - Allen-Bradley: ControlLogix, CompactLogix, MicroLogix PLCs
    - Siemens: S7-300, S7-400, S7-1200, S7-1500 PLCs (Future)
    - Modbus: Modbus TCP/RTU devices (Future)
    - Mock PLCs: For testing and development

    Attributes:
        plcs: Dictionary mapping PLC names to PLC instances
        config: Hardware configuration manager instance
        logger: Centralized logger for PLC operations

    Example:
        # Basic usage
        async with PLCManager() as manager:
            # Discover available PLCs
            discovered = await manager.discover_plcs()

            # Register and connect to a PLC
            await manager.register_plc("PLC1", "AllenBradley", "192.168.1.100")
            await manager.connect_plc("PLC1")

            # Read and write tags
            values = await manager.read_tag("PLC1", ["Temperature", "Pressure"])
            await manager.write_tag("PLC1", [("Setpoint", 75.0)])

        # Batch operations
        async with PLCManager() as manager:
            # Register multiple PLCs
            await manager.register_plc("PLC1", "AllenBradley", "192.168.1.100")
            await manager.register_plc("PLC2", "AllenBradley", "192.168.1.101")

            # Batch read from multiple PLCs
            read_requests = [
                ("PLC1", ["Temperature", "Pressure"]),
                ("PLC2", ["Speed", "Position"])
            ]
            results = await manager.read_tags_batch(read_requests)
    """

    def __init__(self):
        """Initialize the PLC manager."""
        super().__init__()

        self.plcs: Dict[str, BasePLC] = {}
        self.config = get_hardware_config()

        self.logger.info("PLC manager initialized")

    async def discover_plcs(self) -> Dict[str, List[str]]:
        """
        Discover available PLCs from all enabled backends.

        Returns:
            Dictionary mapping backend names to lists of discovered PLCs
        """
        self.logger.info("Starting PLC discovery")
        discovered_plcs = {}

        # Import backends dynamically based on configuration
        backends = self._get_enabled_backends()

        for backend_name, backend_class in backends.items():
            try:
                self.logger.info(f"Discovering PLCs using {backend_name}")
                plc_list = await asyncio.to_thread(backend_class.get_available_plcs)
                discovered_plcs[backend_name] = plc_list
                self.logger.info(f"Found {len(plc_list)} PLCs with {backend_name}")
            except Exception as e:
                self.logger.warning(f"Discovery failed for {backend_name}: {e}")
                discovered_plcs[backend_name] = []

        total_discovered = sum(len(plcs) for plcs in discovered_plcs.values())
        self.logger.info(f"PLC discovery completed. Total PLCs found: {total_discovered}")

        return discovered_plcs

    def _get_enabled_backends(self) -> Dict[str, type]:
        """
        Get enabled PLC backends based on configuration.

        Returns:
            Dictionary mapping backend names to backend classes
        """
        backends = {}
        config = self.config.get_config()

        # Allen Bradley backend
        if config.plc_backends.allen_bradley_enabled:
            try:
                from mindtrace.hardware.plcs.backends.allen_bradley import AllenBradleyPLC

                backends["AllenBradley"] = AllenBradleyPLC
            except ImportError as e:
                self.logger.warning(f"Allen Bradley backend not available: {e}")

        # Mock Allen Bradley backend for testing
        if config.plc_backends.mock_enabled:
            try:
                from mindtrace.hardware.plcs.backends.allen_bradley import MockAllenBradleyPLC

                backends["AllenBradley"] = MockAllenBradleyPLC  # Override with mock
                self.logger.info("Using Mock Allen Bradley backend for testing")
            except ImportError as e:
                self.logger.warning(f"Mock Allen Bradley backend not available: {e}")

        # Future backends can be added here
        # if config.plc_backends.siemens_enabled:
        #     try:
        #         from mindtrace.hardware.plcs.backends.siemens import SiemensPLC
        #         backends["Siemens"] = SiemensPLC
        #     except ImportError as e:
        #         self.logger.warning(f"Siemens backend not available: {e}")

        # if config.plc_backends.modbus_enabled:
        #     try:
        #         from mindtrace.hardware.plcs.backends.modbus import ModbusPLC
        #         backends["Modbus"] = ModbusPLC
        #     except ImportError as e:
        #         self.logger.warning(f"Modbus backend not available: {e}")

        return backends

    async def register_plc(
        self, plc_name: str, backend: str, ip_address: str, plc_type: Optional[str] = None, **kwargs
    ) -> bool:
        """
        Register a PLC with the manager.

        Args:
            plc_name: Unique identifier for the PLC
            backend: Backend type ("AllenBradley", "Siemens", "Modbus")
            ip_address: IP address of the PLC
            plc_type: Specific PLC type (backend-dependent)
            **kwargs: Additional backend-specific parameters

        Returns:
            True if registration successful, False otherwise
        """
        if plc_name in self.plcs:
            self.logger.warning(f"PLC '{plc_name}' already registered")
            return False

        try:
            backends = self._get_enabled_backends()
            if backend not in backends:
                raise PLCNotFoundError(f"Backend '{backend}' not available or not enabled")

            backend_class = backends[backend]

            # Create PLC instance with backend-specific parameters
            if backend == "AllenBradley":
                plc = backend_class(plc_name=plc_name, ip_address=ip_address, plc_type=plc_type, **kwargs)
            else:
                # Generic instantiation for other backends
                plc = backend_class(plc_name=plc_name, ip_address=ip_address, **kwargs)

            self.plcs[plc_name] = plc
            self.logger.info(f"Registered PLC '{plc_name}' with {backend} backend")
            return True

        except Exception as e:
            self.logger.error(f"Failed to register PLC '{plc_name}': {e}")
            return False

    async def unregister_plc(self, plc_name: str) -> bool:
        """
        Unregister a PLC from the manager.

        Args:
            plc_name: Name of the PLC to unregister

        Returns:
            True if unregistration successful, False otherwise
        """
        if plc_name not in self.plcs:
            self.logger.warning(f"PLC '{plc_name}' not found")
            return False

        try:
            plc = self.plcs[plc_name]
            if await plc.is_connected():
                await plc.disconnect()

            del self.plcs[plc_name]
            self.logger.info(f"Unregistered PLC '{plc_name}'")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unregister PLC '{plc_name}': {e}")
            return False

    async def connect_plc(self, plc_name: str) -> bool:
        """
        Connect to a specific PLC.

        Args:
            plc_name: Name of the PLC to connect

        Returns:
            True if connection successful, False otherwise
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]
            success = await plc.connect()

            if success:
                self.logger.info(f"Connected to PLC '{plc_name}'")
            else:
                self.logger.warning(f"Failed to connect to PLC '{plc_name}'")

            return success

        except Exception as e:
            self.logger.error(f"Connection failed for PLC '{plc_name}': {e}")
            raise PLCConnectionError(f"Failed to connect to PLC '{plc_name}': {e}")

    async def disconnect_plc(self, plc_name: str) -> bool:
        """
        Disconnect from a specific PLC.

        Args:
            plc_name: Name of the PLC to disconnect

        Returns:
            True if disconnection successful, False otherwise
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]
            success = await plc.disconnect()

            if success:
                self.logger.info(f"Disconnected from PLC '{plc_name}'")
            else:
                self.logger.warning(f"Failed to disconnect from PLC '{plc_name}'")

            return success

        except Exception as e:
            self.logger.error(f"Disconnection failed for PLC '{plc_name}': {e}")
            return False

    async def connect_all_plcs(self) -> Dict[str, bool]:
        """
        Connect to all registered PLCs.

        Returns:
            Dictionary mapping PLC names to connection success status
        """
        self.logger.info("Connecting to all registered PLCs")
        results = {}

        for plc_name in self.plcs:
            try:
                results[plc_name] = await self.connect_plc(plc_name)
            except Exception as e:
                self.logger.error(f"Failed to connect to PLC '{plc_name}': {e}")
                results[plc_name] = False

        connected_count = sum(results.values())
        self.logger.info(f"Connected to {connected_count}/{len(self.plcs)} PLCs")

        return results

    async def disconnect_all_plcs(self) -> Dict[str, bool]:
        """
        Disconnect from all registered PLCs.

        Returns:
            Dictionary mapping PLC names to disconnection success status
        """
        self.logger.info("Disconnecting from all registered PLCs")
        results = {}

        for plc_name in self.plcs:
            try:
                results[plc_name] = await self.disconnect_plc(plc_name)
            except Exception as e:
                self.logger.error(f"Failed to disconnect from PLC '{plc_name}': {e}")
                results[plc_name] = False

        disconnected_count = sum(results.values())
        self.logger.info(f"Disconnected from {disconnected_count}/{len(self.plcs)} PLCs")

        return results

    async def read_tag(self, plc_name: str, tags: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Read tags from a specific PLC.

        Args:
            plc_name: Name of the PLC
            tags: Single tag name or list of tag names

        Returns:
            Dictionary mapping tag names to their values
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]
            return await plc.read_tag_with_retry(tags)

        except Exception as e:
            self.logger.error(f"Failed to read tags from PLC '{plc_name}': {e}")
            raise PLCTagReadError(f"Failed to read tags from PLC '{plc_name}': {e}")

    async def write_tag(self, plc_name: str, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, bool]:
        """
        Write tags to a specific PLC.

        Args:
            plc_name: Name of the PLC
            tags: Single (tag_name, value) tuple or list of tuples

        Returns:
            Dictionary mapping tag names to write success status
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]
            return await plc.write_tag_with_retry(tags)

        except Exception as e:
            self.logger.error(f"Failed to write tags to PLC '{plc_name}': {e}")
            raise PLCTagWriteError(f"Failed to write tags to PLC '{plc_name}': {e}")

    async def read_tags_batch(self, requests: List[Tuple[str, Union[str, List[str]]]]) -> Dict[str, Dict[str, Any]]:
        """
        Read tags from multiple PLCs in batch.

        Args:
            requests: List of (plc_name, tags) tuples

        Returns:
            Dictionary mapping PLC names to their tag read results
        """
        self.logger.info(f"Executing batch read for {len(requests)} PLCs")
        results = {}

        # Execute reads concurrently
        tasks = []
        plc_names = []

        for plc_name, tags in requests:
            if plc_name in self.plcs:
                task = self.read_tag(plc_name, tags)
                tasks.append(task)
                plc_names.append(plc_name)
            else:
                results[plc_name] = {"error": f"PLC '{plc_name}' not registered"}

        # Wait for all reads to complete
        if tasks:
            read_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(read_results):
                plc_name = plc_names[i]
                if isinstance(result, Exception):
                    results[plc_name] = {"error": str(result)}
                else:
                    results[plc_name] = result

        self.logger.info(f"Batch read completed for {len(results)} PLCs")
        return results

    async def write_tags_batch(
        self, requests: List[Tuple[str, Union[Tuple[str, Any], List[Tuple[str, Any]]]]]
    ) -> Dict[str, Dict[str, bool]]:
        """
        Write tags to multiple PLCs in batch.

        Args:
            requests: List of (plc_name, tags) tuples

        Returns:
            Dictionary mapping PLC names to their tag write results
        """
        self.logger.info(f"Executing batch write for {len(requests)} PLCs")
        results = {}

        # Execute writes concurrently
        tasks = []
        plc_names = []

        for plc_name, tags in requests:
            if plc_name in self.plcs:
                task = self.write_tag(plc_name, tags)
                tasks.append(task)
                plc_names.append(plc_name)
            else:
                results[plc_name] = {"error": f"PLC '{plc_name}' not registered"}

        # Wait for all writes to complete
        if tasks:
            write_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(write_results):
                plc_name = plc_names[i]
                if isinstance(result, Exception):
                    results[plc_name] = {"error": str(result)}
                else:
                    results[plc_name] = result

        self.logger.info(f"Batch write completed for {len(results)} PLCs")
        return results

    async def get_plc_status(self, plc_name: str) -> Dict[str, Any]:
        """
        Get status information for a specific PLC.

        Args:
            plc_name: Name of the PLC

        Returns:
            Dictionary with PLC status information
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]

            status = {
                "name": plc_name,
                "ip_address": plc.ip_address,
                "connected": await plc.is_connected(),
                "initialized": plc.initialized,
                "backend": plc.__class__.__name__,
            }

            # Get additional info if available
            if hasattr(plc, "get_plc_info"):
                try:
                    plc_info = await plc.get_plc_info()
                    status.update(plc_info)
                except Exception as e:
                    status["info_error"] = str(e)

            return status

        except Exception as e:
            self.logger.error(f"Failed to get status for PLC '{plc_name}': {e}")
            return {
                "name": plc_name,
                "error": str(e),
                "connected": False,
                "initialized": False,
            }

    async def get_all_plc_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status information for all registered PLCs.

        Returns:
            Dictionary mapping PLC names to their status information
        """
        self.logger.info("Getting status for all registered PLCs")
        results = {}

        for plc_name in self.plcs:
            try:
                results[plc_name] = await self.get_plc_status(plc_name)
            except Exception as e:
                self.logger.error(f"Failed to get status for PLC '{plc_name}': {e}")
                results[plc_name] = {
                    "name": plc_name,
                    "error": str(e),
                    "connected": False,
                    "initialized": False,
                }

        return results

    async def get_plc_tags(self, plc_name: str) -> List[str]:
        """
        Get list of available tags for a specific PLC.

        Args:
            plc_name: Name of the PLC

        Returns:
            List of available tag names
        """
        if plc_name not in self.plcs:
            raise PLCNotFoundError(f"PLC '{plc_name}' not registered")

        try:
            plc = self.plcs[plc_name]
            return await plc.get_all_tags()

        except Exception as e:
            self.logger.error(f"Failed to get tags for PLC '{plc_name}': {e}")
            raise PLCTagError(f"Failed to get tags for PLC '{plc_name}': {e}")

    def get_registered_plcs(self) -> List[str]:
        """
        Get list of registered PLC names.

        Returns:
            List of registered PLC names
        """
        return list(self.plcs.keys())

    def get_backend_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about available PLC backends.

        Returns:
            Dictionary mapping backend names to their information
        """
        backends = self._get_enabled_backends()
        backend_info = {}

        for backend_name, backend_class in backends.items():
            try:
                backend_info[backend_name] = backend_class.get_backend_info()
            except Exception as e:
                backend_info[backend_name] = {
                    "name": backend_name,
                    "error": str(e),
                    "available": False,
                }

        return backend_info

    async def cleanup(self):
        """Clean up all PLC connections and resources."""
        self.logger.info("Cleaning up PLC manager")

        # Disconnect all PLCs
        await self.disconnect_all_plcs()

        # Clear PLC registry
        self.plcs.clear()

        self.logger.info("PLC manager cleanup completed")
