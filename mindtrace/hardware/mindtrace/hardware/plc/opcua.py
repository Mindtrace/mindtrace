"""OPCUAClient — OPC-UA PLC client via the asyncua library.

Because the public mindtrace-hardware API is synchronous, this class runs
an asyncio event loop on a dedicated background thread.  All async
``asyncua`` calls are submitted to that loop via
:func:`asyncio.run_coroutine_threadsafe`, which blocks the calling thread
until the coroutine completes.

All ``asyncua`` imports are guarded by the ``_ASYNCUA_AVAILABLE`` flag so
the module is importable without the optional dependency installed.

Typical usage::

    from mindtrace.hardware.plc import OPCUAClient

    with OPCUAClient(host="192.168.1.50", namespace=2) as plc:
        tag = plc.read("ns=2;s=Conveyor.Speed")
        print(tag.value, tag.data_type)
        plc.write("ns=2;s=Conveyor.SetPoint", 120.5)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any

from mindtrace.hardware.plc.base import AbstractPLC, PLCStatus, PLCTag
from mindtrace.hardware.core.exceptions import (
    PLCConnectionError,
    PLCTagError,
    PLCTagReadError,
    PLCTagWriteError,
    SDKNotAvailableError,
)

# ---------------------------------------------------------------------------
# Optional SDK guard
# ---------------------------------------------------------------------------
try:
    import asyncua  # type: ignore[import]
    import asyncua.ua  # type: ignore[import]

    _ASYNCUA_AVAILABLE = True
except ImportError:
    _ASYNCUA_AVAILABLE = False

_ASYNCUA_INSTALL_MSG = (
    "The 'asyncua' package is required for OPC-UA PLC communication.\n"
    "Install it with:\n"
    "    pip install mindtrace-hardware[opcua]\n"
    "or directly:\n"
    "    pip install asyncua>=1.0\n"
    "Ensure the target PLC exposes an OPC-UA server endpoint."
)

# Sentinel for OPC-UA node-id types
_OPCUA_DATA_TYPE_MAP: dict[str, str] = {
    "Boolean": "bool",
    "Int16": "int16",
    "Int32": "int32",
    "UInt16": "int16",
    "UInt32": "int32",
    "Float": "float",
    "Double": "float",
    "String": "string",
}


class OPCUAClient(AbstractPLC):
    """Synchronous OPC-UA client backed by asyncua running in a daemon thread.

    An internal asyncio event loop is started in a background daemon thread
    inside :meth:`connect`.  The thread and loop are stopped in
    :meth:`disconnect`.  All read/write operations block the calling thread
    until the coroutine finishes or the *timeout* elapses.

    Args:
        host: Hostname or IP address of the OPC-UA server.
        port: OPC-UA endpoint port.  Defaults to 4840 (standard).
        namespace: OPC-UA namespace index used to build ``NodeId`` strings
            when the caller supplies bare tag names without a namespace
            prefix.  Defaults to 2.
        username: Optional OPC-UA session username.
        password: Optional OPC-UA session password.
        timeout: Per-call timeout in seconds for read / write operations.
        config: Optional dict of extra configuration (currently unused,
            reserved for future extension).
    """

    def __init__(
        self,
        host: str,
        port: int = 4840,
        namespace: int = 2,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(host=host, port=port, config=config)
        self._namespace = namespace
        self._username = username
        self._password = password
        self._timeout = timeout
        self._status = PLCStatus.DISCONNECTED

        # Background event-loop thread
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None

        # asyncua client handle
        self._client: Any = None

    # ------------------------------------------------------------------
    # AbstractPLC implementation
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the OPC-UA server, starting the background event loop.

        Raises:
            SDKNotAvailableError: If ``asyncua`` is not installed.
            PLCConnectionError: If the server is unreachable or the
                session cannot be established.
        """
        if not _ASYNCUA_AVAILABLE:
            raise SDKNotAvailableError(
                sdk_name="asyncua",
                installation_instructions=_ASYNCUA_INSTALL_MSG,
            )

        if self._status == PLCStatus.CONNECTED:
            self.logger.debug(
                f"OPCUAClient {self._host}:{self._port} already connected — skipping."
            )
            return

        self.logger.info(
            f"Connecting OPCUAClient to opc.tcp://{self._host}:{self._port}"
        )

        try:
            self._start_event_loop()
            self._run_sync(self._async_connect())
            self._status = PLCStatus.CONNECTED
            self.logger.info(
                f"OPCUAClient connected: opc.tcp://{self._host}:{self._port}"
            )
        except PLCConnectionError:
            raise
        except Exception as exc:
            self._status = PLCStatus.ERROR
            self._stop_event_loop()
            raise PLCConnectionError(
                f"OPCUAClient failed to connect to "
                f"opc.tcp://{self._host}:{self._port}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the OPC-UA session and stop the background event loop.

        Safe to call when already disconnected (idempotent).
        """
        if self._status == PLCStatus.DISCONNECTED:
            return

        self.logger.info(
            f"Disconnecting OPCUAClient from opc.tcp://{self._host}:{self._port}"
        )

        try:
            if self._loop is not None and self._client is not None:
                self._run_sync(self._async_disconnect())
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                f"Error during OPCUAClient disconnect: {exc}"
            )
        finally:
            self._stop_event_loop()
            self._client = None
            self._status = PLCStatus.DISCONNECTED
            self.logger.info(
                f"OPCUAClient disconnected from opc.tcp://{self._host}:{self._port}"
            )

    def read(self, tag: str) -> PLCTag:
        """Read a single OPC-UA node value.

        Args:
            tag: A full OPC-UA node-id string such as ``"ns=2;s=Motor.Speed"``
                or a bare symbolic name which will be prefixed with the
                configured namespace index.

        Returns:
            A :class:`~mindtrace.hardware.plc.base.PLCTag` containing
            the node value, its variant type string, and a timestamp.

        Raises:
            PLCConnectionError: If not connected.
            PLCTagReadError: If the node cannot be read.
        """
        self._assert_connected("read")
        node_id = self._resolve_node_id(tag)

        try:
            value, data_type = self._run_sync(self._async_read(node_id))
        except (PLCConnectionError, PLCTagReadError):
            raise
        except Exception as exc:
            raise PLCTagReadError(
                f"OPCUAClient failed to read tag {tag!r} "
                f"(node_id={node_id!r}): {exc}"
            ) from exc

        return PLCTag(
            name=tag,
            value=value,
            data_type=data_type,
            timestamp=time.time(),
        )

    def write(self, tag: str, value: Any) -> None:
        """Write a value to a single OPC-UA node.

        Args:
            tag: Node-id string or bare tag name (namespace prefix applied
                automatically if absent).
            value: Value to write.

        Raises:
            PLCConnectionError: If not connected.
            PLCTagWriteError: If the write fails.
        """
        self._assert_connected("write")
        node_id = self._resolve_node_id(tag)

        try:
            self._run_sync(self._async_write(node_id, value))
        except (PLCConnectionError, PLCTagWriteError):
            raise
        except Exception as exc:
            raise PLCTagWriteError(
                f"OPCUAClient failed to write tag {tag!r} "
                f"(node_id={node_id!r}) value={value!r}: {exc}"
            ) from exc

        self.logger.debug(f"OPCUAClient wrote tag {tag!r} = {value!r}")

    @property
    def status(self) -> PLCStatus:
        return self._status

    # ------------------------------------------------------------------
    # Private — async coroutines executed on the background loop
    # ------------------------------------------------------------------

    async def _async_connect(self) -> None:
        """Async coroutine that opens the OPC-UA session."""
        import asyncua  # type: ignore[import]

        url = f"opc.tcp://{self._host}:{self._port}"
        client = asyncua.Client(url=url, timeout=self._timeout)

        if self._username and self._password:
            client.set_user(self._username)
            client.set_password(self._password)

        await client.connect()
        self._client = client

    async def _async_disconnect(self) -> None:
        """Async coroutine that closes the OPC-UA session."""
        if self._client is not None:
            await self._client.disconnect()

    async def _async_read(self, node_id: str) -> tuple[Any, str]:
        """Read one node and return (value, data_type_string)."""
        node = self._client.get_node(node_id)
        dv = await node.read_data_value()
        value = dv.Value.Value
        type_name = type(value).__name__

        # Map asyncua variant type to friendly string
        import asyncua.ua as ua  # type: ignore[import]

        variant_type = dv.Value.VariantType
        data_type = _OPCUA_DATA_TYPE_MAP.get(variant_type.name, type_name.lower())

        return value, data_type

    async def _async_write(self, node_id: str, value: Any) -> None:
        """Write one node value."""
        import asyncua.ua as ua  # type: ignore[import]

        node = self._client.get_node(node_id)
        await node.write_value(value)

    # ------------------------------------------------------------------
    # Private — event loop management
    # ------------------------------------------------------------------

    def _start_event_loop(self) -> None:
        """Create and start the background asyncio event loop thread."""
        loop = asyncio.new_event_loop()
        self._loop = loop

        def run_loop() -> None:
            loop.run_forever()

        thread = threading.Thread(
            target=run_loop,
            daemon=True,
            name=f"opcua-loop-{self._host}:{self._port}",
        )
        thread.start()
        self._loop_thread = thread

    def _stop_event_loop(self) -> None:
        """Signal the background loop to stop and join the thread."""
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:  # noqa: BLE001
                pass

        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5.0)

        self._loop = None
        self._loop_thread = None

    def _run_sync(self, coro: Any) -> Any:
        """Submit *coro* to the background event loop and block until done.

        Args:
            coro: An awaitable (coroutine) to execute.

        Returns:
            The coroutine's return value.

        Raises:
            PLCConnectionError: On timeout.
            Any exception raised inside the coroutine.
        """
        if self._loop is None:
            raise PLCConnectionError(
                f"OPCUAClient {self._host}:{self._port}: "
                "event loop is not running.  Call connect() first."
            )

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise PLCConnectionError(
                f"OPCUAClient {self._host}:{self._port}: "
                f"operation timed out after {self._timeout}s"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_connected(self, operation: str) -> None:
        """Raise :class:`PLCConnectionError` if the client is not connected."""
        if self._status != PLCStatus.CONNECTED:
            raise PLCConnectionError(
                f"OPCUAClient {self._host}:{self._port} is not connected "
                f"(status={self._status.value!r}).  "
                f"Cannot perform '{operation}'.  Call connect() first."
            )

    def _resolve_node_id(self, tag: str) -> str:
        """Return a full OPC-UA node-id string.

        If *tag* already starts with ``"ns="`` or ``"i="`` it is returned
        unchanged.  Otherwise ``"ns=<namespace>;s=<tag>"`` is prepended.
        """
        if tag.startswith("ns=") or tag.startswith("i="):
            return tag
        return f"ns={self._namespace};s={tag}"
