"""MockPLC — in-memory PLC for unit tests and CI pipelines.

The mock maintains a simple dict-based tag store.  :meth:`write` inserts or
updates a tag; :meth:`read` returns the stored value wrapped in a
:class:`~mindtrace.hardware.plc.base.PLCTag`.  Reading a tag that was never
written raises :class:`~mindtrace.hardware.core.exceptions.PLCTagNotFoundError`.

No network connection or third-party SDK is required.

Typical usage::

    from mindtrace.hardware.plc import MockPLC

    with MockPLC() as plc:
        plc.write("Motor.Speed", 120.5)
        plc.write("Conveyor.Active", True)
        tag = plc.read("Motor.Speed")
        print(tag.value, tag.data_type)   # 120.5  float
        batch = plc.read_many(["Motor.Speed", "Conveyor.Active"])
"""

from __future__ import annotations

import time
from typing import Any

from mindtrace.hardware.core.exceptions import (
    PLCConnectionError,
    PLCTagNotFoundError,
)
from mindtrace.hardware.plc.base import AbstractPLC, PLCStatus, PLCTag


class MockPLC(AbstractPLC):
    """In-memory PLC that stores tag values in a plain Python dict.

    Args:
        host: Descriptive host string — has no network significance.
            Defaults to ``"mock-plc"``.
        port: Descriptive port number.  Defaults to 0.
        initial_tags: Optional pre-seeded tag dict ``{tag_name: value}``.
    """

    def __init__(
        self,
        host: str = "mock-plc",
        port: int = 0,
        initial_tags: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(host=host, port=port)
        self._tag_store: dict[str, Any] = dict(initial_tags or {})
        self._status = PLCStatus.DISCONNECTED

    # ------------------------------------------------------------------
    # AbstractPLC implementation
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Mark the mock PLC as connected."""
        self._status = PLCStatus.CONNECTED
        self.logger.info(f"MockPLC {self._host!r} connected.")

    def disconnect(self) -> None:
        """Mark the mock PLC as disconnected."""
        self._status = PLCStatus.DISCONNECTED
        self.logger.info(f"MockPLC {self._host!r} disconnected.")

    def read(self, tag: str) -> PLCTag:
        """Return the stored value for *tag*.

        Args:
            tag: Tag name as used in :meth:`write`.

        Returns:
            A :class:`~mindtrace.hardware.plc.base.PLCTag` with the stored
            value, inferred *data_type*, and current timestamp.

        Raises:
            PLCConnectionError: If :meth:`connect` has not been called.
            PLCTagNotFoundError: If *tag* was never written.
        """
        self._assert_connected("read")

        if tag not in self._tag_store:
            raise PLCTagNotFoundError(
                f"MockPLC {self._host!r}: tag {tag!r} not found.  Available tags: {list(self._tag_store.keys())}"
            )

        value = self._tag_store[tag]
        return PLCTag(
            name=tag,
            value=value,
            data_type=self._infer_data_type(value),
            timestamp=time.time(),
        )

    def write(self, tag: str, value: Any) -> None:
        """Store *value* under *tag*.

        Args:
            tag: Tag name string (any non-empty string is accepted).
            value: Value to store.

        Raises:
            PLCConnectionError: If :meth:`connect` has not been called.
        """
        self._assert_connected("write")
        self._tag_store[tag] = value
        self.logger.debug(f"MockPLC {self._host!r}: wrote {tag!r} = {value!r} ({self._infer_data_type(value)})")

    @property
    def status(self) -> PLCStatus:
        return self._status

    # ------------------------------------------------------------------
    # Additional mock-specific API
    # ------------------------------------------------------------------

    def get_all_tags(self) -> dict[str, Any]:
        """Return a snapshot of the entire tag store.

        Useful in tests to assert the full PLC state without reading
        individual tags.
        """
        return dict(self._tag_store)

    def clear_tags(self) -> None:
        """Remove all stored tags (useful between test cases)."""
        self._tag_store.clear()
        self.logger.debug(f"MockPLC {self._host!r}: tag store cleared.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_connected(self, operation: str) -> None:
        if self._status != PLCStatus.CONNECTED:
            raise PLCConnectionError(
                f"MockPLC {self._host!r} is not connected "
                f"(status={self._status.value!r}).  "
                f"Cannot perform '{operation}'.  Call connect() first."
            )

    @staticmethod
    def _infer_data_type(value: Any) -> str:
        """Map a Python value to a PLC data-type string."""
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int32"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        return type(value).__name__
