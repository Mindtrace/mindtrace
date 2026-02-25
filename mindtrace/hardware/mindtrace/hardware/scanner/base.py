"""AbstractScanner — unified synchronous interface for scanner devices.

Scanner devices encompass barcode / QR-code readers, 3-D structured-light
scanners, laser profilometers, and any other device whose primary output is
a discrete *scan result* rather than a continuous image stream.

All scanner backends in mindtrace-hardware extend this class.  Concrete
implementations must provide :meth:`connect`, :meth:`disconnect`, and
:meth:`scan`.  The context manager protocol wraps those calls automatically.
"""
from __future__ import annotations

import time
import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.exceptions import HardwareOperationError


@dataclass
class ScanResult:
    """The result of a single scan operation.

    Attributes:
        scan_id: Unique identifier for this scan event (UUID4 by default).
        timestamp: Unix epoch seconds at the moment the scan completed.
        data: Scan payload.  For barcode scanners this is typically a
            ``str``; for 3-D scanners it may be a :class:`numpy.ndarray`
            point cloud or a structured dict.
        scanner_type: Human-readable backend identifier (e.g.
            ``"barcode"``, ``"point_cloud"``, ``"mock"``).
        metadata: Arbitrary backend-supplied metadata (e.g. symbology,
            quality score, scan duration, device serial).
    """

    scan_id: str
    timestamp: float
    data: Any
    scanner_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AbstractScanner(MindtraceABC):
    """Unified synchronous interface for scanner devices.

    Subclasses must implement :meth:`connect`, :meth:`disconnect`, and
    :meth:`scan`.  The context manager protocol calls :meth:`connect` on
    entry and :meth:`disconnect` on exit.

    Args:
        scanner_id: Unique identifier for this scanner instance — typically
            a serial number, USB path, or IP address.
        config: Optional dict of backend-specific configuration forwarded
            to the concrete implementation.
    """

    def __init__(
        self,
        scanner_id: str = "scanner-0",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._scanner_id = scanner_id
        self._config: dict[str, Any] = config or {}
        self._scan_counter: int = 0

        self.logger.debug(f"AbstractScanner initialised: scanner_id={scanner_id!r}")

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Open a connection to the scanner device.

        Raises:
            HardwareOperationError: If the device cannot be reached.
            ImportError: If a required third-party SDK is not installed.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Release the scanner connection and free resources.

        Implementations must be idempotent (safe to call when already
        disconnected).
        """

    @abstractmethod
    def scan(self) -> ScanResult:
        """Trigger a single scan and return the result.

        Returns:
            A populated :class:`ScanResult`.

        Raises:
            HardwareOperationError: If the scan cannot be completed.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    @property
    def scanner_id(self) -> str:
        """The scanner_id string passed at construction time."""
        return self._scanner_id

    @staticmethod
    def _new_scan_id() -> str:
        """Generate a unique scan identifier."""
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> AbstractScanner:
        self.logger.debug(
            f"Entering context manager for {self.name} ({self._scanner_id!r})"
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
            f"Exiting context manager for {self.name} ({self._scanner_id!r})"
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
        return f"<{type(self).__name__} scanner_id={self._scanner_id!r}>"
