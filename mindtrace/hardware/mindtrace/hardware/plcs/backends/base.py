"""
Abstract base classes for PLC implementations.

This module defines the interface that all PLC backends must implement,
providing a consistent API for PLC operations across different manufacturers
and communication protocols.

Features:
    - Abstract base class with comprehensive async PLC interface
    - Consistent async pattern matching camera backends
    - Type-safe method signatures with full type hints
    - Configuration system integration
    - Resource management and cleanup
    - Default implementations for optional features
    - Standardized constructor signature across all backends
    - Retry logic with exponential backoff
    - Connection management and monitoring

Usage:
    This is an abstract base class and cannot be instantiated directly.
    PLC backends should inherit from BasePLC and implement all
    abstract methods.

Example:
    class MyPLCBackend(BasePLC):
        async def initialize(self) -> Tuple[bool, Any, Any]:
            # Implementation here
            pass

        async def connect(self) -> bool:
            # Implementation here
            pass

        async def read_tag(self, tags: Union[str, List[str]]) -> Dict[str, Any]:
            # Implementation here
            pass

        # ... implement other abstract methods

Backend Requirements:
    All PLC backends must implement the following abstract methods:
    - initialize(): Establish initial connection and setup
    - connect(): Connect to the PLC
    - disconnect(): Disconnect from the PLC
    - is_connected(): Check connection status
    - read_tag(): Read tag values from PLC
    - write_tag(): Write tag values to PLC
    - get_all_tags(): List all available tags
    - get_tag_info(): Get detailed tag information
    - get_available_plcs(): Static method for PLC discovery
    - get_backend_info(): Static method for backend information

Error Handling:
    Backends should raise appropriate exceptions from the PLC exception hierarchy:
    - PLCError: Base exception for all PLC-related errors
    - PLCNotFoundError: PLC not found during discovery
    - PLCConnectionError: Connection establishment or maintenance failures
    - PLCInitializationError: PLC initialization failures
    - PLCCommunicationError: Communication protocol errors
    - PLCTagError: Tag-related operation errors
    - PLCTimeoutError: Operation timeout errors
    - PLCConfigurationError: Configuration-related errors
"""

import asyncio
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.config import get_hardware_config
from mindtrace.hardware.core.exceptions import (
    PLCTagError,
)


class BasePLC(MindtraceABC):
    """
    Abstract base class for PLC implementations.

    This class defines the interface that all PLC backends must implement
    to ensure consistent behavior across different manufacturers and protocols.

    Attributes:
        plc_name: Unique identifier for the PLC instance
        plc_config_file: Path to PLC-specific configuration file
        ip_address: IP address of the PLC
        connection_timeout: Connection timeout in seconds
        read_timeout: Tag read timeout in seconds
        write_timeout: Tag write timeout in seconds
        retry_count: Number of retry attempts for operations
        retry_delay: Delay between retry attempts in seconds
        plc: The underlying PLC connection object
        device_manager: Device-specific manager instance
        initialized: Whether the PLC has been initialized
    """

    def __init__(
        self,
        plc_name: str,
        ip_address: str,
        plc_config_file: Optional[str] = None,
        connection_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        retry_count: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ):
        """
        Initialize the PLC instance.

        Args:
            plc_name: Unique identifier for the PLC
            ip_address: IP address of the PLC
            plc_config_file: Path to PLC configuration file
            connection_timeout: Connection timeout in seconds
            read_timeout: Tag read timeout in seconds
            write_timeout: Tag write timeout in seconds
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        super().__init__()

        self.plc_name = plc_name
        self.ip_address = ip_address
        self.plc_config_file = plc_config_file

        config = get_hardware_config().get_config()

        self.connection_timeout = connection_timeout or config.plcs.connection_timeout
        self.read_timeout = read_timeout or config.plcs.read_timeout
        self.write_timeout = write_timeout or config.plcs.write_timeout
        self.retry_count = retry_count or config.plcs.retry_count
        self.retry_delay = retry_delay or config.plcs.retry_delay

        self.plc = None
        self.device_manager = None
        self.initialized = False

        self._setup_plc_logger_formatting()

        self.logger.info(
            f"PLC base initialized: plc_name={self.plc_name}, "
            f"ip_address={self.ip_address}, "
            f"connection_timeout={self.connection_timeout}s"
        )

    def _setup_plc_logger_formatting(self):
        """
        Setup PLC-specific logger formatting.

        This provides consistent formatting for all PLC-related log messages,
        following the same pattern as camera implementations.
        """
        import logging

        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            formatter = logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(formatter)

            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)

        self.logger.propagate = False

    @abstractmethod
    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the PLC connection.

        Returns:
            Tuple of (success, plc_object, device_manager)
        """
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the PLC.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the PLC.

        Returns:
            True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if PLC is currently connected.

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    async def read_tag(self, tags: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Read values from PLC tags.

        Args:
            tags: Single tag name or list of tag names

        Returns:
            Dictionary mapping tag names to their values
        """
        pass

    @abstractmethod
    async def write_tag(self, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, bool]:
        """
        Write values to PLC tags.

        Args:
            tags: Single (tag_name, value) tuple or list of tuples

        Returns:
            Dictionary mapping tag names to write success status
        """
        pass

    @abstractmethod
    async def get_all_tags(self) -> List[str]:
        """
        Get list of all available tags on the PLC.

        Returns:
            List of tag names
        """
        pass

    @abstractmethod
    async def get_tag_info(self, tag_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific tag.

        Args:
            tag_name: Name of the tag

        Returns:
            Dictionary with tag information (type, description, etc.)
        """
        pass

    @staticmethod
    @abstractmethod
    def get_available_plcs() -> List[str]:
        """
        Discover available PLCs for this backend.

        Returns:
            List of PLC identifiers in format "Backend:Identifier"
        """
        pass

    @staticmethod
    @abstractmethod
    def get_backend_info() -> Dict[str, Any]:
        """
        Get information about this PLC backend.

        Returns:
            Dictionary with backend information
        """
        pass

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the PLC.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            await self.disconnect()
            await asyncio.sleep(self.retry_delay)
            return await self.connect()
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
            return False

    async def read_tag_with_retry(self, tags: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Read tags with retry mechanism.

        Args:
            tags: Single tag name or list of tag names

        Returns:
            Dictionary mapping tag names to their values

        Raises:
            PLCTagError: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(self.retry_count):
            try:
                return await self.read_tag(tags)
            except Exception as e:
                last_exception = e
                self.logger.warning(f"Read attempt {attempt + 1} failed: {e}")

                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                    if not await self.is_connected():
                        await self.reconnect()

        raise PLCTagError(f"Failed to read tags after {self.retry_count} attempts: {last_exception}")

    async def write_tag_with_retry(self, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, bool]:
        """
        Write tags with retry mechanism.

        Args:
            tags: Single (tag_name, value) tuple or list of tuples

        Returns:
            Dictionary mapping tag names to write success status

        Raises:
            PLCTagError: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(self.retry_count):
            try:
                return await self.write_tag(tags)
            except Exception as e:
                last_exception = e
                self.logger.warning(f"Write attempt {attempt + 1} failed: {e}")

                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                    if not await self.is_connected():
                        await self.reconnect()

        raise PLCTagError(f"Failed to write tags after {self.retry_count} attempts: {last_exception}")

    def __str__(self) -> str:
        """String representation of the PLC."""
        return f"{self.__class__.__name__}({self.plc_name}@{self.ip_address})"

    def __repr__(self) -> str:
        """Detailed string representation of the PLC."""
        return (
            f"{self.__class__.__name__}("
            f"plc_name='{self.plc_name}', "
            f"ip_address='{self.ip_address}', "
            f"initialized={self.initialized})"
        )
