"""Unit tests for Horizon configuration."""

import pytest

from mindtrace.apps.horizon.config import (
    HorizonSettings,
    get_horizon_config,
    reset_horizon_config,
)


class TestHorizonSettings:
    """Tests for HorizonSettings Pydantic model."""

    def test_default_values(self):
        """Test that HorizonSettings has sensible defaults."""
        settings = HorizonSettings()

        assert settings.URL == "http://localhost:8080"
        assert settings.MONGO_URI == "mongodb://localhost:27017"
        assert settings.MONGO_DB == "horizon"
        assert settings.AUTH_ENABLED is False
        assert settings.LOG_LEVEL == "INFO"
        assert settings.DEBUG is False

    def test_custom_values(self):
        """Test that HorizonSettings accepts custom values."""
        settings = HorizonSettings(
            URL="http://0.0.0.0:9000",
            MONGO_URI="mongodb://mongo:27017",
            MONGO_DB="custom_db",
            AUTH_ENABLED=True,
            LOG_LEVEL="DEBUG",
            DEBUG=True,
        )

        assert settings.URL == "http://0.0.0.0:9000"
        assert settings.MONGO_URI == "mongodb://mongo:27017"
        assert settings.AUTH_ENABLED is True


class TestGetHorizonConfig:
    """Tests for get_horizon_config function."""

    def test_returns_config_instance(self):
        """Test that get_horizon_config returns a Config instance."""
        from mindtrace.core import Config

        config = get_horizon_config()
        assert isinstance(config, Config)

    def test_has_horizon_section(self):
        """Test that config has HORIZON section with expected keys."""
        config = get_horizon_config()

        assert "HORIZON" in config
        horizon = config["HORIZON"]

        assert "URL" in horizon
        assert "MONGO_URI" in horizon
        assert "MONGO_DB" in horizon
        assert "AUTH_ENABLED" in horizon

    def test_config_is_cached(self):
        """Test that get_horizon_config returns the same instance."""
        config1 = get_horizon_config()
        config2 = get_horizon_config()

        assert config1 is config2

    def test_reset_clears_cache(self):
        """Test that reset_horizon_config clears the cache."""
        config1 = get_horizon_config()
        reset_horizon_config()
        config2 = get_horizon_config()

        assert config1 is not config2

    def test_attribute_access(self):
        """Test that config supports attribute access."""
        config = get_horizon_config()

        assert config.HORIZON.URL == "http://localhost:8080"
        assert config.HORIZON.MONGO_DB == "horizon"

    def test_env_override(self, env_override):
        """Test that environment variables override config values."""
        env_override.set(HORIZON__URL="http://0.0.0.0:9999", HORIZON__MONGO_DB="env_db")
        reset_horizon_config()

        config = get_horizon_config()

        assert config.HORIZON.URL == "http://0.0.0.0:9999"
        assert config.HORIZON.MONGO_DB == "env_db"

    def test_secret_key_is_masked(self):
        """Test that AUTH_SECRET_KEY is masked in normal access."""
        config = get_horizon_config()

        # Secret fields should be masked
        assert config.HORIZON.AUTH_SECRET_KEY == "********"

    def test_secret_key_retrievable(self):
        """Test that AUTH_SECRET_KEY can be retrieved via get_secret."""
        config = get_horizon_config()

        secret = config.get_secret("HORIZON", "AUTH_SECRET_KEY")
        assert secret == "dev-secret-key"

