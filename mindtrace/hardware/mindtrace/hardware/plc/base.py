"""AbstractPLC — unified synchronous interface for PLC / SCADA communication.

All PLC backends in mindtrace-hardware extend this class.  Concrete
implementations must provide :meth:`connect`, :meth:`disconnect`,
:meth:`read`, :meth:`write`, and the :attr:`status` property.

The context manager protocol calls :meth:`connect` on entry and
:meth:`disconnect` on exit.
"""
from __future__ import annotations

import time
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.exceptions import (
    PLCConnectionError,
    PLCTagError,
)


@dataclass
class PLCTag:
    """A single PLC tag value with type and timestamp information.

    Attributes:
        name: Tag address or symbolic name (e.g. ``"Motor1_Speed"`` or
            ``"N7:0"``).
        value: The tag value — type depends on *data_type*.
        data_type: String descriptor for the value type.  Common values:
            ``"bool"``, ``"int16"``, ``"int32"``, ``"float"``, ``"string"``.
        timestamp: Unix epoch seconds at which the value was read.
    """

    name: str
    value: Any
    data_type: str
    timestamp: float


class PLCStatus(str, Enum):
    """Operational state of a PLC connection."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class AbstractPLC(MindtraceABC):
    """Unified synchronous interface for PLC / SCADA communication.

    Subclasses must implement :meth:`connect`, :meth:`disconnect`,
    :meth:`read`, :meth:`write`, and the :attr:`status` property.  The
    convenience methods :meth:`read_many` and :meth:`write_many` delegate
    to the abstract primitives and can be overridden for efficiency.

    Args:
        host: Hostname or IP address of the PLC / OPC-UA server.
        port: TCP port number (default depends on the concrete backend,
            e.g. 4840 for OPC-UA).
        config: Optional dict of backend-specific configuration options.
    """

    def __init__(
        self,
        host: str,
        port: int,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._config: dict[str, Any] = config or {}

        self.logger.debug(
            f"AbstractPLC initialised: host={host!r}, port={port}"
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the PLC.

        Raises:
            PLCConnectionError: If the device is unreachable or the
                handshake fails.
            ImportError: If a required third-party SDK is missing.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Release the PLC connection and free resources.

        Implementations must be safe to call when already disconnected
        (idempotent).
        """

    @abstractmethod
    def read(self, tag: str) -> PLCTag:
        """Read a single tag from the PLC.

        Args:
            tag: Tag address or symbolic name.

        Returns:
            A :class:`PLCTag` populated with the current value.

        Raises:
            PLCConnectionError: If the PLC is not connected.
            PLCTagError: If the tag does not exist or cannot be read.
        """

    @abstractmethod
    def write(self, tag: str, value: Any) -> None:
        """Write a value to a single PLC tag.

        Args:
            tag: Tag address or symbolic name.
            value: Value to write.  Must be compatible with the tag's
                native data type.

        Raises:
            PLCConnectionError: If the PLC is not connected.
            PLCTagError: If the tag does not exist or the write fails.
        """

    @property
    @abstractmethod
    def status(self) -> PLCStatus:
        """Current connection state of the PLC."""

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    @property
    def host(self) -> str:
        """PLC hostname or IP address."""
        return self._host

    @property
    def port(self) -> int:
        """TCP port number used for the connection."""
        return self._port

    def read_many(self, tags: list[str]) -> dict[str, PLCTag]:
        """Read multiple tags and return a mapping of tag name to :class:`PLCTag`.

        The default implementation calls :meth:`read` sequentially.
        Concrete backends may override this method to issue a batch read
        in a single network round-trip.

        Args:
            tags: List of tag addresses or symbolic names.

        Returns:
            Dict mapping each tag name to its :class:`PLCTag` value.

        Raises:
            PLCConnectionError: If the PLC is not connected.
            PLCTagError: If any tag cannot be read.
        """
        result: dict[str, PLCTag] = {}
        for tag in tags:
            result[tag] = self.read(tag)
        return result

    def write_many(self, values: dict[str, Any]) -> None:
        """Write multiple tag values in one call.

        The default implementation calls :meth:`write` sequentially.
        Concrete backends may override this method to issue a batch write.

        Args:
            values: Dict mapping tag addresses to the values to write.

        Raises:
            PLCConnectionError: If the PLC is not connected.
            PLCTagError: If any write fails.
        """
        for tag, value in values.items():
            self.write(tag, value)

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> AbstractPLC:
        self.logger.debug(
            f"Entering context manager for {self.name} ({self._host}:{self._port})"
        )
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        self.logger.debug(
            f"Exiting context manager for {self.name} ({self._host}:{self._port})"
        )
        try:
            self.disconnect()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                f"Non-fatal error during disconnect in __exit__ for {self.name}: {exc}"
            )
        if exc_type is not None:
            self.logger.exception(
                f"Exception propagated through {self.name} context manager",
                exc_info=(exc_type, exc_val, exc_tb),
            )
            return self.suppress
        return False

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} host={self._host!r} port={self._port}"
            f" status={self.status.value!r}>"
        )
