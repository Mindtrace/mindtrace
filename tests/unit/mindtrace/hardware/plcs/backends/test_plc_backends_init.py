"""Tests for PLC backends __init__.py."""

import pytest


def test_allen_bradley_import():
    """Test Allen Bradley PLC import."""
    from mindtrace.hardware.plcs.backends import ALLEN_BRADLEY_AVAILABLE
    
    # Should be a boolean
    assert isinstance(ALLEN_BRADLEY_AVAILABLE, bool)
    
    if ALLEN_BRADLEY_AVAILABLE:
        # If available, should be able to import
        from mindtrace.hardware.plcs.backends import AllenBradleyPLC
        assert AllenBradleyPLC is not None


def test_all_exports():
    """Test __all__ contains expected exports based on availability."""
    import mindtrace.hardware.plcs.backends as plc_backends
    
    # __all__ should be a list
    assert isinstance(plc_backends.__all__, list)
    
    # If Allen Bradley is available, it should be in __all__
    if plc_backends.ALLEN_BRADLEY_AVAILABLE:
        assert "AllenBradleyPLC" in plc_backends.__all__
    else:
        assert "AllenBradleyPLC" not in plc_backends.__all__