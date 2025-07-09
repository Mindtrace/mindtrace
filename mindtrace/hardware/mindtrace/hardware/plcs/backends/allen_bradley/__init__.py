"""
Allen Bradley PLC Backend.

Implements PLC communication for Allen Bradley PLCs using the pycomm3 library.
"""

from .allen_bradley_plc import AllenBradleyPLC
from .mock_allen_bradley import MockAllenBradleyPLC

__all__ = ["AllenBradleyPLC", "MockAllenBradleyPLC"] 