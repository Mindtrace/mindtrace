"""PLC sub-package for mindtrace-hardware.

Provides a unified synchronous interface for PLC / SCADA communication,
with an OPC-UA backend (via asyncua) and an in-memory mock for testing.
"""

from __future__ import annotations

from mindtrace.hardware.plc.base import AbstractPLC, PLCStatus, PLCTag
from mindtrace.hardware.plc.mock import MockPLC
from mindtrace.hardware.plc.opcua import OPCUAClient

__all__ = [
    "AbstractPLC",
    "PLCStatus",
    "PLCTag",
    "MockPLC",
    "OPCUAClient",
]
