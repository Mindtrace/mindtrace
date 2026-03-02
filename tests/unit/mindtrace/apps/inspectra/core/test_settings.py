"""Unit tests for Inspectra core settings."""

import os
from unittest.mock import patch

from mindtrace.apps.inspectra.core.settings import get_inspectra_config, reset_inspectra_config


def test_reset_inspectra_config():
    """reset_inspectra_config clears cache so next get_inspectra_config reloads."""
    get_inspectra_config()
    reset_inspectra_config()
    config = get_inspectra_config()
    assert config is not None
    assert hasattr(config, "INSPECTRA")


def test_get_inspectra_config_invalid_jwt_expires_in_fallback():
    """When JWT_EXPIRES_IN env is not int, config still loads."""
    reset_inspectra_config()
    with patch.dict(
        os.environ, {"MONGO_URI": "mongodb://localhost:27017", "JWT_EXPIRES_IN": "not_an_int"}, clear=False
    ):
        config = get_inspectra_config()
        assert config is not None
    reset_inspectra_config()
