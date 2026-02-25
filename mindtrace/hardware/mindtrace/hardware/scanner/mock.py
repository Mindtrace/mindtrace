"""MockScanner — in-memory scanner for unit tests and CI pipelines.

The mock generates synthetic :class:`~mindtrace.hardware.scanner.base.ScanResult`
objects with incrementing scan IDs and configurable payloads.  No hardware
or third-party SDK is required.

Typical usage::

    from mindtrace.hardware.scanner import MockScanner

    # Default barcode-style mock (returns cycling string payloads)
    with MockScanner() as scanner:
        result = scanner.scan()
        print(result.scan_id, result.data, result.scanner_type)

    # Custom data pool — cycles through provided values:
    with MockScanner(data_pool=["ABC123", "DEF456", "GHI789"]) as scanner:
        for _ in range(6):
            r = scanner.scan()
            print(r.data)   # ABC123 DEF456 GHI789 ABC123 DEF456 GHI789
"""
from __future__ import annotations

import time
from typing import Any

from mindtrace.hardware.scanner.base import AbstractScanner, ScanResult
from mindtrace.hardware.core.exceptions import HardwareOperationError


class MockScanner(AbstractScanner):
    """In-memory scanner that returns configurable synthetic scan results.

    Args:
        scanner_id: Identifier string — defaults to ``"mock-scanner-0"``.
        scanner_type: Value used for :attr:`ScanResult.scanner_type`.
            Defaults to ``"mock"``.
        data_pool: Optional list of payloads to cycle through on each
            :meth:`scan` call.  When ``None`` (default) the scanner
            generates string payloads of the form ``"SCAN-<n>"``.
        metadata_extra: Optional dict of extra key/value pairs to include
            in every :class:`ScanResult`'s metadata.
    """

    def __init__(
        self,
        scanner_id: str = "mock-scanner-0",
        scanner_type: str = "mock",
        data_pool: list[Any] | None = None,
        metadata_extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(scanner_id=scanner_id)
        self._scanner_type = scanner_type
        self._data_pool: list[Any] = list(data_pool) if data_pool else []
        self._pool_index: int = 0
        self._metadata_extra: dict[str, Any] = metadata_extra or {}
        self._connected: bool = False

    # ------------------------------------------------------------------
    # AbstractScanner implementation
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Mark the mock scanner as connected."""
        self._connected = True
        self.logger.info(f"MockScanner {self._scanner_id!r} connected.")

    def disconnect(self) -> None:
        """Mark the mock scanner as disconnected."""
        self._connected = False
        self.logger.info(f"MockScanner {self._scanner_id!r} disconnected.")

    def scan(self) -> ScanResult:
        """Generate and return a synthetic scan result.

        Returns:
            A :class:`~mindtrace.hardware.scanner.base.ScanResult` with
            a unique UUID scan_id, the current timestamp, and either the
            next item from *data_pool* or an auto-generated payload string.

        Raises:
            HardwareOperationError: If :meth:`connect` has not been called.
        """
        if not self._connected:
            raise HardwareOperationError(
                f"MockScanner {self._scanner_id!r} is not connected.  "
                "Call connect() or use as a context manager."
            )

        self._scan_counter += 1
        payload = self._next_payload()

        metadata: dict[str, Any] = {
            "backend": "mock",
            "scanner_id": self._scanner_id,
            "scan_number": self._scan_counter,
        }
        metadata.update(self._metadata_extra)

        result = ScanResult(
            scan_id=self._new_scan_id(),
            timestamp=time.time(),
            data=payload,
            scanner_type=self._scanner_type,
            metadata=metadata,
        )

        self.logger.debug(
            f"MockScanner {self._scanner_id!r}: scan #{self._scan_counter} "
            f"-> {payload!r}"
        )
        return result

    # ------------------------------------------------------------------
    # Mock-specific helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the scan counter and pool index to initial state.

        Useful between test cases to get deterministic scan outputs.
        """
        self._scan_counter = 0
        self._pool_index = 0
        self.logger.debug(f"MockScanner {self._scanner_id!r}: counters reset.")

    def _next_payload(self) -> Any:
        """Return the next data payload, cycling through the pool if set."""
        if self._data_pool:
            payload = self._data_pool[self._pool_index % len(self._data_pool)]
            self._pool_index += 1
            return payload
        return f"SCAN-{self._scan_counter}"
