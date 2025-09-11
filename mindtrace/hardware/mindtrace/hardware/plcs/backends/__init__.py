"""
PLC backends for different manufacturers and protocols.

This module contains implementations for various PLC types including Allen Bradley, Siemens, Modbus, and other
industrial protocols.
"""

# Import available backends
try:
    from mindtrace.hardware.plcs.backends.allen_bradley import AllenBradleyPLC  # noqa

    ALLEN_BRADLEY_AVAILABLE = True
except ImportError:
    ALLEN_BRADLEY_AVAILABLE = False

# Future backends can be imported here
# try:
#     from .siemens import SiemensPLC
#     SIEMENS_AVAILABLE = True
# except ImportError:
#     SIEMENS_AVAILABLE = False

# try:
#     from .modbus import ModbusPLC
#     MODBUS_AVAILABLE = True
# except ImportError:
#     MODBUS_AVAILABLE = False

__all__ = []

if ALLEN_BRADLEY_AVAILABLE:
    __all__.append("AllenBradleyPLC")

# Future backends will be added to __all__ here
