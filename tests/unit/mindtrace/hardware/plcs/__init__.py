"""
PLC Unit Tests

Unit tests for PLC backends and PLC manager functionality, mirroring the cameras test structure.

Structure:
- backends/
  - allen_bradley/
    - test_mock_allen_bradley.py: tests for MockAllenBradleyPLC and driver behaviors
- core/
  - test_plc_manager.py: tests for PLCManager

All tests use mock implementations to avoid hardware dependencies. Integration/performance
scenarios live within the relevant backend or manager tests.
"""
