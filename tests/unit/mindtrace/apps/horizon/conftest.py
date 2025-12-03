"""Pytest fixtures for Horizon unit tests."""

import base64
import os
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from mindtrace.apps.horizon.config import reset_horizon_config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset Horizon config before each test to ensure clean state."""
    reset_horizon_config()
    yield
    reset_horizon_config()


@pytest.fixture
def mock_config():
    """Provide a mock configuration dictionary."""
    return {
        "HORIZON": {
            "URL": "http://localhost:8080",
            "MONGO_URI": "mongodb://localhost:27017",
            "MONGO_DB": "horizon_test",
            "AUTH_ENABLED": False,
            "AUTH_SECRET_KEY": "test-secret-key",
            "LOG_LEVEL": "DEBUG",
            "DEBUG": True,
        }
    }


@pytest.fixture
def sample_image():
    """Create a sample RGB image for testing."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    return img


@pytest.fixture
def sample_image_rgba():
    """Create a sample RGBA image for testing."""
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    return img


@pytest.fixture
def sample_image_base64(sample_image):
    """Create a base64-encoded sample image."""
    buffer = BytesIO()
    sample_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def sample_image_rgba_base64(sample_image_rgba):
    """Create a base64-encoded RGBA sample image."""
    buffer = BytesIO()
    sample_image_rgba.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def mock_motor_client():
    """Create a mock AsyncIOMotorClient."""
    client = MagicMock()
    client.__getitem__ = MagicMock(return_value=MagicMock())
    client.close = MagicMock()
    return client


@pytest.fixture
def mock_horizon_db(mock_motor_client):
    """Create a mock HorizonDB instance."""
    with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_motor_client):
        with patch("mindtrace.apps.horizon.db.init_beanie", new_callable=AsyncMock):
            from mindtrace.apps.horizon.db import HorizonDB

            db = HorizonDB(uri="mongodb://localhost:27017", db_name="test_db")
            yield db


@pytest.fixture
def env_override():
    """Context manager fixture for temporarily overriding environment variables."""

    class EnvOverride:
        def __init__(self):
            self._original = {}

        def set(self, **kwargs):
            """Set environment variables, storing originals for restoration."""
            for key, value in kwargs.items():
                if key in os.environ:
                    self._original[key] = os.environ[key]
                else:
                    self._original[key] = None
                os.environ[key] = str(value)

        def restore(self):
            """Restore original environment variables."""
            for key, original_value in self._original.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value
            self._original.clear()

    override = EnvOverride()
    yield override
    override.restore()

