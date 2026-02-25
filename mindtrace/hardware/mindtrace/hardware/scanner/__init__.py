"""Scanner sub-package for mindtrace-hardware.

Provides a unified synchronous interface for scanner devices (barcode
readers, 3D scanners, etc.) plus an in-memory mock for testing.
"""
from __future__ import annotations

from mindtrace.hardware.scanner.base import AbstractScanner, ScanResult
from mindtrace.hardware.scanner.mock import MockScanner

__all__ = [
    "AbstractScanner",
    "ScanResult",
    "MockScanner",
]
