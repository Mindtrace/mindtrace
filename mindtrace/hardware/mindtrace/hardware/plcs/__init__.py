"""PLC module for Mindtrace hardware system.

Provides unified interface for managing PLCs from different manufacturers
with support for discovery, registration, and batch operations.
"""

from mindtrace.hardware.plcs.plc_manager import PLCManager

__all__ = [
    "PLCManager",
]
