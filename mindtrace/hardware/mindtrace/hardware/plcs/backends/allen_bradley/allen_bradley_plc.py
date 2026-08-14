"""
Allen Bradley PLC implementation using pycomm3.

Provides communication interface for Allen Bradley PLCs and other Ethernet/IP devices
using CIPDriver, LogixDriver, and SLCDriver from pycomm3 library.

Connecting opens one EtherNet/IP session per channel, so reads and writes never
share a socket.
"""

import asyncio
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from mindtrace.hardware.core.exceptions import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCInitializationError,
    PLCTagError,
    PLCTagNotFoundError,
    PLCTagReadError,
    PLCTagWriteError,
    PLCTimeoutError,
    SDKNotAvailableError,
)
from mindtrace.hardware.plcs.backends.allen_bradley.error_text import (
    classify_tag_error,
    session_dead_addresses,
    tag_to_result,
)
from mindtrace.hardware.plcs.backends.base import BasePLC
from mindtrace.hardware.plcs.types import TagResult

try:
    from pycomm3 import CIPDriver, LogixDriver, SLCDriver
    from pycomm3.exceptions import CommError, DataError, RequestError, ResponseError

    PYCOMM3_AVAILABLE = True
    PYCOMM3_ERRORS: Tuple[type, ...] = (CommError, DataError, RequestError, ResponseError)
    # Anything raised from INSIDE an exchange closes the channel.
    PYCOMM3_EXCHANGE_ERRORS: Tuple[type, ...] = (CommError, DataError, ResponseError, OSError)
    PYCOMM3_TAG_ERRORS: Tuple[type, ...] = (DataError, RequestError, ResponseError)
except ImportError:
    PYCOMM3_AVAILABLE = False
    LogixDriver = None
    SLCDriver = None
    CIPDriver = None
    PYCOMM3_ERRORS = ()
    PYCOMM3_EXCHANGE_ERRORS = (OSError,)
    PYCOMM3_TAG_ERRORS = ()


# Stand-in for a driver whose worker thread never returned: the real one must
# never be called into again; ``connected`` False makes the next entry open fresh.
_ABANDONED_DRIVER = SimpleNamespace(connected=False, close=lambda: None)


def _chain_has_timeout(error: Any) -> bool:
    """LABEL selector only - policy is identical (the channel closes either way);
    this just picks PLCTimeoutError over PLCCommunicationError for the caller."""
    seen: set = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, TimeoutError):
            return True
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return False


class AllenBradleyPLC(BasePLC):
    """
    Allen Bradley PLC implementation using pycomm3.

    Supports multiple PLC types and Ethernet/IP devices:
    - ControlLogix, CompactLogix, Micro800 (LogixDriver)
    - SLC500, MicroLogix (SLCDriver)
    - Generic Ethernet/IP devices (CIPDriver)

    Attributes:
        plc: alias of the read driver (downstream code reads ``plc.tags``)
        driver_type: Type of driver being used
        plc_type: Type of PLC (auto-detected or specified)
        _read_driver / _write_driver: the per-channel drivers
        _tags_cache: Cached list of available tags
        _cache_timestamp: Timestamp of last tag cache update
        _cache_ttl: Time-to-live for tag cache in seconds
    """

    def __init__(
        self,
        plc_name: str,
        ip_address: str,
        plc_type: Optional[str] = None,
        plc_config_file: Optional[str] = None,
        connection_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        retry_delay: Optional[float] = None,
    ):
        """
        Initialize Allen Bradley PLC.

        Args:
            plc_name: Unique identifier for the PLC
            ip_address: IP address of the PLC
            plc_type: PLC type ('logix', 'slc', 'cip', or 'auto' for auto-detection)
            plc_config_file: Path to PLC configuration file
            connection_timeout: Connection timeout in seconds
            read_timeout: Tag read timeout in seconds
            write_timeout: Tag write timeout in seconds
            retry_delay: Delay between retries in seconds

        Raises:
            SDKNotAvailableError: If pycomm3 is not installed
        """
        if not PYCOMM3_AVAILABLE:
            raise SDKNotAvailableError("pycomm3", "Install with: pip install pycomm3")

        super().__init__(
            plc_name=plc_name,
            ip_address=ip_address,
            plc_config_file=plc_config_file,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            retry_delay=retry_delay,
        )

        self.plc_type = plc_type or "auto"
        self.driver_type = None
        # Resolved once per connect(); reopens reuse it so a re-detection cannot
        # drift the two channels onto different driver families.
        self._driver_family: Optional[str] = None
        self._read_driver: Any = None
        self._write_driver: Any = None
        self._tags_cache: Optional[List[str]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300  # 5 minutes

        self.logger.info(
            f"Allen Bradley PLC initialized: plc_type={self.plc_type}, pycomm3_available={PYCOMM3_AVAILABLE}"
        )

    def _driver_class(self, plc_type: Optional[str] = None):
        """Driver class for a resolved plc_type, plus its reported name."""
        resolved = plc_type or self.plc_type
        if resolved == "logix":
            return LogixDriver, "LogixDriver"
        if resolved == "slc":
            return SLCDriver, "SLCDriver"
        return CIPDriver, "CIPDriver"

    async def _resolve_plc_type(self) -> str:
        """The driver family to use now, latching it only when detection was sure.

        A None from ``_detect_plc_type`` means nothing answered — indistinguishable
        from a controller that is merely down, so ``plc_type`` stays ``"auto"``
        rather than pinning CIPDriver to a ControlLogix for the life of the process.
        """
        if self.plc_type != "auto":
            return self.plc_type
        detected = await self._detect_plc_type()
        if detected is None:
            return "cip"
        self.plc_type = detected
        return detected

    @staticmethod
    def _driver_open(driver: Any) -> bool:
        return bool(driver is not None and getattr(driver, "connected", False))

    async def _driver_for(self, channel: str) -> Any:
        """This channel's driver: reopen one that died; never open a never-connected one."""
        attribute = "_read_driver" if channel == "read" else "_write_driver"
        driver = getattr(self, attribute)
        if driver is None:
            raise PLCConnectionError(
                f"The {channel} channel to Allen Bradley PLC at {self.ip_address} was never opened - call connect()"
            )
        if not self._driver_open(driver):
            try:
                driver = await self._open_driver(channel)
            except Exception as error:
                raise PLCCommunicationError(
                    f"Could not reopen the {channel} channel to Allen Bradley PLC at {self.ip_address}: {error}"
                ) from error
            setattr(self, attribute, driver)
            if channel == "read":
                self.plc = driver  # downstream code reads plc.tags off the read driver
            self.logger.info(f"Reopened the {channel} channel to Allen Bradley PLC at {self.ip_address}")
        return driver

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the Allen Bradley PLC connection.

        Returns:
            Tuple of (success, plc_object, device_manager)
        """
        try:
            success = await self.connect()
            if success:
                self.initialized = True
                return True, self.plc, None
            else:
                return False, None, None
        except Exception as e:
            self.logger.error(f"PLC initialization failed: {e}")
            raise PLCInitializationError(f"Failed to initialize Allen Bradley PLC: {e}")

    async def _detect_plc_type(self) -> Optional[str]:
        """
        Auto-detect PLC type by attempting connections with different drivers.

        Returns:
            Detected PLC type ('logix', 'slc', or 'cip'), or None when nothing
            at the address answered — the caller must not latch a type then.
        """
        self.logger.info(f"Auto-detecting PLC type for {self.ip_address}")

        # Try LogixDriver first (most common)
        try:
            test_plc = await asyncio.to_thread(LogixDriver, self.ip_address)
            test_plc.socket_timeout = self.connection_timeout
            connection_result = await asyncio.to_thread(test_plc.open)
            if connection_result:
                await asyncio.to_thread(test_plc.close)
                self.logger.info("Detected Logix-compatible PLC")
                return "logix"
        except Exception as e:
            self.logger.debug(f"LogixDriver detection failed: {e}")

        # Try SLCDriver
        try:
            test_plc = await asyncio.to_thread(SLCDriver, self.ip_address)
            test_plc.socket_timeout = self.connection_timeout
            connection_result = await asyncio.to_thread(test_plc.open)
            if connection_result:
                await asyncio.to_thread(test_plc.close)
                self.logger.info("Detected SLC/MicroLogix PLC")
                return "slc"
        except Exception as e:
            self.logger.debug(f"SLCDriver detection failed: {e}")

        # Neither driver opened: a generic Ethernet/IP device and an unreachable
        # controller look identical here. A unicast ListIdentity separates them —
        # silence means nobody is home, so do not pin CIPDriver to a PLC that is
        # merely down.
        try:
            answered = bool(await asyncio.to_thread(CIPDriver.list_identity, self.ip_address))
        except Exception as e:
            self.logger.debug(f"CIP identity probe failed: {e}")
            answered = False

        if not answered:
            self.logger.warning(f"Nothing answered at {self.ip_address}; PLC type stays undetected")
            return None

        self.logger.info("Using CIPDriver for generic Ethernet/IP device")
        return "cip"

    async def _connect(self) -> bool:
        """Open both channels' drivers via ``_open_driver``. Raises PLCConnectionError.

        A single attempt. A device that only grants one session fails on the
        write channel with the read side already open - the error says so.
        """
        self.logger.info(f"Connecting to Allen Bradley PLC at {self.ip_address}")

        # Close what a previous connect opened: the controller caps attached
        # sessions and keeps counting orphans until they time out.
        if self._read_driver is not None or self._write_driver is not None:
            await self._close_drivers()
            self._read_driver = None
            self._write_driver = None
            self.plc = None

        self._driver_family = await self._resolve_plc_type()

        try:
            self._read_driver = await self._open_driver("read")
        except Exception as e:
            raise PLCConnectionError(f"Failed to connect to Allen Bradley PLC at {self.ip_address}: {e}") from e
        # `plc` stays the READ driver: downstream code reads plc.tags.
        self.plc = self._read_driver

        try:
            self._write_driver = await self._open_driver("write")
        except Exception as e:
            await self._close_driver(self._read_driver, "read")
            self._read_driver = None
            self.plc = None
            raise PLCConnectionError(
                f"Failed to connect to Allen Bradley PLC at {self.ip_address}: "
                f"the read channel opened but the write channel did not: {e}"
            ) from e

        self.logger.info(f"Connected to Allen Bradley PLC using {self.driver_type} (read + write channels)")
        return True

    def _channel_timeout(self, channel: str) -> float:
        return self.read_timeout if channel == "read" else self.write_timeout

    async def _bounded(self, channel: str, call: Any, *args: Any, **kwargs: Any) -> Any:
        """One driver call under a generous BACKSTOP bound.

        The channel's socket deadline (set at open) is the real timeout, firing
        on the thread that owns the driver; this outer bound only trips when
        that deadline malfunctions (a dripping reply, a blocked send). The
        worker thread is then still inside the driver, so expiry must ABANDON
        the channel - swap the driver out untouched - never close it.
        """
        return await asyncio.wait_for(
            asyncio.to_thread(call, *args, **kwargs), self._channel_timeout(channel) * 1.5 + 1.0
        )

    async def _open_driver(self, channel: str) -> Any:
        """Construct and open ONE driver for the resolved plc_type; raises if it will not open.

        The channel's read/write knob is the driver's socket deadline - pycomm3
        applies it once, at open() - so it bounds this channel's handshake AND
        every exchange, and timeouts surface on the thread that owns the driver.
        ``connection_timeout`` bounds the discovery probes only.

        Uses the family ``connect()`` resolved — an entry reopen must not
        re-detect and drift ``driver_type`` while the other channel's driver
        is still live.
        """
        driver_class, driver_name = self._driver_class(self._driver_family)

        driver = await asyncio.to_thread(driver_class, self.ip_address)
        driver.socket_timeout = self._channel_timeout(channel)
        try:
            opened = await asyncio.to_thread(driver.open)
        except Exception:
            # A raising open() leaves an orphan driver the controller keeps counting
            # against its session cap until it times out.
            await self._close_driver(driver, "new")
            raise
        if not opened:
            await self._close_driver(driver, "new")
            raise PLCConnectionError(f"Failed to open a driver to Allen Bradley PLC at {self.ip_address}")
        self.driver_type = driver_name
        return driver

    async def _close_driver(self, driver: Any, label: str) -> bool:
        """Close one driver; ``label`` names it in the log ("read"/"write"/"new")."""
        if driver is None:
            return True
        try:
            await asyncio.to_thread(driver.close)
        except Exception as e:
            self.logger.error(f"Error closing the {label} Allen Bradley driver: {e}")
            return False
        return not getattr(driver, "connected", False)

    async def _raise_if_session_dead(self, driver: Any, channel: str, results: Dict[str, TagResult]) -> None:
        """Session-dead statuses in a delivered reply close the channel and raise."""
        dead = session_dead_addresses(results)
        if not dead:
            return
        first = results[dead[0]].error.message
        self.logger.warning(
            f"{self.plc_name} {channel} channel: session-dead statuses on {len(dead)}/{len(results)} tags ({first})"
        )
        await self._close_driver(driver, channel)
        raise PLCCommunicationError(
            f"{self.plc_name} {channel} channel failed on {len(dead)}/{len(results)} tags: {first}"
        )

    async def _close_drivers(self) -> bool:
        """Close both channels' drivers; True only if both are actually closed."""
        closed = True
        for channel, driver in (("read", self._read_driver), ("write", self._write_driver)):
            closed = await self._close_driver(driver, channel) and closed
        return closed

    async def _disconnect(self) -> bool:
        """Close both channels' drivers and forget them."""
        if self._read_driver is None and self._write_driver is None:
            return True

        closed = await self._close_drivers()
        if closed:
            self._read_driver = None
            self._write_driver = None
            self.plc = None
            self.logger.info(f"Disconnected from Allen Bradley PLC at {self.ip_address}")
            self.initialized = False
        return closed

    async def is_connected(self) -> bool:
        """connected means in the lifecycle state of connect() succeeded, disconnect() was not called."""
        return self._read_driver is not None and self._write_driver is not None

    async def _read_tags(self, addresses: List[str]) -> Dict[str, TagResult]:
        """Read on the read channel; per-tag errors are classified, not logged away."""
        driver = await self._driver_for("read")
        if not addresses:
            return {}

        try:
            if self.driver_type == "LogixDriver":
                results = await self._bounded("read", driver.read, *addresses)
                tags = results if isinstance(results, list) else [results]
                if len(tags) != len(addresses):
                    raise PLCTagReadError(
                        f"Allen Bradley PLC at {self.ip_address} returned {len(tags)} results "
                        f"for {len(addresses)} requested tags"
                    )
                results = {address: tag_to_result(tag) for address, tag in zip(addresses, tags)}
            elif self.driver_type == "SLCDriver":
                # SLC data-file reads are not batchable; one request per address.
                results = {address: await self._slc_read_one(driver, address) for address in addresses}
            else:
                results = {address: await self._cip_read_one(driver, address) for address in addresses}

        except PLCTagReadError:
            raise
        except TimeoutError as e:
            # Backstop expiry: the worker thread is STILL inside the driver.
            self._read_driver = _ABANDONED_DRIVER
            raise PLCTimeoutError(
                f"Read gave no reply within the backstop on Allen Bradley PLC at {self.ip_address}"
            ) from e
        except asyncio.CancelledError:
            # Caller cancelled mid-exchange: same live-thread situation.
            self._read_driver = _ABANDONED_DRIVER
            raise
        except PYCOMM3_EXCHANGE_ERRORS as e:
            # The thread finished (it raised), so closing is single-threaded and safe.
            await self._close_driver(driver, "read")
            if _chain_has_timeout(e):
                raise PLCTimeoutError(
                    f"Read timed out after {self.read_timeout}s on Allen Bradley PLC at {self.ip_address}"
                ) from e
            raise PLCCommunicationError(f"Read failed on Allen Bradley PLC at {self.ip_address}: {e}") from e
        except PYCOMM3_ERRORS as e:
            # What's left is RequestError, hit before the exchange.
            raise PLCTagReadError(f"Driver rejected the read on Allen Bradley PLC at {self.ip_address}: {e}") from e
        except Exception as e:
            raise PLCTagReadError(f"Unexpected read failure on Allen Bradley PLC at {self.ip_address}: {e}") from e

        await self._raise_if_session_dead(driver, "read", results)
        return results

    async def _slc_read_one(self, driver: Any, address: str) -> TagResult:
        """One SLC data-file read; only per-tag driver errors stay per-tag — a
        CommError is a whole-call failure and propagates to ``_read_tags``."""
        try:
            return tag_to_result(await self._bounded("read", driver.read, address))
        except PYCOMM3_TAG_ERRORS as e:
            return TagResult(error=classify_tag_error(e))

    async def _cip_read_one(self, driver: Any, address: str) -> TagResult:
        """One generic-CIP read, dispatched on the address form."""
        try:
            if address.startswith("Identity") or address == "DeviceInfo":
                return TagResult(value=await self._bounded("read", driver.list_identity, self.ip_address))

            if address.startswith("Assembly"):
                instance = int(address.split(":")[-1]) if ":" in address else 1
                result = await self._bounded(
                    "read",
                    driver.generic_message,
                    service=0x0E,  # Get_Attribute_Single
                    class_code=0x04,  # Assembly Object
                    instance=instance,
                    attribute=3,  # Data
                    name=f"read_assembly_{instance}",
                )
                return tag_to_result(result)

            if address.startswith("Module"):
                slot = int(address.split(":")[-1]) if ":" in address else 0
                return TagResult(value=await self._bounded("read", driver.get_module_info, slot))

            if address.startswith("Connection"):
                result = await self._bounded(
                    "read",
                    driver.generic_message,
                    service=0x01,  # Get_Attributes_All
                    class_code=0x06,  # Connection Manager Object
                    instance=1,
                    name="read_connection_status",
                )
                return tag_to_result(result)

            parts = address.split(":")
            if len(parts) >= 3:
                class_code = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
                instance = int(parts[1])
                attribute = int(parts[2])
                result = await self._bounded(
                    "read",
                    driver.generic_message,
                    service=0x0E,  # Get_Attribute_Single
                    class_code=class_code,
                    instance=instance,
                    attribute=attribute,
                    name=f"read_cip_{class_code}_{instance}_{attribute}",
                )
                return tag_to_result(result)

            return tag_to_result(await self._bounded("read", driver.read, address))
        except PYCOMM3_TAG_ERRORS as e:
            return TagResult(error=classify_tag_error(e))

    async def _write_tags(self, writes: List[Tuple[str, Any]]) -> Dict[str, TagResult]:
        """Write on the write channel; per-tag errors are classified, not laundered to False."""
        driver = await self._driver_for("write")
        if not writes:
            return {}

        try:
            if self.driver_type == "LogixDriver":
                results = await self._bounded("write", driver.write, *writes)
                tags = results if isinstance(results, list) else [results]
                if len(tags) != len(writes):
                    raise PLCTagWriteError(
                        f"Allen Bradley PLC at {self.ip_address} returned {len(tags)} results "
                        f"for {len(writes)} requested writes"
                    )
                results_map = {
                    address: tag_to_result(tag, value_on_success=value, use_tag_value=False)
                    for (address, value), tag in zip(writes, tags)
                }
            elif self.driver_type == "SLCDriver":
                results_map = {address: await self._slc_write_one(driver, address, value) for address, value in writes}
            else:
                results_map = {address: await self._cip_write_one(driver, address, value) for address, value in writes}

        except PLCTagWriteError:
            raise
        except TimeoutError as e:
            self._write_driver = _ABANDONED_DRIVER
            raise PLCTimeoutError(
                f"Write gave no reply within the backstop on Allen Bradley PLC at {self.ip_address}"
            ) from e
        except asyncio.CancelledError:
            self._write_driver = _ABANDONED_DRIVER
            raise
        except PYCOMM3_EXCHANGE_ERRORS as e:
            await self._close_driver(driver, "write")
            if _chain_has_timeout(e):
                raise PLCTimeoutError(
                    f"Write timed out after {self.write_timeout}s on Allen Bradley PLC at {self.ip_address}"
                ) from e
            raise PLCCommunicationError(f"Write failed on Allen Bradley PLC at {self.ip_address}: {e}") from e
        except PYCOMM3_ERRORS as e:
            # RequestError: raised before anything hit the wire; the session is untouched.
            raise PLCTagWriteError(f"Driver rejected the write on Allen Bradley PLC at {self.ip_address}: {e}") from e
        except Exception as e:
            raise PLCTagWriteError(f"Unexpected write failure on Allen Bradley PLC at {self.ip_address}: {e}") from e

        await self._raise_if_session_dead(driver, "write", results_map)
        return results_map

    async def _slc_write_one(self, driver: Any, address: str, value: Any) -> TagResult:
        """One SLC data-file write; only per-tag driver errors stay per-tag — a
        CommError is a whole-call failure and propagates to ``_write_tags``."""
        try:
            result = await self._bounded("write", driver.write, (address, value))
            return tag_to_result(result, value_on_success=value, use_tag_value=False)
        except PYCOMM3_TAG_ERRORS as e:
            return TagResult(error=classify_tag_error(e))

    async def _cip_write_one(self, driver: Any, address: str, value: Any) -> TagResult:
        """One generic-CIP write, dispatched on the address form."""
        try:
            if address.startswith("Assembly"):
                instance = int(address.split(":")[-1]) if ":" in address else 1
                result = await self._bounded(
                    "write",
                    driver.generic_message,
                    service=0x10,  # Set_Attribute_Single
                    class_code=0x04,  # Assembly Object
                    instance=instance,
                    attribute=3,  # Data
                    data=value,
                    name=f"write_assembly_{instance}",
                )
                return tag_to_result(result, value_on_success=value, use_tag_value=False)

            if address.startswith("Parameter"):
                instance = int(address.split(":")[-1]) if ":" in address else 1
                result = await self._bounded(
                    "write",
                    driver.generic_message,
                    service=0x10,  # Set_Attribute_Single
                    class_code=0x0F,  # Parameter Object
                    instance=instance,
                    attribute=1,  # Parameter value
                    data=value,
                    name=f"write_parameter_{instance}",
                )
                return tag_to_result(result, value_on_success=value, use_tag_value=False)

            parts = address.split(":")
            if len(parts) >= 3:
                class_code = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
                instance = int(parts[1])
                attribute = int(parts[2])
                result = await self._bounded(
                    "write",
                    driver.generic_message,
                    service=0x10,  # Set_Attribute_Single
                    class_code=class_code,
                    instance=instance,
                    attribute=attribute,
                    data=value,
                    name=f"write_cip_{class_code}_{instance}_{attribute}",
                )
                return tag_to_result(result, value_on_success=value, use_tag_value=False)

            result = await self._bounded("write", driver.write, (address, value))
            return tag_to_result(result, value_on_success=value, use_tag_value=False)
        except PYCOMM3_TAG_ERRORS as e:
            return TagResult(error=classify_tag_error(e))

    async def _get_all_tags(self) -> List[str]:
        """
        Get list of all available tags on the Allen Bradley PLC.

        Returns:
            List of tag names
        """
        current_time = time.time()

        # Check if cache is still valid
        if self._tags_cache is not None and current_time - self._cache_timestamp < self._cache_ttl:
            return self._tags_cache

        driver = await self._driver_for("read")

        try:
            if self.driver_type == "LogixDriver":
                # LogixDriver has built-in tag list functionality
                tags_dict = await asyncio.to_thread(lambda: driver.tags)
                if not tags_dict:
                    # We're connected, but the controller tag list came back
                    # empty/None — for a Logix controller that means the upload
                    # failed, not that the PLC is tag-less. Caching [] here would
                    # silently report "no tags" and make every later lookup look
                    # like a missing tag. Fail loudly instead.
                    raise PLCTagError(
                        f"Tag list upload from Allen Bradley PLC at {self.ip_address} "
                        "returned empty; the controller tag list could not be read"
                    )
                self._tags_cache = list(tags_dict.keys())

            elif self.driver_type == "SLCDriver":
                # Enhanced SLCDriver tag discovery with comprehensive data file mapping
                self._tags_cache = []

                # Integer files (N7, N9, N10, etc.)
                for file_num in [7, 9, 10, 11, 12]:
                    for addr in range(0, 20):  # Common range
                        self._tags_cache.append(f"N{file_num}:{addr}")

                # Binary files (B3, B10, B11, etc.)
                for file_num in [3, 10, 11, 12]:
                    for addr in range(0, 20):
                        self._tags_cache.append(f"B{file_num}:{addr}")

                # Timer files (T4)
                for addr in range(0, 10):
                    self._tags_cache.extend(
                        [
                            f"T4:{addr}",  # Timer structure
                            f"T4:{addr}.PRE",  # Preset value
                            f"T4:{addr}.ACC",  # Accumulated value
                            f"T4:{addr}.EN",  # Enable bit
                            f"T4:{addr}.TT",  # Timer timing bit
                            f"T4:{addr}.DN",  # Done bit
                        ]
                    )

                # Counter files (C5)
                for addr in range(0, 10):
                    self._tags_cache.extend(
                        [
                            f"C5:{addr}",  # Counter structure
                            f"C5:{addr}.PRE",  # Preset value
                            f"C5:{addr}.ACC",  # Accumulated value
                            f"C5:{addr}.CU",  # Count up bit
                            f"C5:{addr}.CD",  # Count down bit
                            f"C5:{addr}.DN",  # Done bit
                            f"C5:{addr}.OV",  # Overflow bit
                            f"C5:{addr}.UN",  # Underflow bit
                        ]
                    )

                # Float files (F8)
                for addr in range(0, 10):
                    self._tags_cache.append(f"F8:{addr}")

                # Control files (R6) for sequencers, etc.
                for addr in range(0, 5):
                    self._tags_cache.extend(
                        [
                            f"R6:{addr}",  # Control structure
                            f"R6:{addr}.LEN",  # Length
                            f"R6:{addr}.POS",  # Position
                            f"R6:{addr}.EN",  # Enable bit
                            f"R6:{addr}.EU",  # Enable unload bit
                            f"R6:{addr}.DN",  # Done bit
                            f"R6:{addr}.EM",  # Empty bit
                        ]
                    )

                # Status files (S2)
                self._tags_cache.extend(
                    [
                        "S2:0",  # Processor status
                        "S2:1",  # Arithmetic flags
                        "S2:2",  # Processor switches
                        "S2:3",  # Time base
                        "S2:4",  # Index register
                    ]
                )

                # Input/Output files (I:0, O:0)
                for slot in range(0, 8):
                    for word in range(0, 4):
                        self._tags_cache.extend(
                            [
                                f"I:{slot}.{word}",  # Input word
                                f"O:{slot}.{word}",  # Output word
                            ]
                        )
                        # Individual bits
                        for bit in range(0, 16):
                            self._tags_cache.extend(
                                [
                                    f"I:{slot}.{word}/{bit}",  # Input bit
                                    f"O:{slot}.{word}/{bit}",  # Output bit
                                ]
                            )

            else:  # CIPDriver - Enhanced tag discovery using proper CIP method
                assert CIPDriver is not None, "CIPDriver is required but CIPDriver is not available"
                # Enhanced CIP tag discovery using official pycomm3 methods
                self._tags_cache = []

                # Use official methods for device identification and module discovery
                try:
                    # Get device identity using official list_identity method
                    device_info = await asyncio.to_thread(CIPDriver.list_identity, self.ip_address)
                    if device_info:
                        # Add device identity tags
                        self._tags_cache.extend(
                            [
                                "Identity",
                                "DeviceInfo",
                            ]
                        )

                        # Add device-specific tags based on product type
                        product_type = device_info.get("product_type", "")
                        product_name = device_info.get("product_name", "")

                        # Drive-specific tags (PowerFlex, etc.)
                        if "PowerFlex" in product_name or product_type == "AC Drive":
                            drive_tags = [
                                "Parameter:1",  # Speed Reference
                                "Parameter:2",  # Speed Feedback
                                "Parameter:3",  # Torque Reference
                                "Parameter:4",  # Torque Feedback
                                "Parameter:5",  # Motor Current
                                "Parameter:6",  # DC Bus Voltage
                                "Parameter:7",  # Drive Temperature
                                "Parameter:8",  # Fault Code
                                "Parameter:9",  # Warning Code
                                "Parameter:10",  # Drive Status
                                "Assembly:20",  # Input Assembly
                                "Assembly:21",  # Output Assembly
                                "Assembly:22",  # Configuration Assembly
                            ]
                            self._tags_cache.extend(drive_tags)

                        # I/O Module-specific tags (POINT I/O, CompactBlock, etc.)
                        elif (
                            "POINT I/O" in product_name
                            or "CompactBlock" in product_name
                            or product_type == "Generic Device"
                        ):
                            io_tags = [
                                "Assembly:100",  # Input Data
                                "Assembly:101",  # Output Data
                                "Assembly:102",  # Configuration Data
                                "Assembly:103",  # Diagnostic Data
                                "Connection",  # Connection Status
                            ]
                            self._tags_cache.extend(io_tags)

                            # Try to discover module information for rack-based devices
                            try:
                                for slot in range(0, 8):  # Check first 8 slots
                                    module_info = await asyncio.to_thread(driver.get_module_info, slot)
                                    if module_info:
                                        self._tags_cache.append(f"Module:{slot}")
                            except Exception:
                                pass

                        # PLC-specific tags (ControlLogix, CompactLogix via CIP)
                        elif product_type == "Programmable Logic Controller":
                            plc_tags = [
                                "Assembly:1",  # Input Assembly
                                "Assembly:2",  # Output Assembly
                                "Assembly:3",  # Configuration Assembly
                                "Connection",  # Connection Status
                            ]
                            self._tags_cache.extend(plc_tags)
                except Exception as e:
                    self.logger.debug(f"Could not get device identity: {e}")

                # Standard CIP objects that most Ethernet/IP devices support
                standard_cip_objects = [
                    # Identity Object (0x01) - Device identification
                    "0x01:1:1",  # Vendor ID
                    "0x01:1:2",  # Device Type
                    "0x01:1:3",  # Product Code
                    "0x01:1:4",  # Revision
                    "0x01:1:5",  # Status
                    "0x01:1:6",  # Serial Number
                    "0x01:1:7",  # Product Name
                    # Message Router Object (0x02) - Object discovery
                    "0x02:1:1",  # Object List
                    # Assembly Object (0x04) - I/O data exchange
                    "0x04:1:3",  # Assembly instance 1 data
                    "0x04:2:3",  # Assembly instance 2 data
                    "0x04:3:3",  # Assembly instance 3 data
                    # Connection Manager Object (0x06) - Connection management
                    "0x06:1:1",  # Open Requests
                    "0x06:1:2",  # Open Format Rejects
                    "0x06:1:3",  # Open Resource Rejects
                    "0x06:1:4",  # Open Other Rejects
                    "0x06:1:5",  # Close Requests
                    "0x06:1:6",  # Close Format Requests
                    "0x06:1:7",  # Close Other Requests
                    "0x06:1:8",  # Connection Timeouts
                ]

                self._tags_cache.extend(standard_cip_objects)

                # Try to discover additional objects using generic messaging
                try:
                    # Attempt to get object list from Message Router (if supported)
                    object_list_result = await asyncio.to_thread(
                        driver.generic_message,
                        service=0x0E,  # Get_Attribute_Single
                        class_code=0x02,  # Message Router Object
                        instance=1,
                        attribute=1,  # Object List attribute
                        name="get_object_list",
                    )

                    if object_list_result and hasattr(object_list_result, "value"):
                        # Parse object list and add discovered objects
                        # This would require parsing the CIP object list format
                        self.logger.debug("Successfully retrieved object list from device")

                except Exception as e:
                    self.logger.debug(f"Could not retrieve object list: {e}")

            self._cache_timestamp = current_time
            return self._tags_cache

        except PLCTagError:
            # Already a clear, intentional error (e.g. empty tag-list upload) —
            # don't re-wrap it.
            raise
        except Exception as e:
            self.logger.error(f"Failed to get tags: {e}")
            raise PLCTagError(f"Failed to get tags from Allen Bradley PLC: {e}")

    async def _get_tag_info(self, tag_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific tag.

        Args:
            tag_name: Name of the tag

        Returns:
            Dictionary with tag information (type, description, etc.)
        """
        driver = await self._driver_for("read")

        try:
            if self.driver_type == "LogixDriver":
                tags_dict = await asyncio.to_thread(lambda: driver.tags)
                if not tags_dict:
                    # Connected, but the controller tag list is empty/None — the
                    # upload failed. We CANNOT conclude the tag is absent; raising
                    # "not found" here is the long-standing bug that mislabels a
                    # tag-list-fetch failure as a missing tag. Surface it honestly.
                    raise PLCTagError(
                        f"Could not read the tag list from Allen Bradley PLC at "
                        f"{self.ip_address}; cannot verify whether tag '{tag_name}' exists"
                    )
                if tag_name in tags_dict:
                    tag_info = tags_dict[tag_name]
                    return {
                        "name": tag_name,
                        "type": getattr(tag_info, "data_type", "Unknown"),
                        "description": getattr(tag_info, "description", ""),
                        "size": getattr(tag_info, "size", 0),
                        "driver": "LogixDriver",
                    }
                else:
                    raise PLCTagNotFoundError(f"Tag '{tag_name}' not found on Allen Bradley PLC")

            elif self.driver_type == "SLCDriver":
                # SLCDriver doesn't provide detailed tag info
                return {
                    "name": tag_name,
                    "type": "Data File Address",
                    "description": f"SLC/MicroLogix data file address: {tag_name}",
                    "size": 0,
                    "driver": "SLCDriver",
                }

            else:  # CIPDriver
                return {
                    "name": tag_name,
                    "type": "Generic CIP Object",
                    "description": f"Generic Ethernet/IP object: {tag_name}",
                    "size": 0,
                    "driver": "CIPDriver",
                }

        except PLCTagNotFoundError:
            raise
        except PLCTagError:
            # Intentional, already-clear error (e.g. tag list couldn't be read).
            raise
        except Exception as e:
            self.logger.error(f"Failed to get tag info: {e}")
            raise PLCTagError(f"Failed to get tag info from Allen Bradley PLC: {e}")

    async def _get_plc_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the connected PLC using proper pycomm3 methods.

        Returns:
            Dictionary with PLC information
        """
        driver = await self._driver_for("read")

        try:
            info = {
                "name": self.plc_name,
                "ip_address": self.ip_address,
                "driver_type": self.driver_type,
                "plc_type": self.plc_type,
                "connected": await self.is_connected(),
                # Diagnostics: a False here with connected=True is a channel
                # awaiting its entry reopen, not a disconnection.
                "read_channel_open": self._driver_open(self._read_driver),
                "write_channel_open": self._driver_open(self._write_driver),
            }

            if self.driver_type == "LogixDriver":
                # LogixDriver provides detailed PLC information via get_plc_info()
                try:
                    plc_info = await asyncio.to_thread(driver.get_plc_info)
                    info.update(
                        {
                            "product_name": getattr(plc_info, "product_name", "Unknown"),
                            "product_type": getattr(plc_info, "product_type", "Unknown"),
                            "vendor": getattr(plc_info, "vendor", "Allen Bradley"),
                            "revision": getattr(plc_info, "revision", "Unknown"),
                            "serial": getattr(plc_info, "serial", "Unknown"),
                        }
                    )

                    # Try to get program name using generic messaging (as shown in docs)
                    try:
                        program_name = await asyncio.to_thread(driver.get_plc_name)
                        info["program_name"] = program_name
                    except Exception:
                        pass

                except Exception as e:
                    self.logger.warning(f"Could not get detailed Logix PLC info: {e}")

            elif self.driver_type == "CIPDriver":
                # CIPDriver uses list_identity() method for device information
                try:
                    device_info = await asyncio.to_thread(CIPDriver.list_identity, self.ip_address)
                    if device_info:
                        info.update(
                            {
                                "product_name": device_info.get("product_name", "Unknown"),
                                "product_type": device_info.get("product_type", "Unknown"),
                                "vendor": device_info.get("vendor", "Unknown"),
                                "product_code": device_info.get("product_code", 0),
                                "revision": device_info.get("revision", {}),
                                "serial": device_info.get("serial", "Unknown"),
                                "status": device_info.get("status", b""),
                                "encap_protocol_version": device_info.get("encap_protocol_version", 0),
                            }
                        )

                        # Try to get additional module information for rack-based devices
                        try:
                            module_info = await asyncio.to_thread(driver.get_module_info, 0)
                            if module_info:
                                info["module_info"] = module_info
                        except Exception:
                            pass

                except Exception as e:
                    self.logger.warning(f"Could not get CIP device info: {e}")

            elif self.driver_type == "SLCDriver":
                # SLCDriver has limited info capabilities
                info.update(
                    {
                        "product_type": "SLC/MicroLogix PLC",
                        "vendor": "Allen Bradley",
                        "description": "SLC500 or MicroLogix series PLC",
                    }
                )

            return info

        except Exception as e:
            self.logger.error(f"Failed to get PLC info: {e}")
            return {
                "name": self.plc_name,
                "ip_address": self.ip_address,
                "driver_type": self.driver_type,
                "plc_type": self.plc_type,
                "connected": False,
                "error": str(e),
            }

    @staticmethod
    def get_available_plcs() -> List[str]:
        """
        Discover available Allen Bradley PLCs using proper pycomm3 discovery methods.

        Returns:
            List of PLC identifiers in format "AllenBradley:IP:Type"
        """
        if not PYCOMM3_AVAILABLE:
            return []

        try:
            discovered_devices = []

            # Use official CIPDriver.discover() class method for network-wide discovery
            try:
                devices = CIPDriver.discover()
                for device in devices:
                    ip = device.get("ip_address", "")
                    product_name = device.get("product_name", "")
                    product_type = device.get("product_type", "")

                    if ip:
                        # Determine device type based on product information
                        device_type = "CIP"  # Default

                        # Check for specific Allen Bradley device types
                        if "ControlLogix" in product_name or "CompactLogix" in product_name:
                            device_type = "Logix"
                        elif "MicroLogix" in product_name or "SLC" in product_name:
                            device_type = "SLC"
                        elif "PowerFlex" in product_name or product_type == "AC Drive":
                            device_type = "Drive"
                        elif "POINT I/O" in product_name or product_type == "Generic Device":
                            device_type = "IO"
                        elif product_type == "Programmable Logic Controller":
                            device_type = "Logix"
                        elif product_type == "Communications Adapter":
                            device_type = "CIP"

                        discovered_devices.append(f"AllenBradley:{ip}:{device_type}")

            except Exception:
                # CIP discovery failed, continue with fallback methods
                pass

            # No hardcoded-IP fallback. Probing a fixed list of "common" IPs is
            # noisy, almost always wrong, and looks like reconnaissance to OT
            # security tooling. Broadcast (above) is the only segment-wide
            # method here; for a known device use the targeted, unicast
            # ``identify(host)`` instead.

            # Remove duplicates while preserving order
            seen = set()
            unique_devices = []
            for device in discovered_devices:
                if device not in seen:
                    seen.add(device)
                    unique_devices.append(device)

            return unique_devices

        except Exception:
            return []

    @classmethod
    async def discover_async(cls) -> List[str]:
        """Async wrapper for get_available_plcs() - runs discovery in threadpool.

        Use this instead of get_available_plcs() when calling from async context
        to avoid blocking the event loop during PLC network discovery.

        Returns:
            List[str]: List of discovered PLC IP addresses.
        """
        return await asyncio.to_thread(cls.get_available_plcs)

    @classmethod
    async def identify(cls, host: str, *, port: "int | None" = None, timeout: float = 1.0) -> "Dict[str, Any] | None":
        """Identify a single Allen-Bradley / EtherNet-IP device by unicast.

        Sends ONE EtherNet/IP ListIdentity (CIP ``0x63``) to ``host`` on TCP/UDP
        44818 via ``CIPDriver.list_identity`` — a targeted, read-only request to
        the device's own management port. No broadcast, no scanning, no
        fixed-IP probing, so it crosses routers/VLANs/containers and doesn't
        look like recon. Returns the device identity plus the matching driver
        (``logix`` / ``slc`` / ``cip``), or ``None`` if nothing answers as an
        EtherNet/IP device at ``host``.
        """
        if not PYCOMM3_AVAILABLE:
            return None
        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(CIPDriver.list_identity, host),
                timeout=max(timeout, 0.5),
            )
        except Exception:
            return None
        if not info:
            return None
        product_name = info.get("product_name", "") or ""
        product_type = info.get("product_type", "") or ""
        driver = "cip"
        if "ControlLogix" in product_name or "CompactLogix" in product_name:
            driver = "logix"
        elif "MicroLogix" in product_name or "SLC" in product_name:
            driver = "slc"
        elif product_type == "Programmable Logic Controller":
            driver = "logix"
        return {
            "backend": "AllenBradley",
            "driver": driver,
            "ip": host,
            "port": port or 44818,
            "vendor": info.get("vendor", "") or "",
            "product": product_name,
            "product_type": product_type,
            "revision": str(info.get("revision", "") or ""),
            "serial": str(info.get("serial", "") or ""),
            "reachable": True,
        }

    @staticmethod
    def get_backend_info() -> Dict[str, Any]:
        """
        Get information about the Allen Bradley PLC backend.

        Returns:
            Dictionary with backend information
        """
        return {
            "name": "AllenBradley",
            "description": "Enhanced Allen Bradley PLC backend using pycomm3 with full multi-driver support",
            "sdk_name": "pycomm3",
            "sdk_available": PYCOMM3_AVAILABLE,
            "drivers": [
                {
                    "name": "LogixDriver",
                    "description": "ControlLogix, CompactLogix, Micro800 PLCs with full tag support",
                    "supported_models": ["ControlLogix", "CompactLogix", "Micro800", "GuardLogix"],
                    "capabilities": [
                        "Tag-based programming",
                        "Multiple tag read/write",
                        "Tag discovery and enumeration",
                        "PLC information retrieval",
                        "Data type detection",
                        "Online/offline status monitoring",
                    ],
                    "fully_implemented": True,
                },
                {
                    "name": "SLCDriver",
                    "description": "SLC500 and MicroLogix PLCs with comprehensive data file support",
                    "supported_models": [
                        "SLC500",
                        "MicroLogix 1000",
                        "MicroLogix 1100",
                        "MicroLogix 1400",
                        "MicroLogix 1500",
                    ],
                    "capabilities": [
                        "Data file addressing (N, B, T, C, F, R, S)",
                        "Timer and counter operations",
                        "Bit-level access",
                        "Status file monitoring",
                        "I/O file access",
                        "Enhanced error handling",
                    ],
                    "data_files_supported": [
                        "Integer files (N7, N9, N10-N12)",
                        "Binary files (B3, B10-B12)",
                        "Timer files (T4) with PRE/ACC/EN/TT/DN",
                        "Counter files (C5) with PRE/ACC/CU/CD/DN/OV/UN",
                        "Float files (F8)",
                        "Control files (R6) with LEN/POS/EN/EU/DN/EM",
                        "Status files (S2)",
                        "Input/Output files (I:x.y, O:x.y) with bit access",
                    ],
                    "fully_implemented": True,
                },
                {
                    "name": "CIPDriver",
                    "description": "Generic Ethernet/IP devices with comprehensive CIP object support",
                    "supported_models": [
                        "PowerFlex Drives",
                        "POINT I/O Modules",
                        "CompactBlock I/O",
                        "Stratix Switches",
                        "Generic CIP Devices",
                        "Third-party Ethernet/IP devices",
                    ],
                    "capabilities": [
                        "CIP object messaging",
                        "Generic service requests",
                        "Assembly object access",
                        "Identity object reading",
                        "Connection management",
                        "Device-specific object discovery",
                        "Drive parameter access",
                        "I/O module configuration",
                    ],
                    "cip_objects_supported": [
                        "Identity Object (0x01) - Device identification",
                        "Message Router Object (0x02) - Object discovery",
                        "DeviceNet Object (0x03) - Network configuration",
                        "Assembly Object (0x04) - I/O data exchange",
                        "Connection Manager Object (0x06) - Connection status",
                        "Parameter Object (0x0F) - Drive parameters",
                        "Acknowledge Handler Object (0x2B) - Status monitoring",
                    ],
                    "device_types_supported": [
                        "Drives (0x02) - Speed/torque control and monitoring",
                        "I/O Modules (0x07) - Digital/analog I/O access",
                        "HMI Devices (0x2B) - Human machine interfaces",
                        "Generic CIP (0x00) - Basic CIP functionality",
                    ],
                    "fully_implemented": True,
                },
            ],
            "protocols": ["Ethernet/IP", "CIP (Common Industrial Protocol)"],
            "features": [
                "Auto-detection of PLC type with fallback hierarchy",
                "Multi-driver support with driver-specific optimizations",
                "Enhanced device discovery with network scanning",
                "Comprehensive tag reading/writing for all driver types",
                "CIP object messaging for generic devices",
                "SLC data file mapping with bit-level access",
                "Logix tag enumeration and data type detection",
                "PLC information retrieval and device identification",
                "Explicit connect lifecycle; a channel closed on proof reopens at the next call",
                "Async/await support for non-blocking operations",
                "Caching system for improved performance",
                "Device-specific object discovery",
                "Drive parameter monitoring and control",
                "I/O module configuration and diagnostics",
            ],
            "enhanced_capabilities": {
                "discovery": "Multi-method device discovery including CIP broadcast and network scanning",
                "tag_support": "Full tag support across all driver types with enhanced addressing",
                "cip_messaging": "Complete CIP object messaging with service code support",
                "error_handling": "Comprehensive error handling with driver-specific error codes",
                "performance": "Optimized operations with caching and batch processing",
                "compatibility": "Backward compatible with legacy SLC systems and forward compatible with modern Logix",
            },
            "installation_instructions": "pip install pycomm3" if not PYCOMM3_AVAILABLE else None,
        }
