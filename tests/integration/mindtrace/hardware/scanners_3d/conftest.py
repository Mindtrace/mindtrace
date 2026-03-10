"""Pytest configuration for 3D scanner integration tests."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "hardware: marks tests as requiring hardware (deselect with '-m \"not hardware\"')",
    )


@pytest.fixture(scope="session")
def check_scanner_available():
    """Session-scoped fixture to check if scanner is available."""
    try:
        from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
            PhotoneoBackend,
        )

        devices = PhotoneoBackend.discover_devices()
        return len(devices) > 0
    except Exception:
        return False
