"""Abstract base class for PLC backends.

Transport contract — every ``read_tag`` / ``write_tag`` outcome is one of:

- ``{addr: value}``: it worked.
- ``{addr: error}``: that ADDRESS is wrong — a stable verdict; retrying is pointless.
- raises ``PLCCommunicationError``: the LINK is sick; already retried
  ``retry_count`` times with a channel reconnect between attempts.
- raises ``PLCTagError``: the REQUEST is wrong; never retried.

Link trouble never appears in a returned map: pycomm3 stamps a failed packet
exchange onto that packet's tags instead of raising, so any transport-kind entry
is promoted here into the retry loop and, past the budget, into the raise (the
partial map rides on ``.results``). Access is serialized per channel (read/write
locks); the first retry on a still-connected session skips the reconnect.
"""

import asyncio
from abc import abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from mindtrace.core import MindtraceABC
from mindtrace.hardware.core.config import get_hardware_config
from mindtrace.hardware.core.exceptions import PLCCommunicationError
from mindtrace.hardware.plcs.types import TagErrorKind, TagResult


def _transport_failures(results: Optional[Dict[str, TagResult]]) -> List[str]:
    """Addresses whose error says the exchange failed, not that the address is wrong.

    One is enough to condemn the call: pycomm3 stamps a failed packet onto every
    tag it carried, and stamped entries escalate instead of being returned.
    """
    if not results:
        return []
    return [
        address
        for address, result in results.items()
        if result.error is not None and result.error.kind is TagErrorKind.transport
    ]


class BasePLC(MindtraceABC):
    """Base for PLC backends: serialized channels, typed results, honest errors.

    Attributes:
        plc_name: Unique identifier for the PLC instance
        plc_config_file: Path to PLC-specific configuration file
        ip_address: IP address of the PLC
        connection_timeout: Connection timeout in seconds
        read_timeout: Tag read timeout in seconds
        write_timeout: Tag write timeout in seconds
        retry_count: Number of retry attempts for operations
        retry_delay: Delay between retry attempts in seconds
        plc: The underlying PLC connection object (read channel, where applicable)
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

        # Per-instance channel locks. Lifecycle ops take BOTH, always
        # read-then-write — the single global ordering that avoids deadlock.
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

        self._setup_plc_logger_formatting()

        self.logger.info(f"PLC base initialized: plc_name={self.plc_name}, ip_address={self.ip_address}")

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

    # --- Public API: takes the lock, delegates to the backend implementation ---

    async def read_tag(self, tags: Union[str, List[str]]) -> Dict[str, TagResult]:
        """Read tags on the read channel, recovering the channel if it fails.

        Address verdicts land in the results, keyed by address — a repeated address
        collapses to its last result. Link trouble raises; see the module
        docstring's table.
        """
        batch = [tags] if isinstance(tags, str) else list(tags)
        async with self._read_lock:
            return await self._run_with_recovery("read", lambda: self._read_tags(list(batch)))

    async def write_tag(self, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, TagResult]:
        """Write tags on the write channel, recovering the channel if it fails.

        Address verdicts land in the results, keyed by address — a repeated address
        collapses to its last result, though every write is still issued. Link
        trouble raises; see the module docstring's table.
        """
        batch = [tags] if isinstance(tags, tuple) else list(tags)
        async with self._write_lock:
            return await self._run_with_recovery("write", lambda: self._write_tags(list(batch)))

    # --- In-transport recovery: bounded retry + channel-scoped reconnect ---

    async def _run_with_recovery(
        self, channel: str, operation: Callable[[], Awaitable[Dict[str, TagResult]]]
    ) -> Dict[str, TagResult]:
        """Attempt ``operation`` up to ``retry_count`` times, resetting ``channel`` between tries.

        Transport-class = a raised ``PLCCommunicationError`` or a batch carrying
        any transport-kind result; anything else propagates on attempt 1. The
        caller holds this channel's lock, so recovery uses ``_reconnect_channel``
        — never the public ``reconnect`` (both locks: deadlock).
        """
        attempts = max(1, int(self.retry_count or 1))
        last_error: Optional[PLCCommunicationError] = None
        results: Optional[Dict[str, TagResult]] = None
        stamped: List[str] = []

        for attempt in range(1, attempts + 1):
            try:
                results = await operation()
            except PLCCommunicationError as error:
                last_error, results, stamped = error, None, []
            else:
                last_error = None
                stamped = _transport_failures(results)
                if not stamped:
                    return results
                self.logger.warning(
                    f"{self.plc_name} {channel} channel stamped {len(stamped)}/{len(results)} "
                    f"results with transport errors"
                )

            if attempt == attempts:
                break

            await asyncio.sleep(self.retry_delay)

            # The first retry on a session the driver still calls open is free:
            # bouncing it would turn one hiccup into a torn-down socket. After
            # that the session is lying, so reset it.
            if attempt == 1 and await self.is_connected():
                continue

            # A failed reconnect is logged, never fatal: the next attempt fails fast
            # into another reconnect or the exhausted raise.
            self.logger.info(f"{self.plc_name} {channel} channel reconnect attempt")
            try:
                if await self._reconnect_channel(channel):
                    self.logger.info(f"{self.plc_name} {channel} channel reconnect ok")
                    continue
                detail = " (channel did not reopen)"
            except Exception as error:
                detail = f" ({error})"
            self.logger.warning(f"{self.plc_name} {channel} channel reconnect failed{detail}")

        if last_error is not None:
            # A fresh PLCCommunicationError, not type(last_error)(...): subclass
            # constructors differ. Chained to the original driver cause.
            cause = last_error.__cause__ or last_error
            raise PLCCommunicationError(f"{last_error} (attempts={attempts})") from cause
        if stamped:
            # Stamped entries are transient (and, for writes, ambiguous: the
            # request may have executed with only the reply lost) — returning them
            # would reintroduce retryable map errors. Raise, partial map attached.
            message = (
                f"{self.plc_name} {channel} channel failed on {len(stamped)}/{len(results or {})} tags: "
                f"{(results or {})[stamped[0]].error.message} (attempts={attempts})"
            )
            error = PLCCommunicationError(message)
            error.results = results  # type: ignore[attr-defined]
            error.transport_addresses = tuple(stamped)  # type: ignore[attr-defined]
            raise error
        return results if results is not None else {}

    @abstractmethod
    async def _reconnect_channel(self, channel: str) -> bool:
        """Reset ONLY this channel's transport; ``channel`` is "read" or "write".

        The caller holds this channel's lock — never call the public
        ``reconnect``/``connect``/``disconnect`` from here. A backend whose
        channels share one driver cannot reset it safely mid-call and should
        return ``False`` (recovery then retries and raises honestly; healing
        happens via the explicit public ``reconnect``).
        """
        pass

    async def get_plc_info(self) -> Dict[str, Any]:
        """Controller identity/status. Probes share the read channel by design."""
        async with self._read_lock:
            return await self._get_plc_info()

    async def get_all_tags(self) -> List[str]:
        """List available tags; hits the device, so it takes the read channel."""
        async with self._read_lock:
            return await self._get_all_tags()

    async def get_tag_info(self, tag_name: str) -> Dict[str, Any]:
        """Describe one tag; hits the device, so it takes the read channel."""
        async with self._read_lock:
            return await self._get_tag_info(tag_name)

    async def connect(self) -> bool:
        """Open the connection. Holds both channels so no op sees a half-open device."""
        async with self._read_lock, self._write_lock:
            return await self._connect()

    async def disconnect(self) -> bool:
        """Close the connection. Holds both channels for the same reason as connect."""
        async with self._read_lock, self._write_lock:
            return await self._disconnect()

    async def reconnect(self) -> bool:
        """Close, settle, reopen under both locks, so no queued read or write lands
        on a socket being torn down. Failures propagate as ``connect`` propagates them."""
        async with self._read_lock, self._write_lock:
            await self._disconnect()
            await asyncio.sleep(self.retry_delay)
            return await self._connect()

    # --- Backend implementations: run alone on their channel ---

    @abstractmethod
    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the PLC connection.

        Returns:
            Tuple of (success, plc_object, device_manager)
        """
        pass

    @abstractmethod
    async def _connect(self) -> bool:
        """Open the device connection. Raises on failure."""
        pass

    @abstractmethod
    async def _disconnect(self) -> bool:
        """Close the device connection."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if PLC is currently connected.

        Lock-free: callers use it as a cheap predicate.

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    async def _read_tags(self, addresses: List[str]) -> Dict[str, TagResult]:
        """Read ``addresses``, one TagResult each.

        Whole-call failures raise ``PLCCommunicationError`` if reconnecting the
        channel could fix it, anything else typed and final.
        """
        pass

    @abstractmethod
    async def _write_tags(self, writes: List[Tuple[str, Any]]) -> Dict[str, TagResult]:
        """Write ``(address, value)`` pairs, one TagResult each; same raise contract as ``_read_tags``."""
        pass

    @abstractmethod
    async def _get_all_tags(self) -> List[str]:
        """List available tag names."""
        pass

    @abstractmethod
    async def _get_tag_info(self, tag_name: str) -> Dict[str, Any]:
        """Describe a single tag (type, description, size, driver)."""
        pass

    async def _get_plc_info(self) -> Dict[str, Any]:
        """Backend-agnostic identity; backends override with device detail."""
        return {
            "name": self.plc_name,
            "ip_address": self.ip_address,
            "connected": await self.is_connected(),
        }

    @staticmethod
    @abstractmethod
    def get_available_plcs() -> List[str]:
        """
        Discover available PLCs for this backend.

        Returns:
            List of PLC identifiers in format "Backend:Identifier"
        """
        pass

    @classmethod
    async def identify(cls, host: str, *, port: "int | None" = None, timeout: float = 1.0) -> "Dict[str, Any] | None":
        """Probe a SINGLE host for its device identity (unicast, read-only).

        The targeted, firewall-safe counterpart to ``get_available_plcs``:
        rather than broadcasting or scanning, send ONE native identity request
        to a host the operator named — on the device's own service port,
        read-only — and return the device identity plus the driver that fits,
        or ``None`` if the host doesn't answer as this backend's device type.

        Backends override this with their protocol-native primitive (EtherNet/IP
        ListIdentity, Siemens S7 SZL read, Modbus Read-Device-Identification).
        The default is "not supported", so a backend that hasn't implemented it
        never claims a host (the manager moves on to the next backend).

        Args:
            host: IP / hostname to probe.
            port: Optional service-port override (backend default otherwise).
            timeout: Per-probe timeout in seconds.

        Returns:
            Identity dict with keys ``backend, driver, ip, port, vendor,
            product, revision, serial, reachable`` — or ``None``.
        """
        return None

    @staticmethod
    @abstractmethod
    def get_backend_info() -> Dict[str, Any]:
        """
        Get information about this PLC backend.

        Returns:
            Dictionary with backend information
        """
        pass

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
